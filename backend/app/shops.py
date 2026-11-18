import datetime as dt
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb
from pydantic import BaseModel

from . import checks
from .auth import current_user
from .db import pool

router = APIRouter(prefix="/api/shops", dependencies=[Depends(current_user)])

ShopType = Literal["wholesaler", "importer", "retailer", "nursery"]
ShopStatus = Literal["suggested", "in_setup", "active", "paused", "not_allowed", "adapter_broken"]
PROVIDES_KEYS = ("price", "availability", "quantity", "pot_size")

LIST_SQL = """
SELECT s.*, r.started_at AS last_run_at, r.finished_at AS last_run_finished_at,
       r.result AS last_run_result, r.error AS last_run_error
FROM shops s
LEFT JOIN LATERAL (
    SELECT started_at, finished_at, result, error FROM runs
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
            "SELECT id, kind, started_at, finished_at, result, http_status, error FROM runs"
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


@router.patch("/{shop_id}")
def update_shop(shop_id: int, body: ShopPatch):
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and not (changes["name"] or "").strip():
        raise HTTPException(422, "Name can't be empty.")
    if changes.get("status") is None:
        changes.pop("status", None)
    if changes.get("access") is None:
        changes.pop("access", None)
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
    checks.start_in_background(shop_id)
    return {"started": True}
