"""Rule-based trends (no AI): weekly event counts, trend score, rankings, wholesale signals, weekly summary."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from . import ntfy
from .analytics import EVENTS_BASE, _event_filters, _key, _name, _num
from .auth import current_user
from .db import pool

log = logging.getLogger("trends")
router = APIRouter(prefix="/api/trends", dependencies=[Depends(current_user)])

RECENT_WEEKS = 4
BEFORE_WEEKS = 12
MIN_EVENTS = 3
WEEK = "date_trunc('week', e.happened_at AT TIME ZONE 'Europe/Berlin')::date"


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


@router.get("/scores")
def scores(level: str = "species", shops: list[int] | None = Query(None), kinds: list[str] | None = Query(None)):
    """Events per week over the last 16 weeks, and recent rate / earlier rate per species."""
    ef, ep = _event_filters(7 * (RECENT_WEEKS + BEFORE_WEEKS) + 7, shops)
    if kinds:
        ef += " AND e.kind = ANY(%s)"
        ep.append(kinds)
    with pool.connection() as conn:
        rows = conn.execute(
            f"SELECT {_key(level)} AS key, {_name(level)} AS name, {WEEK} AS week, count(*) AS n,"
            " count(DISTINCT l.shop_id) AS shops"
            f" {EVENTS_BASE} AND a.listing_id IS NOT NULL {ef} GROUP BY 1, 2, 3",
            ep,
        ).fetchall()
        today = conn.execute("SELECT (now() AT TIME ZONE 'Europe/Berlin')::date AS d").fetchone()["d"]
    this_week = _monday(today)
    weeks = [this_week - timedelta(weeks=i) for i in range(RECENT_WEEKS + BEFORE_WEEKS - 1, -1, -1)]
    recent_from = weeks[-RECENT_WEEKS]

    by: dict[str, dict] = {}
    for r in rows:
        t = by.setdefault(r["key"], {"key": r["key"], "name": r["name"], "weeks": defaultdict(int)})
        t["weeks"][r["week"]] += r["n"]
    out = []
    for t in by.values():
        recent = sum(n for w, n in t["weeks"].items() if w >= recent_from)
        before = sum(n for w, n in t["weeks"].items() if w < recent_from)
        total = recent + before
        recent_rate = recent / RECENT_WEEKS
        before_rate = before / BEFORE_WEEKS
        if total < MIN_EVENTS:
            score, label = None, "too few events"
        elif before == 0:
            score, label = None, "new activity"
        else:
            score, label = round(recent_rate / before_rate, 2), None
        out.append({
            "key": t["key"], "name": t["name"], "recent": recent, "before": before,
            "recent_per_week": round(recent_rate, 2), "before_per_week": round(before_rate, 2),
            "score": score, "label": label,
            "weekly": [t["weeks"].get(w, 0) for w in weeks],
        })
    out.sort(key=lambda x: (x["score"] is None, -(x["score"] or 0), -x["recent"]))
    return {"weeks": [str(w) for w in weeks], "recent_from": str(recent_from), "min_events": MIN_EVENTS,
            "taxa": out}


def _ranking(conn, kinds: list[str], days: int, shops, level: str, limit: int) -> list[dict]:
    ef, ep = _event_filters(days, shops)
    return conn.execute(
        f"SELECT {_key(level)} AS key, {_name(level)} AS name, count(*) AS events, count(DISTINCT l.shop_id) AS shops,"
        " string_agg(DISTINCT sh.name, ', ') AS shop_names, max(e.happened_at) AS last"
        f" {EVENTS_BASE} AND a.listing_id IS NOT NULL AND e.kind = ANY(%s) {ef}"
        " GROUP BY 1, 2 ORDER BY count(DISTINCT l.shop_id) DESC, count(*) DESC, 2 LIMIT %s",
        [kinds] + ep + [limit],
    ).fetchall()


def _price_moves(conn, days: int, shops, level: str) -> list[dict]:
    """Median net price on the first vs. the last night of the period, per species (both must exist)."""
    shop_sql = " AND l.shop_id = ANY(%s)" if shops else ""
    period_sql = " AND o.observed_at >= now() - make_interval(days => %s)" if days > 0 else ""
    params = ([days] if days > 0 else []) + ([shops] if shops else [])
    rows = conn.execute(
        f"WITH d AS (SELECT {_key(level)} AS key, {_name(level)} AS name,"
        " (o.observed_at AT TIME ZONE 'Europe/Berlin')::date AS day,"
        " percentile_cont(0.5) WITHIN GROUP (ORDER BY o.price_eur_net) AS price"
        " FROM observations o JOIN listings l ON l.id = o.listing_id"
        " JOIN assignments a ON a.listing_id = l.id AND a.confirmed AND NOT a.ignored"
        " LEFT JOIN species s ON s.id = a.species_id LEFT JOIN cultivars c ON c.id = a.cultivar_id"
        f" WHERE o.price_eur_net IS NOT NULL{period_sql}{shop_sql} GROUP BY 1, 2, 3)"
        " SELECT key, name, (array_agg(price ORDER BY day))[1] AS first_price, min(day) AS first_day,"
        " (array_agg(price ORDER BY day DESC))[1] AS last_price, max(day) AS last_day"
        " FROM d GROUP BY 1, 2 HAVING min(day) < max(day)",
        params,
    ).fetchall()
    out = []
    for r in rows:
        a, b = _num(r["first_price"]), _num(r["last_price"])
        if a and b and abs(b - a) >= 0.005:
            out.append({"key": r["key"], "name": r["name"], "from": a, "to": b, "change_pct": round((b - a) / a * 100, 1),
                        "first_day": str(r["first_day"]), "last_day": str(r["last_day"])})
    return out


@router.get("/rankings")
def rankings(days: int = 28, level: str = "species", shops: list[int] | None = Query(None), limit: int = 15):
    with pool.connection() as conn:
        restocked = _ranking(conn, ["restock", "back_in_stock"], days, shops, level, limit)
        new = _ranking(conn, ["new"], days, shops, level, limit)
        gone = _ranking(conn, ["disappeared"], days, shops, level, limit)
        moves = _price_moves(conn, days, shops, level)
        widest = conn.execute(
            f"SELECT {_key(level)} AS key, {_name(level)} AS name, count(DISTINCT l.shop_id) AS shops,"
            " string_agg(DISTINCT sh.name, ', ') AS shop_names, count(DISTINCT l.id) AS offers"
            " FROM listings l JOIN shops sh ON sh.id = l.shop_id"
            " JOIN assignments a ON a.listing_id = l.id AND a.confirmed AND NOT a.ignored"
            " LEFT JOIN species s ON s.id = a.species_id LEFT JOIN cultivars c ON c.id = a.cultivar_id"
            " WHERE l.gone_since IS NULL" + (" AND l.shop_id = ANY(%s)" if shops else "")
            + " GROUP BY 1, 2 ORDER BY 3 DESC, 5 DESC, 2 LIMIT %s",
            ([shops] if shops else []) + [limit],
        ).fetchall()
    return {
        "restocked": restocked,
        "new": new,
        "gone": gone,
        "price_down": sorted([m for m in moves if m["change_pct"] < 0], key=lambda m: m["change_pct"])[:limit],
        "price_up": sorted([m for m in moves if m["change_pct"] > 0], key=lambda m: -m["change_pct"])[:limit],
        "widest": widest,
    }


@router.get("/wholesale")
def wholesale(days: int = 0, level: str = "species", limit: int = 15):
    """Stock rises (incoming) and drops (sell-through) between nights at wholesalers and importers."""
    period = " AND o.observed_at >= now() - make_interval(days => %s)" if days > 0 else ""
    params = [days] if days > 0 else []
    base = (
        "WITH q AS (SELECT o.listing_id, o.observed_at, o.quantity,"
        "  o.quantity - lag(o.quantity) OVER (PARTITION BY o.listing_id ORDER BY o.observed_at) AS delta"
        "  FROM observations o JOIN listings l ON l.id = o.listing_id JOIN shops sh ON sh.id = l.shop_id"
        f"  WHERE sh.type IN ('wholesaler', 'importer') AND o.quantity IS NOT NULL{period})"
    )
    with pool.connection() as conn:
        weekly = conn.execute(
            base + " SELECT date_trunc('week', q.observed_at AT TIME ZONE 'Europe/Berlin')::date AS week,"
            " sum(delta) FILTER (WHERE delta > 0) AS incoming, -sum(delta) FILTER (WHERE delta < 0) AS sold"
            " FROM q WHERE delta IS NOT NULL GROUP BY 1 ORDER BY 1",
            params,
        ).fetchall()
        top = conn.execute(
            base + f" SELECT {_key(level)} AS key, {_name(level)} AS name,"
            " coalesce(sum(delta) FILTER (WHERE delta > 0), 0) AS incoming,"
            " coalesce(-sum(delta) FILTER (WHERE delta < 0), 0) AS sold, count(DISTINCT q.listing_id) AS offers"
            " FROM q JOIN assignments a ON a.listing_id = q.listing_id AND a.confirmed AND NOT a.ignored"
            " LEFT JOIN species s ON s.id = a.species_id LEFT JOIN cultivars c ON c.id = a.cultivar_id"
            " WHERE delta IS NOT NULL GROUP BY 1, 2 ORDER BY 3 DESC, 4 DESC LIMIT %s",
            params + [limit],
        ).fetchall()
    return {
        "weekly": [{"week": str(w["week"]), "incoming": w["incoming"] or 0, "sold": w["sold"] or 0} for w in weekly],
        "top": top,
    }


def weekly_summary() -> None:
    """Monday 8:00: the past week's main movements via ntfy."""
    try:
        r = rankings(days=7, level="species", shops=None, limit=5)
        with pool.connection() as conn:
            n = conn.execute(
                "SELECT count(*) AS n FROM events WHERE happened_at >= now() - interval '7 days'"
            ).fetchone()["n"]
        lines = [f"{n} events in the last 7 days."]

        def block(title, items, fmt):
            if items:
                lines.append(f"\n{title}:")
                lines.extend(f"• {fmt(i)}" for i in items)

        block("Restocked", r["restocked"], lambda i: f"{i['name']} ({i['shop_names']})")
        block("New", r["new"], lambda i: f"{i['name']} ({i['shop_names']})")
        block("Price down", r["price_down"], lambda i: f"{i['name']} {i['change_pct']:+.0f}%")
        block("Price up", r["price_up"], lambda i: f"{i['name']} {i['change_pct']:+.0f}%")
        block("Gone", r["gone"], lambda i: f"{i['name']} ({i['shop_names']})")
        ntfy.send("Market Trends: week", "\n".join(lines), tags=["bar_chart"])
    except Exception:
        log.exception("weekly summary failed")

