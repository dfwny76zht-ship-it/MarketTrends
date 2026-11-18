import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import analytics, archive, auth, collect, collector, config, groupings, images, markus, migrate, shops, taxa, taxonomy, trends
from .db import pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

scheduler = BackgroundScheduler(timezone=config.TIMEZONE)
scheduler.add_job(
    collect.nightly,
    "cron",
    hour=3,
    minute=0,
    id="nightly",
    coalesce=True,
    misfire_grace_time=3600,
)
# Photos after the night run (it takes ~45 min); waits for the run lock if that runs longer.
scheduler.add_job(images.nightly, "cron", hour=4, minute=45, id="images", coalesce=True, misfire_grace_time=3600)
scheduler.add_job(
    collector.check_overdue, "cron", hour=6, minute=0, id="pi_overdue", coalesce=True, misfire_grace_time=3600,
)
scheduler.add_job(
    trends.weekly_summary,
    "cron",
    day_of_week="mon",
    hour=8,
    minute=0,
    id="weekly_summary",
    coalesce=True,
    misfire_grace_time=6 * 3600,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate.run()
    pool.open(wait=True)
    with pool.connection() as conn:  # runs cut off by a restart would otherwise show "Running" forever
        conn.execute(
            "UPDATE runs SET finished_at = now(), result = 'error', error = 'interrupted (app restarted)'"
            " WHERE finished_at IS NULL"
        )
    taxonomy.seed()
    taxonomy.backfill_size_classes()
    taxonomy.match_pending()
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)
    pool.close()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(auth.router)
app.include_router(shops.router)
app.include_router(taxa.router)
app.include_router(analytics.router)
app.include_router(trends.router)
app.include_router(groupings.router)
app.include_router(images.router)
app.include_router(collector.router)
app.include_router(markus.router)
app.include_router(archive.router)


@app.get("/api/health")
def health():
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return {"ok": True}


STATIC = Path(__file__).resolve().parent.parent / "static"
if STATIC.is_dir():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
