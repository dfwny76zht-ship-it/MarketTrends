"""Event derivation against a real, throwaway Postgres. Skipped unless TEST_DATABASE_URL is set.

On the server:  see deploy/test.sh
"""

import os
from decimal import Decimal

import pytest

if not os.environ.get("TEST_DATABASE_URL"):
    pytest.skip("TEST_DATABASE_URL not set", allow_module_level=True)

os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from app import collect, migrate  # noqa: E402
from app.adapters import Offer  # noqa: E402
from app.db import pool  # noqa: E402


@pytest.fixture(scope="module")
def shop():
    migrate.run()
    pool.open(wait=True)
    with pool.connection() as conn:
        s = conn.execute(
            "INSERT INTO shops (name, url, host, price_basis, vat_rate) VALUES ('Test', 'https://t.example/', 't.example', 'gross', 7)"
            " RETURNING *"
        ).fetchone()
    yield s
    pool.close()


def run(shop, offers, complete=True):
    with pool.connection() as conn:
        run_id = conn.execute(
            "INSERT INTO runs (shop_id, kind) VALUES (%s, 'collect') RETURNING id", (shop["id"],)
        ).fetchone()["id"]
    collect._store(shop, run_id, offers, complete)
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT l.item_key, e.kind, e.old_value, e.new_value FROM events e JOIN listings l ON l.id = e.listing_id"
            " WHERE e.run_id = %s ORDER BY l.item_key, e.kind",
            (run_id,),
        ).fetchall()
    return {(r["item_key"], r["kind"]): (r["old_value"], r["new_value"]) for r in rows}


def offer(key, price, availability, quantity=None):
    return Offer(item_key=key, name=f"Hoya {key}", price=Decimal(price), currency="EUR",
                 availability=availability, quantity=quantity)


def test_event_sequence(shop):
    # Night 1: starting point, no events.
    ev = run(shop, [offer("A", "10.00", "available"), offer("B", "5.00", "sold_out"), offer("C", "3.00", "available", 5)])
    assert ev == {}

    # Night 2: price change, back in stock, restock, new.
    ev = run(shop, [offer("A", "12.00", "available"), offer("B", "5.00", "available"),
                    offer("C", "3.00", "available", 8), offer("D", "7.00", "low")])
    assert ev == {
        ("A", "price_change"): ("10.00", "12.00"),
        ("B", "back_in_stock"): ("sold_out", "available"),
        ("C", "restock"): ("5", "8"),
        ("D", "new"): (None, "low"),
    }

    # Night 3: B gone, C sold out.
    ev = run(shop, [offer("A", "12.00", "available"), offer("C", "3.00", "sold_out", 0), offer("D", "7.00", "low")])
    assert ev == {("B", "disappeared"): (None, None), ("C", "sold_out"): ("available", "sold_out")}

    # Night 4: incomplete run must not mark anything as disappeared.
    ev = run(shop, [offer("A", "12.00", "available")], complete=False)
    assert ev == {}

    # Night 5: B is back and in stock.
    ev = run(shop, [offer("A", "12.00", "available"), offer("B", "5.00", "available"),
                    offer("C", "3.00", "sold_out", 0), offer("D", "7.00", "low")])
    assert ev == {("B", "back_in_stock"): ("gone", "available")}


def test_net_price(shop):
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT o.price_eur_net FROM observations o JOIN listings l ON l.id = o.listing_id"
            " WHERE l.shop_id = %s AND l.item_key = 'A' ORDER BY o.observed_at LIMIT 1",
            (shop["id"],),
        ).fetchone()
    assert row["price_eur_net"] == Decimal("9.3458")  # 10.00 / 1.07
