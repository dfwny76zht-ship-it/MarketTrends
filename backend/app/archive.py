"""History from web archives (step 8): list archived copies of a shop's pages, fetch each once from
the archive (never from the shop), read them, and store the offers as observations with
source = 'archive'. No events are made from archive data. Runs by hand per shop.

Requests go only to archive.org, at least 5 s apart, with the tool's generic name.
"""

from __future__ import annotations

import gzip
import hashlib
import logging
import os
import re
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb

from . import config, names, taxonomy
from .adapters.floraccess_archive import parse_archived
from .auth import current_user
from .db import pool

log = logging.getLogger("archive")
router = APIRouter(prefix="/api/archive", dependencies=[Depends(current_user)])

CDX = "https://web.archive.org/cdx/search/cdx"
GAP = 5.0
FROM_YEAR = "2018"
_lock = threading.Lock()
_progress: dict[int, dict] = {}

# Per shop: which archived addresses belong to the Hoya range, and how to read them.
SOURCES = {
    "floraccess.com": {
        "domain": "floraccess.com",
        "filter": "original:.*[Hh]oya.*",
        "reader": parse_archived,
    },
}


def _source(shop: dict) -> dict:
    src = SOURCES.get(shop["host"])
    if not src:
        raise HTTPException(422, "No archive reader for this shop yet.")
    return src


def _kind(url: str) -> tuple[str | None, str | None]:
    if m := re.search(r"/v/(\d+)/", url):
        return "offer", m.group(1)
    if m := re.search(r"/product/(\d+)/", url):
        return "product", m.group(1)
    if "/category/" in url:
        return "category", None
    return None, None


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": config.USER_AGENT}, timeout=60, follow_redirects=True)


# ---------- 1. list what exists ----------

def discover(shop_id: int) -> dict:
    """Asks the Wayback index for the shop's Hoya pages since 2018. Keeps one copy per page and
    month (English preferred), which is enough for a monthly history."""
    with pool.connection() as conn:
        shop = conn.execute("SELECT * FROM shops WHERE id = %s", (shop_id,)).fetchone()
    if not shop:
        raise HTTPException(404, "Shop not found.")
    src = _source(shop)
    with _client() as c:
        r = c.get(CDX, params={"url": src["domain"], "matchType": "domain", "from": FROM_YEAR, "filter": src["filter"],
                               "fl": "timestamp,original,statuscode,mimetype", "output": "json"})
        r.raise_for_status()
        rows = r.json()[1:]
    best: dict[tuple, tuple] = {}
    for ts, url, status, mime in rows:
        if status != "200" or "html" not in mime:
            continue
        kind, key = _kind(url)
        if not kind:
            continue
        page = key or re.sub(r"https?://(www\.)?[^/]+/[a-z]{2}/", "/", url).split("?")[0]
        slot = (kind, page, ts[:6])
        rank = (0 if "/en/" in url else 1, ts)
        if slot not in best or rank < best[slot][0]:
            best[slot] = (rank, ts, url, kind, key)
    added = 0
    with pool.connection() as conn:
        for _, ts, url, kind, key in best.values():
            at = datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            cur = conn.execute(
                "INSERT INTO archive_captures (shop_id, captured_at, url, kind, item_key) VALUES (%s, %s, %s, %s, %s)"
                " ON CONFLICT DO NOTHING RETURNING id",
                (shop_id, at, url, kind, key),
            )
            added += cur.rowcount
    return {"listed": len(rows), "kept": len(best), "new": added}


# ---------- 2. fetch and read ----------

def _store_snapshot(shop_id: int, run_id: int, archive_url: str, status: int, body: bytes) -> int:
    sha = hashlib.sha256(body).hexdigest()
    rel = f"{shop_id}/{sha[:2]}/{sha}.gz"
    full = Path(config.SNAPSHOT_DIR) / rel
    if not full.exists():
        full.parent.mkdir(parents=True, exist_ok=True)
        tmp = full.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress(body))
        os.replace(tmp, full)
    with pool.connection() as conn:
        return conn.execute(
            "INSERT INTO snapshots (shop_id, run_id, url, http_status, sha256, path) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (shop_id, run_id, archive_url, status, sha, rel),
        ).fetchone()["id"]


def _import(conn, shop_id: int, run_id: int, capture: dict, offers: list[dict]) -> int:
    n = 0
    for o in offers:
        if not o.get("item_key") or o.get("price") is None:
            continue
        at = o["observed_at"]
        listing = conn.execute("SELECT id, first_seen FROM listings WHERE shop_id = %s AND item_key = %s",
                               (shop_id, o["item_key"])).fetchone()
        if listing:
            lid = listing["id"]
            conn.execute("UPDATE listings SET first_seen = LEAST(first_seen, %s), grower = COALESCE(grower, %s) WHERE id = %s",
                         (at, o.get("grower"), lid))
        else:
            # Only known from the archive: gone since its last archived sighting.
            lid = conn.execute(
                "INSERT INTO listings (shop_id, item_key, name, url, first_seen, last_seen, gone_since, grower, name_key)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (shop_id, o["item_key"], o["name"], capture["url"], at, at, at, o.get("grower"), names.name_key(o["name"])),
            ).fetchone()["id"]
        conn.execute(
            "UPDATE listings SET last_seen = GREATEST(last_seen, %s), gone_since = GREATEST(gone_since, %s)"
            " WHERE id = %s AND gone_since IS NOT NULL AND NOT EXISTS"
            " (SELECT 1 FROM observations x WHERE x.listing_id = listings.id AND x.source = 'live')",
            (at, at, lid),
        )
        dup = conn.execute(
            "SELECT 1 FROM observations WHERE listing_id = %s AND source = 'archive'"
            " AND (observed_at AT TIME ZONE 'UTC')::date = (%s AT TIME ZONE 'UTC')::date AND price = %s",
            (lid, at, o["price"]),
        ).fetchone()
        if dup:
            continue
        conn.execute(
            "INSERT INTO observations (listing_id, run_id, observed_at, price, currency, price_basis, price_eur_net,"
            " availability, pot_size, plant_size, raw, source, size_class, grower)"
            " VALUES (%s, %s, %s, %s, 'EUR', 'net', %s, %s, %s, %s, %s, 'archive', %s, %s)",
            (lid, run_id, at, o["price"], o["price"], o["availability"], o.get("pot"), o.get("height"),
             Jsonb({"archive": capture["archive"], "archive_url": capture["archive_url"], "page": capture["kind"],
                    "captured_at": capture["captured_at"].isoformat(), "note": o.get("note")}),
             names.size_class(o.get("pot"), o["name"]), o.get("grower")),
        )
        n += 1
    return n


def run(shop_id: int, limit: int | None = None) -> dict:
    """Fetches and reads every capture not yet done (resumable). Blocks; call from a thread."""
    with pool.connection() as conn:
        shop = conn.execute("SELECT * FROM shops WHERE id = %s", (shop_id,)).fetchone()
        src = _source(shop)
        todo = conn.execute(
            "SELECT * FROM archive_captures WHERE shop_id = %s AND status IN ('new', 'failed') ORDER BY captured_at"
            + (" LIMIT %s" % int(limit) if limit else ""),
            (shop_id,),
        ).fetchall()
        run_id = conn.execute("INSERT INTO runs (shop_id, kind, details) VALUES (%s, 'archive', %s) RETURNING id",
                              (shop_id, Jsonb({"captures": len(todo)}))).fetchone()["id"]
    prog = _progress[shop_id] = {"total": len(todo), "done": 0, "offers": 0, "unreadable": 0, "failed": 0, "running": True}
    last = 0.0
    try:
        with _client() as c:
            for cap in todo:
                ts = cap["captured_at"].strftime("%Y%m%d%H%M%S")
                archive_url = f"https://web.archive.org/web/{ts}id_/{cap['url']}"
                wait = GAP - (time.monotonic() - last)
                if wait > 0:
                    time.sleep(wait)
                try:
                    r = c.get(archive_url)
                except httpx.HTTPError as exc:
                    r, err = None, type(exc).__name__
                last = time.monotonic()
                if r is not None and r.status_code == 429:
                    log.warning("archive.org asks to slow down; stopping this run")
                    prog["stopped"] = "archive.org asked to slow down — try again later"
                    break
                if r is None or r.status_code >= 400:
                    with pool.connection() as conn:
                        conn.execute("UPDATE archive_captures SET status = 'failed', error = %s, fetched_at = now() WHERE id = %s",
                                     (err if r is None else f"HTTP {r.status_code}", cap["id"]))
                    prog["failed"] += 1
                    prog["done"] += 1
                    continue
                snap = _store_snapshot(shop_id, run_id, archive_url, r.status_code, r.content)
                offers = src["reader"](r.text, cap["url"], cap["kind"], cap["captured_at"])
                with pool.connection() as conn:
                    n = _import(conn, shop_id, run_id, dict(cap, archive="wayback", archive_url=archive_url), offers)
                    conn.execute(
                        "UPDATE archive_captures SET status = %s, snapshot_id = %s, offers = %s, error = NULL, fetched_at = now()"
                        " WHERE id = %s",
                        ("parsed" if offers else "unreadable", snap, len(offers), cap["id"]),
                    )
                prog["offers"] += n
                prog["unreadable"] += 0 if offers else 1
                prog["done"] += 1
    finally:
        prog["running"] = False
        with pool.connection() as conn:
            conn.execute(
                "UPDATE runs SET finished_at = now(), result = 'ok', offers_found = %s, pages = %s WHERE id = %s",
                (prog["offers"], prog["done"], run_id),
            )
        taxonomy.match_pending(shop_id)
        taxonomy.backfill_size_classes()
    return prog


def reread(shop_id: int) -> dict:
    """Reads the stored archive copies again (after a reader fix), without fetching anything."""
    with pool.connection() as conn:
        shop = conn.execute("SELECT * FROM shops WHERE id = %s", (shop_id,)).fetchone()
        src = _source(shop)
        caps = conn.execute(
            "SELECT c.*, s.path, s.url AS archive_url, s.run_id FROM archive_captures c JOIN snapshots s ON s.id = c.snapshot_id"
            " WHERE c.shop_id = %s", (shop_id,)).fetchall()
    found = 0
    for cap in caps:
        body = gzip.decompress((Path(config.SNAPSHOT_DIR) / cap["path"]).read_bytes()).decode("utf-8", "replace")
        offers = src["reader"](body, cap["url"], cap["kind"], cap["captured_at"])
        with pool.connection() as conn:
            found += _import(conn, shop_id, cap["run_id"], dict(cap, archive="wayback"), offers)
            conn.execute("UPDATE archive_captures SET status = %s, offers = %s WHERE id = %s",
                         ("parsed" if offers else "unreadable", len(offers), cap["id"]))
    taxonomy.match_pending(shop_id)
    taxonomy.backfill_size_classes()
    return {"captures": len(caps), "new_observations": found}


# ---------- API ----------

def _shop_or_404(shop_id: int) -> dict:
    with pool.connection() as conn:
        shop = conn.execute("SELECT * FROM shops WHERE id = %s", (shop_id,)).fetchone()
    if not shop:
        raise HTTPException(404, "Shop not found.")
    return shop


@router.get("/{shop_id}")
def coverage(shop_id: int):
    shop = _shop_or_404(shop_id)
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT to_char(captured_at, 'YYYY-MM') AS month, kind, status, count(*) AS n, sum(offers) AS offers"
            " FROM archive_captures WHERE shop_id = %s GROUP BY 1, 2, 3 ORDER BY 1",
            (shop_id,),
        ).fetchall()
        obs = conn.execute(
            "SELECT to_char(o.observed_at, 'YYYY') AS year, count(*) AS n, count(DISTINCT o.listing_id) AS offers,"
            " count(DISTINCT o.grower) AS growers"
            " FROM observations o JOIN listings l ON l.id = o.listing_id WHERE l.shop_id = %s AND o.source = 'archive'"
            " GROUP BY 1 ORDER BY 1",
            (shop_id,),
        ).fetchall()
    months: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        months[r["month"]][f"{r['kind']}_{r['status']}"] += r["n"]
        months[r["month"]]["offers"] += r["offers"] or 0
    return {"supported": shop["host"] in SOURCES, "months": [{"month": m, **v} for m, v in months.items()],
            "years": obs, "progress": _progress.get(shop_id)}


@router.post("/{shop_id}/discover")
def api_discover(shop_id: int):
    _shop_or_404(shop_id)
    return discover(shop_id)


@router.post("/{shop_id}/run")
def api_run(shop_id: int):
    _shop_or_404(shop_id)
    if not _lock.acquire(blocking=False):
        raise HTTPException(409, "A history run is already going.")

    def work():
        try:
            run(shop_id)
        except Exception:
            log.exception("archive run failed")
        finally:
            _lock.release()

    threading.Thread(target=work, daemon=True).start()
    return {"started": True}


# ---------- reference check against hand-collected rows (Victor's CSV) ----------

def import_reference(shop_id: int, csv_text: str) -> int:
    """Columns: Monat, Angebot, Topf (cm), Höhe (cm), Preis netto (€), Erzeuger, Quelle. Live rows are skipped."""
    import csv
    import io

    rows = list(csv.DictReader(io.StringIO(csv_text)))
    n = 0
    with pool.connection() as conn:
        conn.execute("DELETE FROM archive_reference WHERE shop_id = %s", (shop_id,))
        for r in rows:
            if not (r.get("Quelle") or "").lower().startswith("internet archive"):
                continue
            conn.execute(
                "INSERT INTO archive_reference (shop_id, month, name, pot_cm, height, price_net, grower, source)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (shop_id, f"{r['Monat']}-01", r["Angebot"].strip(), float(r["Topf (cm)"]) if r["Topf (cm)"] else None,
                 r["Höhe (cm)"] or None, float(r["Preis netto (€)"].replace(",", ".")) if r["Preis netto (€)"] else None,
                 r.get("Erzeuger") or None, r.get("Quelle")),
            )
            n += 1
    return n


def _pot_cm(v) -> float | None:
    m = re.match(r"\s*([\d.,]+)", str(v or ""))
    return float(m.group(1).replace(",", ".")) if m else None


@router.get("/{shop_id}/reference-check")
def reference_check(shop_id: int):
    """Each reference row against what the archive reader found: same name, pot size and month."""
    with pool.connection() as conn:
        refs = conn.execute("SELECT * FROM archive_reference WHERE shop_id = %s ORDER BY month, name", (shop_id,)).fetchall()
        obs = conn.execute(
            "SELECT l.name, o.pot_size, o.plant_size, o.price_eur_net AS price, o.grower,"
            " to_char(o.observed_at, 'YYYY-MM') AS month, o.raw->>'page' AS page"
            " FROM observations o JOIN listings l ON l.id = o.listing_id"
            " WHERE l.shop_id = %s AND o.source = 'archive'",
            (shop_id,),
        ).fetchall()
    by_key: dict[tuple, list] = defaultdict(list)
    for o in obs:
        by_key[(names.name_key(o["name"]), _pot_cm(o["pot_size"]), o["month"])].append(o)
    out = []
    for r in refs:
        cands = by_key.get((names.name_key(r["name"]), float(r["pot_cm"]) if r["pot_cm"] is not None else None,
                            r["month"].strftime("%Y-%m")), [])
        ref_price = float(r["price_net"]) if r["price_net"] is not None else None
        same = [c for c in cands if ref_price is not None and abs(float(c["price"]) - ref_price) < 0.006]
        status = "match" if same else "price differs" if cands else "not found"
        out.append({"month": r["month"].strftime("%Y-%m"), "name": r["name"], "pot_cm": float(r["pot_cm"]) if r["pot_cm"] else None,
                    "height": r["height"], "price": ref_price, "grower": r["grower"], "status": status,
                    "found": [{"price": float(c["price"]), "height": c["plant_size"], "grower": c["grower"], "page": c["page"]}
                              for c in cands]})
    summary = defaultdict(int)
    for x in out:
        summary[x["status"]] += 1
    return {"summary": dict(summary), "rows": out}
