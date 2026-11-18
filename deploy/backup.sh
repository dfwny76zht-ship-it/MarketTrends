#!/usr/bin/env bash
# Nightly database dump, kept 14 days. Called from /etc/cron.d/markettrends-backup.
set -euo pipefail
dir=/opt/markettrends/backups
mkdir -p "$dir"
file="$dir/markettrends_$(date +%F).sql.gz"
docker compose -f /opt/markettrends/app/docker-compose.yml exec -T db \
    pg_dump -U markettrends markettrends | gzip > "$file.tmp"
mv "$file.tmp" "$file"
find "$dir" -name 'markettrends_*.sql.gz' -mtime +14 -delete
echo "$(date -Is) backup ok: $file"
