"""Groupings API: price ranges, type, and manual groups of species / cultivars."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import errors
from pydantic import BaseModel

from . import filters as flt
from .analytics import BASE, TAXON_NAME, _key, _taxon_filter
from .auth import current_user
from .db import pool
from .filters import TYPES, load_groupings

router = APIRouter(prefix="/api/groupings", dependencies=[Depends(current_user)])


def _all(conn) -> list[dict]:
    out = list(load_groupings(conn).values())
    members = conn.execute(
        "SELECT m.grouping_id, m.group_id,"
        " CASE WHEN m.species_id IS NOT NULL THEN 's' || m.species_id ELSE 'c' || m.cultivar_id END AS key,"
        " CASE WHEN m.species_id IS NOT NULL THEN 'Hoya ' || s.epithet"
        "      WHEN c.kind IN ('cultivar', 'hybrid') THEN 'Hoya ' || coalesce(cs.epithet || ' ', '') || '''' || c.name || ''''"
        "      ELSE 'Hoya ' || coalesce(cs.epithet || ' ', '') || c.name END AS name"
        " FROM grouping_members m LEFT JOIN species s ON s.id = m.species_id"
        " LEFT JOIN cultivars c ON c.id = m.cultivar_id LEFT JOIN species cs ON cs.id = c.species_id ORDER BY 4"
    ).fetchall()
    by_group: dict[int, list] = {}
    for m in members:
        by_group.setdefault(m["group_id"], []).append({"key": m["key"], "name": m["name"]})
    for g in out:
        for gg in g["groups"]:
            gg["members"] = by_group.get(gg["id"], [])
            for k in ("price_from", "price_to"):
                gg[k] = float(gg[k]) if gg[k] is not None else None
    return out


@router.get("")
def list_groupings():
    with pool.connection() as conn:
        return _all(conn)


class GroupingIn(BaseModel):
    name: str
    start: str = "empty"  # empty | species | type | copy:<grouping id>


def seed_plan(conn, start: str) -> list[dict]:
    """Groups and members for a starting point, without saving anything: [{name, members: [key]}]."""
    if start == "empty":
        return []
    if start == "species":
        rows = conn.execute(
            "SELECT DISTINCT s.id, s.epithet FROM assignments a JOIN species s ON s.id = a.species_id"
            " WHERE a.confirmed AND NOT a.ignored ORDER BY s.epithet"
        ).fetchall()
        plan = [{"name": f"Hoya {r['epithet']}", "members": [f"s{r['id']}"]} for r in rows]
        hybrids = [f"c{r['id']}" for r in conn.execute(
            "SELECT DISTINCT c.id FROM assignments a JOIN cultivars c ON c.id = a.cultivar_id"
            " WHERE a.confirmed AND NOT a.ignored AND c.species_id IS NULL ORDER BY 1"
        )]
        if hybrids:
            plan.append({"name": "Hybrids", "members": hybrids})
        return plan
    if start == "type":
        species = [f"s{r['species_id']}" for r in conn.execute(
            "SELECT DISTINCT a.species_id FROM assignments a WHERE a.confirmed AND NOT a.ignored"
            " AND a.cultivar_id IS NULL AND a.species_id IS NOT NULL ORDER BY 1"
        )]
        by_kind: dict[str, list] = {"form": [], "cultivar": [], "hybrid": []}
        for r in conn.execute(
            "SELECT DISTINCT c.id, c.kind FROM assignments a JOIN cultivars c ON c.id = a.cultivar_id"
            " WHERE a.confirmed AND NOT a.ignored ORDER BY 1"
        ):
            by_kind["form" if r["kind"] in ("form", "subspecies") else r["kind"]].append(f"c{r['id']}")
        return [{"name": "Species", "members": species}, {"name": "Forms / subspecies", "members": by_kind["form"]},
                {"name": "Cultivars", "members": by_kind["cultivar"]}, {"name": "Hybrids", "members": by_kind["hybrid"]}]
    if start.startswith("copy:"):
        try:
            source = int(start[5:])
        except ValueError:
            raise HTTPException(422, "Unknown starting point.")
        src = conn.execute("SELECT kind FROM groupings WHERE id = %s", (source,)).fetchone()
        if not src:
            raise HTTPException(404, "Grouping to copy not found.")
        if src["kind"] == "type":
            return seed_plan(conn, "type")
        if src["kind"] != "manual":
            raise HTTPException(422, "Price ranges can't be copied into plant groups.")
        plan = []
        for g in conn.execute("SELECT id, name FROM grouping_groups WHERE grouping_id = %s ORDER BY position, id",
                              (source,)).fetchall():
            plan.append({"name": g["name"], "members": [r["key"] for r in conn.execute(
                "SELECT CASE WHEN species_id IS NOT NULL THEN 's' || species_id ELSE 'c' || cultivar_id END AS key"
                " FROM grouping_members WHERE group_id = %s ORDER BY 1", (g["id"],))]})
        return plan
    raise HTTPException(422, "Unknown starting point.")


def _apply_plan(conn, gid: int, plan: list[dict]) -> None:
    for pos, g in enumerate(plan):
        group_id = conn.execute(
            "INSERT INTO grouping_groups (grouping_id, name, position) VALUES (%s, %s, %s) RETURNING id",
            (gid, g["name"], pos),
        ).fetchone()["id"]
        for key in g["members"]:
            _set_one(conn, gid, key, group_id)


@router.get("/seed")
def seed(start: str):
    with pool.connection() as conn:
        return seed_plan(conn, start)


@router.post("")
def create(body: GroupingIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Give the grouping a name.")
    with pool.connection() as conn:
        with conn.transaction():
            try:
                gid = conn.execute(
                    "INSERT INTO groupings (name, kind, position) VALUES (%s, 'manual',"
                    " (SELECT coalesce(max(position), -1) + 1 FROM groupings)) RETURNING id",
                    (name,),
                ).fetchone()["id"]
            except errors.UniqueViolation:
                raise HTTPException(409, f"A grouping called {name} already exists.")
            _apply_plan(conn, gid, seed_plan(conn, body.start))
        return {"id": gid, "groupings": _all(conn)}


class RenameIn(BaseModel):
    name: str


@router.patch("/{grouping_id}")
def rename(grouping_id: int, body: RenameIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Give the grouping a name.")
    with pool.connection() as conn:
        try:
            if not conn.execute("UPDATE groupings SET name = %s WHERE id = %s RETURNING id", (name, grouping_id)).fetchone():
                raise HTTPException(404, "Grouping not found.")
        except errors.UniqueViolation:
            raise HTTPException(409, f"A grouping called {name} already exists.")
        return _all(conn)


@router.delete("/{grouping_id}")
def delete(grouping_id: int):
    with pool.connection() as conn:
        g = conn.execute("SELECT kind FROM groupings WHERE id = %s", (grouping_id,)).fetchone()
        if g and g["kind"] in ("type", "price"):
            raise HTTPException(422, "Price and Type are built in and can't be deleted.")
        conn.execute("DELETE FROM groupings WHERE id = %s", (grouping_id,))
        return _all(conn)


class GroupIn(BaseModel):
    id: int | None = None
    name: str = ""
    price_from: Decimal | None = None
    price_to: Decimal | None = None
    type_value: str | None = None


class GroupsIn(BaseModel):
    groups: list[GroupIn]


def check_price_groups(groups: list[GroupIn]) -> None:
    """Sections in order, each from < to, no gaps or overlaps. Only the first may be open below,
    only the last open above."""
    if not groups:
        raise HTTPException(422, "Keep at least one section.")
    for i, g in enumerate(groups):
        if g.price_from is not None and g.price_from < 0 or g.price_to is not None and g.price_to < 0:
            raise HTTPException(422, "Prices can't be negative.")
        if g.price_from is None and i > 0:
            raise HTTPException(422, "Only the first section can start without a lower price.")
        if g.price_to is None and i < len(groups) - 1:
            raise HTTPException(422, "Only the last section can be open upwards.")
        if g.price_from is not None and g.price_to is not None and g.price_from >= g.price_to:
            raise HTTPException(422, f"Section {i + 1}: 'from' must be below 'to'.")
        if i > 0:
            prev = groups[i - 1].price_to
            if g.price_from < prev:
                raise HTTPException(422, f"Sections {i} and {i + 1} overlap.")
            if g.price_from > prev:
                raise HTTPException(422, f"Gap between sections {i} and {i + 1}.")


@router.put("/{grouping_id}/groups")
def set_groups(grouping_id: int, body: GroupsIn):
    with pool.connection() as conn:
        grouping = conn.execute("SELECT * FROM groupings WHERE id = %s", (grouping_id,)).fetchone()
        if not grouping:
            raise HTTPException(404, "Grouping not found.")
        kind = grouping["kind"]
        if kind == "price":
            check_price_groups(body.groups)
        elif kind == "type":
            values = sorted(g.type_value or "" for g in body.groups)
            if values != sorted(TYPES):
                raise HTTPException(422, "The type grouping keeps its four groups; only names can change.")
        elif any(not g.name.strip() for g in body.groups):
            raise HTTPException(422, "Every group needs a name.")
        existing = {r["id"] for r in conn.execute("SELECT id FROM grouping_groups WHERE grouping_id = %s", (grouping_id,))}
        keep = set()
        for pos, g in enumerate(body.groups):
            vals = (g.name.strip(), pos, g.price_from if kind == "price" else None,
                    g.price_to if kind == "price" else None, g.type_value if kind == "type" else None)
            if g.id in existing:
                conn.execute(
                    "UPDATE grouping_groups SET name = %s, position = %s, price_from = %s, price_to = %s, type_value = %s"
                    " WHERE id = %s",
                    vals + (g.id,),
                )
                keep.add(g.id)
            else:
                conn.execute(
                    "INSERT INTO grouping_groups (name, position, price_from, price_to, type_value, grouping_id)"
                    " VALUES (%s, %s, %s, %s, %s, %s)",
                    vals + (grouping_id,),
                )
        gone = list(existing - keep)
        if gone:
            conn.execute("DELETE FROM grouping_groups WHERE id = ANY(%s)", (gone,))
        return _all(conn)


class BulkIn(BaseModel):
    keys: list[str]
    group_id: int | None = None


@router.post("/{grouping_id}/members/bulk")
def set_members(grouping_id: int, body: BulkIn):
    """Move several plants into one group (or out of the grouping) at once."""
    with pool.connection() as conn:
        with conn.transaction():
            _check_manual(conn, grouping_id, body.group_id)
            for key in body.keys:
                _set_one(conn, grouping_id, key, body.group_id)
        return _all(conn)


def _check_manual(conn, grouping_id: int, group_id: int | None) -> None:
    g = conn.execute("SELECT kind FROM groupings WHERE id = %s", (grouping_id,)).fetchone()
    if not g or g["kind"] != "manual":
        raise HTTPException(422, "Plants are only added by hand to your own groupings.")
    if group_id is not None and not conn.execute(
        "SELECT 1 FROM grouping_groups WHERE id = %s AND grouping_id = %s", (group_id, grouping_id)
    ).fetchone():
        raise HTTPException(404, "Group not found.")


def _set_one(conn, grouping_id: int, key: str, group_id: int | None) -> None:
    col = "species_id" if key.startswith("s") else "cultivar_id"
    _, tid = _taxon_filter(key)
    conn.execute(f"DELETE FROM grouping_members WHERE grouping_id = %s AND {col} = %s", (grouping_id, tid))
    if group_id is not None:
        conn.execute(
            f"INSERT INTO grouping_members (grouping_id, group_id, {col}) VALUES (%s, %s, %s)",
            (grouping_id, group_id, tid),
        )


class MemberIn(BaseModel):
    key: str
    group_id: int | None = None  # None removes the plant from this grouping


@router.post("/{grouping_id}/members")
def set_member(grouping_id: int, body: MemberIn):
    with pool.connection() as conn:
        with conn.transaction():
            _check_manual(conn, grouping_id, body.group_id)
            _set_one(conn, grouping_id, body.key, body.group_id)
        return _all(conn)


@router.get("/plants")
def all_plants(days: int = 28, shops: list[int] | None = Query(None), size: str | None = None,
               scope: str = "period", types: list[str] | None = Query(None)):
    """Every plant with offers under the filters, for the editor (memberships come from the grouping list)."""
    return _plants(None, days, shops, size, scope, types)


@router.get("/{grouping_id}/plants")
def plants(grouping_id: int, days: int = 28, shops: list[int] | None = Query(None), size: str | None = None,
           scope: str = "period", types: list[str] | None = Query(None)):
    return _plants(grouping_id, days, shops, size, scope, types)


def _plants(grouping_id: int | None, days: int = 28, shops: list[int] | None = Query(None), size: str | None = None,
           scope: str = "period", types: list[str] | None = Query(None)):
    """Every plant (species-level offers and each cultivar / form / hybrid) with its own membership, its offers
    under the current filters (each offer's latest observation), median net price and a photo."""
    fl = flt.make(days, shops, size, scope, types, None)
    key, name = _key("cultivar"), TAXON_NAME
    with pool.connection() as conn:
        if grouping_id is not None and not conn.execute(
                "SELECT 1 FROM groupings WHERE id = %s AND kind = 'manual'", (grouping_id,)).fetchone():
            raise HTTPException(404, "Grouping not found.")
        all_time = fl.scope != "period"
        f, p = flt.where(conn, fl, "obs", period=not all_time)
        window = "" if all_time or fl.days <= 0 else " WHERE observed_at >= now() - make_interval(days => %s)"
        f += f" AND o.id IN (SELECT DISTINCT ON (listing_id) id FROM observations{window} ORDER BY listing_id, observed_at DESC)"
        if window:
            p = p + [fl.days]
        rows = conn.execute(
            f"SELECT {key} AS key, {name} AS name, {flt.TYPE_SQL} AS type,"
            " CASE WHEN a.species_id IS NOT NULL THEN 's' || a.species_id END AS species_key,"
            " count(DISTINCT l.id) AS offers, count(DISTINCT l.shop_id) AS shops,"
            " count(DISTINCT l.shop_id) FILTER (WHERE o.availability IN ('available', 'low')) AS in_stock_shops,"
            " percentile_cont(0.5) WITHIN GROUP (ORDER BY o.price_eur_net) AS price, sum(o.quantity) AS stock,"
            " max(l.id) FILTER (WHERE EXISTS (SELECT 1 FROM images i WHERE i.listing_id = l.id AND i.status = 'ok')) AS photo"
            f" {BASE} {f} GROUP BY 1, 2, 3, 4 ORDER BY 2",
            p,
        ).fetchall()
        members = {
            r["key"]: r["group_id"]
            for r in conn.execute(
                "SELECT CASE WHEN species_id IS NOT NULL THEN 's' || species_id ELSE 'c' || cultivar_id END AS key, group_id"
                " FROM grouping_members WHERE grouping_id = %s",
                (grouping_id,),
            )
        }
    out = []
    for r in rows:
        own = members.get(r["key"])
        out.append(dict(r, price=float(r["price"]) if r["price"] is not None else None, own=own,
                        species_group=members.get(r["species_key"]) if r["key"].startswith("c") else None))
    return out
