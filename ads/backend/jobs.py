"""One background thread per gunicorn worker: processes webhook deliveries as
soon as they arrive, pulls the latest from Meta every few minutes (Settings, Automatic
refresh) and syncs a full week every hour. A Postgres advisory lock
keeps two workers from doing the same job at once."""
import logging
import threading
import time

import config
import db

log = logging.getLogger(__name__)

_event = threading.Event()
_started = False
SYNC_EVERY = 3600


def wake():
    _event.set()


def _locked(conn, key):
    with conn.cursor() as cur:
        cur.execute("SELECT pg_try_advisory_lock(%s)", (key,))
        return cur.fetchone()[0]


def _loop():
    import crm_events
    import insights
    import leads
    import notify
    import refresh_api
    import settings_store

    import account_ctx

    last_sync, last_auto_try, last_alerts = {}, {}, {}
    ALERTS_EVERY = 900

    def quick(acct):
        """What can't wait: new leads, replies, Claude's schedules, reminders, lead stages, report
        emails. Done for every account before any slow Meta pull. Errors stay inside the job."""
        for name, job in (("new leads", leads.process_pending_events),
                          ("announcing new leads", leads.announce_pending),
                          ("lead quality backfill", lambda: __import__("lead_quality_store").backfill_once()),
                          ("Meta status webhooks", lambda: __import__("status_history").process_webhooks()),
                          ("lead replies", lambda: __import__("replies").process_pending()),
                          ("Desk schedules", lambda: __import__("schedules").run()),
                          ("lead reminders", lambda: __import__("reminders").run()),
                          ("lead stages to Meta", crm_events.process_pending),
                          ("approvals cut off mid-apply", lambda: __import__("ads_api").sweep_applying()),
                          ("client report emails", lambda: __import__("reports_api").send_due())):
            try:
                job()
            except Exception:
                log.exception("account %s: %s failed", acct, name)

    def quick_all(accounts):
        for acct in accounts:
            with account_ctx.use(acct), db.reusing():
                quick(acct)
        try:
            notify.process_pending()  # one queue for everyone
        except Exception:
            log.exception("sending alerts failed")

    def slow(conn, acct):
        """The account's Meta reads: the automatic pull, the hourly sync, alerts, tests, advice."""
        now = time.time()
        pulled = False
        if acct not in last_sync:  # after a restart, carry on from the last sync instead of pulling at once
            last_sync[acct] = synced_at(settings_store.get("last_performance_sync"))
        if settings_store.get("meta_system_token") and settings_store.get("meta_ad_account_id") and refresh_api.auto_due(
                settings_store.get("last_refresh_at"), last_auto_try.get(acct), now,
                refresh_api.auto_minutes(settings_store.get("auto_refresh_minutes"))):
            try:
                pulled = refresh_api.pull_latest(conn) is not None
                last_auto_try.pop(acct, None)
            except Exception as exc:
                last_auto_try[acct] = now
                log.info("account %s: automatic refresh skipped: %s", acct, exc)
        if settings_store.get("meta_ad_account_id") and time.time() - last_sync.get(acct, 0) > SYNC_EVERY:
            synced_now = False
            try:
                # Under the account's pull lock (D1): never alongside a Refresh or a numbers pull, whose before/after
                # reads would count this sync's writes as Meta's corrections. A held lock: the next pass tries.
                with refresh_api.holding_pull_lock(acct) as mine:
                    if mine:
                        last_sync[acct] = time.time()
                        # A pull in this pass has just read the structure (and its video pictures): only the week's results are left.
                        insights.sync_all(days=7, structure=not pulled)
                        pulled = synced_now = True
            except Exception as exc:  # Meta not configured yet, network, …
                last_sync[acct] = time.time()
                log.info("account %s: meta sync skipped: %s", acct, exc)
            if synced_now:
                try:
                    insights.backfill_daily()  # once per ad account: results from before the first sync
                except Exception as exc:
                    log.info("account %s: older results not read yet: %s", acct, exc)
        try:
            # D1: once a night (4 AM, account time) read the older days again and compare with Ads Manager's totals;
            # the alerts right below then say so in the same pass.
            import numbers_check
            if numbers_check.run_nightly():
                pulled = True
        except Exception as exc:
            log.info("account %s: numbers check skipped: %s", acct, exc)
        if pulled or time.time() - last_alerts.get(acct, 0) > ALERTS_EVERY:
            last_alerts[acct] = time.time()
            try:
                import alerts
                alerts.run()
            except Exception:
                log.exception("account %s: alert rules failed", acct)
            try:
                import change_checks_db
                change_checks_db.run()
            except Exception:
                log.exception("account %s: did it work failed", acct)
            try:
                import meta_tests
                meta_tests.sync_running()
            except Exception:
                log.exception("account %s: reading Meta A/B tests failed", acct)
            if settings_store.get("meta_system_token") and settings_store.get("meta_ad_account_id"):
                for name, mod in (("Meta's advice", "advice_api"), ("tracking health", "tracking_api")):
                    try:
                        __import__(mod).refresh_if_stale()
                    except Exception as exc:
                        log.info("account %s: %s not read: %s", acct, name, exc)

    last_prune = 0.0
    while True:
        _event.wait(timeout=30)
        _event.clear()
        conn = None
        try:
            conn = db.connect()
            if _locked(conn, 7001):
                try:
                    import telegram
                    telegram.poll_updates(conn)
                except Exception as exc:
                    log.info("telegram updates skipped: %s", exc)
                accounts = [r["id"] for r in db.query("SELECT id FROM accounts WHERE archived_at IS NULL ORDER BY id")]
                quick_all(accounts)
                for acct in accounts:
                    if _event.is_set():  # a lead arrived while another account was pulling: tell people first
                        _event.clear()
                        quick_all(accounts)
                    with account_ctx.use(acct), db.reusing():
                        try:
                            slow(conn, acct)
                        except Exception:
                            log.exception("account %s: worker pass failed", acct)
                if time.time() - last_prune > PRUNE_EVERY:
                    last_prune = time.time()
                    try:
                        prune()
                    except Exception:
                        log.exception("pruning old rows failed")
                beat()
        except Exception:
            log.exception("worker pass failed")
        finally:
            if conn is not None:
                conn.close()  # releases the advisory lock


def synced_at(value):
    """The unix time of a stored ISO timestamp; 0 when there's none."""
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def beat():
    """The worker's heartbeat: /api/health and Today read it to tell when the worker stopped."""
    import settings_store
    from datetime import datetime, timezone
    settings_store.set("worker_last_pass", datetime.now(timezone.utc).isoformat(timespec="seconds"))


def worker_expected():
    """Dev and tests run without the worker (WORKERS_ENABLED=0): no banner there."""
    return config.WORKERS_ENABLED


_BOOTED = time.time()


def worker_stale(last_pass, now, limit=600, booted=None):
    """True when the worker hasn't finished a pass within `limit` seconds. A freshly started process
    gets `limit` seconds of grace (an Update restarts it; its first pass may still be running)."""
    if now - (_BOOTED if booted is None else booted) < limit:
        return False
    at = synced_at(last_pass)
    return not at or now - at > limit


PRUNE_EVERY = 86400
# What grows forever otherwise. Meta changes and leads are kept: they are the record.
PRUNE = (
    ("activity", "at < now() - interval '180 days'"),
    ("notifications", "status IN ('sent','failed','skipped') AND created_at < now() - interval '90 days'"),
    ("webhook_events", "processed_at IS NOT NULL AND received_at < now() - interval '90 days'"),
    ("meta_cache", "fetched_at < now() - interval '30 days'"),
    ("alerts", "resolved_at IS NOT NULL AND resolved_at < now() - interval '180 days'"),
    ("alert_snoozes", "ended_at IS NOT NULL AND ended_at < now() - interval '180 days'"),
    ("numbers_runs", "started_at < now() - interval '180 days'"),
    # Read marks of alerts (30 days in the Inbox) and leads (7) whose item has left the feed. A pending proposal
    # stays in it however old, so its mark stays (audit A3-131).
    ("inbox_reads", "item_key NOT LIKE 'proposal:%' AND read_at < now() - interval '35 days'"),
)


def prune():
    import account_ctx
    with account_ctx.all_accounts():
        for table, where in PRUNE:
            db.execute(f"DELETE FROM {table} WHERE {where}")
        # FU-D: Claude's previews keep their row ("Preview removed after 30 days"); only the bytes go.
        db.execute("""UPDATE desk_attachments SET body = NULL, pruned_at = now()
                      WHERE body IS NOT NULL AND created_at < now() - interval '30 days'""")


def start():
    global _started
    if _started or not config.WORKERS_ENABLED:
        return
    _started = True
    threading.Thread(target=_loop, name="ebads-worker", daemon=True).start()
