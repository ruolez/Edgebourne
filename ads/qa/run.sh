#!/bin/sh
# End-to-end QA against the dev stack. The fake Meta keeps its state in memory, so every run
# starts from a fresh one (and a fresh sync); a second run without this sees the first run's
# test campaigns and fails on them. Meta reads cached in the database go too.
set -e
cd "$(dirname "$0")/.."
docker restart edgebourne-fake-meta edgebourne-ads-backend >/dev/null
sleep 6
docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -c "import db, insights; db.execute('DELETE FROM meta_cache'); db.execute('DELETE FROM status_events'); db.execute('DELETE FROM alerts'); insights.sync_structure(); db.execute('DELETE FROM ad_versions')" >/dev/null
node qa/flows.cjs
