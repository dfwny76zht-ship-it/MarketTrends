"""Offer photos: each shop photo is copied once (politely, like the pages), with a small thumbnail for lists.

Only for shops collected from Hetzner. Photos stay after an offer disappears. They are shown only inside this
private, logged-in tool.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from . import checks, config
from .adapters.base import is_challenge
from .auth import current_user
from .db import pool

log = logging.getLogger("images")
router = APIRouter(prefix="/api/images", dependencies=[Depends(current_user)])

MAX_BYTES = 8 * 1024 * 1024
THUMB = (240, 240)
MAX_ATTEMPTS = 3

DUE_SQL = """
SELECT l.id, l.image_url FROM listings l LEFT JOIN images i ON i.listing_id = l.id
WHERE l.shop_id = %s AND l.image_url IS NOT NULL
  AND (i.listing_id IS NULL OR i.source_url <> l.image_url
       OR (i.status = 'failed' AND i.attempts < %s AND i.fetched_at < now() - interval '20 hours'))
ORDER BY l.gone_since IS NULL DESC, l.last_seen DESC
LIMIT %s
"""


def _record(listing_id: int, url: str, status: str, **kw) -> None:
    cols = ["source_url", "status", "sha256", "path", "thumb_path", "width", "height", "error"]
    vals = [url, status] + [kw.get(c) for c in cols[2:]]
    with pool.connection() as conn:
        conn.execute(
            f"INSERT INTO images (listing_id, {', '.join(cols)}) VALUES (%s, {', '.join(['%s'] * len(cols))})"
            " ON CONFLICT (listing_id) DO UPDATE SET "
            + ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
            + ", fetched_at = now(),"
            " attempts = CASE WHEN images.source_url = EXCLUDED.source_url AND EXCLUDED.status <> 'ok'"
            "   THEN images.attempts + 1 ELSE 1 END",
            [listing_id] + vals,
        )


def store(shop_id: int, body: bytes) -> dict:
    """Saves the original and a webp thumbnail (content-addressed). Raises ValueError for non-images."""
    try:
        img = Image.open(io.BytesIO(body))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"not an image ({exc.__class__.__name__})") from exc
    sha = hashlib.sha256(body).hexdigest()
    ext = (img.format or "img").lower().replace("jpeg", "jpg")
    base = Path(config.SNAPSHOT_DIR)
    rel = f"images/{shop_id}/{sha[:2]}/{sha}.{ext}"
    rel_t = f"images/{shop_id}/{sha[:2]}/{sha}_t.webp"
    full = base / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    if not full.exists():
        tmp = full.with_suffix(".tmp")
        tmp.write_bytes(body)
        os.replace(tmp, full)
    if not (base / rel_t).exists():
        thumb = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB")
        thumb.thumbnail(THUMB)
        buf = io.BytesIO()
        thumb.save(buf, "WEBP", quality=80)
        tmp = (base / rel_t).with_suffix(".tmp")
        tmp.write_bytes(buf.getvalue())
        os.replace(tmp, base / rel_t)
    return {"sha256": sha, "path": rel, "thumb_path": rel_t, "width": img.width, "height": img.height}


def collect_shop(shop: dict, limit: int = 400) -> dict:
    with pool.connection() as conn:
        due = conn.execute(DUE_SQL, (shop["id"], MAX_ATTEMPTS, limit)).fetchall()
    counts = {"ok": 0, "failed": 0, "disallowed": 0, "blocked": 0}
    if not due:
        return counts
    robots: dict[str, dict] = {}
    client = httpx.Client(headers={"User-Agent": config.USER_AGENT}, timeout=30, follow_redirects=True)
    last = 0.0
    try:
        for row in due:
            url = row["image_url"]
            parts = urlsplit(url)
            if parts.scheme not in ("http", "https"):
                _record(row["id"], url, "failed", error="not a web address")
                counts["failed"] += 1
                continue
            host = parts.netloc
            if host not in robots:
                robots[host] = checks.fetch_robots(f"{parts.scheme}://{host}/")
            rb = robots[host]
            if rb["result"] == "blocked":
                _record(row["id"], url, "blocked", error=rb.get("error"))
                counts["blocked"] += 1
                break
            parser = rb.get("parser")
            if rb["result"] in ("disallowed", "error") or (parser and not parser.can_fetch(config.USER_AGENT, url)):
                _record(row["id"], url, "disallowed", error=rb.get("error") or "robots.txt forbids it")
                counts["disallowed"] += 1
                continue
            gap = max(config.MIN_GAP_SECONDS, float(shop.get("crawl_delay") or 0), rb.get("crawl_delay") or 0)
            wait = gap - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = client.get(url)
            except httpx.HTTPError as exc:
                _record(row["id"], url, "failed", error=type(exc).__name__)
                counts["failed"] += 1
                continue
            finally:
                last = time.monotonic()
            if resp.status_code in (403, 429) or (resp.status_code == 200 and is_challenge(resp.content[:4096])):
                _record(row["id"], url, "blocked", error=f"HTTP {resp.status_code}")
                counts["blocked"] += 1
                break  # stop for this shop tonight
            if resp.status_code >= 400:
                _record(row["id"], url, "failed", error=f"HTTP {resp.status_code}")
                counts["failed"] += 1
                continue
            if len(resp.content) > MAX_BYTES:
                _record(row["id"], url, "failed", error="too large")
                counts["failed"] += 1
                continue
            try:
                info = store(shop["id"], resp.content)
            except ValueError as exc:
                _record(row["id"], url, "failed", error=str(exc))
                counts["failed"] += 1
                continue
            _record(row["id"], url, "ok", **info)
            counts["ok"] += 1
    finally:
        client.close()
    return counts


def nightly(limit: int = 400) -> dict:
    """After the night run: new or changed photos for every active Hetzner shop."""
    with pool.connection() as conn:
        shops = conn.execute(
            "SELECT * FROM shops WHERE collector = 'hetzner' AND adapter IS NOT NULL"
            " AND status NOT IN ('paused', 'not_allowed') AND (next_run_after IS NULL OR next_run_after <= now())"
            " ORDER BY id"
        ).fetchall()
    out = {}
    with checks.run_lock:
        for shop in shops:
            try:
                out[shop["name"]] = collect_shop(shop, limit)
            except Exception:
                log.exception("photos failed for %s", shop["name"])
    log.info("photos: %s", out)
    return out


@router.get("/{listing_id}")
def image(listing_id: int, full: bool = False):
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT path, thumb_path FROM images WHERE listing_id = %s AND status = 'ok'", (listing_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "No photo.")
    path = Path(config.SNAPSHOT_DIR) / (row["path"] if full else row["thumb_path"])
    if not path.is_file():
        raise HTTPException(404, "No photo.")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=604800"})
