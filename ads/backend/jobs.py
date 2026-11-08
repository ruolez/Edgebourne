"""One background thread per gunicorn worker: processes webhook deliveries as
soon as they arrive and syncs campaigns every hour. A Postgres advisory lock
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
    import insights
    import leads

    last_sync = 0.0
    while True:
        _event.wait(timeout=30)
        _event.clear()
        conn = None
        try:
            conn = db.connect()
            if _locked(conn, 7001):
                leads.process_pending_events()
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
