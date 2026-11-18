"""Analysis queries against a throwaway Postgres: every endpoint runs and returns the expected shape."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.adapters import Offer


@pytest.fixture(scope="module")
def data(db):
    from app import collect, taxonomy

    taxonomy.seed()
    with db.connection() as conn:
        shop = conn.execute(
            "INSERT INTO shops (name, url, host, price_basis, vat_rate) VALUES ('Whole', 'https://w.example/', 'w.example', 'net', 9)"
            " RETURNING *"
        ).fetchone()

    def night(days_ago, qty, price):
        with db.connection() as conn:
            run_id = conn.execute("INSERT INTO runs (shop_id, kind) VALUES (%s, 'collect') RETURNING id",
                                  (shop["id"],)).fetchone()["id"]
        when = datetime.now(timezone.utc) - timedelta(days=days_ago)
        offers = [
            Offer(item_key="r1", name="Hoya carnosa 'Krimson Queen'", price=Decimal(price), currency="EUR",
                  availability="available", quantity=qty, pot_size="6 cm"),
            Offer(item_key="k1", name="Hoya pubicalyx", price=Decimal("3.10"), currency="EUR",
                  availability="available", quantity=50, pot_size="12 cm"),
        ]
        collect._store(shop, run_id, offers, True, now=when)

    night(3, 100, "2.00")
    night(2, 60, "2.00")
    night(1, 200, "2.20")
    taxonomy.match_pending()
    taxonomy.confirm_likely()
    with db.connection() as conn:
        rosita = conn.execute("SELECT id FROM cultivars WHERE name = 'Krimson Queen'").fetchone()["id"]
        kerrii = conn.execute("SELECT id FROM species WHERE epithet = 'pubicalyx'").fetchone()["id"]
    return {"shop": shop["id"], "rosita": f"c{rosita}", "kerrii": f"s{kerrii}"}


def test_overview(data):
    from app import analytics

    o = analytics.overview(days=28, shops=[data["shop"]])
    assert len(o["days"]) == 3
    assert o["events"]["restock"]
    assert o["events"]["price_change"]


def test_taxa_table(data):
    from app import analytics

    rows = analytics.taxa(days=28, level="cultivar", shops=[data["shop"]], size=None, keys=None)
    by_key = {r["key"]: r for r in rows}
    assert data["rosita"] in by_key and data["kerrii"] in by_key
    assert by_key[data["rosita"]]["quantity"] == 200
    assert by_key[data["rosita"]]["events"]["restock"] == 1
    rows = analytics.taxa(days=28, level="cultivar", shops=None, size=None, keys=[data["rosita"]])
    assert [r["key"] for r in rows] == [data["rosita"]]


def test_taxon_page(data):
    from app import analytics

    t = analytics.taxon(data["rosita"], days=0, shops=None, size=None)
    pts = t["series"][0]["points"]
    assert [p["quantity"] for p in pts] == [100, 60, 200]
    assert pts[1]["sold_est"] == 40 and pts[2]["restocked"] == 140
    assert t["title"] == "Hoya carnosa 'Krimson Queen'"
    assert t["sizes"] and t["offers"]


def test_scatter_and_events(data):
    from app import analytics

    pts = analytics.scatter(days=0, level="cultivar", shops=[data["shop"]], size=None)
    assert {p["key"] for p in pts} == {data["rosita"], data["kerrii"]}
    by_species = analytics.scatter(days=0, level="species", shops=[data["shop"]], size=None)
    assert data["rosita"] not in {p["key"] for p in by_species}  # counted under Hoya carnosa
    assert next(p for p in pts if p["key"] == data["rosita"])["quantity"] == 200
    ev = analytics.events(days=28, shops=[data["shop"]], kind="restock", limit=50)
    assert len(ev) == 1 and ev[0]["taxon"] == "Hoya carnosa 'Krimson Queen'"


def test_watchlist(data, db):
    from app import analytics

    analytics.watch(analytics.WatchIn(key=data["rosita"]))
    assert [w["key"] for w in analytics.watchlist()] == [data["rosita"]]
    with db.connection() as conn:
        lines = analytics.watchlist_events_since(conn, datetime.now(timezone.utc) - timedelta(days=30))
    assert any("Krimson Queen" in line and "restocked" in line for line in lines)
    analytics.unwatch(analytics.WatchIn(key=data["rosita"]))
    assert analytics.watchlist() == []
