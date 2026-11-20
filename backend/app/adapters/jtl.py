"""JTL shops (Uhlig, Ben's Jungle): category pages <url>, <url>_s2, <url>_s3 ... with product boxes."""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser, Node

from .base import (
    Adapter,
    FetchError,
    CollectResult,
    Offer,
    availability_from_schema,
    availability_from_text,
    clean,
    parse_price,
)

TOTAL_RE = re.compile(r"Artikel\s+\d+\s*-\s*\d+\s+von\s+(\d+)")


class JtlAdapter(Adapter):
    key = "jtl"
    version = "1"

    def collect(self, fetch) -> CollectResult:
        url = self.config["category_url"].rstrip("/")
        prefix = self.config.get("name_prefix", "hoya").lower()
        res = CollectResult()
        all_ids: set[str] = set()
        for page in range(1, 41):
            html = fetch(url if page == 1 else f"{url}_s{page}")
            items, total = parse_category(html)
            if page == 1:
                res.expected_total = total
            new = 0
            for item in items:
                if isinstance(item, str):
                    res.errors.append(f"page {page}: {item}")
                    continue
                if item.item_key in all_ids:
                    continue
                all_ids.add(item.item_key)
                new += 1
                if item.name.lower().startswith(prefix):
                    res.offers.append(item)
            if new == 0 or (total and len(all_ids) >= total):
                break
        hoya = {o.item_key for o in res.offers}
        for name, sort in RANK_SORTS:
            if self.config.get("ranks") is False:
                break
            try:
                order = _ranked(fetch, url, sort, len(all_ids))
            except FetchError as exc:
                res.errors.append(f"{name} order: {exc}")
                continue
            res.ranks[name] = [k for k in order if k in hoya]
        return res


# The shop's own sort orders, read as a demand signal (JTL "Sortierung" values).
RANK_SORTS = (("bestseller", 11), ("newest", 6))


def _ranked(fetch, url: str, sort: int, expected: int) -> list[str]:
    """Item ids in the order the shop lists them when sorted by `sort`, over all pages."""
    order: list[str] = []
    for page in range(1, 41):
        html = fetch(f"{url}?Sortierung={sort}" if page == 1 else f"{url}_s{page}?Sortierung={sort}")
        items, _ = parse_category(html)
        new = [i.item_key for i in items if not isinstance(i, str) and i.item_key not in order]
        order += new
        if not new or len(order) >= expected:
            break
    return order


def parse_category(html: str) -> tuple[list, int | None]:
    """Returns (offers or error strings, total count shown by the shop)."""
    tree = HTMLParser(html)
    m = TOTAL_RE.search(clean(tree.body.text(separator=" ")) if tree.body else "")
    total = int(m.group(1)) if m else None
    items, seen = [], set()
    for box in tree.css("div.productbox"):
        id_input = box.css_first("input[name=a]")
        pid = id_input.attributes.get("value") if id_input else None
        if not pid or pid in seen:
            continue
        seen.add(pid)
        try:
            items.append(parse_box(box, pid))
        except Exception as exc:
            items.append(f"item {pid}: {type(exc).__name__}: {exc}")
    return items, total


def _attr(node: Node | None, name: str) -> str | None:
    return node.attributes.get(name) if node else None


def parse_box(box: Node, pid: str) -> Offer:
    title = box.css_first(".productbox-title")
    name = clean(title.text()) if title else ""
    if not name:
        raise ValueError("no name")
    url = _attr(box.css_first("meta[itemprop=url]"), "content") or _attr(title.css_first("a"), "href")

    status_node = (
        box.css_first(".delivery-status .status")
        or box.css_first(".delivery-status .signal_image")
        or box.css_first(".delivery-status")
    )
    status_text = clean(status_node.text()) if status_node else None
    status_class = _attr(status_node, "class") or ""
    schema = _attr(box.css_first("link[itemprop=availability]"), "href")

    availability = availability_from_text(status_text)
    if availability == "unknown":
        m = re.search(r"status-(\d)", status_class)
        availability = {"0": "sold_out", "1": "low", "2": "available"}.get(m.group(1) if m else "", "unknown")
    if availability == "unknown":
        availability = availability_from_schema(schema)

    image = None
    for img in box.css("img"):
        src = img.attributes.get("src") or ""
        if src and "keinBild" not in src:
            image = src
            break

    return Offer(
        item_key=pid,
        item_no=pid,
        name=name,
        url=url,
        image_url=image,
        price=parse_price(_attr(box.css_first("meta[itemprop=price]"), "content")),
        currency=_attr(box.css_first("meta[itemprop=priceCurrency]"), "content") or "EUR",
        availability_text=status_text,
        availability=availability,
        raw={
            "ribbons": [clean(r.text()) for r in box.css(".ribbon")],
            "status_class": status_class or None,
            "schema_availability": schema,
        },
    )
