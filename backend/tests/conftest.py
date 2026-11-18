import os

import pytest

DB = os.environ.get("TEST_DATABASE_URL")
if DB:
    os.environ["DATABASE_URL"] = DB


@pytest.fixture(scope="session")
def db():
    if not DB:
        pytest.skip("TEST_DATABASE_URL not set")
    from app import migrate
    from app.db import pool

    migrate.run()
    pool.open(wait=True)
    yield pool
    pool.close()
