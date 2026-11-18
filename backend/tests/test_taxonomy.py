"""Species seeding, suggestions, confirming and merging against a throwaway Postgres."""

import pytest


@pytest.fixture(scope="module")
def setup(db):
    from app import taxonomy

    taxonomy.seed()
    with db.connection() as conn:
        a = conn.execute(
            "INSERT INTO shops (name, url, host) VALUES ('Shop A', 'https://a.example/', 'a.example') RETURNING id"
        ).fetchone()["id"]
        b = conn.execute(
            "INSERT INTO shops (name, url, host) VALUES ('Shop B', 'https://b.example/', 'b.example') RETURNING id"
        ).fetchone()["id"]

        def listing(shop, key, name):
            return conn.execute(
                "INSERT INTO listings (shop_id, item_key, name, first_seen, last_seen) VALUES (%s, %s, %s, now(), now())"
                " RETURNING id",
                (shop, key, name),
            ).fetchone()["id"]

        ids = {
            "imb_a": listing(a, "1", "Hoya imbricata"),
            "imb_b": listing(b, "1", "Hoya imbricata Babyplant"),
            "lisa": listing(a, "2", "Hoya australis 'Lisa' – 8cm Rundtopf"),
            "rosita": listing(b, "2", "Hoya 'Rosita'"),
            "comp": listing(a, "3", "Hoya carnosa compacta L"),
            "typo": listing(b, "3", "Hoya finlaysoni"),
            "mix": listing(a, "4", "Hoya MIX"),
            "kerrii": listing(b, "4", "Hoya kerrii variegata"),
        }
    taxonomy.match_pending()
    return ids


def assignment(db, listing_id):
    with db.connection() as conn:
        return conn.execute(
            "SELECT a.*, s.epithet, c.name AS cultivar, c.kind FROM assignments a"
            " LEFT JOIN species s ON s.id = a.species_id LEFT JOIN cultivars c ON c.id = a.cultivar_id"
            " WHERE a.listing_id = %s",
            (listing_id,),
        ).fetchone()


def test_seed(db, setup):
    with db.connection() as conn:
        n = conn.execute("SELECT count(*) AS n FROM species").fetchone()["n"]
        lab = {r["epithet"] for r in conn.execute("SELECT epithet FROM species WHERE in_lims")}
        hybrids = {r["name"] for r in conn.execute("SELECT name FROM cultivars WHERE species_id IS NULL")}
    assert n >= 567
    assert {"carnosa", "kerrii", "kloppenburgii", "wayetii"} <= lab
    assert {"Rosita", "Elephant"} <= hybrids


def test_suggestions(db, setup):
    a = assignment(db, setup["imb_a"])
    assert (a["epithet"], a["confidence"], a["confirmed"]) == ("imbricata", "likely", False)
    a = assignment(db, setup["rosita"])
    assert (a["cultivar"], a["kind"], a["confidence"]) == ("Rosita", "hybrid", "likely")
    a = assignment(db, setup["kerrii"])
    assert (a["epithet"], a["cultivar"], a["confidence"]) == ("kerrii", "Variegata", "likely")
    a = assignment(db, setup["typo"])
    assert (a["epithet"], a["confidence"]) == ("finlaysonii", "unsure")
    a = assignment(db, setup["comp"])
    assert a["epithet"] == "carnosa" and a["suggestion"]["cultivar"] == "Compacta" and a["confidence"] == "unsure"


def test_confirm_applies_to_all_shops(db, setup):
    from app import taxonomy

    with db.connection() as conn:
        sid = conn.execute("SELECT id FROM species WHERE epithet = 'imbricata'").fetchone()["id"]
    n = taxonomy.confirm("imbricata", species_id=sid)
    assert n == 2  # "Hoya imbricata" and "Hoya imbricata Babyplant" share the spelling key
    assert assignment(db, setup["imb_b"])["confirmed"]


def test_new_cultivar_and_ignore(db, setup):
    from app import taxonomy

    with db.connection() as conn:
        sid = conn.execute("SELECT id FROM species WHERE epithet = 'carnosa'").fetchone()["id"]
    taxonomy.confirm("carnosa compacta", species_id=sid, new_cultivar="Compacta", kind="cultivar")
    a = assignment(db, setup["comp"])
    assert (a["epithet"], a["cultivar"], a["confirmed"]) == ("carnosa", "Compacta", True)
    taxonomy.confirm("mix", ignore=True)
    a = assignment(db, setup["mix"])
    assert a["confirmed"] and a["ignored"]


def test_confirm_likely_creates_quoted_cultivar(db, setup):
    from app import taxonomy

    taxonomy.confirm_likely()
    a = assignment(db, setup["lisa"])
    assert (a["epithet"], a["cultivar"], a["confirmed"]) == ("australis", "Lisa", True)
    assert not assignment(db, setup["typo"])["confirmed"]  # unsure ones stay open


def test_known_spelling_is_matched_automatically(db, setup):
    from app import taxonomy

    with db.connection() as conn:
        shop = conn.execute("SELECT id FROM shops WHERE host = 'b.example'").fetchone()["id"]
        new = conn.execute(
            "INSERT INTO listings (shop_id, item_key, name, first_seen, last_seen)"
            " VALUES (%s, '9', 'Hoya australis ‚Lisa‘ 12 cm Ampel', now(), now()) RETURNING id",
            (shop,),
        ).fetchone()["id"]
    taxonomy.match_pending()
    a = assignment(db, new)
    assert (a["cultivar"], a["confidence"], a["confirmed"]) == ("Lisa", "sure", True)


def test_merge_species(db, setup):
    from app import taxonomy

    with db.connection() as conn:
        wrong = conn.execute("INSERT INTO species (epithet, source) VALUES ('imbricatta', 'manual') RETURNING id").fetchone()["id"]
        right = conn.execute("SELECT id FROM species WHERE epithet = 'imbricata'").fetchone()["id"]
    taxonomy.merge_species(wrong, right)
    with db.connection() as conn:
        syn = conn.execute("SELECT species_id FROM species_synonyms WHERE epithet = 'imbricatta'").fetchone()
        gone = conn.execute("SELECT 1 FROM species WHERE id = %s", (wrong,)).fetchone()
    assert syn["species_id"] == right and gone is None


def test_species_becomes_cultivar_and_back(db, setup):
    from app import taxonomy

    with db.connection() as conn:
        odd = conn.execute("INSERT INTO species (epithet, source) VALUES ('mauna', 'manual') RETURNING id").fetchone()["id"]
        shop = conn.execute("SELECT id FROM shops WHERE host = 'a.example'").fetchone()["id"]
        lid = conn.execute(
            "INSERT INTO listings (shop_id, item_key, name, first_seen, last_seen) VALUES (%s, '20', 'Hoya mauna', now(), now())"
            " RETURNING id", (shop,)).fetchone()["id"]
    taxonomy.match_pending()
    taxonomy.confirm("mauna", species_id=odd)

    cid = taxonomy.species_to_cultivar(odd, "cultivar", "carnosa", "Mauna Loa")
    a = assignment(db, lid)
    assert (a["epithet"], a["cultivar"], a["kind"], a["confirmed"]) == ("carnosa", "Mauna Loa", "cultivar", True)

    sid = taxonomy.cultivar_to_species(cid, "maunaloa")
    a = assignment(db, lid)
    assert (a["epithet"], a["cultivar"], a["confirmed"]) == ("maunaloa", None, True)
    assert sid


def test_unconfirm_sends_back_to_list(db, setup):
    from app import taxonomy

    taxonomy.unconfirm("mix")
    a = assignment(db, setup["mix"])
    assert not a["confirmed"] and not a["ignored"]
