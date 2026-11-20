"""Reads archived JTL shop pages (Wayback copies): Ben's Jungle, Uhlig. Two template generations:
- "Evo" (until about 2023): product cells `result-wrapper_buy_form_<id>`, name in h4.title, price in
  <strong class="price"><span>5,90 €</span>, status in `signal_image status-N`; pages often ISO-8859-1.
- "NOVA" (2024 →): the same markup the live adapter reads (div.productbox, meta itemprop=price).
Every offer carries the shop's article id (kArtikel, hidden input "a"), the same key the live
adapter uses, so archived and live sightings land on one listing. Prices are consumer prices incl. VAT.
Product pages give one offer, and say whether it was available.
"""

from __future__ import annotations

import html as htmlmod
import re
from datetime import datetime

from . import jtl

EVO_CELL = re.compile(r'id="result-wrapper_buy_form_(\d+)"')
EVO_NAME = re.compile(r'<h4 class="title"[^>]*>\s*<a[^>]*>(.*?)</a>', re.S)
EVO_PRICE = re.compile(r'class="price[^"]*"[^>]*>\s*<span>\s*([\d.]*\d+,\d{2})')
STATUS_N = re.compile(r"status-(\d)")
CURRENT = re.compile(r'<input[^>]*(?:id="AktuellerkArtikel"|current_article)[^>]*>')
VALUE = re.compile(r'value="(\d+)"')
META_PRICE = re.compile(r'itemprop="price"[^>]*content="([\d.]+)"')
SCHEMA_AV = re.compile(r'itemprop="availability"[^>]*href="[^"]*/(\w+)"')
SOLD_OUT = re.compile(r"item not available|nicht verf|ausverkauft|sold out|derzeit nicht", re.I)
RIBBON = re.compile(r'class="ribbon[^"]*"[^>]*>\s*([^<]+?)\s*<')
POT = re.compile(r"(\d+(?:[.,]\d)?)\s*cm[ -]?Topf", re.I)
SKU = re.compile(r'itemprop="sku"[^>]*>\s*([A-Za-z]*\d+)\s*<')
DELIVERY = re.compile(r"Lieferzeit:?\s*(?:<[^>]+>\s*)*(\d+\s*-\s*\d+\s*Werktage)")


def _clean(s: str) -> str:
    s = htmlmod.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()


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


def _avail_from_status(n: str | None) -> str:
    return {"0": "sold_out", "1": "low", "2": "available"}.get(n or "", "unknown")


def _offer(key, name, price, availability, at, note, **extra) -> dict:
    return {"item_key": key, "name": name, "price": price, "pot": extra.pop("pot", None), "height": None,
            "grower": None, "availability": availability, "observed_at": at, "note": note, **extra}


def parse_category(text: str, captured_at: datetime) -> list[dict]:
    out, seen = [], set()
    # NOVA (current template): same as the live shop
    if "productbox" in text:
        items, _ = jtl.parse_category(text)
        for i, it in enumerate(x for x in items if not isinstance(x, str)):
            if it.item_key in seen or not it.name.lower().startswith("hoya") or it.price is None:
                continue
            seen.add(it.item_key)
            out.append(_offer(it.item_key, it.name, float(it.price), it.availability, captured_at, "category page",
                              ribbons=it.raw.get("ribbons") or []))
        return out
    # Evo (older template)
    starts = [m for m in EVO_CELL.finditer(text)]
    for n, m in enumerate(starts):
        block = text[m.start(): starts[n + 1].start() if n + 1 < len(starts) else m.start() + 8000]
        key = m.group(1)
        name_m, price_m = EVO_NAME.search(block), EVO_PRICE.search(block)
        if key in seen or not (name_m and price_m):
            continue
        name = _clean(name_m.group(1))
        price = _price(price_m.group(1))
        if not name.lower().startswith("hoya") or price is None:
            continue
        seen.add(key)
        st = STATUS_N.search(block)
        out.append(_offer(key, name, price, _avail_from_status(st.group(1) if st else None), captured_at, "category page",
                          ribbons=[r for r in RIBBON.findall(block)]))
    return out


def parse_product(text: str, captured_at: datetime) -> list[dict]:
    cur = CURRENT.search(text)
    key_m = VALUE.search(cur.group(0)) if cur else None
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S)
    if not (key_m and h1):
        return []
    name = _clean(h1.group(1))
    if not name.lower().startswith("hoya"):
        return []
    main = text[h1.end(): h1.end() + 20000]
    price_m = META_PRICE.search(main) or META_PRICE.search(text)
    price = _price(price_m.group(1)) if price_m else None
    if price is None:
        return []
    st = STATUS_N.search(main)
    av = SCHEMA_AV.search(main)
    if st:
        availability = _avail_from_status(st.group(1))
    elif av:
        availability = "available" if av.group(1).lower() in ("instock", "limitedavailability") else "sold_out"
    else:
        availability = "unknown"
    if availability == "unknown" and SOLD_OUT.search(main[:6000]):
        availability = "sold_out"
    pot = POT.search(text)
    sku = SKU.search(text)
    dl = DELIVERY.search(main)
    rib = RIBBON.search(text[:h1.start()]) or RIBBON.search(main[:8000])
    return [_offer(key_m.group(1), name, price, availability, captured_at, "product page",
                   pot=f"{pot.group(1)} cm" if pot else None, sku=sku.group(1) if sku else None,
                   delivery=_clean(dl.group(1)) if dl else None, ribbons=[rib.group(1)] if rib else [])]


def parse_archived(text: str, url: str, kind: str, captured_at: datetime) -> list[dict]:
    return parse_category(text, captured_at) if kind == "category" else parse_product(text, captured_at)
