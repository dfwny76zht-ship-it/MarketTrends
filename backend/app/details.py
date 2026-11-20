"""Weekly product details (Sundays): every listed Hoya product page of shops with a details reader.
Same polite fetching as the night run (robots.txt, crawl delay, raw copies kept). A pot size found
here fills in the newest observation when the category page gave none, so size classes improve."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import checks, names
from .adapters import Blocked, Disallowed, FetchError
from .adapters import jtl_details
from .collect import _finish
from .db import pool
from .fetching import Fetcher

log = logging.getLogger("details")
READERS = {"jtl": jtl_details.parse_details}


def weekly() -> None:
    with pool.connection() as conn:
        shops = conn.execute(
            "SELECT * FROM shops WHERE adapter = ANY(%s) AND collector = 'hetzner' AND status = 'active'"
            " AND coalesce((adapter_config->>'details')::boolean, true)", (list(READERS),)).fetchall()
    with checks.run_lock:
        for shop in shops:
            try:
                details_one(shop)
            except Exception:
                log.exception("product details failed for %s", shop["name"])


def details_one(shop: dict) -> dict:
    read = READERS[shop["adapter"]]
    with pool.connection() as conn:
        run_id = conn.execute("INSERT INTO runs (shop_id, kind) VALUES (%s, 'details') RETURNING id", (shop["id"],)).fetchone()["id"]
        listings = conn.execute(
            "SELECT id, item_key, url FROM listings WHERE shop_id = %s AND gone_since IS NULL AND url IS NOT NULL ORDER BY id",
            (shop["id"],)).fetchall()
    ids = {l["item_key"]: l["id"] for l in listings}
    robots = checks.fetch_robots(shop["url"])
    if robots["result"] not in ("allowed", "no_robots"):
        _finish(run_id, robots["result"], robots.get("error"))
        return {"error": robots["result"]}
    fetcher = Fetcher(shop["id"], run_id, robots.get("parser"), robots.get("crawl_delay") or 0)
    now = datetime.now(timezone.utc)
    stored, errors = 0, []
    try:
        for l in listings:
            try:
                d = read(fetcher.get(l["url"]))
            except (FetchError, Disallowed) as exc:
                errors.append(str(exc))
                continue
            also = [ids[k] for k in d["also_bought"] if k in ids]
            with pool.connection() as conn:
                conn.execute(
                    "INSERT INTO listing_details (listing_id, run_id, observed_at, sku, pot_size, delivery, availability_text,"
                    " discount_pct, also_bought) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (l["id"], run_id, now, d["sku"], d["pot_size"], d["delivery"], d["availability_text"], d["discount_pct"], also))
                if d["pot_size"]:
                    conn.execute(
                        "UPDATE observations SET pot_size = %s, size_class = %s WHERE id = (SELECT id FROM observations"
                        " WHERE listing_id = %s ORDER BY observed_at DESC LIMIT 1) AND pot_size IS NULL",
                        (d["pot_size"], names.size_class(d["pot_size"]), l["id"]))
            stored += 1
    except Blocked as exc:
        _finish(run_id, "blocked", str(exc), offers=stored, pages=fetcher.requests)
        return {"blocked": str(exc)}
    finally:
        fetcher.close()
    _finish(run_id, "ok", "; ".join(errors[:3]) or None, offers=stored, pages=fetcher.requests,
            details={"errors": errors[:20], "listings": len(listings)})
    return {"stored": stored, "errors": len(errors)}
