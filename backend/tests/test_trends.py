"""Trend score, rankings and wholesale signals against a throwaway Postgres."""

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
            "INSERT INTO shops (name, url, host, type, price_basis) VALUES ('Grower', 'https://g.example/', 'g.example',"
            " 'wholesaler', 'net') RETURNING *"
        ).fetchone()
    now = datetime.now(timezone.utc)
    # 14 weeks ago to now, one night per week: 'linearis' restocks every week in the last 4 weeks only,
    # 'retusa' is steady, price of retusa drops in the last week.
    for i, weeks_ago in enumerate(range(14, -1, -1)):
        with db.connection() as conn:
            run_id = conn.execute("INSERT INTO runs (shop_id, kind) VALUES (%s, 'collect') RETURNING id",
                                  (shop["id"],)).fetchone()["id"]
        lin_qty = 100 + (50 * (4 - weeks_ago) if weeks_ago < 4 else 0)
        offers = [
            Offer(item_key="lin", name="Hoya linearis", price=Decimal("4.00"), currency="EUR",
                  availability="available", quantity=lin_qty),
            Offer(item_key="ret", name="Hoya retusa", price=Decimal("3.00" if weeks_ago else "2.40"), currency="EUR",
                  availability="available", quantity=500 - i * 10),
        ]
        collect._store(shop, run_id, offers, True, now=now - timedelta(weeks=weeks_ago, hours=1))
    taxonomy.match_pending()
    taxonomy.confirm_likely()
    with db.connection() as conn:
        lin = conn.execute("SELECT id FROM species WHERE epithet = 'linearis'").fetchone()["id"]
        ret = conn.execute("SELECT id FROM species WHERE epithet = 'retusa'").fetchone()["id"]
    return {"shop": shop["id"], "lin": f"s{lin}", "ret": f"s{ret}"}


def test_scores(data):
    from app import trends

    s = trends.scores(level="species", shops=[data["shop"]], kinds=None)
    by = {t["key"]: t for t in s["taxa"]}
    lin = by[data["lin"]]
    assert lin["recent"] == 4 and lin["before"] == 0 and lin["label"] == "new activity"
    assert len(s["weeks"]) == 16


def test_rankings(data):
    from app import trends

    r = trends.rankings(days=35, level="species", shops=[data["shop"]], limit=10)
    assert r["restocked"][0]["key"] == data["lin"]
    down = {m["key"]: m for m in r["price_down"]}
    assert down[data["ret"]]["change_pct"] == -20.0
    assert any(w["key"] == data["lin"] for w in r["widest"])


def test_wholesale(data):
    from app import trends

    w = trends.wholesale(days=0, level="species", limit=10)
    top = {t["key"]: t for t in w["top"]}
    assert top[data["lin"]]["incoming"] == 200
    assert top[data["ret"]]["sold"] == 140
    assert w["weekly"]


def test_weekly_summary_runs(data, monkeypatch):
    from app import ntfy, trends

    sent = []
    monkeypatch.setattr(ntfy, "send", lambda title, msg, **kw: sent.append((title, msg)))
    trends.weekly_summary()
    assert sent and "events in the last 7 days" in sent[0][1]
