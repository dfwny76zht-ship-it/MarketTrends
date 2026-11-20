"""Adapters against stored shop pages (saved 2026-11-18). Run: pytest backend/tests"""

import gzip
from decimal import Decimal
from pathlib import Path

from app.adapters import floraccess, jtl, shopify
from app.adapters.floraccess import FlorAccessAdapter
from app.adapters.base import FetchError
from app.adapters.jtl import JtlAdapter
from app.adapters.shopify import ShopifyAdapter

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return gzip.decompress((FIX / name).read_bytes()).decode("utf-8")


def fake_fetch(pages: dict[str, str]):
    calls = []

    def fetch(url: str) -> str:
        calls.append(url)
        if url not in pages:
            raise AssertionError(f"unexpected fetch {url}")
        return pages[url]

    fetch.calls = calls
    return fetch


# --- Shopify (Jungle Leaves) ---

def test_shopify_collection():
    base = "https://jungle-leaves.de"
    fetch = fake_fetch({f"{base}/collections/sukkulenten/products.json?limit=250&page=1": load("jungle_leaves_sukkulenten.json.gz")})
    res = ShopifyAdapter({"base": base, "collection": "sukkulenten", "name_filter": "hoya"}).collect(fetch)
    assert not res.errors
    assert len({o.raw["handle"] for o in res.offers}) == 21
    lisa = next(o for o in res.offers if o.item_no == "Hoy009-8")
    assert lisa.name == "Hoya australis 'Lisa' – 8cm Rundtopf"
    assert lisa.price == Decimal("8.99")
    assert lisa.availability == "available"
    assert lisa.pot_size == "8 cm"
    sold = next(o for o in res.offers if o.item_no == "Hoy012-6")
    assert sold.availability == "sold_out"
    assert len(fetch.calls) == 1


# --- JTL (Uhlig, Ben's Jungle) ---

def test_jtl_uhlig_page():
    items, total = jtl.parse_category(load("uhlig_hoya_p1.html.gz"))
    assert total == 309
    assert len(items) == 32
    by_name = {o.name: o for o in items}
    assert by_name["Hoya acicularis"].availability == "sold_out"
    assert by_name["Hoya acicularis"].price == Decimal("18.00")
    assert by_name["Hoya aff. pottsii"].availability == "low"
    assert by_name["Hoya amoena"].availability == "available"
    assert by_name["Hoya amoena"].url.startswith("https://uhlig-kakteen.de/")


def test_jtl_bens_jungle_page():
    items, total = jtl.parse_category(load("bens_jungle_hoya_p1.html.gz"))
    assert total == 87
    assert len(items) == 20
    imb = next(o for o in items if o.name == "Hoya imbricata")
    assert imb.price == Decimal("14.90")
    assert imb.availability == "available"
    assert "Sale 50%" in imb.raw["ribbons"]
    assert imb.image_url.endswith(".jpg")


def test_jtl_paging_stops_when_nothing_new():
    url = "https://uhlig-kakteen.de/Hoya-und-Dischidia"
    page = load("uhlig_hoya_p1.html.gz")
    fetch = fake_fetch({url: page, f"{url}_s2": page})
    res = JtlAdapter({"category_url": url, "name_prefix": "hoya", "ranks": False}).collect(fetch)
    assert len(fetch.calls) == 2
    assert res.expected_total == 309
    assert len(res.offers) == 19  # 32 boxes minus 13 Dischidia
    assert all(o.name.lower().startswith("hoya") for o in res.offers)


def test_jtl_sort_orders_become_ranks():
    url = "https://uhlig-kakteen.de/Hoya-und-Dischidia"
    page = load("uhlig_hoya_p1.html.gz")
    pages = {url: page, f"{url}_s2": page}
    for sort in (11, 6):
        pages[f"{url}?Sortierung={sort}"] = page
        pages[f"{url}_s2?Sortierung={sort}"] = page
    res = JtlAdapter({"category_url": url, "name_prefix": "hoya"}).collect(fake_fetch(pages))
    hoya_order = [o.item_key for o in res.offers]
    assert res.ranks["bestseller"] == hoya_order and res.ranks["newest"] == hoya_order


def test_jtl_missing_sort_page_keeps_offers():
    url = "https://uhlig-kakteen.de/Hoya-und-Dischidia"
    page = load("uhlig_hoya_p1.html.gz")

    def fetch(u):
        if "Sortierung" in u:
            raise FetchError("simulated")
        return page

    res = JtlAdapter({"category_url": url, "name_prefix": "hoya"}).collect(fetch)
    assert len(res.offers) == 19 and res.ranks == {} and any("bestseller order" in e for e in res.errors)


# --- FlorAccess ---

def test_floraccess_category():
    tiles, total = floraccess.parse_category(load("floraccess_hoya_p1.html.gz"))
    assert total == 154
    assert len(tiles) == 24
    first = tiles[0]
    assert first["id"] == "76949"
    assert first["pot"] == "6 cm"
    assert first["height"] == "12 cm"


def test_floraccess_product():
    tiles, _ = floraccess.parse_category(load("floraccess_hoya_p1.html.gz"))
    offer = floraccess.parse_product(load("floraccess_product_76949.html.gz"), tiles[0], "https://www.floraccess.com")
    assert offer.quantity == 4648
    assert offer.price == Decimal("1.44")
    assert offer.availability == "available"
    assert offer.pot_size == "6 cm"
    tray = offer.tier_prices[0]
    assert tray == {"unit": "tray", "min_qty": 12, "price": "1.48"}
    assert {"unit": "layer", "layers": 1, "min_qty": 120, "price": "1.44"} in offer.tier_prices


def test_floraccess_collect_falls_back_to_tile_on_error():
    base = "https://www.floraccess.com"
    cat = load("floraccess_hoya_p1.html.gz")
    product = load("floraccess_product_76949.html.gz")
    tiles, _ = floraccess.parse_category(cat)

    def fetch(url):
        if url == f"{base}/en/category/571/hoya/":
            return cat
        if url.startswith(f"{base}/en/category/571/hoya/?page="):
            return cat  # nothing new -> stop
        if "/product/76949/" in url:
            return product
        from app.adapters.base import FetchError
        raise FetchError("simulated")

    res = FlorAccessAdapter({"base": base, "category_path": "/en/category/571/hoya/"}).collect(fetch)
    assert len(res.offers) == len([t for t in tiles if "hoya" in t["name"].lower()])
    assert res.complete is False
    assert next(o for o in res.offers if o.item_key == "76949").quantity == 4648


def test_challenge_pages_are_recognised():
    import os
    os.environ.setdefault("DATABASE_URL", "postgresql://unused")
    from app.fetching import is_challenge

    assert is_challenge(b"<html><title>uhlig-kakteen.de</title><body>Please enable JavaScript to continue.</body></html>")
    assert is_challenge(b"<!DOCTYPE html><html><head><title>Just a moment...</title></head></html>")
    assert not is_challenge(gzip.decompress((FIX / "bens_jungle_hoya_p1.html.gz").read_bytes()))


def test_floraccess_product_without_machine_readable_block():
    tile = {"id": "119221", "path": "/en/product/119221/x/", "name": "Hoya carnosa 'Compacta Mauna Loa'",
            "price": "€6.03", "pot": "6 cm", "height": "8 cm", "image": None}
    offer = floraccess.parse_product(load("floraccess_product_119221_nold.html.gz"), tile, "https://www.floraccess.com")
    assert offer.quantity == 100
    assert offer.availability == "available"
    assert offer.price == Decimal("6.03")
    assert {"unit": "layer", "layers": 1, "min_qty": 36, "price": "6.03"} in offer.tier_prices
    assert offer.raw["from"] == "page text"
