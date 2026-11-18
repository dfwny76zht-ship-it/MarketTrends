"""Polite page fetching for one collection run: robots.txt, gaps, conditional requests, raw page storage."""

import gzip
import hashlib
import os
import time
from pathlib import Path

import httpx

from . import config
from .adapters import Blocked, Disallowed, FetchError
from .adapters.base import is_challenge  # noqa: F401  (re-exported for tests)
from .db import pool


class Fetcher:
    def __init__(self, shop_id: int, run_id: int, robots_parser, delay: float):
        self.shop_id = shop_id
        self.run_id = run_id
        self.parser = robots_parser
        self.delay = max(config.MIN_GAP_SECONDS, delay or 0)
        self.requests = 0
        self.unchanged = 0
        self._last = 0.0
        self._client = httpx.Client(
            headers={"User-Agent": config.USER_AGENT}, timeout=30, follow_redirects=True
        )

    def close(self) -> None:
        self._client.close()

    def _wait(self) -> None:
        gap = self.delay - (time.monotonic() - self._last)
        if gap > 0:
            time.sleep(gap)

    def get(self, url: str) -> str:
        if self.parser is not None and not self.parser.can_fetch(config.USER_AGENT, url):
            raise Disallowed(f"robots.txt forbids {url}")

        with pool.connection() as conn:
            prev = conn.execute(
                "SELECT sha256, path, etag, last_modified FROM snapshots"
                " WHERE shop_id = %s AND url = %s ORDER BY fetched_at DESC LIMIT 1",
                (self.shop_id, url),
            ).fetchone()
        headers = {}
        if prev and prev["etag"]:
            headers["If-None-Match"] = prev["etag"]
        if prev and prev["last_modified"]:
            headers["If-Modified-Since"] = prev["last_modified"]

        self._wait()
        try:
            resp = self._client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise FetchError(f"{url}: {type(exc).__name__}") from exc
        finally:
            self._last = time.monotonic()
            self.requests += 1

        status = resp.status_code
        if status in (403, 429) or (status == 200 and is_challenge(resp.content)):
            raise Blocked(status, url)
        if status == 304 and prev:
            body = gzip.decompress((Path(config.SNAPSHOT_DIR) / prev["path"]).read_bytes())
            sha, path = prev["sha256"], prev["path"]
            etag = resp.headers.get("etag") or prev["etag"]
            last_modified = resp.headers.get("last-modified") or prev["last_modified"]
            self.unchanged += 1
            text = body.decode("utf-8", errors="replace")
        elif status >= 400 or status == 304:
            raise FetchError(f"{url}: HTTP {status}")
        else:
            body = resp.content
            sha = hashlib.sha256(body).hexdigest()
            path = f"{self.shop_id}/{sha[:2]}/{sha}.gz"
            full = Path(config.SNAPSHOT_DIR) / path
            if not full.exists():
                full.parent.mkdir(parents=True, exist_ok=True)
                tmp = full.with_suffix(".tmp")
                tmp.write_bytes(gzip.compress(body))
                os.replace(tmp, full)
            etag = resp.headers.get("etag")
            last_modified = resp.headers.get("last-modified")
            text = resp.text

        with pool.connection() as conn:
            conn.execute(
                "INSERT INTO snapshots (shop_id, run_id, url, http_status, sha256, path, etag, last_modified)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (self.shop_id, self.run_id, url, status, sha, path, etag, last_modified),
            )
        return text
