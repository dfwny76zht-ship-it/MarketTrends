"""Exchange rates from the European Central Bank (one request per day, only when a non-EUR price shows up)."""

import logging
import re
from decimal import Decimal

import httpx

from . import config
from .db import pool

log = logging.getLogger("fx")
ECB_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
_RATE_RE = re.compile(r"currency='([A-Z]{3})' rate='([\d.]+)'")
_DAY_RE = re.compile(r"time='(\d{4}-\d{2}-\d{2})'")


def per_eur(currency: str) -> Decimal | None:
    """How many units of `currency` one euro buys, from the newest stored ECB day (fetched if older than today)."""
    if currency == "EUR":
        return Decimal(1)
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT day, per_eur FROM fx_rates WHERE currency = %s ORDER BY day DESC LIMIT 1", (currency,)
        ).fetchone()
        today = conn.execute("SELECT (now() AT TIME ZONE 'Europe/Berlin')::date AS d").fetchone()["d"]
    if row and (today - row["day"]).days <= 3:
        return row["per_eur"]
    try:
        xml = httpx.get(ECB_URL, headers={"User-Agent": config.USER_AGENT}, timeout=20).text
        day = _DAY_RE.search(xml).group(1)
        with pool.connection() as conn:
            for cur, rate in _RATE_RE.findall(xml):
                conn.execute(
                    "INSERT INTO fx_rates (day, currency, per_eur) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (day, cur, rate),
                )
        rates = dict(_RATE_RE.findall(xml))
        return Decimal(rates[currency]) if currency in rates else (row["per_eur"] if row else None)
    except Exception as exc:
        log.warning("ECB rates unavailable: %s", exc)
        return row["per_eur"] if row else None
