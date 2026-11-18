"""Archived FlorAccess observations (Internet Archive captures) with plant, pot and look-alike group, for the
price-development chart. Runs inside the app container:

    docker compose exec -T app python - < investor/markus/history_export.py > archive.json
"""

import json
import sys

from app import filters as flt
from app.analytics import BASE, TAXON_NAME, _key
from app.db import pool

GROUPING = "Very Similar or closely related"

pool.open(wait=True)
with pool.connection() as conn:
    gid = conn.execute("SELECT id FROM groupings WHERE name = %s", (GROUPING,)).fetchone()["id"]
    grouping = flt.load_groupings(conn, [gid])[gid]
    expr = flt.group_expr(grouping, "o.price_eur_net", split_subgroups=True)
    rows = conn.execute(
        f"SELECT l.id AS lid, l.name, {TAXON_NAME} AS plant, {_key('cultivar')} AS plant_key, ({expr})::int AS grp,"
        " (o.observed_at AT TIME ZONE 'Europe/Berlin')::date::text AS day, o.price_eur_net AS net, o.price_basis,"
        " o.pot_size AS pot, o.plant_size AS height"
        f" {BASE} AND sh.name = 'FlorAccess' AND o.observed_at < '2026-11-01'"
        " ORDER BY day",
    ).fetchall()
json.dump([dict(r, net=float(r["net"]) if r["net"] is not None else None) for r in rows], sys.stdout, ensure_ascii=False)
