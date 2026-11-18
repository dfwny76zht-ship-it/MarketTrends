"""robots.txt check. Used on its own for shops without an adapter, and before every collection run."""

import logging
import threading
import time
from urllib import robotparser
from urllib.parse import urlsplit

import httpx

from . import config
from .db import pool

log = logging.getLogger("checks")

# One run at a time across the whole tool (robots checks and collection runs).
run_lock = threading.Lock()
_last_request = 0.0


def _wait_for_gap() -> None:
    gap = config.REQUEST_GAP_SECONDS - (time.monotonic() - _last_request)
    if gap > 0:
        time.sleep(gap)


def fetch_robots(url: str) -> dict:
    """Returns result, http_status, error, and for collection: parser (None = allow all) and crawl_delay."""
    global _last_request
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    _wait_for_gap()
    try:
        resp = httpx.get(robots_url, headers={"User-Agent": config.USER_AGENT}, timeout=20, follow_redirects=True)
    except httpx.HTTPError as exc:
        return {"result": "error", "http_status": None, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        _last_request = time.monotonic()

    status = resp.status_code
    if status in (403, 429):
        return {"result": "blocked", "http_status": status, "error": f"robots.txt answered {status}"}
    if status in (404, 410):
        return {"result": "no_robots", "http_status": status, "error": None, "parser": None, "crawl_delay": None}
    if status >= 400:
        return {"result": "error", "http_status": status, "error": f"robots.txt answered {status}"}

    parser = robotparser.RobotFileParser()
    parser.parse(resp.text.splitlines())
    delay = parser.crawl_delay(config.USER_AGENT)
    delay = float(delay) if delay else None
    if not parser.can_fetch(config.USER_AGENT, url):
        return {"result": "disallowed", "http_status": status, "error": "robots.txt disallows the shop URL"}
    return {
        "result": "allowed",
        "http_status": status,
        "error": f"crawl-delay {delay:g} s" if delay else None,
        "parser": parser,
        "crawl_delay": delay,
    }


def record_robots(shop_id: int, res: dict) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE shops SET robots_checked_at = now(), robots_result = %s, crawl_delay = %s WHERE id = %s",
            (res["result"], res.get("crawl_delay"), shop_id),
        )


def robots_one(shop: dict) -> str | None:
    """robots.txt check as its own run. Returns a problem text for ntfy, or None."""
    with pool.connection() as conn:
        run_id = conn.execute(
            "INSERT INTO runs (shop_id, kind) VALUES (%s, 'robots') RETURNING id", (shop["id"],)
        ).fetchone()["id"]
    try:
        res = fetch_robots(shop["url"])
    except Exception as exc:  # never leave a run open
        log.exception("robots check crashed for %s", shop["name"])
        res = {"result": "error", "http_status": None, "error": f"{type(exc).__name__}: {exc}"}
    with pool.connection() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = now(), result = %s, http_status = %s, error = %s WHERE id = %s",
            (res["result"], res["http_status"], res["error"], run_id),
        )
    record_robots(shop["id"], res)
    if res["result"] in ("blocked", "disallowed", "error"):
        return f"{shop['name']}: {res['error'] or res['result']}"
    return None


def check_in_background(shop_id: int) -> None:
    def work():
        with run_lock:
            with pool.connection() as conn:
                shop = conn.execute("SELECT id, name, url FROM shops WHERE id = %s", (shop_id,)).fetchone()
            if shop:
                robots_one(shop)

    threading.Thread(target=work, daemon=True).start()
