#!/usr/bin/env bash
# Runs all backend tests on the server against a throwaway Postgres (never the real database).
set -euo pipefail
cd /opt/markettrends/app
docker compose build -q app
net=mt-test-$$
cleanup() { docker rm -f "$net-db" >/dev/null 2>&1 || true; docker network rm "$net" >/dev/null 2>&1 || true; }
trap cleanup EXIT
docker network create "$net" >/dev/null
docker run -d --name "$net-db" --network "$net" -e POSTGRES_PASSWORD=test postgres:17 >/dev/null
for i in $(seq 1 30); do docker exec "$net-db" pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done
sleep 2
docker run --rm --network "$net" --user root \
    -e TEST_DATABASE_URL="postgresql://postgres:test@$net-db:5432/postgres" \
    -v /opt/markettrends/app/backend/tests:/app/tests:ro \
    markettrends-app sh -c "pip install -q pytest==8.3.4 2>/dev/null && python -m pytest -q -p no:cacheprovider tests"
