"""Interface for the Pi collector. The Pi only connects outward, with its own token (PI_TOKEN in .env)."""

from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import io
import logging
import os
import secrets
import tarfile
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from . import checks, collect, config, ntfy
from .adapters import REGISTRY, FetchError
from .db import pool

log = logging.getLogger("collector")
router = APIRouter(prefix="/api/collector")
ADAPTERS_DIR = Path(__file__).parent / "adapters"


def require_pi(authorization: str = Header("")) -> str:
    token = os.environ.get("PI_TOKEN", "")
    given = authorization.removeprefix("Bearer ").strip()
    if not token or not given or not secrets.compare_digest(given, token):
        raise HTTPException(401, "Unknown collector")
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO collectors (name, last_seen) VALUES ('pi', now())"
            " ON CONFLICT (name) DO UPDATE SET last_seen = now()"
        )
    return "pi"


DUE_SQL = """
SELECT s.id, s.name, s.url, s.adapter, s.adapter_config, s.run_requested_at IS NOT NULL AS manual
FROM shops s
WHERE s.collector = 'pi' AND s.adapter IS NOT NULL
  AND s.status NOT IN ('paused', 'not_allowed')
  AND (s.next_run_after IS NULL OR s.next_run_after <= now())
  AND (s.pi_claimed_at IS NULL OR s.pi_claimed_at < now() - interval '2 hours')
  AND NOT EXISTS (SELECT 1 FROM runs r WHERE r.shop_id = s.id AND r.kind = 'collect'
                  AND (r.started_at AT TIME ZONE 'Europe/Berlin')::date = (now() AT TIME ZONE 'Europe/Berlin')::date)
  AND (s.run_requested_at IS NOT NULL
       OR (s.status IN ('active', 'adapter_broken')
           AND (now() AT TIME ZONE 'Europe/Berlin')::time >= time '03:00'))
ORDER BY s.id
"""


@router.get("/jobs")
def jobs(_: str = Depends(require_pi)):
    with pool.connection() as conn:
        due = conn.execute(DUE_SQL).fetchall()
        for s in due:
            conn.execute(
                "UPDATE shops SET pi_claimed_at = now(), run_requested_at = NULL WHERE id = %s", (s["id"],)
            )
    return [
        {"shop_id": s["id"], "name": s["name"], "url": s["url"], "adapter": s["adapter"],
         "config": s["adapter_config"] or {}, "manual": s["manual"], "user_agent": config.USER_AGENT,
         "min_gap": config.MIN_GAP_SECONDS}
        for s in due
    ]


@router.get("/adapters.tar.gz")
def adapters_bundle(_: str = Depends(require_pi)):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for f in sorted(ADAPTERS_DIR.glob("*.py")):
            tar.add(f, arcname=f"adapters/{f.name}")
    return Response(buf.getvalue(), media_type="application/gzip")


class Page(BaseModel):
    url: str
    status: int
    body_gz_b64: str
    etag: str | None = None
    last_modified: str | None = None


class Upload(BaseModel):
    shop_id: int
    started_at: datetime
    robots: dict
    pages: list[Page] = []
    outcome: str  # ok | blocked | disallowed | error
    error: str | None = None
    http_status: int | None = None
    manual: bool = False


@router.post("/result")
def result(body: Upload, _: str = Depends(require_pi)):
    with pool.connection() as conn:
        shop = conn.execute("SELECT * FROM shops WHERE id = %s AND collector = 'pi'", (body.shop_id,)).fetchone()
    if not shop:
        raise HTTPException(404, "Not a Pi shop")
    pages = {}
    for p in body.pages:
        try:
            pages[p.url] = (p, gzip.decompress(base64.b64decode(p.body_gz_b64)))
        except (binascii.Error, OSError, EOFError):
            raise HTTPException(422, f"Broken page data for {p.url}")

    def work():
        with checks.run_lock:
            problem = process_upload(shop, body, pages)
        if problem and not body.manual:
            ntfy.send("Market Trends: Pi run", problem, tags=["warning"])

    threading.Thread(target=work, daemon=True).start()
    return {"accepted": len(pages)}


def _store_snapshot(shop_id: int, run_id: int, page: Page, body: bytes) -> None:
    sha = hashlib.sha256(body).hexdigest()
    path = f"{shop_id}/{sha[:2]}/{sha}.gz"
    full = Path(config.SNAPSHOT_DIR) / path
    if not full.exists():
        full.parent.mkdir(parents=True, exist_ok=True)
        tmp = full.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress(body))
        os.replace(tmp, full)
    with pool.connection() as conn:
        conn.execute(
            "INSERT INTO snapshots (shop_id, run_id, url, fetched_at, http_status, sha256, path, etag, last_modified)"
            " VALUES (%s, %s, %s, now(), %s, %s, %s, %s, %s)",
            (shop_id, run_id, page.url, page.status, sha, path, page.etag, page.last_modified),
        )


def process_upload(shop: dict, body: Upload, pages: dict) -> str | None:
    name = shop["name"]
    with pool.connection() as conn:
        run_id = conn.execute(
            "INSERT INTO runs (shop_id, kind, started_at, details) VALUES (%s, 'collect', %s, %s) RETURNING id",
            (shop["id"], body.started_at, Jsonb({"collector": "pi"})),
        ).fetchone()["id"]
        conn.execute("UPDATE shops SET pi_claimed_at = NULL WHERE id = %s", (shop["id"],))

    robots = body.robots or {}
    checks.record_robots(shop["id"], {"result": robots.get("result"), "crawl_delay": robots.get("crawl_delay")})
    for url, (page, raw) in pages.items():
        _store_snapshot(shop["id"], run_id, page, raw)

    if body.outcome == "blocked":
        days = collect._backoff(shop["id"])
        reason = "bot check page" if body.http_status == 200 else body.http_status
        collect._finish(run_id, "blocked", f"{body.error}; next try in {days} d", http_status=body.http_status,
                        pages=len(pages), details={"collector": "pi"})
        return f"{name} (Pi): blocked ({reason}), next try in {days} d"
    if body.outcome != "ok":
        collect._finish(run_id, body.outcome if body.outcome in ("disallowed", "error") else "error", body.error,
                        http_status=body.http_status, pages=len(pages), details={"collector": "pi"})
        return f"{name} (Pi): {body.error or body.outcome}"

    adapter_cls = REGISTRY.get(shop["adapter"] or "")
    if not adapter_cls:
        collect._finish(run_id, "error", "no adapter set", details={"collector": "pi"})
        return f"{name}: no adapter set"

    def fetch(url: str) -> str:
        if url not in pages:
            raise FetchError(f"{url}: not delivered by the Pi")
        return pages[url][1].decode("utf-8", "replace")

    adapter = adapter_cls(shop["adapter_config"] or {})
    try:
        result = adapter.collect(fetch)
    except Exception as exc:
        log.exception("reading Pi pages failed for %s", name)
        collect._finish(run_id, "error", f"{type(exc).__name__}: {exc}", pages=len(pages), details={"collector": "pi"})
        return f"{name} (Pi): {type(exc).__name__}: {exc}"
    return collect._conclude(shop, run_id, adapter, result, len(pages), {"collector": "pi"})


def check_overdue() -> None:
    """6:00: Pi shops that should have been collected tonight but weren't."""
    with pool.connection() as conn:
        late = conn.execute(
            "SELECT s.name FROM shops s WHERE s.collector = 'pi' AND s.adapter IS NOT NULL"
            " AND s.status IN ('active', 'adapter_broken')"
            " AND (s.next_run_after IS NULL OR s.next_run_after <= now())"
            " AND NOT EXISTS (SELECT 1 FROM runs r WHERE r.shop_id = s.id AND r.kind = 'collect'"
            "   AND (r.started_at AT TIME ZONE 'Europe/Berlin')::date = (now() AT TIME ZONE 'Europe/Berlin')::date)"
        ).fetchall()
        seen = conn.execute("SELECT last_seen FROM collectors WHERE name = 'pi'").fetchone()
    if late:
        last = seen["last_seen"].astimezone().strftime("%d.%m. %H:%M") if seen and seen["last_seen"] else "never"
        ntfy.send(
            "Market Trends: Pi collector",
            f"No data from the Pi tonight for: {', '.join(r['name'] for r in late)}. Last contact: {last}.",
            tags=["warning"],
        )
