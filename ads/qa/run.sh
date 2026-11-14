#!/bin/sh
# End-to-end QA against the dev stack. The fake Meta keeps its state in memory, so every run
# starts from a fresh one (and a fresh sync); a second run without this sees the first run's
# test campaigns and fails on them. Meta reads cached in the database go too.
# Exits non-zero when any check FAILs or a page logs a console error (flows.cjs sets the code).
# QA_ONLY='edit' (or 'core,link,edit', any of them) runs the shared setup plus only those check blocks of
# flows.cjs while iterating; unset runs everything (see the header of qa/flows.cjs).
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
# The Ads Manager link (AM-A / AM-B): a run that stopped inside its block leaves the fake link connected, drafts behind and
# account 2 reading the fake's Tokyo Test KK (the block's own ad account for it; FU-A's picker expects it free).
docker exec edgebourne-postgres psql -U edgebourne -d ebads -qtAc "UPDATE am_link SET state = 'not_connected', client_kind = NULL, connected_as = NULL, connected_at = NULL, last_ok_at = NULL, last_error = NULL, fallback_reason = NULL, connect_requested_at = NULL, scope = NULL WHERE id = 1; DELETE FROM am_link_runs WHERE pass_hash NOT LIKE 'ACCT%'; DELETE FROM am_snapshots WHERE scope = ''; DELETE FROM am_drafts WHERE source IS DISTINCT FROM 'ACCT2MARKsrc'; DELETE FROM alerts WHERE rule IN ('link_down', 'draft_new', 'draft_problems'); DELETE FROM settings WHERE key ~ '^meta_ad_account_id@[0-9]+$' AND value = '4445556667778889'" >/dev/null
node qa/flows.cjs
