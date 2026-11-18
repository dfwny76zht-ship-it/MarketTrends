"""One filter set for every analysis endpoint: time, shops, size, type, groups and scope.

Builds the WHERE part for queries on observations (o), events (e) or listings (l). All of them must join
listings l, assignments a (confirmed) and cultivars c.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

SCOPES = ("available", "listed", "period", "ever")
TYPES = ("species", "form", "cultivar", "hybrid")

TYPE_SQL = (
    "(CASE WHEN a.cultivar_id IS NULL THEN 'species' WHEN c.kind IN ('form', 'subspecies') THEN 'form'"
    " ELSE c.kind END)"
)
LATEST_PRICE = "(SELECT x.price_eur_net FROM observations x WHERE x.listing_id = l.id ORDER BY x.observed_at DESC LIMIT 1)"
LATEST_SIZE = "(SELECT x.size_class FROM observations x WHERE x.listing_id = l.id ORDER BY x.observed_at DESC LIMIT 1)"
LATEST_AVAIL = "(SELECT x.availability FROM observations x WHERE x.listing_id = l.id ORDER BY x.observed_at DESC LIMIT 1)"


def _list(v):
    """Query(None) defaults arrive as objects when functions are called directly (tests): treat as empty."""
    return list(v) if isinstance(v, (list, tuple)) and v else None


@dataclass
class F:
    days: int = 28
    shops: list[int] | None = None
    size: str | None = None
    scope: str = "period"
    types: list[str] | None = None
    groups: list[int] | None = None


def make(days=28, shops=None, size=None, scope="period", types=None, group=None) -> F:
    scope = scope if isinstance(scope, str) else "period"
    if scope not in SCOPES:
        raise HTTPException(422, "Unknown scope.")
    types = _list(types)
    if types and any(t not in TYPES for t in types):
        raise HTTPException(422, "Unknown type.")
    return F(days=days if isinstance(days, int) else 28, shops=_list(shops),
             size=size if isinstance(size, str) and size else None, scope=scope, types=types,
             groups=[int(g) for g in _list(group) or []] or None)


def load_groupings(conn, ids: list[int] | None = None) -> dict[int, dict]:
    rows = conn.execute(
        "SELECT g.id, g.name, g.kind, g.position FROM groupings g"
        + (" WHERE g.id = ANY(%s)" if ids is not None else "") + " ORDER BY g.position, g.id",
        [ids] if ids is not None else None,
    ).fetchall()
    out = {r["id"]: dict(r, groups=[]) for r in rows}
    if out:
        for gg in conn.execute(
            "SELECT id, grouping_id, name, position, price_from, price_to, type_value FROM grouping_groups"
            " WHERE grouping_id = ANY(%s) ORDER BY position, id",
            [list(out)],
        ):
            out[gg["grouping_id"]]["groups"].append(dict(gg, label=group_label(dict(gg), out[gg["grouping_id"]]["kind"])))
    return out


def _eur(v) -> str:
    v = float(v)
    return f"€{v:g}" if v == int(v) else f"€{v:.2f}"


def group_label(g: dict, kind: str) -> str:
    if g.get("name"):
        return g["name"]
    if kind == "price":
        lo, hi = g.get("price_from"), g.get("price_to")
        if lo is None and hi is None:
            return "Any price"
        if lo is None:
            return f"Under {_eur(hi)}"
        if hi is None:
            return f"{_eur(lo)} and up"
        return f"{_eur(lo)} – {_eur(hi)}"
    return g.get("type_value") or "Group"


def group_expr(grouping: dict, price_sql: str) -> str:
    """SQL giving the group id a row falls into within one grouping, or NULL ("Other").
    Values come from the database (ids, numbers, fixed type names), so they are inlined safely."""
    kind, groups = grouping["kind"], grouping["groups"]
    if kind == "price":
        parts = []
        for g in groups:
            cond = []
            if g["price_from"] is not None:
                cond.append(f"{price_sql} >= {float(g['price_from'])!r}")
            if g["price_to"] is not None:
                cond.append(f"{price_sql} < {float(g['price_to'])!r}")
            parts.append(f"WHEN {' AND '.join(cond) or 'true'} THEN {int(g['id'])}")
        if not parts:
            return "NULL::integer"
        return f"(CASE WHEN {price_sql} IS NULL THEN NULL {' '.join(parts)} END)"
    if kind == "type":
        parts = [f"WHEN '{g['type_value']}' THEN {int(g['id'])}" for g in groups if g["type_value"] in TYPES]
        return f"(CASE {TYPE_SQL} {' '.join(parts)} END)" if parts else "NULL::integer"
    gid = int(grouping["id"])
    return (
        f"coalesce((SELECT m.group_id FROM grouping_members m WHERE m.grouping_id = {gid} AND m.cultivar_id = a.cultivar_id),"
        f" (SELECT m.group_id FROM grouping_members m WHERE m.grouping_id = {gid} AND m.species_id = a.species_id))"
    )


def where(conn, f: F, on: str = "obs", period: bool = True) -> tuple[str, list]:
    """on: 'obs' (observations o), 'event' (events e) or 'listing' (listings only, no time).
    period=False ignores the time filter (snapshots for the scopes 'available', 'listed', 'ever')."""
    sql, params = [], []
    time_col = {"obs": "o.observed_at", "event": "e.happened_at"}.get(on)
    price = "o.price_eur_net" if on == "obs" else LATEST_PRICE
    size = "o.size_class" if on == "obs" else LATEST_SIZE
    if period and time_col and f.days > 0:
        sql.append(f"{time_col} >= now() - make_interval(days => %s)")
        params.append(f.days)
    if f.shops:
        sql.append("l.shop_id = ANY(%s)")
        params.append(f.shops)
    if f.size:
        sql.append(f"{size} = %s")
        params.append(f.size)
    if f.scope == "available":
        sql.append(f"l.gone_since IS NULL AND {LATEST_AVAIL} IN ('available', 'low')")
    elif f.scope == "listed":
        sql.append("l.gone_since IS NULL")
    if f.types:
        sql.append(f"{TYPE_SQL} = ANY(%s)")
        params.append(f.types)
    if f.groups:
        owners = conn.execute(
            "SELECT grouping_id, array_agg(id) AS ids FROM grouping_groups WHERE id = ANY(%s) GROUP BY 1", [f.groups]
        ).fetchall()
        groupings = load_groupings(conn, [o["grouping_id"] for o in owners])
        for o in owners:
            sql.append(f"{group_expr(groupings[o['grouping_id']], price)} = ANY(%s)")
            params.append(o["ids"])
    return (" AND " + " AND ".join(sql)) if sql else "", params
