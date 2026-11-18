"""Collection runs: fetch with the shop's adapter, check the result, store offers, derive events."""

import logging
import statistics
import threading
from datetime import datetime, timezone
from decimal import Decimal

from psycopg.types.json import Jsonb

from . import checks, fx, names, ntfy, taxonomy
from .adapters import REGISTRY, Blocked, Disallowed, FetchError, Offer
from .db import pool
from .fetching import Fetcher

log = logging.getLogger("collect")

COLLECT_STATUSES = ("active", "adapter_broken")
BACKOFF_STEPS = (1, 2, 4, 7)


def _finish(run_id: int, result: str, error: str | None = None, **extra) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = now(), result = %s, error = %s, http_status = %s,"
            " offers_found = %s, events_found = %s, pages = %s, details = %s WHERE id = %s",
            (
                result,
                error,
                extra.get("http_status"),
                extra.get("offers"),
                extra.get("events"),
                extra.get("pages"),
                Jsonb(extra.get("details") or {}),
                run_id,
            ),
        )


def _backoff(shop_id: int) -> int:
    with pool.connection() as conn:
        current = conn.execute("SELECT backoff_days FROM shops WHERE id = %s", (shop_id,)).fetchone()["backoff_days"]
        nxt = next((d for d in BACKOFF_STEPS if d > current), BACKOFF_STEPS[-1])
        conn.execute(
            "UPDATE shops SET backoff_days = %s, next_run_after = now() + make_interval(days => %s) WHERE id = %s",
            (nxt, nxt, shop_id),
        )
    return nxt


def _health_problem(shop_id: int, n_offers: int, n_errors: int) -> str | None:
    if n_offers == 0:
        return "no offers found"
    if n_errors > max(2, n_offers * 0.1):
        return f"{n_errors} parse errors"
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT offers_found FROM runs WHERE shop_id = %s AND kind = 'collect' AND result = 'ok'"
            " ORDER BY started_at DESC LIMIT 7",
            (shop_id,),
        ).fetchall()
    usual = [r["offers_found"] for r in rows if r["offers_found"]]
    if usual:
        median = statistics.median(usual)
        if abs(n_offers - median) > 0.5 * median:
            return f"{n_offers} offers, usually {median:g}"
    return None


def _eur_net(price: Decimal | None, currency: str | None, basis: str | None, vat_rate) -> Decimal | None:
    if price is None or not currency:
        return None
    rate = fx.per_eur(currency)
    if not rate:
        return None
    value = Decimal(price) / Decimal(rate)
    if basis != "net":
        value = value / (1 + Decimal(vat_rate) / 100)
    return value.quantize(Decimal("0.0001"))


def _store(shop: dict, run_id: int, offers: list[Offer], complete: bool, now: datetime | None = None) -> int:
    """Writes listings, observations and events. Returns the number of events."""
    now = now or datetime.now(timezone.utc)
    basis = shop["price_basis"] or "gross"
    events = 0
    seen: list[int] = []
    unique: dict[str, Offer] = {}
    for o in offers:
        unique.setdefault(o.item_key, o)

    with pool.connection() as conn:
        baseline = conn.execute(
            "SELECT NOT EXISTS (SELECT 1 FROM listings WHERE shop_id = %s) AS b", (shop["id"],)
        ).fetchone()["b"]

        def event(listing_id, kind, old=None, new=None, obs=None, prev_obs=None):
            nonlocal events
            events += 1
            conn.execute(
                "INSERT INTO events (listing_id, run_id, kind, happened_at, old_value, new_value,"
                " observation_id, previous_observation_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (listing_id, run_id, kind, now, old, new, obs, prev_obs),
            )

        for o in unique.values():
            listing = conn.execute(
                "SELECT id, gone_since FROM listings WHERE shop_id = %s AND item_key = %s",
                (shop["id"], o.item_key),
            ).fetchone()
            if listing:
                listing_id, returned = listing["id"], listing["gone_since"] is not None
                conn.execute(
                    "UPDATE listings SET item_no = %s, name = %s, url = %s, category = %s, image_url = %s,"
                    " last_seen = %s, gone_since = NULL WHERE id = %s",
                    (o.item_no, o.name, o.url, o.category, o.image_url, now, listing_id),
                )
            else:
                listing_id, returned = conn.execute(
                    "INSERT INTO listings (shop_id, item_key, item_no, name, url, category, image_url, first_seen, last_seen)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                    (shop["id"], o.item_key, o.item_no, o.name, o.url, o.category, o.image_url, now, now),
                ).fetchone()["id"], False
            seen.append(listing_id)

            prev = conn.execute(
                "SELECT id, price, currency, availability, quantity FROM observations"
                " WHERE listing_id = %s ORDER BY observed_at DESC LIMIT 1",
                (listing_id,),
            ).fetchone()
            obs_id = conn.execute(
                "INSERT INTO observations (listing_id, run_id, observed_at, price, currency, price_basis, tier_prices,"
                " price_eur_net, availability_text, availability, quantity, pot_size, plant_size, raw, size_class)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    listing_id, run_id, now, o.price, o.currency, basis,
                    Jsonb(o.tier_prices) if o.tier_prices else None,
                    _eur_net(o.price, o.currency, basis, shop["vat_rate"]),
                    o.availability_text, o.availability, o.quantity, o.pot_size, o.plant_size, Jsonb(o.raw),
                    names.size_class(o.pot_size, o.name),
                ),
            ).fetchone()["id"]

            in_stock = o.availability in ("available", "low")
            if not listing:
                if not baseline:  # first run of a shop is the starting point, not news
                    event(listing_id, "new", new=o.availability, obs=obs_id)
                continue
            if returned:
                if in_stock:
                    event(listing_id, "back_in_stock", "gone", o.availability, obs_id, prev["id"] if prev else None)
                continue
            if not prev:
                continue
            was_in_stock = prev["availability"] in ("available", "low")
            if prev["availability"] == "sold_out" and in_stock:
                event(listing_id, "back_in_stock", prev["availability"], o.availability, obs_id, prev["id"])
            elif was_in_stock and o.availability == "sold_out":
                event(listing_id, "sold_out", prev["availability"], o.availability, obs_id, prev["id"])
            if prev["quantity"] is not None and o.quantity is not None and o.quantity > prev["quantity"]:
                event(listing_id, "restock", str(prev["quantity"]), str(o.quantity), obs_id, prev["id"])
            if (
                prev["price"] is not None and o.price is not None
                and prev["currency"] == o.currency and Decimal(prev["price"]) != o.price
            ):
                event(listing_id, "price_change", str(prev["price"]), str(o.price), obs_id, prev["id"])

        if complete:
            gone = conn.execute(
                "UPDATE listings SET gone_since = %s WHERE shop_id = %s AND gone_since IS NULL"
                " AND NOT (id = ANY(%s)) RETURNING id",
                (now, shop["id"], seen),
            ).fetchall()
            for row in gone:
                event(row["id"], "disappeared")
    return events


def collect_one(shop_id: int) -> str | None:
    """One collection run for one shop. Caller holds checks.run_lock. Returns a problem text, or None."""
    with pool.connection() as conn:
        shop = conn.execute("SELECT * FROM shops WHERE id = %s", (shop_id,)).fetchone()
        run_id = conn.execute(
            "INSERT INTO runs (shop_id, kind) VALUES (%s, 'collect') RETURNING id", (shop_id,)
        ).fetchone()["id"]
    name = shop["name"]
    adapter_cls = REGISTRY.get(shop["adapter"] or "")
    if not adapter_cls:
        _finish(run_id, "error", "no adapter set")
        return f"{name}: no adapter set"

    robots = checks.fetch_robots(shop["url"])
    checks.record_robots(shop_id, robots)
    if robots["result"] == "blocked":
        days = _backoff(shop_id)
        _finish(run_id, "blocked", f"{robots['error']}; next try in {days} d", http_status=robots["http_status"])
        return f"{name}: blocked ({robots['http_status']}), next try in {days} d"
    if robots["result"] in ("disallowed", "error"):
        _finish(run_id, robots["result"], robots["error"], http_status=robots["http_status"])
        return f"{name}: {robots['error']}"

    adapter = adapter_cls(shop["adapter_config"] or {})
    fetcher = Fetcher(shop_id, run_id, robots.get("parser"), robots.get("crawl_delay") or 0)
    try:
        result = adapter.collect(fetcher.get)
    except Blocked as exc:
        days = _backoff(shop_id)
        _finish(run_id, "blocked", f"{exc}; next try in {days} d", http_status=exc.status, pages=fetcher.requests)
        return f"{name}: blocked ({'bot check' if exc.status == 200 else exc.status}), next try in {days} d"
    except (Disallowed, FetchError) as exc:
        _finish(run_id, "error", str(exc), pages=fetcher.requests)
        return f"{name}: {exc}"
    except Exception as exc:
        log.exception("collection crashed for %s", name)
        _finish(run_id, "error", f"{type(exc).__name__}: {exc}", pages=fetcher.requests)
        return f"{name}: adapter crashed ({type(exc).__name__})"
    finally:
        fetcher.close()

    details = {
        "adapter": f"{adapter.key} v{adapter.version}",
        "expected_total": result.expected_total,
        "complete": result.complete,
        "unchanged_pages": fetcher.unchanged,
        "errors": result.errors[:20],
    }
    n = len({o.item_key for o in result.offers})
    problem = _health_problem(shop_id, n, len(result.errors))
    if problem:
        with pool.connection() as conn:
            conn.execute(
                "UPDATE shops SET status = 'adapter_broken', updated_at = now() WHERE id = %s AND status = 'active'",
                (shop_id,),
            )
        _finish(run_id, "broken", problem, offers=n, pages=fetcher.requests, details=details)
        return f"{name}: adapter broken – {problem}"

    events = _store(shop, run_id, result.offers, result.complete)
    try:
        taxonomy.match_pending(shop_id)
    except Exception:
        log.exception("matching species failed for %s", name)
    with pool.connection() as conn:
        recovered = conn.execute(
            "UPDATE shops SET backoff_days = 0, next_run_after = NULL,"
            " status = CASE WHEN status = 'adapter_broken' THEN 'active' ELSE status END"
            " WHERE id = %s RETURNING (%s = 'adapter_broken') AS recovered",
            (shop_id, shop["status"]),
        ).fetchone()["recovered"]
    _finish(run_id, "ok", "; ".join(result.errors[:3]) or None, offers=n, events=events,
            pages=fetcher.requests, details=details)
    return f"{name}: adapter works again ({n} offers)" if recovered else None


def nightly() -> None:
    """Every shop once: collection if it has a working adapter, otherwise just the robots.txt check."""
    started = datetime.now(timezone.utc)
    with pool.connection() as conn:
        shops = conn.execute(
            "SELECT s.id, s.name, s.url, s.adapter, s.status,"
            " (s.next_run_after IS NOT NULL AND s.next_run_after > now()) AS waiting,"
            " EXISTS (SELECT 1 FROM runs r WHERE r.shop_id = s.id AND r.kind = 'collect'"
            "   AND (r.started_at AT TIME ZONE 'Europe/Berlin')::date = (now() AT TIME ZONE 'Europe/Berlin')::date)"
            "   AS collected_today"
            " FROM shops s WHERE s.status NOT IN ('paused', 'not_allowed') ORDER BY s.id"
        ).fetchall()
    problems = []
    with checks.run_lock:
        for shop in shops:
            try:
                if shop["adapter"] and shop["status"] in COLLECT_STATUSES:
                    if shop["waiting"] or shop["collected_today"]:
                        continue
                    problem = collect_one(shop["id"])
                else:
                    problem = checks.robots_one(shop)
            except Exception as exc:
                log.exception("nightly run failed for %s", shop["name"])
                problem = f"{shop['name']}: {type(exc).__name__}"
            if problem:
                problems.append(problem)
    if problems:
        ntfy.send("Market Trends: night run", "\n".join(problems), tags=["warning"])
    try:
        from .analytics import watchlist_events_since

        with pool.connection() as conn:
            lines = watchlist_events_since(conn, started)
        if lines:
            more = f"\n… and {len(lines) - 15} more" if len(lines) > 15 else ""
            ntfy.send("Market Trends: watchlist", "\n".join(lines[:15]) + more, tags=["seedling"])
    except Exception:
        log.exception("watchlist message failed")


def collect_in_background(shop_id: int) -> None:
    def work():
        with checks.run_lock:
            collect_one(shop_id)

    threading.Thread(target=work, daemon=True).start()


def reparse_run(run_id: int) -> str:
    """Parses the raw pages stored by an earlier run again (no requests to the shop) and stores the result
    under that run, if it hasn't been stored yet."""
    import gzip
    from pathlib import Path

    from . import config

    with pool.connection() as conn:
        run = conn.execute("SELECT * FROM runs WHERE id = %s AND kind = 'collect'", (run_id,)).fetchone()
        if not run:
            return "run not found"
        if run["result"] == "ok":
            return "run already stored"
        shop = conn.execute("SELECT * FROM shops WHERE id = %s", (run["shop_id"],)).fetchone()
        pages = {
            r["url"]: r["path"]
            for r in conn.execute(
                "SELECT DISTINCT ON (url) url, path FROM snapshots WHERE run_id = %s ORDER BY url, id DESC", (run_id,)
            )
        }

    def fetch(url: str) -> str:
        if url not in pages:
            raise FetchError(f"{url}: not stored in run {run_id}")
        return gzip.decompress((Path(config.SNAPSHOT_DIR) / pages[url]).read_bytes()).decode("utf-8", "replace")

    adapter = REGISTRY[shop["adapter"]](shop["adapter_config"] or {})
    result = adapter.collect(fetch)
    n = len({o.item_key for o in result.offers})
    problem = _health_problem(shop["id"], n, len(result.errors))
    details = dict(run["details"] or {}, reparsed=f"{adapter.key} v{adapter.version}", errors=result.errors[:20],
                   complete=result.complete)
    if problem:
        _finish(run_id, "broken", problem, offers=n, pages=run["pages"], details=details)
        return f"still broken: {problem}"
    events = _store(shop, run_id, result.offers, result.complete, now=run["started_at"])
    taxonomy.match_pending(shop["id"])
    _finish(run_id, "ok", "; ".join(result.errors[:3]) or None, offers=n, events=events, pages=run["pages"],
            details=details)
    return f"stored {n} offers, {events} events"
