#!/usr/bin/env python3
"""Market Trends collector on the lab Pi.

Every 10 minutes (systemd timer): ask Hetzner which shops are due, fetch their pages politely from the lab's
connection with the shop's adapter (downloaded fresh from Hetzner), and send the raw pages back. Nothing is kept
here. Needs MT_URL and MT_TOKEN in the environment.
"""

import base64
import fcntl
import gzip
import io
import logging
import os
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from urllib import robotparser
from urllib.parse import urlsplit

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("mt-collector")

BASE = os.environ["MT_URL"].rstrip("/")
TOKEN = os.environ["MT_TOKEN"]
LOCK = "/tmp/mt-collector.lock"


def load_adapters(api: httpx.Client):
    data = api.get("/api/collector/adapters.tar.gz").raise_for_status().content
    target = tempfile.mkdtemp(prefix="mt-adapters-")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.startswith("adapters/") or ".." in member.name:
                raise RuntimeError(f"unexpected file in adapter bundle: {member.name}")
        tar.extractall(target)  # names checked above (Python 3.11.2 has no extraction filter)
    sys.path.insert(0, target)
    import adapters  # noqa: E402

    return adapters


def robots_for(web: httpx.Client, url: str) -> dict:
    parts = urlsplit(url)
    try:
        r = web.get(f"{parts.scheme}://{parts.netloc}/robots.txt")
    except httpx.HTTPError as exc:
        return {"result": "error", "error": f"{type(exc).__name__}", "status": None}
    if r.status_code in (403, 429):
        return {"result": "blocked", "error": f"robots.txt answered {r.status_code}", "status": r.status_code}
    if r.status_code in (404, 410):
        return {"result": "no_robots", "status": r.status_code, "parser": None, "crawl_delay": None}
    if r.status_code >= 400:
        return {"result": "error", "error": f"robots.txt answered {r.status_code}", "status": r.status_code}
    parser = robotparser.RobotFileParser()
    parser.parse(r.text.splitlines())
    return {"result": "allowed", "status": r.status_code, "parser": parser,
            "crawl_delay": float(parser.crawl_delay("MarketTrends") or 0) or None}


def run_job(job: dict, adapters, api: httpx.Client) -> None:
    ua = job["user_agent"]
    started = datetime.now(timezone.utc)
    web = httpx.Client(headers={"User-Agent": ua}, timeout=30, follow_redirects=True)
    pages, outcome, error, http_status = [], "ok", None, None
    robots = robots_for(web, job["url"])
    parser = robots.get("parser")
    if robots["result"] == "allowed" and not parser.can_fetch(ua, job["url"]):
        robots["result"], robots["error"] = "disallowed", "robots.txt disallows the shop URL"

    if robots["result"] in ("blocked", "disallowed", "error"):
        outcome, error, http_status = robots["result"], robots.get("error"), robots.get("status")
    else:
        gap = max(job.get("min_gap", 5), robots.get("crawl_delay") or 0)
        last = [time.monotonic()]

        def fetch(url: str) -> str:
            if parser is not None and not parser.can_fetch(ua, url):
                raise adapters.Disallowed(f"robots.txt forbids {url}")
            wait = gap - (time.monotonic() - last[0])
            if wait > 0:
                time.sleep(wait)
            try:
                r = web.get(url)
            except httpx.HTTPError as exc:
                raise adapters.FetchError(f"{url}: {type(exc).__name__}") from exc
            finally:
                last[0] = time.monotonic()
            pages.append({"url": url, "status": r.status_code,
                          "body_gz_b64": base64.b64encode(gzip.compress(r.content)).decode(),
                          "etag": r.headers.get("etag"), "last_modified": r.headers.get("last-modified")})
            if r.status_code in (403, 429) or (r.status_code == 200 and adapters.base.is_challenge(r.content)):
                raise adapters.Blocked(r.status_code, url)
            if r.status_code >= 400:
                raise adapters.FetchError(f"{url}: HTTP {r.status_code}")
            return r.text

        try:
            adapters.REGISTRY[job["adapter"]](job["config"]).collect(fetch)
        except adapters.Blocked as exc:
            outcome, error, http_status = "blocked", str(exc), exc.status
        except adapters.Disallowed as exc:
            outcome, error = "disallowed", str(exc)
        except Exception as exc:
            outcome, error = "error", f"{type(exc).__name__}: {exc}"
    web.close()

    payload = {
        "shop_id": job["shop_id"], "started_at": started.isoformat(), "pages": pages, "outcome": outcome,
        "error": error, "http_status": http_status, "manual": job.get("manual", False),
        "robots": {"result": robots["result"], "crawl_delay": robots.get("crawl_delay")},
    }
    r = api.post("/api/collector/result", json=payload, timeout=120)
    r.raise_for_status()
    log.info("%s: %s, %d pages sent", job["name"], outcome, len(pages))


def main() -> None:
    with open(LOCK, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log.info("previous run still going")
            return
        api = httpx.Client(base_url=BASE, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=60)
        jobs = api.get("/api/collector/jobs").raise_for_status().json()
        if not jobs:
            return
        adapters = load_adapters(api)
        for job in jobs:
            try:
                run_job(job, adapters, api)
            except Exception:
                log.exception("job for %s failed", job.get("name"))


if __name__ == "__main__":
    main()
