#!/usr/bin/env bash
# Nightly database dump, kept 14 days. Called from /etc/cron.d/markettrends-backup.
set -euo pipefail
umask 077
dir=/opt/markettrends/backups
mkdir -p "$dir"
file="$dir/markettrends_$(date +%F).sql.gz"
cd /opt/markettrends/app
docker compose exec -T db \
    pg_dump -U markettrends markettrends | gzip > "$file.tmp"
mv "$file.tmp" "$file"
find "$dir" -name 'markettrends_*.sql.gz' -mtime +14 -delete
# Raw pages: copy new files only (they never change; names are their fingerprint), for the Pi to pull.
mkdir -p "$dir/snapshots"
docker run --rm --user "$(id -u):$(id -g)" --entrypoint cp \
    -v markettrends_snapshots:/s:ro -v "$dir/snapshots":/out markettrends-app -rn /s/. /out/
echo "$(date -Is) backup ok: $file"
