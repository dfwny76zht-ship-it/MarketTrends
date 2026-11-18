"""Frozen snapshot for the investor page: every confirmed offer of FlorAccess and Ben's Jungle (latest
observation on the snapshot day), with its group in the look-alike grouping. Runs inside the app container:

    docker compose exec -T app python - < investor/markus/export.py > data.json
"""

import json
import sys

from app import filters as flt
from app.analytics import BASE, TAXON_NAME, _key
from app.db import pool

SHOPS = {"FlorAccess": "Großhandel (NL, nur B2B)", "Ben's Jungle": "Einzelhandel (DE)"}
GROUPING = "Very Similar or closely related"
DAY = "2026-11-18"

pool.open(wait=True)
with pool.connection() as conn:
    shops = conn.execute("SELECT id, name, url FROM shops WHERE name = ANY(%s) ORDER BY id", [list(SHOPS)]).fetchall()
    gid = conn.execute("SELECT id FROM groupings WHERE name = %s", (GROUPING,)).fetchone()["id"]
    grouping = flt.load_groupings(conn, [gid])[gid]
    expr = flt.group_expr(grouping, "o.price_eur_net", split_subgroups=True)
    rows = conn.execute(
        f"SELECT l.id, sh.name AS shop, l.name, l.url, {_key('cultivar')} AS plant_key, {TAXON_NAME} AS plant,"
        f" {_key('species')} AS species_key,"
        f" {flt.TYPE_SQL} AS type, ({expr})::int AS grp,"
        " o.price, o.currency, o.price_basis, o.price_eur_net, o.quantity, o.availability, o.size_class,"
        " o.pot_size, o.plant_size"
        f" {BASE} AND sh.id = ANY(%s)"
        " AND o.id IN (SELECT DISTINCT ON (listing_id) id FROM observations"
        "   WHERE (observed_at AT TIME ZONE 'Europe/Berlin')::date <= %s::date ORDER BY listing_id, observed_at DESC)"
        " AND (o.observed_at AT TIME ZONE 'Europe/Berlin')::date = %s::date"
        " ORDER BY 2, 6, o.price_eur_net",
        [[s["id"] for s in shops], DAY, DAY],
    ).fetchall()

groups = {g["id"]: {"label": g["label"], "parent": None} for g in grouping["groups"]}
groups.update({g["id"]: {"label": g["label"], "parent": g["parent_id"]} for g in grouping["subgroups"]})
num = lambda v: float(v) if v is not None else None
out = {
    "day": DAY,
    "shops": [{"name": s["name"], "role": SHOPS[s["name"]]} for s in shops],
    "groups": [{"id": k, **v} for k, v in groups.items()],
    "offers": [
        {
            "shop": r["shop"], "name": r["name"], "url": r["url"], "plant": r["plant"], "plant_key": r["plant_key"], "species_key": r["species_key"],
            "type": r["type"], "group": r["grp"], "price": num(r["price"]), "currency": r["currency"],
            "basis": r["price_basis"], "net": num(r["price_eur_net"]), "stock": r["quantity"],
            "availability": r["availability"], "size": r["size_class"], "pot": r["pot_size"], "height": r["plant_size"],
        }
        for r in rows
    ],
}
json.dump(out, sys.stdout, ensure_ascii=False)
