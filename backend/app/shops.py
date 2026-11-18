import datetime as dt
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from . import checks, collect
from .auth import current_user
from .db import pool

router = APIRouter(prefix="/api/shops", dependencies=[Depends(current_user)])

ShopType = Literal["wholesaler", "importer", "retailer", "nursery"]
ShopStatus = Literal["suggested", "in_setup", "active", "paused", "not_allowed", "adapter_broken"]
PROVIDES_KEYS = ("price", "availability", "quantity", "pot_size")

LIST_SQL = """
SELECT s.*,
       (SELECT count(*) FROM listings l WHERE l.shop_id = s.id AND l.gone_since IS NULL) AS offers_count,
       EXISTS (SELECT 1 FROM runs c WHERE c.shop_id = s.id AND c.kind = 'collect'
               AND (c.started_at AT TIME ZONE 'Europe/Berlin')::date = (now() AT TIME ZONE 'Europe/Berlin')::date)
           AS collected_today,
       r.kind AS last_run_kind, r.started_at AS last_run_at, r.finished_at AS last_run_finished_at,
       r.result AS last_run_result, r.error AS last_run_error
FROM shops s
LEFT JOIN LATERAL (
    SELECT kind, started_at, finished_at, result, error FROM runs
    WHERE shop_id = s.id ORDER BY started_at DESC LIMIT 1
) r ON true
"""


def normalize_url(raw: str) -> tuple[str, str]:
    raw = raw.strip()
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or "." not in host:
        raise HTTPException(422, "Not a valid shop URL.")
    url = urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or "/", parts.query, ""))
    return url, host.removeprefix("www.")


def _get(conn, shop_id: int) -> dict:
    shop = conn.execute(LIST_SQL + " WHERE s.id = %s", (shop_id,)).fetchone()
    if not shop:
        raise HTTPException(404, "Shop not found.")
    return shop


@router.get("")
def list_shops():
    with pool.connection() as conn:
        return conn.execute(LIST_SQL + " ORDER BY lower(s.name)").fetchall()


class ShopCreate(BaseModel):
    url: str
    note: str = ""


@router.post("", status_code=201)
def create_shop(body: ShopCreate):
    url, host = normalize_url(body.url)
    with pool.connection() as conn:
        existing = conn.execute("SELECT name FROM shops WHERE host = %s", (host,)).fetchone()
        if existing:
            raise HTTPException(409, f"Already in the list: {existing['name']}")
        shop_id = conn.execute(
            "INSERT INTO shops (name, url, host, note) VALUES (%s, %s, %s, %s) RETURNING id",
            (host, url, host, body.note.strip()),
        ).fetchone()["id"]
        return _get(conn, shop_id)


@router.get("/{shop_id}")
def get_shop(shop_id: int):
    with pool.connection() as conn:
        shop = _get(conn, shop_id)
        runs = conn.execute(
            "SELECT id, kind, started_at, finished_at, result, http_status, error, offers_found, events_found,"
            " pages, details FROM runs"
            " WHERE shop_id = %s ORDER BY started_at DESC LIMIT 20",
            (shop_id,),
        ).fetchall()
    return {"shop": shop, "runs": runs}


class ShopPatch(BaseModel):
    name: str | None = None
    url: str | None = None
    type: ShopType | None = None
    status: ShopStatus | None = None
    country: str | None = None
    currency: str | None = None
    price_basis: Literal["net", "gross"] | None = None
    access: Literal["public", "account"] | None = None
    provides: dict[str, bool] | None = None
    note: str | None = None
    terms_checked_at: dt.date | None = None
    vat_rate: float | None = None


@router.patch("/{shop_id}")
def update_shop(shop_id: int, body: ShopPatch):
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and not (changes["name"] or "").strip():
        raise HTTPException(422, "Name can't be empty.")
    if changes.get("status") is None:
        changes.pop("status", None)
    for key in ("access", "vat_rate"):
        if key in changes and changes[key] is None:
            changes.pop(key)
    if "vat_rate" in changes and not 0 <= changes["vat_rate"] <= 30:
        raise HTTPException(422, "VAT rate must be between 0 and 30.")
    if "url" in changes:
        changes["url"], changes["host"] = normalize_url(changes["url"] or "")
    for key in ("country", "currency"):
        if key in changes:
            changes[key] = (changes[key] or "").strip().upper() or None
    if "note" in changes:
        changes["note"] = (changes["note"] or "").strip()
    if "provides" in changes:
        changes["provides"] = Jsonb({k: bool(v) for k, v in (changes["provides"] or {}).items() if k in PROVIDES_KEYS})
    if not changes:
        raise HTTPException(422, "Nothing to change.")

    cols = ", ".join(f"{col} = %s" for col in changes)
    with pool.connection() as conn:
        _get(conn, shop_id)
        try:
            conn.execute(
                f"UPDATE shops SET {cols}, updated_at = now() WHERE id = %s",
                (*changes.values(), shop_id),
            )
        except UniqueViolation:
            raise HTTPException(409, "Another shop already uses this website.")
        return _get(conn, shop_id)


@router.post("/{shop_id}/check", status_code=202)
def check_now(shop_id: int):
    with pool.connection() as conn:
        _get(conn, shop_id)
    checks.check_in_background(shop_id)
    return {"started": True}


@router.post("/{shop_id}/run", status_code=202)
def run_now(shop_id: int):
    with pool.connection() as conn:
        shop = _get(conn, shop_id)
    if not shop["adapter"]:
        raise HTTPException(409, "This shop has no adapter yet.")
    if shop["collected_today"]:
        raise HTTPException(409, "Already collected today.")
    collect.collect_in_background(shop_id)
    return {"started": True}


OFFERS_SQL = """
SELECT l.id, l.item_no, l.name, l.url, l.image_url, l.first_seen, l.last_seen, l.gone_since,
       o.price, o.currency, o.price_basis, o.price_eur_net, o.availability, o.availability_text,
       o.quantity, o.pot_size, o.plant_size, o.tier_prices, o.observed_at
FROM listings l
LEFT JOIN LATERAL (
    SELECT * FROM observations WHERE listing_id = l.id ORDER BY observed_at DESC LIMIT 1
) o ON true
WHERE l.shop_id = %s
ORDER BY l.gone_since IS NOT NULL, lower(l.name)
"""


@router.get("/{shop_id}/offers")
def list_offers(shop_id: int):
    with pool.connection() as conn:
        _get(conn, shop_id)
        return conn.execute(OFFERS_SQL, (shop_id,)).fetchall()
