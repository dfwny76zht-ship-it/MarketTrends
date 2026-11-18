"""FlorAccess (wholesale): Hoya category pages for the list, then each product page for stock and tiers."""

from __future__ import annotations

import json
import re

from selectolax.parser import HTMLParser

from .base import (
    Adapter,
    Blocked,
    CollectResult,
    Disallowed,
    FetchError,
    Offer,
    availability_from_schema,
    clean,
    parse_price,
)

COUNT_RE = re.compile(r"searchData:\{results:\{count:(\d+),pageSize:(\d+)")
PRODUCT_RE = re.compile(r"^/(?:[a-z]{2}/)?product/(\d+)/")
LAYER_RE = re.compile(r"(\d+) layers? / (\d+) products - €\s?([\d.,]+)")
TRAY_PRICE_RE = re.compile(r"Order per tray.*?€\s?([\d.,]+) per product")
TRAY_QTY_RE = re.compile(r"Products per tray (\d+)")
AVAILABLE_RE = re.compile(r"Products available (\d+) products")
DISCOUNT_RE = re.compile(r"(\d+)x (\d+) layers? €\s?([\d.,]+)")


class FlorAccessAdapter(Adapter):
    key = "floraccess"
    version = "1"

    def collect(self, fetch) -> CollectResult:
        base = self.config["base"].rstrip("/")
        path = self.config["category_path"]
        name_filter = self.config.get("name_filter", "hoya").lower()
        res = CollectResult()

        tiles: dict[str, dict] = {}
        for page in range(1, 41):
            html = fetch(f"{base}{path}" + ("" if page == 1 else f"?page={page}"))
            found, total = parse_category(html)
            if page == 1:
                res.expected_total = total
            new = [t for t in found if t["id"] not in tiles]
            for t in new:
                tiles[t["id"]] = t
            if not new or (total and len(tiles) >= total):
                break

        for tile in tiles.values():
            if name_filter not in tile["name"].lower():
                continue
            try:
                html = fetch(base + tile["path"])
                res.offers.append(parse_product(html, tile, base))
            except (Blocked, Disallowed):
                raise
            except FetchError as exc:
                res.errors.append(f"{tile['id']}: {exc}")
                res.offers.append(offer_from_tile(tile, base))
                res.complete = False
            except Exception as exc:
                res.errors.append(f"{tile['id']}: {type(exc).__name__}: {exc}")
                res.offers.append(offer_from_tile(tile, base))
        return res


def parse_category(html: str) -> tuple[list[dict], int | None]:
    m = COUNT_RE.search(html)
    total = int(m.group(1)) if m else None
    tree = HTMLParser(html)
    tiles, seen = [], set()
    for a in tree.css('a[href*="/product/"]'):
        href = (a.attributes.get("href") or "").split("?")[0]
        pm = PRODUCT_RE.match(href)
        name_node = a.css_first(".name")
        if not pm or not name_node or pm.group(1) in seen:
            continue
        seen.add(pm.group(1))
        pot = height = None
        for prop in a.css(".type-tile"):
            icon = prop.css_first("use")
            ref = (icon.attributes.get("href") or "") if icon else ""
            value = clean(prop.text()).replace(" ", "")
            if "IconPot" in ref:
                pot = value.replace("cm", " cm")
            elif "IconHeight" in ref:
                height = value.replace("cm", " cm")
        price_node = a.css_first(".price")
        img = a.css_first("img")
        tiles.append(
            {
                "id": pm.group(1),
                "path": href,
                "name": clean(name_node.text()),
                "price": clean(price_node.text()) if price_node else None,
                "pot": pot,
                "height": height,
                "image": img.attributes.get("src") if img else None,
            }
        )
    return tiles, total


def offer_from_tile(tile: dict, base: str) -> Offer:
    return Offer(
        item_key=tile["id"],
        item_no=tile["id"],
        name=tile["name"],
        url=base + tile["path"],
        image_url=tile.get("image"),
        price=parse_price(tile.get("price")),
        currency="EUR",
        pot_size=tile.get("pot"),
        plant_size=tile.get("height"),
        raw={"tile_price": tile.get("price"), "from": "category tile only"},
    )


def parse_product(html: str, tile: dict, base: str) -> Offer:
    tree = HTMLParser(html)
    product = None
    for script in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.text())
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Product":
            product = data
            break
    for node in tree.css("script, style"):
        node.decompose()
    text = clean(tree.body.text(separator=" ")) if tree.body else ""
    if not product:
        # Some pages carry no machine-readable block; the same facts are in the visible text.
        if not AVAILABLE_RE.search(text):
            raise ValueError("no product data on page")
        product = {}

    offers = product.get("offers") or {}
    quantity = (offers.get("inventoryLevel") or {}).get("value")
    if quantity is None:
        m = AVAILABLE_RE.search(text)
        quantity = int(m.group(1)) if m else None
    availability = availability_from_schema(offers.get("availability"))
    if availability == "unknown" and quantity is not None:
        availability = "available" if quantity > 0 else "sold_out"
    if quantity == 0:
        availability = "sold_out"

    tiers = []
    tray_price, tray_qty = TRAY_PRICE_RE.search(text), TRAY_QTY_RE.search(text)
    if tray_price and tray_qty:
        tiers.append({"unit": "tray", "min_qty": int(tray_qty.group(1)), "price": str(parse_price(tray_price.group(1)))})
    for layers, qty, price in LAYER_RE.findall(text):
        tiers.append({"unit": "layer", "layers": int(layers), "min_qty": int(qty), "price": str(parse_price(price))})
    if not any(t["unit"] == "layer" for t in tiers):
        seen = set()
        for qty, layers, price in DISCOUNT_RE.findall(text):
            if layers not in seen:
                seen.add(layers)
                tiers.append({"unit": "layer", "layers": int(layers), "min_qty": int(qty), "price": str(parse_price(price))})
    layer_price = next((t["price"] for t in tiers if t["unit"] == "layer" and t["layers"] == 1), None)

    return Offer(
        item_key=tile["id"],
        item_no=str(product.get("sku") or tile["id"]),
        name=clean(product.get("name")) or tile["name"],
        url=base + tile["path"],
        image_url=product.get("image") or tile.get("image"),
        price=parse_price(offers.get("price")) or parse_price(layer_price) or parse_price(tile.get("price")),
        currency=offers.get("priceCurrency") or "EUR",
        tier_prices=tiers or None,
        availability_text=f"{quantity} available" if quantity is not None else None,
        availability=availability,
        quantity=quantity,
        pot_size=tile.get("pot"),
        plant_size=tile.get("height"),
        raw={
            "schema_availability": offers.get("availability"),
            "from": "page data" if offers else "page text",
            "price_valid_until": offers.get("priceValidUntil"),
            "tile_price": tile.get("price"),
        },
    )
