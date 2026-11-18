#!/usr/bin/env bash
# Run on Hetzner as user markettrends: fetch the newest version and rebuild.
set -euo pipefail
cd /opt/markettrends/app
git pull --ff-only
docker compose up -d --build
docker image prune -f >/dev/null
for i in $(seq 1 30); do
    if curl -fsS http://127.0.0.1:8090/api/health >/dev/null 2>&1; then
        echo "Market Trends is up ($(git log --oneline -1))"
        exit 0
    fi
    sleep 2
done
echo "Health check failed" >&2
docker compose logs --tail 50 app >&2
exit 1
