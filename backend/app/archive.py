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
from .adapters import floraccess_archive, haage_archive, jtl_archive
from .auth import current_user
from .db import pool

log = logging.getLogger("archive")
router = APIRouter(prefix="/api/archive", dependencies=[Depends(current_user)])

CDX = "https://web.archive.org/cdx/search/cdx"
GAP = 5.0            # normal pause between archive requests (all shops together)
BUSY_GAP = 12.0      # pause while archive.org has recently answered "busy" (503)
BUSY_WAITS = (45, 90, 135)  # waits before retrying a page that got a 503
FROM_YEAR = "2018"
_lock = threading.Lock()
_progress: dict[int, dict] = {}

def _fa_kind(url: str) -> tuple[str | None, str | None]:
    if m := re.search(r"/v/(\d+)/", url):
        return "offer", m.group(1)
    if m := re.search(r"/product/(\d+)/", url):
        return "product", m.group(1)
    if "/category/" in url:
        return "category", None
    return None, None


def _haage_kind(url: str) -> tuple[str | None, str | None]:
    path = re.sub(r"https?://(www\.)?[^/]+(:80)?", "", url).split("?")[0]
    if re.search(r"/(Zubehoer|accessories|Literatur|books|Samen|seeds|modules|Dischidia)/", path, re.I):
        return None, None
    if not re.search(r"/(Pflanzen|plants)/hoya/", path, re.I):
        return None, None
    if path.endswith(".html"):
        return "product", path.rsplit("/", 1)[-1].lower()
    return "category", None


def _jtl_kind(category_re: str):
    """JTL shops: the Hoya category (with its page suffixes _1, _s2 …) and product pages named Hoya-…"""
    def kind(url: str) -> tuple[str | None, str | None]:
        path = re.sub(r"https?://(www\.)?[^/]+(:80|:443)?", "", url).split("?")[0].rstrip("/")
        if re.fullmatch(category_re, path, re.I):
            return "category", None
        if re.fullmatch(r"/Hoya-[^/]+", path, re.I):
            return "product", path.lower()
        return None, None
    return kind


def _body_text(raw: bytes) -> str:
    """Archive copies can come still gzip-compressed, and older JTL pages are ISO-8859-1."""
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", "replace")


# Per shop: which archived addresses belong to the Hoya range, and how to read them.
SOURCES = {
    "floraccess.com": {"domain": "floraccess.com", "filter": "original:.*[Hh]oya.*", "kind": _fa_kind,
                       "reader": floraccess_archive.parse_archived, "basis": "net"},
    "kakteen-haage.de": {"domain": "kakteen-haage.de", "filter": "original:.*[Hh]oya.*", "kind": _haage_kind,
                         "reader": haage_archive.parse_archived, "basis": "gross"},
    "bens-jungle.com": {"domain": "bens-jungle.com", "prefixes": ["bens-jungle.com/Hoya", "www.bens-jungle.com/Hoya"],
                        "kind": _jtl_kind(r"/Hoya(_\d+)?(_s\d+)?"), "reader": jtl_archive.parse_archived, "basis": "gross"},
    "uhlig-kakteen.de": {"domain": "uhlig-kakteen.de", "prefixes": ["uhlig-kakteen.de/Hoya", "www.uhlig-kakteen.de/Hoya"],
                         "kind": _jtl_kind(r"/Hoya-und-Dischidia(_\d+)?(_s\d+)?"), "reader": jtl_archive.parse_archived,
                         "basis": "gross"},
}


def _source(shop: dict) -> dict:
    src = SOURCES.get(shop["host"])
    if not src:
        raise HTTPException(422, "No archive reader for this shop yet.")
    return src


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
    queries = ([{"url": p, "matchType": "prefix"} for p in src["prefixes"]] if src.get("prefixes")
               else [{"url": src["domain"], "matchType": "domain", "filter": src["filter"]}])
    rows = []
    with _client() as c:
        for q in queries:
            # The index is often busy: a narrow prefix query plus a few patient retries.
            for attempt in range(4):
                try:
                    r = c.get(CDX, params={**q, "from": FROM_YEAR, "fl": "timestamp,original,statuscode,mimetype",
                                           "output": "json"}, timeout=180)
                    if r.status_code == 503 and attempt < 3:
                        time.sleep(30 * (attempt + 1))
                        continue
                    r.raise_for_status()
                    break
                except httpx.TimeoutException:
                    if attempt == 3:
                        raise
                    time.sleep(30 * (attempt + 1))
            rows += r.json()[1:] if r.text.strip() else []
            time.sleep(GAP)
    best: dict[tuple, tuple] = {}
    for ts, url, status, mime in rows:
        if status != "200" or "html" not in mime:
            continue
        kind, key = src["kind"](url)
        if not kind:
            continue
        page = key or re.sub(r"https?://(www\.)?[^/]+(:80)?/([a-z]{2}/)?", "/", url).split("?")[0].lower()
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


def _import(conn, shop_id: int, run_id: int, capture: dict, offers: list[dict], basis: str = "net") -> int:
    """basis 'gross': prices incl. VAT (consumer shops); the net price uses the shop's VAT rate."""
    n = 0
    vat = conn.execute("SELECT vat_rate FROM shops WHERE id = %s", (shop_id,)).fetchone()["vat_rate"]
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
            " VALUES (%s, %s, %s, %s, 'EUR', %s, %s, %s, %s, %s, %s, 'archive', %s, %s)",
            (lid, run_id, at, o["price"], basis,
             o["price"] if basis == "net" else round(o["price"] / (1 + float(vat) / 100), 4),
             o["availability"], o.get("pot"), o.get("height"),
             Jsonb({"archive": capture["archive"], "archive_url": capture["archive_url"], "page": capture["kind"],
                    "captured_at": capture["captured_at"].isoformat(), "note": o.get("note"),
                    **{k: o[k] for k in ("ribbons", "sku", "delivery") if o.get(k)}}),
             names.size_class(o.get("pot"), o["name"]), o.get("grower")),
        )
        n += 1
    return n


def run(shop_id: int, limit: int | None = None) -> dict:
    return run_queue([shop_id], limit)


def _fetch(c: httpx.Client, url: str, state: dict) -> tuple[httpx.Response | None, str | None]:
    """One archive request; a 503 ('busy') waits and retries the same page, then slows the pace."""
    for attempt in range(len(BUSY_WAITS) + 1):
        try:
            r = c.get(url)
        except httpx.HTTPError as exc:
            return None, type(exc).__name__
        if r.status_code != 503:
            return r, None
        state["busy_until"] = time.monotonic() + 600
        state["busy_count"] = state.get("busy_count", 0) + 1
        if attempt < len(BUSY_WAITS):
            state["waiting"] = BUSY_WAITS[attempt]
            time.sleep(BUSY_WAITS[attempt])
            state["waiting"] = None
    return r, "HTTP 503 (archive busy)"


def run_queue(shop_ids: list[int], limit: int | None = None) -> dict:
    """Fetches and reads every capture not yet done for these shops, alternating between the
    shops so all of them progress at once while archive.org sees one polite stream. Resumable."""
    shops, todo, run_ids = {}, {}, {}
    with pool.connection() as conn:
        for sid in shop_ids:
            shops[sid] = conn.execute("SELECT * FROM shops WHERE id = %s", (sid,)).fetchone()
            _source(shops[sid])
            todo[sid] = conn.execute(
                "SELECT * FROM archive_captures WHERE shop_id = %s AND status IN ('new', 'failed') ORDER BY captured_at"
                + (" LIMIT %s" % int(limit) if limit else ""),
                (sid,),
            ).fetchall()
            run_ids[sid] = conn.execute(
                "INSERT INTO runs (shop_id, kind, details) VALUES (%s, 'archive', %s) RETURNING id",
                (sid, Jsonb({"captures": len(todo[sid]), "queue": shop_ids})),
            ).fetchone()["id"]
    # Round robin: one page of each shop in turn.
    order = []
    for i in range(max((len(v) for v in todo.values()), default=0)):
        order += [todo[sid][i] for sid in shop_ids if i < len(todo[sid])]
    prog = {sid: {"offers": 0, "done": 0} for sid in shop_ids}
    state: dict = {}
    last = 0.0
    try:
        with _client() as c:
            for cap in order:
                sid = cap["shop_id"]
                src = _source(shops[sid])
                ts = cap["captured_at"].strftime("%Y%m%d%H%M%S")
                archive_url = f"https://web.archive.org/web/{ts}id_/{cap['url']}"
                gap = BUSY_GAP if time.monotonic() < state.get("busy_until", 0) else GAP
                wait = gap - (time.monotonic() - last)
                if wait > 0:
                    time.sleep(wait)
                r, err = _fetch(c, archive_url, state)
                last = time.monotonic()
                if r is not None and r.status_code == 429:
                    log.warning("archive.org asks to slow down; stopping this run")
                    break
                if err or r is None or r.status_code >= 400:
                    with pool.connection() as conn:
                        conn.execute("UPDATE archive_captures SET status = 'failed', error = %s, fetched_at = now() WHERE id = %s",
                                     (err or f"HTTP {r.status_code}", cap["id"]))
                    continue
                snap = _store_snapshot(sid, run_ids[sid], archive_url, r.status_code, r.content)
                offers = src["reader"](_body_text(r.content), cap["url"], cap["kind"], cap["captured_at"])
                with pool.connection() as conn:
                    n = _import(conn, sid, run_ids[sid], dict(cap, archive="wayback", archive_url=archive_url), offers,
                                src["basis"])
                    conn.execute(
                        "UPDATE archive_captures SET status = %s, snapshot_id = %s, offers = %s, error = NULL, fetched_at = now()"
                        " WHERE id = %s",
                        ("parsed" if offers else "unreadable", snap, len(offers), cap["id"]),
                    )
                prog[sid]["offers"] += n
                prog[sid]["done"] += 1
    finally:
        with pool.connection() as conn:
            for sid in shop_ids:
                conn.execute("UPDATE runs SET finished_at = now(), result = 'ok', offers_found = %s, pages = %s WHERE id = %s",
                             (prog[sid]["offers"], prog[sid]["done"], run_ids[sid]))
        for sid in shop_ids:
            taxonomy.match_pending(sid)
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
        body = _body_text(gzip.decompress((Path(config.SNAPSHOT_DIR) / cap["path"]).read_bytes()))
        offers = src["reader"](body, cap["url"], cap["kind"], cap["captured_at"])
        with pool.connection() as conn:
            found += _import(conn, shop_id, cap["run_id"], dict(cap, archive="wayback"), offers, src["basis"])
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


@router.get("/shops")
def archive_shops():
    """Shops with an archive reader (for the progress boxes), whether or not they collect live."""
    with pool.connection() as conn:
        return conn.execute(
            "SELECT s.id, s.name, (SELECT count(*) FROM archive_captures c WHERE c.shop_id = s.id) AS captures"
            " FROM shops s WHERE s.host = ANY(%s) ORDER BY s.id", (list(SOURCES),)).fetchall()


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
            run_queue([shop_id])
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


@router.get("/{shop_id}/status")
def status(shop_id: int):
    """Progress of the history run, read from the database (the run may live in another process)."""
    _shop_or_404(shop_id)
    with pool.connection() as conn:
        counts = {r["status"]: r for r in conn.execute(
            "SELECT status, count(*) AS n, coalesce(sum(offers), 0) AS offers FROM archive_captures WHERE shop_id = %s GROUP BY 1",
            (shop_id,))}
        run = conn.execute(
            "SELECT id, started_at, finished_at, result FROM runs WHERE shop_id = %s AND kind = 'archive' ORDER BY id DESC LIMIT 1",
            (shop_id,)).fetchone()
        recent = conn.execute(
            "SELECT to_char(captured_at, 'YYYY-MM') AS month, kind, url, status, offers, error, fetched_at"
            " FROM archive_captures WHERE shop_id = %s AND fetched_at IS NOT NULL ORDER BY fetched_at DESC LIMIT 6",
            (shop_id,)).fetchall()
        nxt = conn.execute(
            "SELECT to_char(captured_at, 'YYYY-MM') AS month, kind, url FROM archive_captures"
            " WHERE shop_id = %s AND status IN ('new', 'failed') ORDER BY captured_at LIMIT 1", (shop_id,)).fetchone()
        rate = conn.execute(
            "SELECT count(*) AS n, extract(epoch FROM max(fetched_at) - min(fetched_at)) AS secs FROM ("
            "  SELECT fetched_at FROM archive_captures WHERE shop_id = %s AND fetched_at > now() - interval '15 minutes'"
            "  ORDER BY fetched_at DESC LIMIT 30) t", (shop_id,)).fetchone()
        obs = conn.execute(
            "SELECT count(*) AS n FROM observations o JOIN listings l ON l.id = o.listing_id"
            " WHERE l.shop_id = %s AND o.source = 'archive'", (shop_id,)).fetchone()["n"]
    n = lambda s: counts.get(s, {}).get("n", 0)
    total = sum(r["n"] for r in counts.values())
    done = n("parsed") + n("unreadable")
    running = bool(run and run["finished_at"] is None)
    per_min = None
    if rate["n"] and rate["n"] > 1 and rate["secs"]:
        per_min = round((rate["n"] - 1) / float(rate["secs"]) * 60, 1)
    left = n("new") + n("failed")
    return {
        "total": total, "parsed": n("parsed"), "unreadable": n("unreadable"), "failed": n("failed"), "waiting": n("new"),
        "done": done, "offers_read": sum(r["offers"] for r in counts.values()), "observations": obs,
        "running": running, "started_at": run["started_at"] if run else None,
        "per_min": per_min, "eta_min": round(left / per_min) if per_min and running else None,
        "next": nxt if running else None, "recent": recent,
    }
