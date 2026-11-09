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

    last_sync = 0.0
    last_auto_try = None
    while True:
        _event.wait(timeout=30)
        _event.clear()
        conn = None
        try:
            conn = db.connect()
            if _locked(conn, 7001):
                leads.process_pending_events()
                try:
                    import telegram
                    telegram.poll_updates(conn)
                except Exception as exc:
                    log.info("telegram updates skipped: %s", exc)
                try:
                    import replies
                    replies.process_pending()
                except Exception:
                    log.exception("sending lead replies failed")
                try:
                    import reminders
                    reminders.run()
                except Exception:
                    log.exception("lead reminders failed")
                try:
                    notify.process_pending()
                except Exception:
                    log.exception("sending alerts failed")
                try:
                    crm_events.process_pending()
                except Exception:
                    log.exception("sending lead stages to Meta failed")
                now = time.time()
                if settings_store.get("meta_system_token") and refresh_api.auto_due(
                        settings_store.get("last_refresh_at"), last_auto_try, now,
                        refresh_api.auto_minutes(settings_store.get("auto_refresh_minutes"))):
                    try:
                        refresh_api.pull_latest(conn)
                        last_auto_try = None
                    except Exception as exc:
                        last_auto_try = now
                        log.info("automatic refresh skipped: %s", exc)
                if time.time() - last_sync > SYNC_EVERY:
                    last_sync = time.time()
                    try:
                        insights.sync_all(days=7)
                    except Exception as exc:  # Meta not configured yet, network, …
                        log.info("meta sync skipped: %s", exc)
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
