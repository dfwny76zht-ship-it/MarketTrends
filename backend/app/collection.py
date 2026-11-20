"""Collection tab: per shop what is collected, by whom and when, how the runs went, and the history
(archive) import. One endpoint, so the page shows each fact once."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from . import archive
from .auth import current_user
from .db import pool

router = APIRouter(prefix="/api/collection", dependencies=[Depends(current_user)])
scheduler = None  # set by main.py

JOBS = {
    "nightly": "Night run: shops collected by Hetzner, robots.txt checks",
    "images": "Photos of new offers",
    "pi_overdue": "Alarm if the Pi has not delivered its shops",
    "weekly_summary": "Weekly summary to the phone (ntfy)",
}
# What each reader can deliver, in plain words (shops.provides says what is switched on).
READS = {
    "floraccess": ["price (net)", "stock quantity", "pot size", "grower", "available / sold out"],
    "jtl": ["price", "available / sold out", "discount badges"],
    "shopify": ["price per pot size", "available / sold out"],
}


def _secs(a, b):
    return int((b - a).total_seconds()) if a and b else None


@router.get("")
def overview():
    jobs = []
    if scheduler:
        for job_id, what in JOBS.items():
            j = scheduler.get_job(job_id)
            nxt = getattr(j, "next_run_time", None) if j else None
            if j and nxt is None:  # scheduler not started in this process: work it out from the trigger
                nxt = j.trigger.get_next_fire_time(None, datetime.now(timezone.utc))
            jobs.append({"id": job_id, "what": what, "next": nxt.isoformat() if nxt else None})
    with pool.connection() as conn:
        pi = conn.execute("SELECT last_seen FROM collectors WHERE name = 'pi'").fetchone()
        shops = conn.execute(
            "SELECT s.id, s.name, s.url, s.status, s.collector, s.adapter, s.crawl_delay, s.next_run_after, s.note,"
            " (SELECT count(*) FROM listings l WHERE l.shop_id = s.id AND l.gone_since IS NULL) AS listed,"
            " (SELECT count(*) FROM listings l WHERE l.shop_id = s.id) AS ever"
            " FROM shops s ORDER BY s.status = 'active' DESC, s.name").fetchall()
        out = []
        for s in shops:
            runs = conn.execute(
                "SELECT kind, started_at, finished_at, result, offers_found, events_found, pages, error,"
                " details->>'collector' AS by FROM runs WHERE shop_id = %s AND kind <> 'archive'"
                " ORDER BY started_at DESC LIMIT 8", (s["id"],)).fetchall()
            avg = conn.execute(
                "SELECT avg(extract(epoch FROM finished_at - started_at))::int AS secs FROM ("
                " SELECT started_at, finished_at FROM runs WHERE shop_id = %s AND kind = 'collect' AND result = 'ok'"
                " ORDER BY started_at DESC LIMIT 7) t", (s["id"],)).fetchone()["secs"]
            years = conn.execute(
                "SELECT to_char(o.observed_at, 'YYYY') AS year, o.source, count(*) AS n FROM observations o"
                " JOIN listings l ON l.id = o.listing_id WHERE l.shop_id = %s GROUP BY 1, 2 ORDER BY 1", (s["id"],)).fetchall()
            hist = archive.status(s["id"]) if s["url"] and _has_archive(s) else None
            out.append({
                **{k: s[k] for k in ("id", "name", "url", "status", "collector", "adapter", "crawl_delay", "next_run_after",
                                     "listed", "ever")},
                "reads": READS.get(s["adapter"] or "", []),
                "avg_seconds": avg,
                "runs": [{**{k: r[k] for k in ("kind", "started_at", "result", "offers_found", "events_found", "pages", "error")},
                          "seconds": _secs(r["started_at"], r["finished_at"]), "running": r["finished_at"] is None,
                          "by": r["by"] or ("pi" if s["collector"] == "pi" and r["kind"] == "collect" else "hetzner")}
                         for r in runs],
                "years": years,
                "history": hist,
            })
    return {"jobs": jobs, "pi_last_seen": pi["last_seen"] if pi else None, "shops": out}


def _has_archive(shop) -> bool:
    with pool.connection() as conn:
        host = conn.execute("SELECT host FROM shops WHERE id = %s", (shop["id"],)).fetchone()["host"]
    return host in archive.SOURCES
