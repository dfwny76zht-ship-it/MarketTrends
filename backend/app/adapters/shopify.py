"""Shopify shops: the public products.json of one collection. One offer per variant (pot size)."""

from __future__ import annotations

import json

from .base import Adapter, CollectResult, Offer, clean, parse_price, size_cm

PAGE_SIZE = 250


class ShopifyAdapter(Adapter):
    key = "shopify"
    version = "1"

    def collect(self, fetch) -> CollectResult:
        base = self.config["base"].rstrip("/")
        collection = self.config["collection"]
        name_filter = self.config.get("name_filter", "hoya").lower()
        currency = self.config.get("currency", "EUR")
        res = CollectResult()
        for page in range(1, 41):
            data = json.loads(fetch(f"{base}/collections/{collection}/products.json?limit={PAGE_SIZE}&page={page}"))
            products = data.get("products", [])
            for product in products:
                if name_filter not in product.get("title", "").lower():
                    continue
                try:
                    res.offers.extend(parse_product(product, base, currency))
                except Exception as exc:
                    res.errors.append(f"{product.get('handle')}: {type(exc).__name__}: {exc}")
            if len(products) < PAGE_SIZE:
                break
        return res


def parse_product(product: dict, base: str, currency: str) -> list[Offer]:
    images = product.get("images") or []
    product_image = images[0].get("src") if images else None
    title = clean(product["title"])
    offers = []
    for v in product["variants"]:
        variant = clean(v.get("title"))
        if variant.lower() == "default title":
            variant = ""
        available = bool(v.get("available"))
        offers.append(
            Offer(
                item_key=str(v["id"]),
                item_no=v.get("sku") or None,
                name=f"{title} – {variant}" if variant else title,
                url=f"{base}/products/{product['handle']}?variant={v['id']}",
                category=product.get("product_type") or None,
                image_url=(v.get("featured_image") or {}).get("src") or product_image,
                price=parse_price(v.get("price")),
                currency=currency,
                availability_text="available" if available else "sold out",
                availability="available" if available else "sold_out",
                pot_size=size_cm(variant),
                raw={
                    "product_id": product.get("id"),
                    "handle": product.get("handle"),
                    "variant_title": variant or None,
                    "compare_at_price": v.get("compare_at_price"),
                    "created_at": product.get("created_at"),
                    "published_at": product.get("published_at"),
                    "tags": product.get("tags"),
                    "vendor": product.get("vendor"),
                },
            )
        )
    return offers
