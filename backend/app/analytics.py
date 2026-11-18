"""Analysis API: overview, per-species pages, chart window, price vs. quantity, events, watchlist.

Only confirmed species matches count. Prices are compared as net EUR (price_eur_net). Missing values stay
missing: nothing is filled in or estimated, except the clearly labelled sales estimate from quantity drops.
"""

from __future__ import annotations

import re
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from . import filters as flt
from .auth import current_user
from .db import pool

router = APIRouter(prefix="/api/analytics", dependencies=[Depends(current_user)])

AVAIL_RANK = {"available": 3, "low": 2, "sold_out": 1, "unknown": 0}
RANK_AVAIL = {v: k for k, v in AVAIL_RANK.items()}
DAY = "(o.observed_at AT TIME ZONE 'Europe/Berlin')::date"

TAXON_NAME = """
CASE WHEN a.cultivar_id IS NULL THEN 'Hoya ' || s.epithet
     WHEN c.kind IN ('cultivar', 'hybrid') THEN 'Hoya ' || coalesce(s.epithet || ' ', '') || '''' || c.name || ''''
     ELSE 'Hoya ' || coalesce(s.epithet || ' ', '') || c.name END
"""


def _key(level: str) -> str:
    if level == "cultivar":
        return "CASE WHEN a.cultivar_id IS NOT NULL THEN 'c' || a.cultivar_id ELSE 's' || a.species_id END"
    return "CASE WHEN a.species_id IS NOT NULL THEN 's' || a.species_id ELSE 'c' || a.cultivar_id END"


def _name(level: str) -> str:
    if level == "cultivar":
        return TAXON_NAME
    return "CASE WHEN a.species_id IS NOT NULL THEN 'Hoya ' || s.epithet ELSE 'Hoya ''' || c.name || '''' END"


def _taxon_filter(key: str) -> tuple[str, int]:
    m = re.fullmatch(r"([sc])(\d+)", key or "")
    if not m:
        raise HTTPException(422, "Unknown species key.")
    return ("a.species_id = %s" if m.group(1) == "s" else "a.cultivar_id = %s"), int(m.group(2))


BASE = """
FROM observations o
JOIN listings l ON l.id = o.listing_id
JOIN shops sh ON sh.id = l.shop_id
JOIN assignments a ON a.listing_id = l.id AND a.confirmed AND NOT a.ignored
LEFT JOIN species s ON s.id = a.species_id
LEFT JOIN cultivars c ON c.id = a.cultivar_id
WHERE true
"""

EVENTS_BASE = """
FROM events e
JOIN listings l ON l.id = e.listing_id
JOIN shops sh ON sh.id = l.shop_id
LEFT JOIN assignments a ON a.listing_id = l.id AND a.confirmed AND NOT a.ignored
LEFT JOIN species s ON s.id = a.species_id
LEFT JOIN cultivars c ON c.id = a.cultivar_id
WHERE true
"""


def _num(v):
    return float(v) if v is not None else None


@router.get("/shops")
def shop_list():
    with pool.connection() as conn:
        return conn.execute("SELECT id, name FROM shops WHERE adapter IS NOT NULL ORDER BY id").fetchall()


# ---------- overview ----------

@router.get("/overview")
def overview(days: int = 28, shops: list[int] | None = Query(None), size: str | None = None,
             scope: str = "period", types: list[str] | None = Query(None), group: list[int] | None = Query(None)):
    fl = flt.make(days, shops, size, scope, types, group)
    shops = fl.shops
    with pool.connection() as conn:
        f, p = flt.where(conn, fl, "obs")
        ef, ep = flt.where(conn, fl, "event")
        daily = conn.execute(
            f"SELECT {DAY} AS day, count(DISTINCT l.id) AS offers,"
            " count(DISTINCT coalesce('s' || a.species_id, 'c' || a.cultivar_id)) AS species"
            f" {BASE} {f} GROUP BY 1 ORDER BY 1",
            p,
        ).fetchall()
        events = conn.execute(
            f"SELECT (e.happened_at AT TIME ZONE 'Europe/Berlin')::date AS day, e.kind, count(*) AS n {EVENTS_BASE}"
            + (" AND a.listing_id IS NOT NULL" if fl.types or fl.groups else "")
            + f" {ef} GROUP BY 1, 2 ORDER BY 1",
            ep,
        ).fetchall()
        unassigned = conn.execute(
            "SELECT count(*) AS n FROM listings l LEFT JOIN assignments a ON a.listing_id = l.id"
            " WHERE l.gone_since IS NULL AND (a.listing_id IS NULL OR NOT a.confirmed)"
            + (" AND l.shop_id = ANY(%s)" if shops else ""),
            [shops] if shops else None,
        ).fetchone()["n"]
        shop_list = conn.execute(
            "SELECT id, name FROM shops WHERE adapter IS NOT NULL ORDER BY id"
        ).fetchall()
    by_kind: dict[str, dict] = defaultdict(dict)
    for e in events:
        by_kind[e["kind"]][str(e["day"])] = e["n"]
    return {
        "days": [str(d["day"]) for d in daily],
        "offers": [d["offers"] for d in daily],
        "species": [d["species"] for d in daily],
        "events": {k: v for k, v in by_kind.items()},
        "unassigned": unassigned,
        "shops": shop_list,
    }


# ---------- table of species (overview + chart window) ----------

@router.get("/taxa")
def taxa(days: int = 28, level: str = "species", shops: list[int] | None = Query(None),
         size: str | None = None, keys: list[str] | None = Query(None), scope: str = "period",
         types: list[str] | None = Query(None), group: list[int] | None = Query(None)):
    fl = flt.make(days, shops, size, scope, types, group)
    key, name = _key(level), _name(level)
    with pool.connection() as conn:
        f, p = flt.where(conn, fl, "obs")
        ef, ep = flt.where(conn, fl, "event")
        if flt._list(keys):
            f += f" AND {key} = ANY(%s)"
            p = p + [list(keys)]
        rows = conn.execute(
            f"SELECT {key} AS key, {name} AS name, {DAY} AS day,"
            " percentile_cont(0.5) WITHIN GROUP (ORDER BY o.price_eur_net) AS price,"
            " count(DISTINCT l.shop_id) AS shops, count(DISTINCT l.id) AS offers,"
            " sum(o.quantity) AS quantity,"
            " count(DISTINCT l.shop_id) FILTER (WHERE o.availability IN ('available', 'low')) AS in_stock_shops"
            f" {BASE} {f} GROUP BY 1, 2, 3 ORDER BY 1, 3",
            p,
        ).fetchall()
        ev = conn.execute(
            f"SELECT {key} AS key, e.kind, (e.happened_at AT TIME ZONE 'Europe/Berlin')::date AS day, count(*) AS n"
            f" {EVENTS_BASE} AND a.listing_id IS NOT NULL {ef} GROUP BY 1, 2, 3",
            ep,
        ).fetchall()
        watched = {
            ("s" + str(r["species_id"])) if r["species_id"] else ("c" + str(r["cultivar_id"]))
            for r in conn.execute("SELECT species_id, cultivar_id FROM watchlist")
        }
        photos = {
            r["key"]: r["id"]
            for r in conn.execute(
                f"SELECT DISTINCT ON (1) {key} AS key, l.id FROM listings l JOIN images i ON i.listing_id = l.id"
                " AND i.status = 'ok' JOIN assignments a ON a.listing_id = l.id AND a.confirmed AND NOT a.ignored"
                " LEFT JOIN cultivars c ON c.id = a.cultivar_id"
                " ORDER BY 1, l.gone_since IS NULL DESC, l.last_seen DESC"
            )
        }
    out: dict[str, dict] = {}
    for r in rows:
        t = out.setdefault(r["key"], {"key": r["key"], "name": r["name"], "series": []})
        t["series"].append({"day": str(r["day"]), "price": _num(r["price"]), "shops": r["shops"],
                            "offers": r["offers"], "quantity": r["quantity"], "in_stock_shops": r["in_stock_shops"]})
    events: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    events_daily: dict[str, dict] = defaultdict(lambda: defaultdict(int))
    for e in ev:
        events[e["key"]][e["kind"]] += e["n"]
        events_daily[e["key"]][str(e["day"])] += e["n"]
    result = []
    for t in out.values():
        last = t["series"][-1]
        t.update(
            price=last["price"], shops=last["shops"], offers=last["offers"], quantity=last["quantity"],
            in_stock_shops=last["in_stock_shops"], last_day=last["day"], events=dict(events.get(t["key"], {})),
            events_daily=dict(events_daily.get(t["key"], {})),
            watched=t["key"] in watched, photo=photos.get(t["key"]),
        )
        t["event_total"] = sum(t["events"].values())
        result.append(t)
    result.sort(key=lambda t: (-t["event_total"], -t["shops"], t["name"]))
    return result


# ---------- one species / cultivar ----------

@router.get("/taxon/{key}")
def taxon(key: str, days: int = 0, shops: list[int] | None = Query(None), size: str | None = None,
          scope: str = "period", types: list[str] | None = Query(None), group: list[int] | None = Query(None)):
    where, tid = _taxon_filter(key)
    fl = flt.make(days, shops, size, scope, types, group)
    shops = fl.shops
    with pool.connection() as conn:
        f, p = flt.where(conn, fl, "obs")
        nf, np_ = flt.where(conn, fl, "obs", period=False)
        ef, ep = flt.where(conn, fl, "event")
        if key.startswith("s"):
            head = conn.execute("SELECT id, epithet, in_lims, notes FROM species WHERE id = %s", (tid,)).fetchone()
            if not head:
                raise HTTPException(404, "Species not found.")
            title = f"Hoya {head['epithet']}"
        else:
            head = conn.execute(
                "SELECT c.id, c.name, c.kind, c.species_id, s.epithet FROM cultivars c"
                " LEFT JOIN species s ON s.id = c.species_id WHERE c.id = %s",
                (tid,),
            ).fetchone()
            if not head:
                raise HTTPException(404, "Cultivar not found.")
            cname = f"'{head['name']}'" if head["kind"] in ("cultivar", "hybrid") else head["name"]
            title = "Hoya " + (f"{head['epithet']} " if head["epithet"] else "") + cname

        per_shop = conn.execute(
            f"SELECT {DAY} AS day, l.shop_id, sh.name AS shop,"
            " percentile_cont(0.5) WITHIN GROUP (ORDER BY o.price_eur_net) AS price,"
            " min(o.price_eur_net) AS price_min, max(o.price_eur_net) AS price_max,"
            " count(*) AS offers, max(CASE o.availability WHEN 'available' THEN 3 WHEN 'low' THEN 2"
            "   WHEN 'sold_out' THEN 1 ELSE 0 END) AS avail,"
            " sum(o.quantity) AS quantity, bool_or(o.source = 'archive') AS archive"
            f" {BASE} AND {where} {f} GROUP BY 1, 2, 3 ORDER BY 1, 2",
            [tid] + p,
        ).fetchall()
        overall = conn.execute(
            f"SELECT {DAY} AS day, percentile_cont(0.5) WITHIN GROUP (ORDER BY o.price_eur_net) AS price,"
            " count(DISTINCT l.shop_id) AS shops"
            f" {BASE} AND {where} {f} GROUP BY 1 ORDER BY 1",
            [tid] + p,
        ).fetchall()
        sizes = conn.execute(
            f"SELECT o.size_class, sh.name AS shop, percentile_cont(0.5) WITHIN GROUP (ORDER BY o.price_eur_net) AS price,"
            " count(DISTINCT l.id) AS offers"
            f" {BASE} AND {where} AND o.id IN (SELECT DISTINCT ON (listing_id) id FROM observations"
            f"   ORDER BY listing_id, observed_at DESC) {nf}"
            " GROUP BY 1, 2 ORDER BY 1, 2",
            [tid] + np_,
        ).fetchall()
        offers = conn.execute(
            "SELECT l.id, l.name, l.url, l.gone_since, sh.name AS shop, o.price, o.currency, o.price_basis,"
            " EXISTS (SELECT 1 FROM images i WHERE i.listing_id = l.id AND i.status = 'ok') AS photo,"
            " o.price_eur_net, o.availability, o.quantity, o.size_class, o.pot_size, o.observed_at, o.source"
            f" {BASE} AND {where} AND o.id IN (SELECT DISTINCT ON (listing_id) id FROM observations"
            f"   ORDER BY listing_id, observed_at DESC) {nf}"
            " ORDER BY l.gone_since IS NOT NULL, sh.name, o.price_eur_net",
            [tid] + np_,
        ).fetchall()
        events = conn.execute(
            "SELECT e.id, e.kind, e.happened_at, e.old_value, e.new_value, l.name, sh.name AS shop"
            f" {EVENTS_BASE} AND {where} {ef} ORDER BY e.happened_at DESC LIMIT 200",
            [tid] + ep,
        ).fetchall()
        watched = conn.execute(
            "SELECT 1 FROM watchlist WHERE " + ("species_id" if key.startswith("s") else "cultivar_id") + " = %s",
            (tid,),
        ).fetchone() is not None

    shops_seen: dict[int, str] = {}
    by_shop: dict[int, list] = defaultdict(list)
    for r in per_shop:
        shops_seen[r["shop_id"]] = r["shop"]
        by_shop[r["shop_id"]].append(r)

    series = []
    for sid, rows in by_shop.items():
        points, prev_q = [], None
        for r in rows:
            q = r["quantity"]
            change = (q - prev_q) if (q is not None and prev_q is not None) else None
            points.append({
                "day": str(r["day"]), "price": _num(r["price"]), "price_min": _num(r["price_min"]),
                "price_max": _num(r["price_max"]), "offers": r["offers"], "availability": RANK_AVAIL[r["avail"]],
                "quantity": q, "sold_est": -change if change is not None and change < 0 else None,
                "restocked": change if change is not None and change > 0 else None,
                "archive": r["archive"],
            })
            if q is not None:
                prev_q = q
        series.append({"shop_id": sid, "shop": shops_seen[sid], "points": points})

    return {
        "key": key, "title": title, "head": head, "watched": watched,
        "series": series,
        "overall": [{"day": str(r["day"]), "price": _num(r["price"]), "shops": r["shops"]} for r in overall],
        "sizes": [dict(r, price=_num(r["price"])) for r in sizes],
        "offers": offers, "events": events,
    }


# ---------- price vs. quantity ----------

@router.get("/scatter")
def scatter(days: int = 0, level: str = "species", shops: list[int] | None = Query(None), size: str | None = None,
            scope: str = "period", types: list[str] | None = Query(None), group: list[int] | None = Query(None)):
    fl = flt.make(days, shops, size, scope, types, group)
    with pool.connection() as conn:
        f, p = flt.where(conn, fl, "obs")
        rows = conn.execute(
            f"WITH latest AS (SELECT l.shop_id, max(o.observed_at) AS t {BASE} {f} AND o.quantity IS NOT NULL GROUP BY 1)"
            f" SELECT {_key(level)} AS key, {_name(level)} AS name, sh.id AS shop_id, sh.name AS shop,"
            " percentile_cont(0.5) WITHIN GROUP (ORDER BY o.price_eur_net) AS price, sum(o.quantity) AS quantity,"
            " count(*) AS offers, max(o.observed_at) AS observed_at, string_agg(DISTINCT o.size_class, ', ') AS sizes"
            f" {BASE} {f} AND o.quantity IS NOT NULL AND o.price_eur_net IS NOT NULL"
            "  AND o.observed_at >= (SELECT t FROM latest WHERE latest.shop_id = l.shop_id) - interval '1 hour'"
            " GROUP BY 1, 2, 3, 4 ORDER BY 2",
            p + p,
        ).fetchall()
    return [dict(r, price=_num(r["price"])) for r in rows]


# ---------- breakdown: pie / bars / over time by grouping ----------

MEASURES = {
    "offers": "count(DISTINCT l.id)",
    "species": None,  # filled in per level
    "stock": "sum(o.quantity)",
    "value": "sum(o.quantity * o.price_eur_net)",
}


@router.get("/breakdown")
def breakdown(by: str = "top", measure: str = "offers", mode: str = "snapshot", split: bool = False,
              level: str = "species", days: int = 28, shops: list[int] | None = Query(None), size: str | None = None,
              scope: str = "period", types: list[str] | None = Query(None), group: list[int] | None = Query(None),
              top: int = 5):
    """by: 'top' (top species), 'shop', or a grouping id. mode: 'snapshot' (each offer's latest observation)
    or 'series' (per day). split: one panel per shop."""
    if measure not in MEASURES:
        raise HTTPException(422, "Unknown measure.")
    if mode not in ("snapshot", "series"):
        raise HTTPException(422, "Unknown mode.")
    fl = flt.make(days, shops, size, scope, types, group)
    m_sql = MEASURES[measure] or f"count(DISTINCT {_key(level)})"
    with pool.connection() as conn:
        snapshot_all_time = mode == "snapshot" and fl.scope != "period"
        f, p = flt.where(conn, fl, "obs", period=not snapshot_all_time)
        if mode == "snapshot":
            window = "" if snapshot_all_time or fl.days <= 0 else " WHERE observed_at >= now() - make_interval(days => %s)"
            f += (" AND o.id IN (SELECT DISTINCT ON (listing_id) id FROM observations"
                  f"{window} ORDER BY listing_id, observed_at DESC)")
            if window:
                p = p + [fl.days]
        grouping = None
        if by == "top":
            g_sql, n_sql = _key(level), _name(level)
        elif by == "shop":
            g_sql, n_sql = "l.shop_id::text", "sh.name"
        else:
            try:
                gid = int(by)
            except ValueError:
                raise HTTPException(422, "Unknown grouping.")
            grouping = flt.load_groupings(conn, [gid]).get(gid)
            if not grouping:
                raise HTTPException(404, "Grouping not found.")
            g_sql, n_sql = f"{flt.group_expr(grouping, 'o.price_eur_net')}::text", "NULL::text"
        cols = ["l.shop_id AS panel" if split else "NULL::integer AS panel",
                f"{DAY} AS day" if mode == "series" else "NULL::date AS day"]
        rows = conn.execute(
            f"SELECT {', '.join(cols)}, {g_sql} AS g, max({n_sql}) AS name, {m_sql} AS v"
            f" {BASE} {f} GROUP BY 1, 2, 3 ORDER BY 1, 2",
            p,
        ).fetchall()
        panels = []
        if split:
            panels = conn.execute(
                "SELECT id, name FROM shops WHERE id = ANY(%s) ORDER BY id", [list({r["panel"] for r in rows})]
            ).fetchall()

    totals: dict[str, float] = defaultdict(float)
    names: dict[str, str] = {}
    for r in rows:
        if r["g"] is not None:
            totals[r["g"]] += float(r["v"] or 0)
            names[r["g"]] = r["name"]
    if grouping:
        groups = [{"id": str(g["id"]), "name": g["label"]} for g in grouping["groups"]]
        keep = {g["id"] for g in groups}
    elif by == "shop":
        groups = [{"id": k, "name": names[k]} for k in sorted(totals, key=int)]
        keep = set(totals)
    else:
        ranked = sorted(totals, key=lambda k: (-totals[k], names[k]))[:max(1, min(top, 12))]
        groups = [{"id": k, "name": names[k]} for k in ranked]
        keep = set(ranked)

    folded: dict[tuple, float] = defaultdict(float)
    for r in rows:
        g = r["g"] if r["g"] in keep else "other"
        if r["v"] is not None:
            folded[(r["panel"], str(r["day"]) if r["day"] else None, g)] += float(r["v"])
    if any(k[2] == "other" for k in folded):
        groups.append({"id": "other", "name": "Other"})
    # A pie needs parts that add up: counting species across price ranges or shops counts some twice.
    additive = not (measure == "species" and (by == "shop" or (grouping and grouping["kind"] == "price")))
    return {
        "groups": groups, "panels": panels, "additive": additive, "measure": measure, "mode": mode,
        "rows": [{"panel": k[0], "day": k[1], "group": k[2], "value": round(v, 2)} for k, v in folded.items()],
    }


# ---------- events ----------

@router.get("/events")
def events(days: int = 28, shops: list[int] | None = Query(None), kind: str | None = None, limit: int = 500,
           size: str | None = None, scope: str = "period", types: list[str] | None = Query(None),
           group: list[int] | None = Query(None)):
    fl = flt.make(days, shops, size, scope, types, group)
    with pool.connection() as conn:
        ef, ep = flt.where(conn, fl, "event")
    if fl.types or fl.groups:
        ef += " AND a.listing_id IS NOT NULL"
    if kind:
        ef += " AND e.kind = %s"
        ep.append(kind)
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT e.id, e.kind, e.happened_at, e.old_value, e.new_value, l.name, l.url, sh.name AS shop,"
            f" {_key('species')} AS key, {_name('cultivar')} AS taxon"
            f" {EVENTS_BASE} {ef} ORDER BY e.happened_at DESC, e.id DESC LIMIT %s",
            ep + [min(limit, 2000)],
        ).fetchall()
    return rows


# ---------- watchlist ----------

class WatchIn(BaseModel):
    key: str


@router.get("/watchlist")
def watchlist():
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT w.id, w.species_id, w.cultivar_id,"
            " CASE WHEN w.species_id IS NOT NULL THEN 's' || w.species_id ELSE 'c' || w.cultivar_id END AS key,"
            " CASE WHEN w.species_id IS NOT NULL THEN 'Hoya ' || s.epithet"
            "      ELSE 'Hoya ' || coalesce(cs.epithet || ' ', '') || c.name END AS name"
            " FROM watchlist w LEFT JOIN species s ON s.id = w.species_id"
            " LEFT JOIN cultivars c ON c.id = w.cultivar_id LEFT JOIN species cs ON cs.id = c.species_id"
            " ORDER BY 5"
        ).fetchall()
    return rows


@router.post("/watchlist")
def watch(body: WatchIn):
    col = "species_id" if body.key.startswith("s") else "cultivar_id"
    _, tid = _taxon_filter(body.key)
    with pool.connection() as conn:
        conn.execute(f"INSERT INTO watchlist ({col}) VALUES (%s) ON CONFLICT DO NOTHING", (tid,))
    return {"watched": True}


@router.post("/watchlist/remove")
def unwatch(body: WatchIn):
    col = "species_id" if body.key.startswith("s") else "cultivar_id"
    _, tid = _taxon_filter(body.key)
    with pool.connection() as conn:
        conn.execute(f"DELETE FROM watchlist WHERE {col} = %s", (tid,))
    return {"watched": False}


def watchlist_events_since(conn, since) -> list[str]:
    """Lines for ntfy: events since `since` for watched species/cultivars."""
    rows = conn.execute(
        "SELECT DISTINCT e.id, e.kind, e.old_value, e.new_value, sh.name AS shop,"
        f" {TAXON_NAME} AS taxon"
        f" {EVENTS_BASE} AND e.happened_at >= %s AND EXISTS (SELECT 1 FROM watchlist w"
        "   WHERE w.species_id = a.species_id OR w.cultivar_id = a.cultivar_id)"
        " ORDER BY 6, 2",
        (since,),
    ).fetchall()
    labels = {"new": "new", "disappeared": "gone", "sold_out": "sold out", "back_in_stock": "back in stock",
              "restock": "restocked", "price_change": "price"}
    out = []
    for r in rows:
        change = f" {r['old_value']} → {r['new_value']}" if r["kind"] in ("restock", "price_change") else ""
        out.append(f"{r['taxon']}: {labels[r['kind']]}{change} ({r['shop']})")
    return out
