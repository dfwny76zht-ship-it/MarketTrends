#!/usr/bin/env bash
# Run on Hetzner as markettrends: publish the investor page. The data stays frozen unless REFRESH=1.
set -euo pipefail
cd /opt/markettrends/app
out=/opt/markettrends/markus
mkdir -p "$out"
if [ "${REFRESH:-0}" = "1" ] || [ ! -f "$out/data.json" ]; then
    docker compose exec -T app python - < investor/markus/export.py > /tmp/markus_export.json
    python3 investor/markus/build.py /tmp/markus_export.json "$out/data.json.new"
    mv "$out/data.json.new" "$out/data.json"
    rm -f /tmp/markus_export.json
fi
cp investor/markus/site/index.html investor/markus/site/app.js investor/markus/site/style.css investor/markus/site/echarts.min.js "$out/"
chmod -R a+rX "$out"
echo "published $(git log --oneline -1)"
