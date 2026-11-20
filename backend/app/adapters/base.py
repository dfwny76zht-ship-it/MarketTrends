"""Shared pieces for adapters. No database or network code here, so adapters stay testable."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable

Fetch = Callable[[str], str]


class Blocked(Exception):
    """The shop answered 403 or 429: stop the run."""

    def __init__(self, status: int, url: str):
        reason = "bot check page" if status == 200 else str(status)
        super().__init__(f"{url} answered {reason}")
        self.status = status
        self.url = url


class Disallowed(Exception):
    """robots.txt forbids this URL."""


class FetchError(Exception):
    """Network error or unexpected HTTP status for one page."""


# Bot-protection pages that come back with HTTP 200 instead of the shop's content.
CHALLENGE_MARKERS = ("please enable javascript to continue", "<title>just a moment...</title>", "cf-challenge", "_cf_chl_opt")


def is_challenge(body: bytes) -> bool:
    if len(body) > 60_000:
        return False
    head = body.decode("utf-8", errors="replace").lower()
    return any(m in head for m in CHALLENGE_MARKERS)


@dataclass
class Offer:
    item_key: str
    name: str
    url: str | None = None
    item_no: str | None = None
    category: str | None = None
    image_url: str | None = None
    price: Decimal | None = None
    currency: str | None = None
    tier_prices: list[dict] | None = None
    availability_text: str | None = None
    availability: str = "unknown"
    quantity: int | None = None
    pot_size: str | None = None
    plant_size: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class CollectResult:
    offers: list[Offer] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    expected_total: int | None = None
    complete: bool = True
    # The shop's own sort orders (demand signal): list name -> item_keys, best first.
    ranks: dict[str, list[str]] = field(default_factory=dict)


class Adapter:
    key = ""
    version = "1"

    def __init__(self, config: dict):
        self.config = config

    def collect(self, fetch: Fetch) -> CollectResult:
        raise NotImplementedError


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_price(value) -> Decimal | None:
    """'18,00 €', '€1.44', '1.44', 12.5 -> Decimal."""
    if value is None:
        return None
    s = re.sub(r"[^\d,.\-]", "", str(value))
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def size_cm(text: str | None) -> str | None:
    """First 'NN cm' / 'NNcm' in a text -> '12 cm'."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*cm\b", text or "", re.I)
    return f"{m.group(1).replace(',', '.')} cm" if m else None


_SOLD_OUT = ("nicht verfügbar", "ausverkauft", "nicht lieferbar", "vergriffen", "out of stock", "sold out")
_LOW = ("knapp", "wenige", "geringer", "low stock")
_AVAILABLE = ("sofort", "auf lager", "verfügbar", "lieferbar", "in stock", "available")


def availability_from_text(text: str | None) -> str:
    t = (text or "").lower()
    if any(w in t for w in _SOLD_OUT):
        return "sold_out"
    if any(w in t for w in _LOW):
        return "low"
    if any(w in t for w in _AVAILABLE):
        return "available"
    return "unknown"


def availability_from_schema(href: str | None) -> str:
    h = (href or "").lower()
    if "outofstock" in h or "soldout" in h or "discontinued" in h:
        return "sold_out"
    if "limitedavailability" in h:
        return "low"
    if "instock" in h or "preorder" in h:
        return "available"
    return "unknown"
