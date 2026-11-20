"""Shopify shops read from their normal collection pages (what every visitor sees), for shops whose
products.json answers 429 (Jungle Leaves, 2026-11-20). Each page embeds the shop's own analytics data
(`var meta = {...}`): product id, handle and every variant with price (cents), size title and SKU.
Availability comes from the product card ("out-of-stock" badge), so it is per product, not per size.
One offer per variant (pot size), keyed by the variant id, like the products.json adapter.
The shop's sort orders "best-selling" and "created-descending" are read as the demand signal."""

from __future__ import annotations

import html as htmlmod
import json
import re
from decimal import Decimal

from .base import Adapter, CollectResult, FetchError, Offer, clean, size_cm

META = re.compile(r"var meta = (\{.*?\});\s*\n", re.S)
CARD = re.compile(r"<product-card.*?</product-card>", re.S)
HANDLE = re.compile(r'data-product-handle="([^"]+)"')
IMG = re.compile(r'(?:src|data-src)="(//[^"\s]+?\.(?:jpg|jpeg|png|webp)[^"\s]*)"', re.I)
RANK_SORTS = (("bestseller", "best-selling"), ("newest", "created-descending"))


def parse_page(text: str) -> tuple[list[dict], dict[str, dict]]:
    """(products from the page's meta data, card info by handle)."""
    m = META.search(text)
    products = json.loads(m.group(1)).get("products", []) if m else []
    cards = {}
    for c in CARD.findall(text):
        h = HANDLE.search(c)
        if not h:
            continue
        img = IMG.search(c)
        cards.setdefault(h.group(1), {
            "sold_out": "out-of-stock" in c,
            "image": ("https:" + re.sub(r"&width=\d+", "", img.group(1))) if img else None,
        })
    return products, cards


class ShopifyHtmlAdapter(Adapter):
    key = "shopify_html"
    version = "1"

    def _page_url(self, page: int, sort: str | None = None) -> str:
        base = self.config["base"].rstrip("/")
        q = [f"page={page}"] + ([f"sort_by={sort}"] if sort else [])
        return f"{base}/collections/{self.config['collection']}?{'&'.join(q)}"

    def _walk(self, fetch, sort: str | None = None):
        seen: list[str] = []
        for page in range(1, 41):
            products, cards = parse_page(fetch(self._page_url(page, sort)))
            new = [p for p in products if p["handle"] not in seen]
            if not new:
                break
            seen += [p["handle"] for p in new]
            yield new, cards

    def collect(self, fetch) -> CollectResult:
        base = self.config["base"].rstrip("/")
        name_filter = self.config.get("name_filter", "hoya").lower()
        res = CollectResult()
        variants_of: dict[str, list[str]] = {}
        for products, cards in self._walk(fetch):
            for p in products:
                card = cards.get(p["handle"], {})
                keys = []
                for v in p.get("variants", []):
                    name = clean(htmlmod.unescape(v.get("name") or ""))
                    if not name.lower().startswith(name_filter):
                        continue
                    sold = card.get("sold_out")
                    size = v.get("public_title")
                    res.offers.append(Offer(
                        item_key=str(v["id"]), item_no=v.get("sku") or None, name=name,
                        url=f"{base}/products/{p['handle']}?variant={v['id']}", image_url=card.get("image"),
                        price=Decimal(v["price"]) / 100, currency="EUR",
                        availability_text=None if sold is None else ("sold out" if sold else "available"),
                        availability="unknown" if sold is None else ("sold_out" if sold else "available"),
                        pot_size=size_cm(size or name),
                        raw={"product_id": p.get("id"), "handle": p["handle"], "variant_title": size,
                             "availability_basis": "product card"},
                    ))
                    keys.append(str(v["id"]))
                if keys:
                    variants_of[p["handle"]] = keys
        # Sort orders: one position per product; its sizes share it.
        for name, sort in RANK_SORTS:
            if self.config.get("ranks") is False:
                break
            try:
                order = [p["handle"] for products, _ in self._walk(fetch, sort) for p in products]
            except FetchError as exc:
                res.errors.append(f"{name} order: {exc}")
                continue
            res.ranks[name] = [variants_of[h] for h in order if h in variants_of]
        return res
