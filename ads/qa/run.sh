#!/bin/sh
# End-to-end QA against the dev stack. The fake Meta keeps its state in memory, so every run
# starts from a fresh one (and a fresh sync); a second run without this sees the first run's
# test campaigns and fails on them. Meta reads cached in the database go too.
# Exits non-zero when any check FAILs or a page logs a console error (flows.cjs sets the code).
set -e
cd "$(dirname "$0")/.."
docker restart edgebourne-fake-meta edgebourne-ads-backend >/dev/null
sleep 6
docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -c "import db, insights; db.execute('DELETE FROM meta_cache'); db.execute('DELETE FROM status_events'); db.execute('DELETE FROM alerts'); insights.sync_structure(); db.execute('DELETE FROM ad_versions')" >/dev/null
# Client reports (W2) of every account start unsent, with emailing off and the default review.
docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python -c "import account_ctx, db
with account_ctx.all_accounts():
    db.execute('DELETE FROM client_reports'); db.execute(\"DELETE FROM alerts WHERE rule IN ('report_review', 'report_sent')\")
    db.execute(\"DELETE FROM settings WHERE key ~ '^report_(review|email|last_sent|sent_to)(@[0-9]+)?$'\")" >/dev/null
# "Did it work?" (D3): a run that stopped half-way leaves its seeded campaigns and spend behind; they go first.
docker cp dev/seed_checks.py edgebourne-ads-backend:/tmp/seed_checks.py >/dev/null
docker exec -w /app -e WORKERS_ENABLED=0 edgebourne-ads-backend python /tmp/seed_checks.py --clean >/dev/null
node qa/flows.cjs
