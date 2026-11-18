"""Pi collector path against a throwaway Postgres: due jobs, claiming, upload, parsing, storing."""

import base64
import gzip
from datetime import datetime, timezone
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures"
URL = "https://pi-shop.example/Hoya"


@pytest.fixture(scope="module")
def shop(db, tmp_path_factory):
    from app import config

    config.SNAPSHOT_DIR = str(tmp_path_factory.mktemp("snaps"))
    with db.connection() as conn:
        return conn.execute(
            "INSERT INTO shops (name, url, host, adapter, adapter_config, collector, status, price_basis)"
            " VALUES ('PiShop', %s, 'pi-shop.example', 'jtl', %s, 'pi', 'in_setup', 'gross') RETURNING *",
            (URL, '{"category_url": "%s", "name_prefix": "hoya"}' % URL),
        ).fetchone()


def test_manual_request_becomes_a_job_once(db, shop):
    from app import collector

    assert all(j["shop_id"] != shop["id"] for j in collector.jobs("pi"))  # in setup, not requested
    with db.connection() as conn:
        conn.execute("UPDATE shops SET run_requested_at = now() WHERE id = %s", (shop["id"],))
    jobs = [j for j in collector.jobs("pi") if j["shop_id"] == shop["id"]]
    assert len(jobs) == 1 and jobs[0]["manual"] and jobs[0]["adapter"] == "jtl"
    assert all(j["shop_id"] != shop["id"] for j in collector.jobs("pi"))  # claimed


def test_upload_is_parsed_and_stored(db, shop):
    from app import collector

    html = gzip.decompress((FIX / "uhlig_hoya_p1.html.gz").read_bytes())
    page = lambda url: collector.Page(url=url, status=200, body_gz_b64=base64.b64encode(gzip.compress(html)).decode())
    body = collector.Upload(shop_id=shop["id"], started_at=datetime.now(timezone.utc),
                            robots={"result": "allowed", "crawl_delay": 5.0},
                            pages=[page(URL), page(URL + "_s2")], outcome="ok", manual=True)
    pages = {p.url: (p, html) for p in body.pages}
    problem = collector.process_upload(shop, body, pages)
    assert problem is None
    with db.connection() as conn:
        run = conn.execute("SELECT * FROM runs WHERE shop_id = %s ORDER BY id DESC LIMIT 1", (shop["id"],)).fetchone()
        n = conn.execute("SELECT count(*) AS n FROM listings WHERE shop_id = %s", (shop["id"],)).fetchone()["n"]
        snaps = conn.execute("SELECT count(*) AS n FROM snapshots WHERE run_id = %s", (run["id"],)).fetchone()["n"]
    assert run["result"] == "ok" and run["offers_found"] == 19 and run["details"]["collector"] == "pi"
    assert n == 19 and snaps == 2


def test_blocked_upload_backs_off(db, shop):
    from app import collector

    body = collector.Upload(shop_id=shop["id"], started_at=datetime.now(timezone.utc),
                            robots={"result": "allowed"}, pages=[], outcome="blocked",
                            error=f"{URL} answered bot check page", http_status=200)
    problem = collector.process_upload(shop, body, {})
    assert "blocked (bot check page)" in problem
    with db.connection() as conn:
        s = conn.execute("SELECT backoff_days, next_run_after FROM shops WHERE id = %s", (shop["id"],)).fetchone()
    assert s["backoff_days"] == 1 and s["next_run_after"] is not None
