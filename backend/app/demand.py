"""Demand signal: the shops' own "Bestseller" (and "Newest first") orders, read every night.
Position 1 of n becomes score 100, the last becomes 0, so shops of different size compare.
A plant (species, form or hybrid) takes the best score of its offers in that shop on that day."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .auth import current_user
from .db import pool

router = APIRouter(prefix="/api/demand", dependencies=[Depends(current_user)])

SQL = """
WITH r AS (
  SELECT lr.listing_id, (lr.observed_at AT TIME ZONE 'Europe/Berlin')::date AS day, lr.position, lr.list_size,
         round(100 * (1 - (lr.position - 1)::numeric / greatest(lr.list_size - 1, 1))) AS score
  FROM listing_ranks lr WHERE lr.list = %(list)s AND lr.observed_at > now() - make_interval(days => %(days)s)
), t AS (
  SELECT l.shop_id, a.species_id, a.cultivar_id, r.day, max(r.score) AS score, min(r.position) AS position,
         max(r.list_size) AS list_size, count(DISTINCT r.listing_id) AS offers
  FROM r JOIN listings l ON l.id = r.listing_id JOIN assignments a ON a.listing_id = l.id
  WHERE NOT a.ignored AND (a.species_id IS NOT NULL OR a.cultivar_id IS NOT NULL)
  GROUP BY 1, 2, 3, 4
), last AS (SELECT shop_id, max(day) AS day FROM t GROUP BY 1)
SELECT t.shop_id, sh.name AS shop, t.species_id, t.cultivar_id,
       coalesce(sp.epithet, csp.epithet) AS epithet, c.name AS cultivar, c.kind,
       max(t.score) FILTER (WHERE t.day = last.day) AS score_now,
       min(t.position) FILTER (WHERE t.day = last.day) AS position_now,
       max(t.list_size) FILTER (WHERE t.day = last.day) AS list_size,
       round(avg(t.score)) AS score_avg, count(*) AS days, max(t.offers) AS offers
FROM t JOIN last ON last.shop_id = t.shop_id JOIN shops sh ON sh.id = t.shop_id
LEFT JOIN species sp ON sp.id = t.species_id
LEFT JOIN cultivars c ON c.id = t.cultivar_id LEFT JOIN species csp ON csp.id = c.species_id
GROUP BY 1, 2, 3, 4, 5, 6, 7
"""


@router.get("")
def demand(list: str = Query("bestseller", pattern="^(bestseller|newest)$"), days: int = Query(30, ge=1, le=365)):
    with pool.connection() as conn:
        rows = conn.execute(SQL, {"list": list, "days": days}).fetchall()
        shops = conn.execute(
            "SELECT DISTINCT sh.id, sh.name, max(lr.observed_at) AS last, count(DISTINCT lr.run_id) AS runs"
            " FROM listing_ranks lr JOIN listings l ON l.id = lr.listing_id JOIN shops sh ON sh.id = l.shop_id"
            " WHERE lr.list = %s GROUP BY 1, 2 ORDER BY 2", (list,)).fetchall()
    plants: dict[str, dict] = {}
    for r in rows:
        key = f"c{r['cultivar_id']}" if r["cultivar_id"] else f"s{r['species_id']}"
        if r["kind"] == "hybrid":
            name = f"Hoya '{r['cultivar']}'"
        else:
            name = f"Hoya {r['epithet'] or 'sp.'}" + (f" '{r['cultivar']}'" if r["cultivar"] else "")
        p = plants.setdefault(key, {"key": key, "name": name, "kind": r["kind"] or "species", "shops": {}})
        p["shops"][r["shop_id"]] = {k: r[k] for k in ("score_now", "position_now", "list_size", "score_avg", "days", "offers")}
    out = sorted(plants.values(), key=lambda p: -max((s["score_avg"] or 0) for s in p["shops"].values()))
    return {"list": list, "days": days, "shops": shops, "plants": out}
