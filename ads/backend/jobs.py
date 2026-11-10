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

    def each_account(conn, acct):
        """One account's pass: its leads, replies, Claude's schedules, reminders, lead stages,
        the automatic pull, the hourly sync, alerts and Meta reads. Errors stay inside the account."""
        leads.process_pending_events()
        for name, job in (("lead replies", lambda: __import__("replies").process_pending()),
                          ("Desk schedules", lambda: __import__("schedules").run()),
                          ("lead reminders", lambda: __import__("reminders").run()),
                          ("lead stages to Meta", crm_events.process_pending),
                          ("client report emails", lambda: __import__("reports_api").send_due())):
            try:
                job()
            except Exception:
                log.exception("account %s: %s failed", acct, name)
        now = time.time()
        pulled = False
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
            last_sync[acct] = time.time()
            try:
                insights.sync_all(days=7)
                pulled = True
            except Exception as exc:  # Meta not configured yet, network, …
                log.info("account %s: meta sync skipped: %s", acct, exc)
        if pulled or time.time() - last_alerts.get(acct, 0) > ALERTS_EVERY:
            last_alerts[acct] = time.time()
            try:
                import alerts
                alerts.run()
            except Exception:
                log.exception("account %s: alert rules failed", acct)
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
                for row in db.query("SELECT id FROM accounts WHERE archived_at IS NULL ORDER BY id"):
                    with account_ctx.use(row["id"]):
                        try:
                            each_account(conn, row["id"])
                        except Exception:
                            log.exception("account %s: worker pass failed", row["id"])
                try:
                    notify.process_pending()  # one queue for everyone
                except Exception:
                    log.exception("sending alerts failed")
        except Exception:
            log.exception("worker pass failed")
        finally:
            if conn is not None:
                conn.close()  # releases the advisory lock


def start():
    global _started
    if _started or not config.WORKERS_ENABLED:
        return
    _started = True
    threading.Thread(target=_loop, name="ebads-worker", daemon=True).start()
