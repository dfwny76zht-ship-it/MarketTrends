"""API for species, cultivars and the "To assign" list."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation
from pydantic import BaseModel

from . import taxonomy
from .auth import current_user
from .db import pool

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])

Kind = Literal["cultivar", "form", "subspecies", "hybrid"]


def _bad(exc: Exception):
    raise HTTPException(422, str(exc))


# ---------- To assign ----------

GROUPS_SQL = """
WITH open AS (
    SELECT l.name_key AS key, l.name, l.gone_since, s.name AS shop, a.*
    FROM assignments a
    JOIN listings l ON l.id = a.listing_id
    JOIN shops s ON s.id = l.shop_id
    WHERE NOT a.confirmed AND l.name_key IS NOT NULL
)
SELECT o.key,
       (array_agg(DISTINCT o.name))[1:3] AS names,
       array_agg(DISTINCT o.shop) AS shops,
       count(*) AS listings,
       bool_or(o.gone_since IS NULL) AS on_offer,
       f.species_id, f.cultivar_id, f.suggestion, f.confidence, f.reason, f.method,
       sp.epithet AS species, c.name AS cultivar, c.kind AS cultivar_kind
FROM open o
JOIN LATERAL (
    SELECT * FROM open o2 WHERE o2.key = o.key
    ORDER BY CASE o2.confidence WHEN 'sure' THEN 0 WHEN 'likely' THEN 1 ELSE 2 END LIMIT 1
) f ON true
LEFT JOIN species sp ON sp.id = f.species_id
LEFT JOIN cultivars c ON c.id = f.cultivar_id
GROUP BY o.key, f.species_id, f.cultivar_id, f.suggestion, f.confidence, f.reason, f.method, sp.epithet, c.name, c.kind
ORDER BY CASE f.confidence WHEN 'likely' THEN 0 ELSE 1 END, o.key
"""


@router.get("/assign")
def open_groups():
    with pool.connection() as conn:
        groups = conn.execute(GROUPS_SQL).fetchall()
        done = conn.execute(
            "SELECT count(*) FILTER (WHERE a.confirmed) AS confirmed, count(*) AS total FROM assignments a"
        ).fetchone()
    return {"groups": groups, "confirmed": done["confirmed"], "total": done["total"]}


class ConfirmIn(BaseModel):
    key: str
    species_id: int | None = None
    new_species: str | None = None
    cultivar_id: int | None = None
    new_cultivar: str | None = None
    kind: Kind | None = None
    ignore: bool = False


@router.post("/assign/confirm")
def confirm(body: ConfirmIn):
    try:
        n = taxonomy.confirm(**body.model_dump())
    except ValueError as exc:
        _bad(exc)
    return {"updated": n}


@router.post("/assign/confirm-likely")
def confirm_likely():
    return {"confirmed": taxonomy.confirm_likely()}


@router.post("/assign/rematch")
def rematch():
    return {"checked": taxonomy.match_pending()}


# ---------- search ----------

@router.get("/taxa/search")
def search(q: str = ""):
    q = q.strip().lower().removeprefix("hoya ").strip()
    if not q:
        return {"species": [], "cultivars": []}
    with pool.connection() as conn:
        species = conn.execute(
            "SELECT id, epithet, in_lims FROM species WHERE epithet LIKE %s"
            " ORDER BY (epithet = %s) DESC, in_lims DESC, epithet LIMIT 12",
            (q + "%", q),
        ).fetchall()
        cultivars = conn.execute(
            "SELECT c.id, c.name, c.kind, c.species_id, s.epithet AS species FROM cultivars c"
            " LEFT JOIN species s ON s.id = c.species_id"
            " WHERE lower(c.name) LIKE %s OR s.epithet LIKE %s"
            " ORDER BY (lower(c.name) = %s) DESC, c.name LIMIT 15",
            ("%" + q + "%", q + "%", q),
        ).fetchall()
    return {"species": species, "cultivars": cultivars}


# ---------- species ----------

SPECIES_SQL = """
SELECT s.id, s.epithet, s.source, s.in_lims, s.notes,
       count(DISTINCT l.id) FILTER (WHERE l.gone_since IS NULL) AS offers,
       count(DISTINCT l.shop_id) FILTER (WHERE l.gone_since IS NULL) AS shops,
       (SELECT count(*) FROM cultivars c WHERE c.species_id = s.id AND c.kind <> 'subspecies') AS cultivars
FROM species s
LEFT JOIN assignments a ON a.species_id = s.id AND a.confirmed AND NOT a.ignored
LEFT JOIN listings l ON l.id = a.listing_id
GROUP BY s.id
"""

HYBRIDS_SQL = """
SELECT c.id, c.name, c.kind, c.parents, c.notes,
       count(DISTINCT l.id) FILTER (WHERE l.gone_since IS NULL) AS offers,
       count(DISTINCT l.shop_id) FILTER (WHERE l.gone_since IS NULL) AS shops
FROM cultivars c
LEFT JOIN assignments a ON a.cultivar_id = c.id AND a.confirmed
LEFT JOIN listings l ON l.id = a.listing_id
WHERE c.species_id IS NULL
GROUP BY c.id ORDER BY lower(c.name)
"""


@router.get("/species")
def list_species():
    with pool.connection() as conn:
        species = conn.execute(SPECIES_SQL + " ORDER BY s.epithet").fetchall()
        hybrids = conn.execute(HYBRIDS_SQL).fetchall()
    return {"species": species, "hybrids": hybrids}


CULTIVARS_SQL = """
SELECT c.id, c.name, c.kind, c.parents, c.notes, c.source,
       count(DISTINCT l.id) FILTER (WHERE l.gone_since IS NULL) AS offers,
       count(DISTINCT l.shop_id) FILTER (WHERE l.gone_since IS NULL) AS shops
FROM cultivars c
LEFT JOIN assignments a ON a.cultivar_id = c.id AND a.confirmed
LEFT JOIN listings l ON l.id = a.listing_id
WHERE {where}
GROUP BY c.id ORDER BY (count(l.id) > 0) DESC, c.kind = 'subspecies', lower(c.name)
"""

OFFERS_SQL = """
SELECT l.id, l.name, l.url, l.gone_since, sh.name AS shop, c.name AS cultivar, c.kind AS cultivar_kind,
       o.price, o.currency, o.price_basis, o.availability, o.quantity, o.size_class
FROM assignments a
JOIN listings l ON l.id = a.listing_id
JOIN shops sh ON sh.id = l.shop_id
LEFT JOIN cultivars c ON c.id = a.cultivar_id
LEFT JOIN LATERAL (SELECT * FROM observations WHERE listing_id = l.id ORDER BY observed_at DESC LIMIT 1) o ON true
WHERE a.confirmed AND NOT a.ignored AND {where}
ORDER BY l.gone_since IS NOT NULL, sh.name, l.name
"""


@router.get("/species/{species_id}")
def species_detail(species_id: int):
    with pool.connection() as conn:
        sp = conn.execute("SELECT * FROM species WHERE id = %s", (species_id,)).fetchone()
        if not sp:
            raise HTTPException(404, "Species not found.")
        cultivars = conn.execute(CULTIVARS_SQL.format(where="c.species_id = %s"), (species_id,)).fetchall()
        offers = conn.execute(OFFERS_SQL.format(where="a.species_id = %s"), (species_id,)).fetchall()
        synonyms = [r["epithet"] for r in conn.execute(
            "SELECT epithet FROM species_synonyms WHERE species_id = %s ORDER BY epithet", (species_id,))]
        spellings = conn.execute(
            "SELECT key, cultivar_id FROM aliases WHERE species_id = %s ORDER BY key", (species_id,)
        ).fetchall()
    return {"species": sp, "cultivars": cultivars, "offers": offers, "synonyms": synonyms, "spellings": spellings}


@router.get("/cultivars/{cultivar_id}")
def cultivar_detail(cultivar_id: int):
    with pool.connection() as conn:
        c = conn.execute(
            "SELECT c.*, s.epithet AS species FROM cultivars c LEFT JOIN species s ON s.id = c.species_id WHERE c.id = %s",
            (cultivar_id,),
        ).fetchone()
        if not c:
            raise HTTPException(404, "Cultivar not found.")
        offers = conn.execute(OFFERS_SQL.format(where="a.cultivar_id = %s"), (cultivar_id,)).fetchall()
        spellings = conn.execute("SELECT key FROM aliases WHERE cultivar_id = %s ORDER BY key", (cultivar_id,)).fetchall()
    return {"cultivar": c, "offers": offers, "spellings": spellings}


class SpeciesPatch(BaseModel):
    epithet: str | None = None
    notes: str | None = None


@router.patch("/species/{species_id}")
def update_species(species_id: int, body: SpeciesPatch):
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    if "epithet" in changes:
        changes["epithet"] = changes["epithet"].strip().lower().removeprefix("hoya ").strip()
        if not changes["epithet"]:
            raise HTTPException(422, "Name can't be empty.")
    if not changes:
        raise HTTPException(422, "Nothing to change.")
    with pool.connection() as conn:
        try:
            conn.execute(
                f"UPDATE species SET {', '.join(f'{k} = %s' for k in changes)} WHERE id = %s",
                (*changes.values(), species_id),
            )
        except UniqueViolation:
            raise HTTPException(409, "That species already exists. Use merge instead.")
    return species_detail(species_id)


class CultivarIn(BaseModel):
    name: str
    kind: Kind
    species_id: int | None = None
    parents: str = ""
    notes: str = ""


@router.patch("/cultivars/{cultivar_id}")
def update_cultivar(cultivar_id: int, body: CultivarIn):
    name = body.name.strip().strip("'").strip()
    if not name:
        raise HTTPException(422, "Name can't be empty.")
    sid = None if body.kind == "hybrid" else body.species_id
    with pool.connection() as conn:
        try:
            conn.execute(
                "UPDATE cultivars SET name = %s, kind = %s, species_id = %s, parents = %s, notes = %s WHERE id = %s",
                (name, body.kind, sid, body.parents.strip(), body.notes.strip(), cultivar_id),
            )
            conn.execute(
                "UPDATE assignments SET species_id = %s WHERE cultivar_id = %s AND confirmed", (sid, cultivar_id)
            )
            conn.execute("UPDATE aliases SET species_id = %s WHERE cultivar_id = %s", (sid, cultivar_id))
        except UniqueViolation:
            raise HTTPException(409, "That cultivar already exists here. Use merge instead.")
    return cultivar_detail(cultivar_id)


class MergeIn(BaseModel):
    into: int


@router.post("/species/{species_id}/merge")
def merge_species(species_id: int, body: MergeIn):
    try:
        taxonomy.merge_species(species_id, body.into)
    except ValueError as exc:
        _bad(exc)
    return {"ok": True}


@router.post("/cultivars/{cultivar_id}/merge")
def merge_cultivar(cultivar_id: int, body: MergeIn):
    try:
        taxonomy.merge_cultivars(cultivar_id, body.into)
    except ValueError as exc:
        _bad(exc)
    return {"ok": True}


class ConvertIn(BaseModel):
    kind: Kind
    parent: str | None = None
    name: str | None = None


@router.post("/species/{species_id}/convert")
def convert_species(species_id: int, body: ConvertIn):
    try:
        cid = taxonomy.species_to_cultivar(species_id, body.kind, body.parent, body.name)
    except ValueError as exc:
        _bad(exc)
    return {"cultivar_id": cid}


class ToSpeciesIn(BaseModel):
    epithet: str | None = None


@router.post("/cultivars/{cultivar_id}/to-species")
def convert_cultivar(cultivar_id: int, body: ToSpeciesIn):
    try:
        sid = taxonomy.cultivar_to_species(cultivar_id, body.epithet)
    except ValueError as exc:
        _bad(exc)
    return {"species_id": sid}


class KeyIn(BaseModel):
    key: str


@router.post("/assign/unconfirm")
def unconfirm(body: KeyIn):
    return {"updated": taxonomy.unconfirm(body.key)}
