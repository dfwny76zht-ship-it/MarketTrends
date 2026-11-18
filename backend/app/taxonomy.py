"""Species list, match suggestions, confirmations and merges."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from psycopg.types.json import Jsonb

from . import names
from .db import pool

log = logging.getLogger("taxonomy")
DATA = Path(__file__).parent / "data"
CONF_ORDER = {"sure": 0, "likely": 1, "unsure": 2}


# ---------- seeding ----------

def seed() -> None:
    """Fills the species list once: Kew checklist, then the LIMS names on top."""
    with pool.connection() as conn:
        if conn.execute("SELECT EXISTS (SELECT 1 FROM species) AS e").fetchone()["e"]:
            return
        kew = json.loads((DATA / "kew_hoya.json").read_text(encoding="utf-8"))
        for epithet in kew["species"]:
            conn.execute("INSERT INTO species (epithet, source) VALUES (%s, 'kew')", (epithet,))
        ids = {r["epithet"]: r["id"] for r in conn.execute("SELECT id, epithet FROM species")}
        for syn, accepted in kew["synonyms"].items():
            if accepted in ids:
                conn.execute(
                    "INSERT INTO species_synonyms (epithet, species_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (syn, ids[accepted]),
                )
        for inf in kew["infraspecific"]:
            if inf["species"] in ids:
                conn.execute(
                    "INSERT INTO cultivars (species_id, name, kind, source) VALUES (%s, %s, 'subspecies', 'kew')"
                    " ON CONFLICT DO NOTHING",
                    (ids[inf["species"]], f"{inf['rank']} {inf['name']}"),
                )
        for entry in json.loads((DATA / "lims_seed.json").read_text(encoding="utf-8")):
            sid = None
            if entry.get("species"):
                sid = ids.get(entry["species"])
                if not sid:
                    sid = conn.execute(
                        "INSERT INTO species (epithet, source) VALUES (%s, 'lims') RETURNING id", (entry["species"],)
                    ).fetchone()["id"]
                    ids[entry["species"]] = sid
                conn.execute("UPDATE species SET in_lims = true WHERE id = %s", (sid,))
                if entry.get("note") and not entry.get("cultivar"):
                    conn.execute("UPDATE species SET notes = %s WHERE id = %s", (entry["note"], sid))
            if entry.get("cultivar"):
                conn.execute(
                    "INSERT INTO cultivars (species_id, name, kind, source, notes) VALUES (%s, %s, %s, 'lims', %s)"
                    " ON CONFLICT DO NOTHING",
                    (sid if entry["kind"] != "hybrid" else None, entry["cultivar"], entry["kind"], entry.get("note", "")),
                )
        log.warning("species list seeded: %s species", len(ids))


def backfill_size_classes() -> None:
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT o.id, o.pot_size, l.name FROM observations o JOIN listings l ON l.id = o.listing_id"
            " WHERE o.size_class IS NULL"
        ).fetchall()
        for r in rows:
            conn.execute(
                "UPDATE observations SET size_class = %s WHERE id = %s", (names.size_class(r["pot_size"], r["name"]), r["id"])
            )


# ---------- suggestions ----------

def _lookups(conn) -> tuple[dict[str, int], dict[str, str]]:
    epithet_ids = {r["epithet"]: r["id"] for r in conn.execute("SELECT id, epithet FROM species")}
    synonyms = {
        r["epithet"]: r["accepted"]
        for r in conn.execute(
            "SELECT y.epithet, s.epithet AS accepted FROM species_synonyms y JOIN species s ON s.id = y.species_id"
        )
    }
    return epithet_ids, synonyms


def _find_cultivar(conn, species_id: int | None, name: str) -> dict | None:
    if species_id:
        row = conn.execute(
            "SELECT id, species_id FROM cultivars WHERE species_id = %s AND lower(name) = lower(%s)", (species_id, name)
        ).fetchone()
        if row:
            return row
    rows = conn.execute(
        "SELECT id, species_id FROM cultivars WHERE lower(name) = lower(%s) AND kind <> 'form'"
        + (" AND species_id IS NULL" if species_id else ""),
        (name,),
    ).fetchall()
    return rows[0] if len(rows) == 1 else None


def suggest(conn, name: str, epithet_ids: dict[str, int], synonyms: dict[str, str]) -> dict:
    p = names.parse(name, set(epithet_ids), synonyms)
    reasons = []
    sid = epithet_ids.get(p.epithet) if p.epithet and p.epithet_match != "unknown" else None
    suggestion = {"species": p.epithet, "cultivar": p.cultivar, "kind": p.kind}

    if p.epithet_match == "exact":
        reasons.append("species name found")
    elif p.epithet_match == "synonym":
        reasons.append(f"'{p.epithet_written}' is an older name for {p.epithet} (Kew)")
    elif p.epithet_match == "fuzzy":
        reasons.append(f"'{p.epithet_written}' read as {p.epithet} (spelling)")
    elif p.epithet_match == "unknown":
        reasons.append(f"'{p.epithet}' is not in the species list")
        suggestion["new_species"] = True

    cultivar = _find_cultivar(conn, sid, p.cultivar) if p.cultivar else None
    if cultivar:
        reasons.append(f"known {p.kind or 'cultivar'}")
        if not sid and cultivar["species_id"]:
            sid = cultivar["species_id"]
    elif p.cultivar:
        reasons.append(f"new {p.kind}: {p.cultivar}")
        suggestion["new_cultivar"] = True

    unsure_qual = p.qualifiers & {"aff", "cf"}
    if unsure_qual:
        reasons.append("marked " + "/".join(f"{q}." for q in sorted(unsure_qual)) + " (only similar)")

    if unsure_qual or p.epithet_match in ("fuzzy", "unknown"):
        confidence = "unsure"
    elif p.epithet_match in ("exact", "synonym"):
        quoted = p.kind == "cultivar" and f"'{p.cultivar}'".lower() in names.name_key(name)
        confidence = "likely" if (not p.cultivar or cultivar or p.kind in ("form", "subspecies") or quoted) else "unsure"
    elif cultivar:
        confidence = "likely"
    else:
        confidence = "unsure"
        if not p.cultivar:
            reasons.append("no species found")

    return {
        "species_id": sid,
        "cultivar_id": cultivar["id"] if cultivar else None,
        "suggestion": suggestion,
        "confidence": confidence,
        "reason": "; ".join(reasons),
        "collection_no": p.collection_no,
    }


_UPSERT = """
INSERT INTO assignments (listing_id, species_id, cultivar_id, suggestion, confirmed, ignored, method, confidence, reason, updated_at)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
ON CONFLICT (listing_id) DO UPDATE SET species_id = EXCLUDED.species_id, cultivar_id = EXCLUDED.cultivar_id,
    suggestion = EXCLUDED.suggestion, confirmed = EXCLUDED.confirmed, ignored = EXCLUDED.ignored,
    method = EXCLUDED.method, confidence = EXCLUDED.confidence, reason = EXCLUDED.reason, updated_at = now()
"""


def match_pending(shop_id: int | None = None) -> int:
    """(Re)computes suggestions for every listing without a confirmed match. Returns how many were handled."""
    with pool.connection() as conn:
        epithet_ids, synonyms = _lookups(conn)
        aliases = {r["key"]: r for r in conn.execute("SELECT key, species_id, cultivar_id, ignored FROM aliases")}
        rows = conn.execute(
            "SELECT l.id, l.name FROM listings l LEFT JOIN assignments a ON a.listing_id = l.id"
            " WHERE (a.listing_id IS NULL OR NOT a.confirmed)" + (" AND l.shop_id = %s" if shop_id else ""),
            (shop_id,) if shop_id else None,
        ).fetchall()
        for r in rows:
            key = names.name_key(r["name"])
            s = suggest(conn, r["name"], epithet_ids, synonyms)
            conn.execute(
                "UPDATE listings SET name_key = %s, collection_no = %s WHERE id = %s", (key, s["collection_no"], r["id"])
            )
            alias = aliases.get(key)
            if alias:
                conn.execute(_UPSERT, (r["id"], alias["species_id"], alias["cultivar_id"], Jsonb({}), True,
                                       alias["ignored"], "alias", "sure", "confirmed spelling"))
                continue
            method = "name"
            if s["collection_no"] and s["confidence"] != "likely":
                prior = conn.execute(
                    "SELECT a.species_id, a.cultivar_id FROM assignments a JOIN listings l ON l.id = a.listing_id"
                    " WHERE l.collection_no = %s AND a.confirmed AND NOT a.ignored LIMIT 1",
                    (s["collection_no"],),
                ).fetchone()
                if prior:
                    s.update(species_id=prior["species_id"], cultivar_id=prior["cultivar_id"], confidence="likely",
                             reason=f"same collection number {s['collection_no']} as a confirmed offer",
                             suggestion={})
                    method = "collection_no"
            conn.execute(_UPSERT, (r["id"], s["species_id"], s["cultivar_id"], Jsonb(s["suggestion"]), False, False,
                                   method, s["confidence"], s["reason"]))
    return len(rows)


def reassess_localities() -> dict:
    """Logged cultivars / hybrids named after a place or a collection number become forms;
    open suggestions are worked out again with the same rule."""
    with pool.connection() as conn:
        rows = conn.execute("SELECT id, name FROM cultivars WHERE kind IN ('cultivar', 'hybrid')").fetchall()
        ids = [r["id"] for r in rows if names.is_locality(r["name"])]
        if ids:
            conn.execute("UPDATE cultivars SET kind = 'form' WHERE id = ANY(%s)", (ids,))
        changed = [r["name"] for r in rows if r["id"] in ids]
    return {"to_form": changed, "open_rechecked": match_pending()}


# ---------- confirming ----------

def _create_species(conn, epithet: str) -> int:
    epithet = epithet.strip().lower()
    if epithet.startswith("hoya "):
        epithet = epithet[5:].strip()
    if not epithet:
        raise ValueError("Species name is empty.")
    return conn.execute(
        "INSERT INTO species (epithet, source) VALUES (%s, 'manual')"
        " ON CONFLICT (genus, epithet) DO UPDATE SET epithet = EXCLUDED.epithet RETURNING id",
        (epithet,),
    ).fetchone()["id"]


def _create_cultivar(conn, species_id: int | None, name: str, kind: str) -> int:
    name = name.strip().strip("'").strip()
    if not name:
        raise ValueError("Cultivar name is empty.")
    sid = None if kind == "hybrid" else species_id
    return conn.execute(
        "INSERT INTO cultivars (species_id, name, kind) VALUES (%s, %s, %s)"
        " ON CONFLICT ((coalesce(species_id, 0)), (lower(name))) DO UPDATE SET name = cultivars.name RETURNING id",
        (sid, name, kind),
    ).fetchone()["id"]


def confirm(key: str, species_id: int | None = None, new_species: str | None = None,
            cultivar_id: int | None = None, new_cultivar: str | None = None, kind: str | None = None,
            ignore: bool = False) -> int:
    """Saves what a spelling means and applies it to every listing with that spelling. Returns listings updated."""
    with pool.connection() as conn:
        sid = cid = None
        if not ignore:
            sid = _create_species(conn, new_species) if new_species else species_id
            if new_cultivar and kind == "hybrid":
                sid = None
            if new_cultivar:
                cid = _create_cultivar(conn, sid, new_cultivar, kind or ("cultivar" if sid else "hybrid"))
            else:
                cid = cultivar_id
            if cid and not sid:
                row = conn.execute("SELECT species_id FROM cultivars WHERE id = %s", (cid,)).fetchone()
                sid = row["species_id"] if row else None
            if not sid and not cid:
                raise ValueError("Choose a species or a cultivar, or mark it as not a single plant.")
        conn.execute(
            "INSERT INTO aliases (key, species_id, cultivar_id, ignored) VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (key) DO UPDATE SET species_id = EXCLUDED.species_id, cultivar_id = EXCLUDED.cultivar_id,"
            " ignored = EXCLUDED.ignored, created_at = now()",
            (key, sid, cid, ignore),
        )
        n = conn.execute(
            "UPDATE assignments a SET species_id = %s, cultivar_id = %s, confirmed = true, ignored = %s,"
            " method = 'alias', confidence = 'sure', reason = 'confirmed spelling', suggestion = '{}', updated_at = now()"
            " FROM listings l WHERE l.id = a.listing_id AND l.name_key = %s",
            (sid, cid, ignore, key),
        ).rowcount
    return n


def confirm_likely() -> int:
    with pool.connection() as conn:
        groups = conn.execute(
            "SELECT DISTINCT ON (l.name_key) l.name_key AS key, a.species_id, a.cultivar_id, a.suggestion"
            " FROM assignments a JOIN listings l ON l.id = a.listing_id"
            " WHERE NOT a.confirmed AND a.confidence = 'likely' AND l.name_key IS NOT NULL ORDER BY l.name_key"
        ).fetchall()
    done = 0
    for g in groups:
        s = g["suggestion"] or {}
        try:
            confirm(
                g["key"],
                species_id=g["species_id"],
                cultivar_id=g["cultivar_id"],
                new_cultivar=s.get("cultivar") if s.get("new_cultivar") and not g["cultivar_id"] else None,
                kind=s.get("kind"),
            )
            done += 1
        except ValueError:
            continue
    match_pending()
    return done


# ---------- merging ----------

def _move_members(conn, col: str, source_id: int, target_id: int) -> None:
    """Manual group memberships follow a merge; where the target already has a group in that grouping, it wins."""
    conn.execute(
        f"UPDATE grouping_members m SET {col} = %s WHERE m.{col} = %s AND NOT EXISTS"
        f" (SELECT 1 FROM grouping_members t WHERE t.grouping_id = m.grouping_id AND t.{col} = %s)",
        (target_id, source_id, target_id),
    )


def _convert_members(conn, from_col: str, from_id: int, to_col: str, to_id: int) -> None:
    """A species became a cultivar (or back): its manual group memberships go along."""
    conn.execute(
        f"INSERT INTO grouping_members (grouping_id, group_id, {to_col})"
        f" SELECT grouping_id, group_id, %s FROM grouping_members WHERE {from_col} = %s ON CONFLICT DO NOTHING",
        (to_id, from_id),
    )
    conn.execute(f"DELETE FROM grouping_members WHERE {from_col} = %s", (from_id,))


def merge_cultivars(source_id: int, target_id: int) -> None:
    if source_id == target_id:
        raise ValueError("Can't merge a cultivar into itself.")
    with pool.connection() as conn:
        target = conn.execute("SELECT id, species_id FROM cultivars WHERE id = %s", (target_id,)).fetchone()
        if not target:
            raise ValueError("Target cultivar not found.")
        for table in ("aliases", "assignments"):
            conn.execute(
                f"UPDATE {table} SET cultivar_id = %s, species_id = coalesce(%s, species_id) WHERE cultivar_id = %s",
                (target_id, target["species_id"], source_id),
            )
        _move_members(conn, "cultivar_id", source_id, target_id)
        conn.execute("DELETE FROM cultivars WHERE id = %s", (source_id,))


def merge_species(source_id: int, target_id: int) -> None:
    if source_id == target_id:
        raise ValueError("Can't merge a species into itself.")
    with pool.connection() as conn:
        src = conn.execute("SELECT * FROM species WHERE id = %s", (source_id,)).fetchone()
        if not src or not conn.execute("SELECT 1 FROM species WHERE id = %s", (target_id,)).fetchone():
            raise ValueError("Species not found.")
        for c in conn.execute("SELECT id, name FROM cultivars WHERE species_id = %s", (source_id,)).fetchall():
            twin = conn.execute(
                "SELECT id FROM cultivars WHERE species_id = %s AND lower(name) = lower(%s)", (target_id, c["name"])
            ).fetchone()
            if twin:
                for table in ("aliases", "assignments"):
                    conn.execute(f"UPDATE {table} SET cultivar_id = %s WHERE cultivar_id = %s", (twin["id"], c["id"]))
                _move_members(conn, "cultivar_id", c["id"], twin["id"])
                conn.execute("DELETE FROM cultivars WHERE id = %s", (c["id"],))
            else:
                conn.execute("UPDATE cultivars SET species_id = %s WHERE id = %s", (target_id, c["id"]))
        for table in ("aliases", "assignments", "species_synonyms"):
            conn.execute(f"UPDATE {table} SET species_id = %s WHERE species_id = %s", (target_id, source_id))
        _move_members(conn, "species_id", source_id, target_id)
        conn.execute(
            "INSERT INTO species_synonyms (epithet, species_id) VALUES (%s, %s) ON CONFLICT (epithet) DO UPDATE"
            " SET species_id = EXCLUDED.species_id",
            (src["epithet"], target_id),
        )
        conn.execute(
            "UPDATE species SET in_lims = in_lims OR %s, notes = trim(notes || ' ' || %s) WHERE id = %s",
            (src["in_lims"], src["notes"], target_id),
        )
        conn.execute("DELETE FROM species WHERE id = %s", (source_id,))
    match_pending()


# ---------- changing type later ----------

def _move_cultivars(conn, from_sid: int, to_sid: int | None) -> None:
    """Moves the cultivars of one species to another (or to no species); same-named ones are merged."""
    for c in conn.execute("SELECT id, name FROM cultivars WHERE species_id = %s", (from_sid,)).fetchall():
        twin = conn.execute(
            "SELECT id FROM cultivars WHERE coalesce(species_id, 0) = coalesce(%s, 0) AND lower(name) = lower(%s)",
            (to_sid, c["name"]),
        ).fetchone()
        if twin:
            for table in ("aliases", "assignments"):
                conn.execute(f"UPDATE {table} SET cultivar_id = %s WHERE cultivar_id = %s", (twin["id"], c["id"]))
            conn.execute("DELETE FROM cultivars WHERE id = %s", (c["id"],))
        else:
            conn.execute(
                "UPDATE cultivars SET species_id = %s, kind = CASE WHEN %s IS NULL AND kind <> 'hybrid' THEN 'hybrid' ELSE kind END"
                " WHERE id = %s",
                (to_sid, to_sid, c["id"]),
            )


def species_to_cultivar(species_id: int, kind: str, parent_epithet: str | None = None, name: str | None = None) -> int:
    """A species turns out to be a cultivar/form/subspecies (of `parent_epithet`) or a hybrid.
    All its offers and spellings move along. Returns the new cultivar id."""
    if kind not in ("cultivar", "form", "subspecies", "hybrid"):
        raise ValueError("Unknown kind.")
    with pool.connection() as conn:
        sp = conn.execute("SELECT * FROM species WHERE id = %s", (species_id,)).fetchone()
        if not sp:
            raise ValueError("Species not found.")
        parent = None
        if kind != "hybrid":
            if not parent_epithet:
                raise ValueError("Choose the species it belongs to, or make it a hybrid.")
            e = parent_epithet.strip().lower().removeprefix("hoya ").strip()
            row = conn.execute("SELECT id FROM species WHERE epithet = %s", (e,)).fetchone()
            if not row:
                raise ValueError(f"Hoya {e} is not in the species list.")
            parent = row["id"]
            if parent == species_id:
                raise ValueError("A species can't belong to itself.")
        cid = _create_cultivar(conn, parent, name or sp["epithet"].capitalize(), kind)
        _move_cultivars(conn, species_id, parent)
        for table in ("aliases", "assignments"):
            conn.execute(f"UPDATE {table} SET cultivar_id = %s WHERE species_id = %s AND cultivar_id IS NULL",
                         (cid, species_id))
            conn.execute(f"UPDATE {table} SET species_id = %s WHERE species_id = %s", (parent, species_id))
        _convert_members(conn, "species_id", species_id, "cultivar_id", cid)
        conn.execute("DELETE FROM species_synonyms WHERE species_id = %s", (species_id,))
        note = f"Was listed as species Hoya {sp['epithet']}." + (f" {sp['notes']}" if sp["notes"] else "")
        conn.execute("UPDATE cultivars SET notes = trim(notes || ' ' || %s) WHERE id = %s", (note, cid))
        conn.execute("DELETE FROM species WHERE id = %s", (species_id,))
    match_pending()
    return cid


def cultivar_to_species(cultivar_id: int, epithet: str | None = None) -> int:
    """A cultivar/form/hybrid turns out to be a species of its own. Returns the species id."""
    with pool.connection() as conn:
        c = conn.execute("SELECT * FROM cultivars WHERE id = %s", (cultivar_id,)).fetchone()
        if not c:
            raise ValueError("Cultivar not found.")
        sid = _create_species(conn, epithet or c["name"])
        for table in ("aliases", "assignments"):
            conn.execute(f"UPDATE {table} SET species_id = %s, cultivar_id = NULL WHERE cultivar_id = %s",
                         (sid, cultivar_id))
        _convert_members(conn, "cultivar_id", cultivar_id, "species_id", sid)
        if c["notes"]:
            conn.execute("UPDATE species SET notes = trim(notes || ' ' || %s) WHERE id = %s", (c["notes"], sid))
        conn.execute("DELETE FROM cultivars WHERE id = %s", (cultivar_id,))
    match_pending()
    return sid


def unconfirm(key: str) -> int:
    """Forgets a confirmed spelling; its offers go back to "To assign"."""
    with pool.connection() as conn:
        conn.execute("DELETE FROM aliases WHERE key = %s", (key,))
        n = conn.execute(
            "UPDATE assignments a SET confirmed = false, ignored = false FROM listings l"
            " WHERE l.id = a.listing_id AND l.name_key = %s",
            (key,),
        ).rowcount
    match_pending()
    return n
