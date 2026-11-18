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
    assert o["avg_price"][-1] is not None and len(o["avg_price"]) == 3


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


def test_groupings_and_breakdown(data):
    from fastapi import HTTPException

    from app import analytics, groupings

    gs = {g["name"]: g for g in groupings.list_groupings()}
    price, typ = gs["Price"], gs["Type"]
    under10 = price["groups"][0]
    assert under10["label"] == "Under €10"

    # Each offer by its own latest price: both test offers (2.20 and 3.10) are under 10.
    b = analytics.breakdown(by=str(price["id"]), measure="offers", mode="snapshot", shops=[data["shop"]], days=28)
    assert {r["group"]: r["value"] for r in b["rows"]} == {str(under10["id"]): 2}
    assert b["additive"]
    assert not analytics.breakdown(by=str(price["id"]), measure="species", shops=[data["shop"]])["additive"]

    # Re-cut the price sections: under 3 / 3 and up.
    G = groupings.GroupIn
    after = groupings.set_groups(price["id"], groupings.GroupsIn(groups=[
        G(id=under10["id"], price_from=None, price_to=3), G(price_from=3, price_to=None)]))
    price = next(g for g in after if g["id"] == price["id"])
    low, high = price["groups"]
    b = analytics.breakdown(by=str(price["id"]), measure="stock", shops=[data["shop"]])
    assert {r["group"]: r["value"] for r in b["rows"]} == {str(low["id"]): 200, str(high["id"]): 50}
    for bad in ([G(price_from=None, price_to=5), G(price_from=6, price_to=None)],      # gap
                [G(price_from=None, price_to=5), G(price_from=4, price_to=None)],      # overlap
                [G(price_from=None, price_to=None), G(price_from=4, price_to=None)]):  # open in the middle
        with pytest.raises(HTTPException):
            groupings.set_groups(price["id"], groupings.GroupsIn(groups=bad))

    # Type grouping and type filter.
    cult = next(g for g in typ["groups"] if g["type_value"] == "cultivar")
    b = analytics.breakdown(by=str(typ["id"]), measure="offers", shops=[data["shop"]])
    assert {r["group"]: r["value"] for r in b["rows"]}[str(cult["id"])] == 1
    rows = analytics.taxa(days=28, level="cultivar", shops=[data["shop"]], types=["cultivar"])
    assert [r["key"] for r in rows] == [data["rosita"]]

    # Manual grouping: put the cultivar in "Favourites", filter by it everywhere.
    after = groupings.create(groupings.GroupingIn(name="Picks"))["groupings"]
    picks = next(g for g in after if g["name"] == "Picks")
    after = groupings.set_groups(picks["id"], groupings.GroupsIn(groups=[G(name="Favourites")]))
    fav = next(g for g in after if g["id"] == picks["id"])["groups"][0]
    groupings.set_member(picks["id"], groupings.MemberIn(key=data["rosita"], group_id=fav["id"]))
    rows = analytics.taxa(days=28, level="cultivar", shops=[data["shop"]], group=[fav["id"]])
    assert [r["key"] for r in rows] == [data["rosita"]]
    ev = analytics.events(days=28, shops=[data["shop"]], group=[fav["id"]])
    assert ev and all(e["taxon"] == "Hoya carnosa 'Krimson Queen'" for e in ev)
    b = analytics.breakdown(by=str(picks["id"]), measure="offers", shops=[data["shop"]], split=True)
    assert {r["group"] for r in b["rows"]} == {str(fav["id"]), "other"} and b["panels"]

    # Over time, top species, by shop.
    s = analytics.breakdown(by="top", measure="stock", mode="series", level="cultivar", shops=[data["shop"]])
    assert len({r["day"] for r in s["rows"]}) == 3
    assert analytics.breakdown(by="shop", measure="offers", shops=[data["shop"]])["groups"][0]["name"] == "Whole"

    # Scopes run.
    for scope in ("available", "listed", "ever"):
        assert analytics.breakdown(by="top", scope=scope, shops=[data["shop"]])["rows"]
    groupings.set_member(picks["id"], groupings.MemberIn(key=data["rosita"], group_id=None))
    groupings.delete(picks["id"])


def test_grouping_rework(data):
    from fastapi import HTTPException

    from app import groupings

    gs = {g["kind"]: g for g in groupings.list_groupings()}
    for builtin in ("price", "type"):
        with pytest.raises(HTTPException):
            groupings.delete(gs[builtin]["id"])

    # Start from Type: the cultivar lands in "Cultivars", the species in "Species".
    r = groupings.create(groupings.GroupingIn(name="Look-alikes", start="type"))
    look = next(g for g in r["groupings"] if g["id"] == r["id"])
    by_name = {g["name"]: g for g in look["groups"]}
    assert data["rosita"] in {m["key"] for m in by_name["Cultivars"]["members"]}
    assert data["kerrii"] in {m["key"] for m in by_name["Species"]["members"]}

    rows = {p["key"]: p for p in groupings.plants(look["id"], days=28, shops=[data["shop"]])}
    assert rows[data["rosita"]]["own"] == by_name["Cultivars"]["id"] and rows[data["rosita"]]["offers"] == 1

    # Bulk move both into one group, then out again.
    groupings.set_members(look["id"], groupings.BulkIn(keys=[data["rosita"], data["kerrii"]], group_id=by_name["Hybrids"]["id"]))
    rows = {p["key"]: p for p in groupings.plants(look["id"], days=28, shops=[data["shop"]])}
    assert {rows[k]["own"] for k in (data["rosita"], data["kerrii"])} == {by_name["Hybrids"]["id"]}
    groupings.set_members(look["id"], groupings.BulkIn(keys=[data["rosita"]], group_id=None))
    rows = {p["key"]: p for p in groupings.plants(look["id"], days=28, shops=[data["shop"]])}
    assert rows[data["rosita"]]["own"] is None

    # Copy keeps groups and members.
    c = groupings.create(groupings.GroupingIn(name="Look-alikes 2", start=f"copy:{look['id']}"))
    copy = next(g for g in c["groupings"] if g["id"] == c["id"])
    assert [g["name"] for g in copy["groups"]] == [g["name"] for g in look["groups"]]
    assert sum(len(g["members"]) for g in copy["groups"]) == sum(
        len(g["members"]) for g in next(x for x in groupings.list_groupings() if x["id"] == look["id"])["groups"])
    groupings.delete(c["id"])
    groupings.delete(look["id"])

    # One group per species: the cultivar follows its species (carnosa).
    sp = groupings.create(groupings.GroupingIn(name="Per species", start="species"))
    rows = {p["key"]: p for p in groupings.plants(sp["id"], days=28, shops=[data["shop"]])}
    assert rows[data["rosita"]]["own"] is None and rows[data["rosita"]]["species_group"] is not None
    names = {g["name"] for g in next(x for x in sp["groupings"] if x["id"] == sp["id"])["groups"]}
    assert {"Hoya carnosa", "Hoya pubicalyx"} <= names
    groupings.delete(sp["id"])

    # Seed preview saves nothing; the generic plant list has no memberships.
    before = len(groupings.list_groupings())
    plan = {g["name"]: g["members"] for g in groupings.seed(start="type")}
    assert data["rosita"] in plan["Cultivars"] and len(groupings.list_groupings()) == before
    assert groupings.seed(start="empty") == []
    assert {p["key"] for p in groupings.all_plants(days=28, shops=[data["shop"]])} >= {data["rosita"], data["kerrii"]}


def test_subgroups(data, db):
    from app import analytics, groupings

    r = groupings.create(groupings.GroupingIn(name="Subs", start="empty"))
    gid = r["id"]
    S = groupings.StructItem
    st = groupings.set_structure(gid, groupings.StructIn(groups=[S(name="Carnosa-like"), S(name="Single leaf", parent=0)]))
    parent, single = st["ids"]
    g = next(x for x in st["groupings"] if x["id"] == gid)
    assert [x["name"] for x in g["groups"]] == ["Carnosa-like"] and g["subgroups"][0]["parent_id"] == parent

    groupings.set_members(gid, groupings.BulkIn(keys=[data["rosita"]], group_id=parent))
    offers = [o for o in groupings.offers(days=28, shops=[data["shop"]]) if o["plant_key"] == data["rosita"]]
    assert len(offers) == 1 and offers[0]["stock"] == 200
    groupings.set_offers(gid, groupings.OffersIn(listing_ids=[offers[0]["id"]], group_id=single))

    # Filter by the subgroup: only that offer; tiles/table see its stock.
    rows = analytics.taxa(days=28, level="cultivar", shops=[data["shop"]], group=[single])
    assert [r["key"] for r in rows] == [data["rosita"]] and rows[0]["quantity"] == 200
    # Split in the chart: the subgroup gets its own slice.
    b = analytics.breakdown(by=str(gid), measure="stock", shops=[data["shop"]], sub=True)
    vals = {r["group"]: r["value"] for r in b["rows"]}
    assert vals[str(single)] == 200 and "Carnosa-like › Single leaf" in {x["name"] for x in b["groups"]}
    # Not split: counted in the parent.
    b = analytics.breakdown(by=str(gid), measure="stock", shops=[data["shop"]])
    assert {r["group"]: r["value"] for r in b["rows"]}[str(parent)] == 200

    # Plant leaves the parent group: the offer no longer counts in the subgroup.
    groupings.set_members(gid, groupings.BulkIn(keys=[data["rosita"]], group_id=None))
    assert analytics.taxa(days=28, level="cultivar", shops=[data["shop"]], group=[single]) == []
    # Deleting the parent removes the subgroup.
    after = groupings.set_structure(gid, groupings.StructIn(groups=[]))
    assert next(x for x in after["groupings"] if x["id"] == gid)["subgroups"] == []
    groupings.delete(gid)
