"""Weekly product details from a JTL product page (Ben's Jungle): article number, pot size from the
description, delivery time, discount badge and the shop's "Kunden kauften dazu" (bought together) list.
No database or network code here."""

from __future__ import annotations

import re

from selectolax.parser import HTMLParser

from . import jtl
from .base import clean, size_cm

SKU = re.compile(r'itemprop="sku"[^>]*>\s*([A-Za-z]*\d+)\s*<')
DELIVERY = re.compile(r"Lieferzeit:?\s*(?:<[^>]+>\s*)*(\d+\s*-\s*\d+\s*Werktage)")
STATUS = re.compile(r'class="[^"]*delivery-status[^"]*"[^>]*>\s*(?:<[^>]+>\s*)*([^<]{3,40}?)\s*<')
SALE = re.compile(r'class="ribbon[^"]*"[^>]*>\s*Sale\s*(\d+)\s*%', re.I)
ALSO = "Kunden kauften dazu"
IMG_ID = re.compile(r"/media/image/product/(\d+)/")


POT = re.compile(r"(\d+(?:[.,]\d)?)\s*cm[ -]?(?:Topf|Rundtopf|Ampel|Pot)", re.I)
SIZE_LINE = re.compile(r"Gr(?:ö|oe)(?:ß|ss)e:([^.]{0,80})", re.I)


def _pot(text: str) -> str | None:
    """Pot size from the description: 'Größe: Bewurzelte Pflanze im 5cm Topf' -> '5 cm'."""
    m = SIZE_LINE.search(text)
    if m and size_cm(m.group(1)):
        return size_cm(m.group(1))
    m = POT.search(text)
    return f"{m.group(1).replace(',', '.')} cm" if m else None


def parse_details(html: str) -> dict:
    i = html.find(ALSO)
    main, also = (html[:i], html[i:]) if i >= 0 else (html, "")
    tree = HTMLParser(main)
    text = clean(tree.body.text(separator=" ")) if tree.body else ""
    sku = SKU.search(main)
    dl = DELIVERY.search(main)
    st = STATUS.search(main)
    sale = SALE.findall(main)
    bought: list[str] = []
    if also:
        items, _ = jtl.parse_category(also)
        bought = [it.item_key for it in items if not isinstance(it, str)]
        if not bought:  # older markup: the article id is in the image path
            bought = list(dict.fromkeys(IMG_ID.findall(also)))
    return {
        "sku": sku.group(1) if sku else None,
        "pot_size": _pot(text),
        "delivery": clean(dl.group(1)) if dl else None,
        "availability_text": clean(st.group(1)) if st else None,
        "discount_pct": int(sale[-1]) if sale else None,
        "also_bought": bought[:24],
    }
