import json
from pathlib import Path

from app.names import name_key, parse, size_class

KEW = json.loads((Path(__file__).parent.parent / "app" / "data" / "kew_hoya.json").read_text())
EPITHETS = set(KEW["species"])
SYNONYMS = KEW["synonyms"]


def p(name):
    return parse(name, EPITHETS, SYNONYMS)


def test_name_key_ignores_shop_extras():
    assert name_key("Hoya australis 'Lisa' – 8cm Rundtopf") == "australis 'lisa'"
    assert name_key("Hoya australis ‚Lisa‘ – 12 cm Ampel") == "australis 'lisa'"
    assert name_key("Hoya Callistophylla 'Long Leaf' selten") == "callistophylla 'long leaf'"
    assert name_key("Hoya carnosa compacta L") == name_key("Hoya carnosa compacta M") == "carnosa compacta"
    assert name_key("Hoya wayetii tricolor variegata Babyplant") == "wayetii tricolor variegata"


def test_species_only():
    r = p("Hoya imbricata")
    assert (r.epithet, r.epithet_match, r.cultivar) == ("imbricata", "exact", None)


def test_capitalised_epithet_and_quoted_cultivar():
    r = p("Hoya Callistophylla 'Long Leaf' selten")
    assert (r.epithet, r.cultivar, r.kind) == ("callistophylla", "Long Leaf", "cultivar")


def test_form_words():
    r = p("Hoya kerrii variegata")
    assert (r.epithet, r.cultivar, r.kind) == ("kerrii", "Variegata", "form")
    r = p("Hoya crassipetiolata Splash")
    assert (r.cultivar, r.kind) == ("Splash", "form")


def test_hybrid_without_species():
    r = p("Hoya 'Rosita'")
    assert (r.epithet, r.cultivar, r.kind) == (None, "Rosita", "hybrid")
    r = p("Hoya cv. Mathilde Splash")
    assert (r.epithet, r.cultivar, r.kind) == (None, "Mathilde Splash", "hybrid")


def test_synonym_and_typo():
    r = p("Hoya parasitica Heart Leaves Splash")
    assert (r.epithet, r.epithet_match) == ("verticillata", "synonym")
    r = p("Hoya finlaysoni")
    assert (r.epithet, r.epithet_match) == ("finlaysonii", "fuzzy")


def test_collection_number_and_subspecies():
    r = p("Hoya australis ssp. sanae IML 0171")
    assert r.collection_no == "IML 0171"
    assert (r.epithet, r.cultivar, r.kind) == ("australis", "subsp. sanae", "subspecies")


def test_aff_is_kept_as_qualifier():
    r = p("Hoya aff. pottsii")
    assert "aff" in r.qualifiers
    assert r.epithet == "verticillata"


def test_size_classes():
    assert size_class("6 cm") == "XS"
    assert size_class("8 cm") == "S"
    assert size_class("12 cm") == "M"
    assert size_class("14 cm") == "L"
    assert size_class("17 cm") == "XL"
    assert size_class(None, "Hoya sigillatis Babyplant") == "XS"
    assert size_class(None, "Hoya carnosa compacta L") == "L"
    assert size_class(None, "Hoya imbricata") == "unknown"


def test_places_and_collection_numbers_are_forms():
    r = p("Hoya carnosa IPPS6260 Vietnam")
    assert (r.epithet, r.cultivar, r.kind, r.collection_no) == ("carnosa", "Vietnam (IPPS 6260)", "form", "IPPS 6260")
    r = p("Hoya australis IPPS0121")
    assert (r.cultivar, r.kind) == ("IPPS 0121", "form")
    r = p("Hoya caudata Sumatra")
    assert (r.cultivar, r.kind) == ("Sumatra", "form")
    r = p("Hoya sp Cianjur")
    assert (r.epithet, r.cultivar, r.kind) == (None, "Cianjur", "form")
    r = p("Hoya 'Lai Chau'")
    assert r.kind == "form"
    r = p("Hoya 'Rosita'")
    assert r.kind == "hybrid"
    r = p("Hoya alagensis NS05-232")
    assert (r.collection_no, r.cultivar, r.kind) == ("NS 05-232", "NS 05-232", "form")
