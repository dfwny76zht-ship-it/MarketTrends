"""Archived FlorAccess pages (Wayback copies) are read correctly and stored as archive observations."""

import gzip
from datetime import datetime, timezone
from pathlib import Path

FIX = Path(__file__).parent / "fixtures"
AT = datetime(2019, 8, 18, tzinfo=timezone.utc)


def page(n):
    return gzip.decompress((FIX / f"fa_archive_p{n}.html.gz").read_bytes()).decode("utf-8", "replace")


def test_category_2019():
    from app.adapters.floraccess_archive import parse_archived

    offers = parse_archived(page(4), "https://www.floraccess.com/en/category/56/hoya/", "category", AT)
    assert len(offers) == 24
    tri = [o for o in offers if o["name"] == "Hoya carnosa 'Tricolor'" and o["pot"] == "5.5 cm"]
    assert tri and tri[0]["price"] == 0.63 and tri[0]["height"] == "10 cm" and tri[0]["grower"] == "Van der Velden"


def test_offer_page_last_available():
    from app.adapters.floraccess_archive import parse_archived

    url = "https://www.floraccess.com/en/v/27784/handelskwekerij-van-der-velden/hoya-carnosa-tricolor-/"
    (o,) = parse_archived(page(1), url, "offer", AT)
    assert (o["item_key"], o["price"], o["pot"], o["height"], o["grower"]) == ("27784", 6.06, "15 cm", "35 cm", "Van der Velden")
    assert o["observed_at"].date().isoformat() == "2018-09-15" and o["availability"] == "available"


def test_offer_page_2022_and_product_2024():
    from app.adapters.floraccess_archive import parse_archived

    (o,) = parse_archived(page(3), "https://www.floraccess.com/de/v/46111/gasa-dk/hoya-australis/", "offer", AT)
    assert (o["name"], o["price"], o["pot"], o["height"], o["grower"]) == ("Hoya australis", 7.44, "14 cm", "45 cm", "Gasa DK")
    (p,) = parse_archived(page(6), "https://www.floraccess.com/de/product/27786/hoya-carnosa-mix/", "product", AT)
    assert (p["item_key"], p["price"], p["pot"], p["height"]) == ("27786", 5.09, "12 cm", "15 cm")


def test_grower_spellings():
    from app.adapters.floraccess_archive import grower_name

    assert {grower_name(x) for x in ("hkw-van-der-velden", "van-der-velden-hkw.", "handelskwekerij-van-der-velden")} == {"Van der Velden"}
    assert grower_name("meyst-werner-de") == "De Meyst Werner"


def test_import_and_reference(db):
    from app import archive

    with db.connection() as conn:
        shop = conn.execute(
            "INSERT INTO shops (name, url, host) VALUES ('FA test', 'https://fa.example/', 'fa.example') RETURNING id"
        ).fetchone()["id"]
        run = conn.execute("INSERT INTO runs (shop_id, kind) VALUES (%s, 'archive') RETURNING id", (shop,)).fetchone()["id"]
    from app.adapters.floraccess_archive import parse_archived

    offers = parse_archived(page(4), "https://www.floraccess.com/en/category/56/hoya/", "category", AT)
    cap = {"url": "https://www.floraccess.com/en/category/56/hoya/", "kind": "category", "captured_at": AT,
           "archive": "wayback", "archive_url": "https://web.archive.org/web/20190818070039id_/x"}
    with db.connection() as conn:
        assert archive._import(conn, shop, run, cap, offers) == 24
        assert archive._import(conn, shop, run, cap, offers) == 0  # same capture again: nothing doubled
        row = conn.execute(
            "SELECT l.gone_since IS NOT NULL AS gone, o.source, o.grower, o.raw->>'page' AS page FROM listings l"
            " JOIN observations o ON o.listing_id = l.id WHERE l.shop_id = %s AND l.item_key = '28695'", (shop,)).fetchone()
    assert row["gone"] and row["source"] == "archive" and row["grower"] == "Van der Velden" and row["page"] == "category"

    csv = ("Monat,Angebot,Topf (cm),Höhe (cm),Preis netto (€),Erzeuger,Quelle\n"
           "2019-08,Hoya carnosa 'Tricolor',5.5,10,\"0,63\",,\"Internet Archive, Kategorieseite\"\n"
           "2019-08,Hoya carnosa 'Tricolor',12,15,\"2,30\",,\"Internet Archive, Kategorieseite\"\n"
           "2019-08,Hoya bella,14,40,\"4,64\",,\"Internet Archive, Kategorieseite\"\n"
           "2026-11,Hoya kerrii,6,15,\"3,66\",,\"FlorAccess, Live-Abruf 18.11.2026\"\n")
    assert archive.import_reference(shop, csv) == 3
    res = archive.reference_check(shop)
    st = {(r["name"], r["pot_cm"]): r["status"] for r in res["rows"]}
    assert st[("Hoya carnosa 'Tricolor'", 5.5)] == "match"
    assert st[("Hoya carnosa 'Tricolor'", 12.0)] == "price differs"


def test_history_endpoints(db):
    from app import taxonomy, trends

    with db.connection() as conn:
        shop = conn.execute("SELECT id FROM shops WHERE host = 'fa.example'").fetchone()["id"]
    taxonomy.seed()
    taxonomy.match_pending(shop)
    with db.connection() as conn:  # confirm only this shop's suggestions (other tests rely on theirs staying open)
        conn.execute("UPDATE assignments a SET confirmed = true FROM listings l WHERE l.id = a.listing_id AND l.shop_id = %s"
                     " AND (a.species_id IS NOT NULL OR a.cultivar_id IS NOT NULL)", (shop,))
    v = trends.history_variety(shops=[shop])
    assert v and v[0]["month"] == "2019-08" and v[0]["complete"] and v[0]["growers"] >= 1
    g = trends.history_growers(shops=[shop])
    assert any(r["grower"] == "Van der Velden" for r in g)
    t = trends.history_taxa(shops=[shop])
    assert t
    p = trends.history_product(key=t[0]["key"], shops=[shop])
    assert p["formats"] and all(pt["source"] == "archive" for fm in p["formats"] for pt in fm["points"])
    assert trends.history_sources(shops=[shop])[0]["page"] == "category"
