"""Reads archived Kakteen-Haage pages (Wayback copies, 2018 →). OXID shop, two layouts:
- 2018: <li class="productData" itemscope Product> with itemprop name / price;
- 2019 →: <div class="productData … productBox"> with the price in <span class="lead text-nowrap">.
Every offer carries its article id (hidden input "aid"). Prices are consumer prices incl. VAT.
Product pages (…/Hoya-xyz.html) give one offer, and say when it is sold out.
"""

from __future__ import annotations

import html as htmlmod
import re
from datetime import datetime

AID = re.compile(r'name="aid" value="(\d+)"')
NAME_SPAN = re.compile(r'<span(?: itemprop="name")?>\s*([^<]*?Hoya[^<]*?)\s*</span>', re.I)
TITLE_ATTR = re.compile(r'class="title"[^>]*title="([^"]+)"')
PRICE_ITEMPROP = re.compile(r'itemprop="price"[^>]*>\s*([\d.]+,\d{2}|\d+[.,]\d{2})')
PRICE_LEAD = re.compile(r'class="lead text-nowrap"[^>]*>\s*([\d.]*\d+,\d{2})')
SOLD_OUT = re.compile(r"ausverkauft|sold out|nicht lieferbar|not available", re.I)


def _price(s: str | None) -> float | None:
    if not s:
        return None
    s = s.strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _name(raw: str) -> str:
    name = htmlmod.unescape(raw)
    name = re.sub(r"[$*]+", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def parse_category(text: str, captured_at: datetime) -> list[dict]:
    out = []
    blocks = re.split(r'class="productData', text)[1:]
    for b in blocks:
        b = b[:6000]
        aid = AID.search(b)
        title = TITLE_ATTR.search(b) or NAME_SPAN.search(b)
        price = PRICE_LEAD.search(b) or PRICE_ITEMPROP.search(b)
        if not (aid and title and price):
            continue
        name = _name(title.group(1))
        if not name.lower().startswith("hoya"):
            continue
        p = _price(price.group(1))
        if p is None:
            continue
        out.append({"item_key": aid.group(1), "name": name, "price": p, "pot": None, "height": None, "grower": None,
                    "availability": "unknown", "observed_at": captured_at, "note": "category page"})
    return out


def parse_product(text: str, captured_at: datetime) -> list[dict]:
    aid = AID.search(text)
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S)
    name = _name(re.sub(r"<[^>]+>", " ", h1.group(1))) if h1 else ""
    price = PRICE_ITEMPROP.search(text) or PRICE_LEAD.search(text)
    if not (aid and name.lower().startswith("hoya") and price):
        return []
    p = _price(price.group(1))
    if p is None:
        return []
    main = text[h1.end():h1.end() + 15000] if h1 else text
    availability = "sold_out" if SOLD_OUT.search(main) else "available"
    return [{"item_key": aid.group(1), "name": name, "price": p, "pot": None, "height": None, "grower": None,
             "availability": availability, "observed_at": captured_at, "note": "product page"}]


def parse_archived(text: str, url: str, kind: str, captured_at: datetime) -> list[dict]:
    return parse_category(text, captured_at) if kind == "category" else parse_product(text, captured_at)
