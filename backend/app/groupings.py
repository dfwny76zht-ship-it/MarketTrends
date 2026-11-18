"""Groupings API: price ranges, type, and manual groups of species / cultivars."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from psycopg import errors
from pydantic import BaseModel

from .analytics import _taxon_filter
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
    kind: str = "manual"


@router.post("")
def create(body: GroupingIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Give the grouping a name.")
    if body.kind not in ("price", "manual"):
        raise HTTPException(422, "New groupings are price ranges or manual.")
    with pool.connection() as conn:
        try:
            gid = conn.execute(
                "INSERT INTO groupings (name, kind, position) VALUES (%s, %s,"
                " (SELECT coalesce(max(position), -1) + 1 FROM groupings)) RETURNING id",
                (name, body.kind),
            ).fetchone()["id"]
        except errors.UniqueViolation:
            raise HTTPException(409, f"A grouping called {name} already exists.")
        if body.kind == "price":
            conn.execute(
                "INSERT INTO grouping_groups (grouping_id, position, price_from, price_to)"
                " VALUES (%s, 0, NULL, 20), (%s, 1, 20, NULL)",
                (gid, gid),
            )
        return _all(conn)


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
        if g and g["kind"] == "type":
            raise HTTPException(422, "The type grouping can't be deleted.")
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


class MemberIn(BaseModel):
    key: str
    group_id: int | None = None  # None removes the plant from this grouping


@router.post("/{grouping_id}/members")
def set_member(grouping_id: int, body: MemberIn):
    col = "species_id" if body.key.startswith("s") else "cultivar_id"
    _, tid = _taxon_filter(body.key)
    with pool.connection() as conn:
        g = conn.execute("SELECT kind FROM groupings WHERE id = %s", (grouping_id,)).fetchone()
        if not g or g["kind"] != "manual":
            raise HTTPException(422, "Plants are only added by hand to manual groupings.")
        if body.group_id is not None and not conn.execute(
            "SELECT 1 FROM grouping_groups WHERE id = %s AND grouping_id = %s", (body.group_id, grouping_id)
        ).fetchone():
            raise HTTPException(404, "Group not found.")
        conn.execute(f"DELETE FROM grouping_members WHERE grouping_id = %s AND {col} = %s", (grouping_id, tid))
        if body.group_id is not None:
            conn.execute(
                f"INSERT INTO grouping_members (grouping_id, group_id, {col}) VALUES (%s, %s, %s)",
                (grouping_id, body.group_id, tid),
            )
        return _all(conn)
