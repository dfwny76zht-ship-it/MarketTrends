"""Reads archived FlorAccess pages (Wayback Machine copies, 2019 → today).

Three page types, all with machine-readable data:
- category pages 2019–2020: an embedded store with every offer ("version": price in cents, pot and
  height in metres, grower id) plus name maps for products and growers;
- grower offer pages /v/<id>/<grower>/<plant>/ (2019–2023) and product pages /product/<id>/
  (2023 →): one offer each, with a schema.org Product block (price in EUR) and pot / height in the
  title, description or label text. Out-of-stock pages say when the offer was last available.
Nothing is guessed: a page without a readable price gives no offer.
"""

from __future__ import annotations

import html as htmlmod
import json
import re
from datetime import datetime, timezone

OFFER_URL = re.compile(r"/v/(\d+)/([^/]+)/")
PRODUCT_URL = re.compile(r"/product/(\d+)/")
TITLE_SIZES = re.compile(r"\(\s*P\s*([\d.,]+)\s*cm\s*H\s*([\d.,\s\-–]+?)\s*cm\s*\)", re.I)
POT_TEXT = [
    re.compile(r"Topfdurchmesser:\s*([\d.,]+)\s*cm", re.I),
    re.compile(r"Pot (?:diameter|size)[^:\d]{0,20}:?\s*([\d.,]+)\s*cm", re.I),
    re.compile(r"Topfgr(?:ö|oe)(?:ß|ss)e[^\d]{0,30}([\d.,]+)\s*cm", re.I),
    re.compile(r"Potmaat[^\d]{0,20}([\d.,]+)\s*cm", re.I),
]
HEIGHT_TEXT = [
    re.compile(r"H(?:ö|oe)he,?\s*inkl(?:usive|\.)?\s*Topf:?\s*([\d.,]+(?:\s*[-–]\s*[\d.,]+)?)\s*cm", re.I),
    re.compile(r"Height,?\s*(?:incl(?:uding|\.)?\s*pot)?:?\s*([\d.,]+(?:\s*[-–]\s*[\d.,]+)?)\s*cm", re.I),
    re.compile(r"Hoogte[^\d]{0,20}([\d.,]+(?:\s*[-–]\s*[\d.,]+)?)\s*cm", re.I),
]
LAST_AVAILABLE = re.compile(r"last available on ([A-Z][a-z]+ \d{1,2}, \d{4})", re.I)

GROWERS = [
    (r"velden", "Van der Velden"), (r"arend", "Van der Arend"), (r"gasa", "Gasa DK"), (r"elstgeest", "Elstgeest"),
    (r"feldborg", "Feldborg"), (r"meyst", "De Meyst Werner"), (r"duijn", "Duijn-Hove"), (r"ruba", "Ruba Baers"),
    (r"giromagi", "Giromagi"), (r"jm-?plants", "JM Plants"), (r"ammerlaan", "Ammerlaan"), (r"kokodama", "Kokodama"),
]


def grower_name(raw: str | None) -> str | None:
    """Same grower appears under several spellings (hkw-van-der-velden, handelskwekerij-van-der-velden …)."""
    if not raw:
        return None
    low = raw.lower()
    for pat, name in GROWERS:
        if re.search(pat, low):
            return name
    words = re.sub(r"[-_.]+", " ", raw).strip()
    return " ".join(w.capitalize() if w.islower() else w for w in words.split())


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _cm(v: str | None) -> str | None:
    if not v:
        return None
    v = re.sub(r"\s+", "", v).replace("–", "-").replace(",", ".")
    parts = [p.rstrip(".") for p in v.split("-") if p]
    parts = [str(int(float(p))) if float(p) == int(float(p)) else str(float(p)) for p in parts if re.fullmatch(r"[\d.]+", p)]
    return f"{'-'.join(parts)} cm" if parts else None


def _json_after(text: str, key: str) -> dict | None:
    """The JSON object that follows "key": in a big embedded script (balanced braces)."""
    i = text.find(f'"{key}":{{')
    if i < 0:
        return None
    start = text.index("{", i)
    depth, j, in_str, esc = 0, start, False, False
    while j < len(text):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:j + 1])
                except ValueError:
                    return None
        j += 1
    return None


def _ld_product(text: str) -> dict | None:
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', text, re.S):
        try:
            d = json.loads(m.group(1))
        except ValueError:
            continue
        for item in d if isinstance(d, list) else [d]:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item
    return None


def _eur_price(offers) -> float | None:
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if not isinstance(offers, dict):
        return None
    if offers.get("priceCurrency") == "EUR" and offers.get("price") not in (None, ""):
        return _num(str(offers["price"]))
    for spec in offers.get("priceSpecification") or []:
        if spec.get("priceCurrency") == "EUR":
            return _num(str(spec.get("price")))
    return None


def _availability(offers) -> str:
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    a = (offers or {}).get("availability", "")
    if "InStock" in a:
        return "available"
    if "OutOfStock" in a or "SoldOut" in a:
        return "sold_out"
    return "unknown"


def parse_category(text: str, captured_at: datetime) -> list[dict]:
    """2019–2020 category pages: every offer from the embedded store."""
    versions = _json_after(text, "version") or {}
    products = _json_after(text, "product") or {}
    orgs = _json_after(text, "organization") or {}
    out = []
    for vid, v in versions.items():
        if not isinstance(v, dict) or "price" not in v or "product" not in v:
            continue
        name = (products.get(str(v["product"])) or {}).get("name")
        if not name or "hoya" not in name.lower():
            continue
        pot = (v.get("potSizeRange") or {}).get("from")
        hp = v.get("heightProduct") or {}
        h_from, h_to = hp.get("from"), hp.get("to")
        height = None
        if h_from:
            height = f"{round(h_from * 100):g}" + (f"-{round(h_to * 100):g}" if h_to and h_to != h_from else "") + " cm"
        org = orgs.get(str(v.get("organization"))) or {}
        out.append({
            "item_key": str(vid), "name": htmlmod.unescape(name), "price": round(v["price"] / 100, 2),
            "pot": f"{round(pot * 100, 1):g} cm" if pot else None, "height": height,
            "grower": grower_name(org.get("name")), "availability": "unknown",
            "observed_at": captured_at, "note": "category page",
        })
    return out


def parse_single(text: str, url: str, captured_at: datetime) -> list[dict]:
    """Grower offer page (/v/) or product page (/product/): one offer."""
    ld = _ld_product(text)
    if not ld:
        return []
    price = _eur_price(ld.get("offers"))
    if price is None:
        return []
    name = htmlmod.unescape(str(ld.get("name") or "")).strip()
    title = re.search(r"<title>(.*?)</title>", text, re.S)
    title = htmlmod.unescape(title.group(1)) if title else ""
    if not name:
        name = re.split(r"\s+[–—-]\s+", title)[0].strip()
    name = TITLE_SIZES.sub("", name).strip()
    m = OFFER_URL.search(url) or PRODUCT_URL.search(url)
    item_key = m.group(1) if m else str(ld.get("sku") or "")
    grower = grower_name(OFFER_URL.search(url).group(2)) if OFFER_URL.search(url) else None

    pot = height = None
    ts = TITLE_SIZES.search(title)
    if ts:
        pot, height = _cm(ts.group(1)), _cm(ts.group(2))
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))
    meta = " ".join(re.findall(r'<meta[^>]+content="([^"]*)"', text))
    for src in (meta, plain):
        if not pot:
            for rx in POT_TEXT:
                mm = rx.search(src)
                if mm:
                    pot = _cm(mm.group(1))
                    break
        if not height:
            for rx in HEIGHT_TEXT:
                mm = rx.search(src)
                if mm:
                    height = _cm(mm.group(1))
                    break

    availability = _availability(ld.get("offers"))
    observed_at, note = captured_at, "product page" if "/product/" in url else "grower offer page"
    if availability == "sold_out":
        # The price shown is the one from when it was last available.
        la = LAST_AVAILABLE.search(plain)
        if la:
            try:
                observed_at = datetime.strptime(la.group(1), "%B %d, %Y").replace(tzinfo=timezone.utc)
                availability, note = "available", f"{note}; price from last availability"
            except ValueError:
                pass
        else:
            own = _json_after(text, item_key) if item_key else None   # this offer's own entry in the store
            last = (own or {}).get("lastAvailable")
            if isinstance(last, int) and last > 10**9:
                observed_at = datetime.fromtimestamp(last, tz=timezone.utc)
                availability, note = "available", f"{note}; price from last availability"
    return [{
        "item_key": item_key, "name": name, "price": price, "pot": pot, "height": height, "grower": grower,
        "availability": availability, "observed_at": observed_at, "note": note,
    }]


def parse_archived(text: str, url: str, kind: str, captured_at: datetime) -> list[dict]:
    if kind == "category":
        return parse_category(text, captured_at)
    return parse_single(text, url, captured_at)
