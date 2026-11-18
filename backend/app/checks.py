"""robots.txt check: the first real run. One request per shop, 5 s apart."""

import logging
import threading
import time
from urllib import robotparser
from urllib.parse import urlsplit

import httpx

from . import config, ntfy
from .db import pool

log = logging.getLogger("checks")

_run_lock = threading.Lock()
_last_request = 0.0


def _wait_for_gap() -> None:
    gap = config.REQUEST_GAP_SECONDS - (time.monotonic() - _last_request)
    if gap > 0:
        time.sleep(gap)


def check_robots(url: str) -> dict:
    global _last_request
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    _wait_for_gap()
    try:
        resp = httpx.get(
            robots_url,
            headers={"User-Agent": config.USER_AGENT},
            timeout=20,
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        return {"result": "error", "http_status": None, "error": f"{type(exc).__name__}: {exc}"}
    finally:
        _last_request = time.monotonic()

    status = resp.status_code
    if status in (403, 429):
        return {"result": "blocked", "http_status": status, "error": f"robots.txt answered {status}"}
    if status in (404, 410):
        return {"result": "no_robots", "http_status": status, "error": None}
    if status >= 400:
        return {"result": "error", "http_status": status, "error": f"robots.txt answered {status}"}

    parser = robotparser.RobotFileParser()
    parser.parse(resp.text.splitlines())
    if not parser.can_fetch(config.USER_AGENT, url):
        return {"result": "disallowed", "http_status": status, "error": "robots.txt disallows the shop URL"}
    delay = parser.crawl_delay(config.USER_AGENT)
    note = f"crawl-delay {delay} s" if delay else None
    return {"result": "allowed", "http_status": status, "error": note}


def run_robots(shop_ids: list[int] | None = None, notify: bool = False) -> None:
    """Nightly: all shops except paused / not allowed. Manual: the given shops, any status."""
    with _run_lock:
        with pool.connection() as conn:
            if shop_ids:
                shops = conn.execute(
                    "SELECT id, name, url FROM shops WHERE id = ANY(%s) ORDER BY id", (shop_ids,)
                ).fetchall()
            else:
                shops = conn.execute(
                    "SELECT id, name, url FROM shops"
                    " WHERE status NOT IN ('paused', 'not_allowed') ORDER BY id"
                ).fetchall()

        problems = []
        for shop in shops:
            with pool.connection() as conn:
                run_id = conn.execute(
                    "INSERT INTO runs (shop_id, kind) VALUES (%s, 'robots') RETURNING id", (shop["id"],)
                ).fetchone()["id"]
            try:
                res = check_robots(shop["url"])
            except Exception as exc:  # never leave a run open
                log.exception("robots check crashed for %s", shop["name"])
                res = {"result": "error", "http_status": None, "error": f"{type(exc).__name__}: {exc}"}
            with pool.connection() as conn:
                conn.execute(
                    "UPDATE runs SET finished_at = now(), result = %s, http_status = %s, error = %s WHERE id = %s",
                    (res["result"], res["http_status"], res["error"], run_id),
                )
                conn.execute(
                    "UPDATE shops SET robots_checked_at = now(), robots_result = %s WHERE id = %s",
                    (res["result"], shop["id"]),
                )
            if res["result"] in ("blocked", "disallowed", "error"):
                problems.append(f"{shop['name']}: {res['error'] or res['result']}")

        if notify and problems:
            ntfy.send("Market Trends: robots.txt check", "\n".join(problems), tags=["warning"])


def start_in_background(shop_id: int) -> None:
    threading.Thread(target=run_robots, args=([shop_id],), daemon=True).start()
