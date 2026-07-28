"""Background jobs: recurring invoices, email retries, Stripe reconciliation.

Runs as its OWN container (same image, different command), not as a thread
inside Flask. A thread was rejected because backend/Dockerfile runs gunicorn
with --preload, so create_app() executes in the arbiter before fork: a thread
started there lives in the master and is not inherited by workers. Worse,
docker-compose.dev.yml does NOT use --preload, so in development the same thread
would land in a worker instead. Different behaviour between dev and prod, in the
code path that generates invoices, is exactly the failure you cannot afford.

Host cron hitting a token-protected endpoint was also rejected: it creates a new
bearer-authenticated endpoint whose whole purpose is to move money, runs the
work on a request thread under the gunicorn timeout, and lives outside the repo
where cmd_remove and reinstalls lose it.

A Postgres advisory lock is still taken, and released every tick, as defence
against the dev overlay running alongside, a stray --once, or a half-finished
deploy. A hung process must not lock out its replacement forever.

Run one pass by hand:
    docker compose run --rm scheduler python scheduler.py --once
"""

import logging
import os
import signal
import sys
import threading
import time
from datetime import date, datetime, timedelta, timezone

import psycopg2.extras

import db
import schedule_dates as sd

log = logging.getLogger("scheduler")

TICK_SECONDS = int(os.environ.get("SCHEDULER_TICK_SECONDS", "60"))
ENABLED = os.environ.get("SCHEDULER_ENABLED", "1") != "0"
LOCK_KEY = 0x62311A9  # arbitrary constant; documented so nobody reuses it
MAX_CATCHUP_PERIODS = 12
RETRY_BACKOFF_MINUTES = [1, 5, 30, 120, 360, 720, 1440, 1440]

_stop = threading.Event()


# ---------------------------------------------------------------------------
# infrastructure
# ---------------------------------------------------------------------------

def _dict_cur(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def fetch(conn, sql, params=None, one=False):
    with _dict_cur(conn) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() if cur.description else []
    return (rows[0] if rows else None) if one else rows


def run(conn, sql, params=None):
    with conn.cursor() as cur:
        cur.execute(sql, params)


def setting(conn, key, default=""):
    row = fetch(conn, "SELECT value FROM settings WHERE key = %s", (key,), one=True)
    return row["value"] if row and row["value"] not in (None, "") else default


def wait_for_schema(timeout=180):
    """The web container runs migrations; depends_on: service_started does not
    wait for them. An early failed tick would be harmless, but a clean startup
    log is worth twenty lines."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not _stop.is_set():
        try:
            with db.standalone() as conn:
                fetch(conn, "SELECT 1 FROM subscriptions LIMIT 1")
                conn.commit()
                return True
        except Exception:
            log.info("waiting for the billing schema…")
            _stop.wait(5)
    return False


def _try_lock(conn):
    row = fetch(conn, "SELECT pg_try_advisory_lock(%s) AS ok", (LOCK_KEY,), one=True)
    conn.commit()
    return bool(row and row["ok"])


def _unlock(conn):
    try:
        run(conn, "SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
        conn.commit()
    except Exception:
        log.exception("failed to release the advisory lock")


def _daily_gate(conn, key, now):
    """True at most once per calendar day, so a crash-loop cannot re-send thirty
    overdue reminders."""
    row = fetch(conn, "SELECT last_run_at FROM scheduler_state WHERE key = %s", (key,), one=True)
    if row and row["last_run_at"] and row["last_run_at"].date() == now.date():
        return False
    run(conn,
        """INSERT INTO scheduler_state (key, last_run_at) VALUES (%s, %s)
           ON CONFLICT (key) DO UPDATE SET last_run_at = EXCLUDED.last_run_at""",
        (key, now))
    conn.commit()
    return True


def heartbeat(conn, now, detail=""):
    """Surfaced as a red dashboard tile past ten minutes. Without it a dead
    scheduler is invisible for a month -- and a month of unbilled retainers."""
    run(conn,
        """INSERT INTO scheduler_state (key, last_run_at, detail) VALUES ('tick', %s, %s)
           ON CONFLICT (key) DO UPDATE SET last_run_at = EXCLUDED.last_run_at,
                                           detail = EXCLUDED.detail""",
        (now, detail[:400]))
    conn.commit()


# ---------------------------------------------------------------------------
# recurring invoices
# ---------------------------------------------------------------------------

def generate_due_invoices(conn, now):
    subs = fetch(conn,
        """SELECT * FROM subscriptions
            WHERE status = 'active' AND next_run_at IS NOT NULL AND next_run_at <= %s
            ORDER BY next_run_at LIMIT 50 FOR UPDATE SKIP LOCKED""",
        (now,))
    conn.commit()
    made = 0
    for sub in subs:
        # Decide UP FRONT whether this is a catch-up. If more than one period is
        # due, every one of them -- including the first -- is held as a draft:
        # the scheduler having been down is exactly when a human should look
        # before a batch of invoices goes out.
        backlog = _periods_due(sub, now)
        generated = 0
        while generated < MAX_CATCHUP_PERIODS and not _stop.is_set():
            sub = fetch(conn, "SELECT * FROM subscriptions WHERE id = %s", (sub["id"],), one=True)
            conn.commit()
            if not sub or sub["status"] != "active":
                break
            if sub["next_run_at"] is None or sub["next_run_at"] > now:
                break
            if sub["max_occurrences"] and sub["occurrences_generated"] >= sub["max_occurrences"]:
                _end(conn, sub, "reached its occurrence limit")
                break
            period_start = sd.nth_period_start(sub, sub["occurrences_generated"])
            if sub["end_date"] and period_start > sub["end_date"]:
                _end(conn, sub, "passed its end date")
                break
            try:
                created = generate_one_period(conn, sub, now, catching_up=backlog > 1)
            except Exception as e:
                conn.rollback()
                log.exception("subscription %s period generation failed", sub["id"])
                _record_failure(conn, sub, e)
                break
            generated += 1
            made += created
        if generated >= MAX_CATCHUP_PERIODS:
            log.error("subscription %s hit the catch-up cap — check next_run_at and the clock",
                      sub["id"])
            _alert(conn, "Recurring billing hit the catch-up cap",
                   f"Subscription #{sub['id']} generated {MAX_CATCHUP_PERIODS} periods in one "
                   f"tick and stopped. Check its dates and the server clock before it runs again.")
    return made


def _periods_due(sub, now, cap=MAX_CATCHUP_PERIODS + 1):
    """How many periods are already due. Used only to decide whether this run is
    a catch-up; the generation loop still advances one period at a time."""
    n = sub["occurrences_generated"]
    count = 0
    while count < cap:
        try:
            when = sd.next_run_for(sub, n + count)
        except Exception:
            break
        if when > now:
            break
        if sub["max_occurrences"] and (n + count) >= sub["max_occurrences"]:
            break
        if sub["end_date"] and sd.nth_period_start(sub, n + count) > sub["end_date"]:
            break
        count += 1
    return count


def generate_one_period(conn, sub, now, catching_up=False):
    """One period = ONE transaction. Claim the run row, create the invoice, copy
    the lines, allocate the number, post the ledger entry, queue the email,
    advance the counters. Any failure rolls all of it back and the run row
    disappears, so the retry re-claims it cleanly."""
    import billing
    import billing_mail
    import money

    n = sub["occurrences_generated"]
    period_start, period_end = sd.period_bounds(sub, n)
    key = sd.period_key(sub, period_start)

    claimed = fetch(conn,
        """INSERT INTO subscription_runs
             (subscription_id, period_key, period_start, period_end, scheduled_for, status)
           VALUES (%s,%s,%s,%s,%s,'pending')
           ON CONFLICT (subscription_id, period_key) DO NOTHING
           RETURNING id""",
        (sub["id"], key, period_start, period_end, sub["next_run_at"]), one=True)
    if not claimed:
        # Already generated. Advance and move on -- this is the guarantee that
        # a double run cannot duplicate an invoice.
        _advance(conn, sub)
        conn.commit()
        log.info("subscription %s period %s already generated; advancing", sub["id"], key)
        return 0

    customer = fetch(conn, "SELECT * FROM customers WHERE id = %s", (sub["customer_id"],), one=True)
    terms = sub["terms_days"] or (customer["terms_days"] if customer else 14)
    title = sub["name"]

    inv = fetch(conn,
        """INSERT INTO invoices (customer_id, project_id, subscription_id, currency, title,
               issue_date, due_date, period_start, period_end, notes_md, terms_md,
               discount_cents)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING *""",
        (sub["customer_id"], sub["project_id"], sub["id"], sub["currency"], title,
         period_start, period_start + timedelta(days=terms), period_start, period_end,
         sub["notes_md"], sub["terms_md"], sub["discount_cents"]), one=True)

    run(conn,
        """INSERT INTO invoice_lines (invoice_id, sort_order, kind, description, detail,
               qty_milli, unit, unit_price_cents, tax_rate_milli)
           SELECT %s, sort_order, kind, description, detail, qty_milli, unit,
                  unit_price_cents, tax_rate_milli
             FROM subscription_lines WHERE subscription_id = %s ORDER BY sort_order, id""",
        (inv["id"], sub["id"]))

    _recompute_totals(conn, inv["id"], sub["discount_cents"])
    inv = fetch(conn, "SELECT * FROM invoices WHERE id = %s", (inv["id"],), one=True)
    if inv["total_cents"] <= 0:
        conn.rollback()
        log.warning("subscription %s produced a zero-total invoice; skipping period %s",
                    sub["id"], key)
        run(conn,
            """UPDATE subscription_runs SET status='skipped', last_error='zero total'
                WHERE subscription_id=%s AND period_key=%s""", (sub["id"], key))
        _advance(conn, sub)
        conn.commit()
        return 0

    # CATCH-UP IS LEFT AS A DRAFT. Not merely unsent: unissued. No number is
    # burned, nothing is posted to the ledger, no customer link exists. If the
    # scheduler has been down long enough to miss a period -- or a clock or
    # timezone bug made it think so -- the admin can delete a draft, whereas an
    # issued invoice can only be voided and leaves a permanent trail.
    if catching_up:
        run(conn,
            """UPDATE subscription_runs SET status='success', invoice_id=%s, updated_at=now()
                WHERE subscription_id=%s AND period_key=%s""",
            (inv["id"], sub["id"], key))
        _advance(conn, sub)
        conn.commit()
        log.info("subscription %s -> DRAFT invoice #%s (%s) [catch-up, held for review]",
                 sub["id"], inv["id"], key)
        return 1

    cap = int(setting(conn, "billing_auto_send_max_cents", "1000000") or 1000000)
    auto = (sub["auto_send"]
            and bool(customer and customer["email"])
            and inv["total_cents"] <= cap
            and setting(conn, "billing_enabled", "1") == "1")

    number = _next_number(conn, "invoice")
    token = billing.new_token("inv")
    ttl = int(setting(conn, "billing_token_ttl_days", "90") or 90)
    run(conn,
        """UPDATE invoices SET number=%s, status='open', issued_at=now(),
               token_hash=%s, token_expires_at=%s, updated_at=now()
             WHERE id=%s""",
        (number, billing.token_hash(token), date.today() + timedelta(days=ttl), inv["id"]))
    run(conn,
        """INSERT INTO credit_ledger (customer_id, kind, delta_cents, currency, invoice_id, memo)
           VALUES (%s,'invoice',%s,%s,%s,%s)""",
        (sub["customer_id"], inv["total_cents"], inv["currency"], inv["id"],
         f"Invoice {number}"))

    email_id = None
    if auto:
        delay = int(setting(conn, "billing_send_delay_minutes", "15") or 15)
        base = setting(conn, "billing_company_name", "EdgeBourne")
        pay_url = f"{_base_url(conn)}/pay/{token}"
        inv = fetch(conn, "SELECT * FROM invoices WHERE id = %s", (inv["id"],), one=True)
        text, html = billing_mail._render(
            "invoice", inv=inv, customer=customer, pay_url=pay_url, reminder=None,
            company={k: setting(conn, f"billing_{k}", "") for k in
                     ("company_name", "company_email", "company_phone", "company_address",
                      "payment_instructions")})
        row = fetch(conn,
            """INSERT INTO email_log (kind, to_addr, cc_addr, subject, body_text, body_html,
                   customer_id, invoice_id, send_after)
               VALUES ('invoice_sent',%s,%s,%s,%s,%s,%s,%s, now() + (%s || ' minutes')::interval)
               RETURNING id""",
            (customer["email"], customer["cc_emails"] or "",
             f"Invoice {number} from {base}", text, html,
             customer["id"], inv["id"], delay), one=True)
        email_id = row["id"]
        run(conn, "UPDATE invoices SET sent_at = now() WHERE id = %s", (inv["id"],))

    run(conn,
        """UPDATE subscription_runs SET status='success', invoice_id=%s, updated_at=now()
            WHERE subscription_id=%s AND period_key=%s""",
        (inv["id"], sub["id"], key))
    _advance(conn, sub)
    conn.commit()
    log.info("subscription %s -> invoice %s (%s)%s", sub["id"], number, key,
             " [queued email]" if email_id else " [draft/not sent]")
    return 1


def _recompute_totals(conn, invoice_id, discount):
    """Same statement as billing.recompute_totals, executed on the scheduler's
    own connection (it has no Flask app context)."""
    run(conn, """
        WITH grp AS (
            SELECT tax_rate_milli, COALESCE(SUM(amount_cents),0)::bigint AS base
              FROM invoice_lines WHERE invoice_id = %(id)s AND kind = 'item'
             GROUP BY tax_rate_milli
        ), sub AS (SELECT COALESCE(SUM(base),0)::bigint AS subtotal FROM grp),
        disc AS (
            SELECT LEAST(GREATEST(COALESCE(%(discount)s, p.discount_cents),0),
                         GREATEST(s.subtotal,0))::bigint AS discount
              FROM sub s, invoices p WHERE p.id = %(id)s
        ), tax AS (
            SELECT COALESCE(SUM(round(
                     (g.base - CASE WHEN s.subtotal = 0 THEN 0
                                    ELSE d.discount::numeric * g.base / s.subtotal END)
                     * g.tax_rate_milli / 100000)),0)::bigint AS tax
              FROM grp g, sub s, disc d
        )
        UPDATE invoices p SET subtotal_cents = s.subtotal, discount_cents = d.discount,
               tax_cents = t.tax, total_cents = s.subtotal - d.discount + t.tax,
               updated_at = now()
          FROM sub s, disc d, tax t WHERE p.id = %(id)s
    """, {"id": invoice_id, "discount": discount})


def _next_number(conn, scope):
    period = str(date.today().year) if setting(conn, "billing_number_period", "year") == "year" else ""
    row = fetch(conn,
        """INSERT INTO document_counters (scope, period, next_value) VALUES (%s,%s,2)
           ON CONFLICT (scope, period)
           DO UPDATE SET next_value = document_counters.next_value + 1
           RETURNING next_value - 1 AS n""", (scope, period), one=True)
    prefix = setting(conn, "billing_invoice_prefix", "INV")
    pad = int(setting(conn, "billing_number_pad", "4") or 4)
    body = f"{row['n']:0{pad}d}"
    return f"{prefix}-{period}-{body}" if period else f"{prefix}-{body}"


def _advance(conn, sub):
    """next_run_at is DERIVED from occurrences_generated, so the two cannot
    drift, and it only ever moves on success."""
    n = sub["occurrences_generated"] + 1
    nxt = sd.next_run_for(sub, n)
    if sub["end_date"] and sd.nth_period_start(sub, n) > sub["end_date"]:
        run(conn, """UPDATE subscriptions SET occurrences_generated=%s, status='ended',
                         next_run_at=NULL, last_run_at=now(), last_error=NULL, updated_at=now()
                       WHERE id=%s""", (n, sub["id"]))
        return
    run(conn, """UPDATE subscriptions SET occurrences_generated=%s, next_run_at=%s,
                     last_run_at=now(), last_error=NULL, updated_at=now()
                   WHERE id=%s""", (n, nxt, sub["id"]))


def _end(conn, sub, why):
    run(conn, """UPDATE subscriptions SET status='ended', next_run_at=NULL, updated_at=now()
                   WHERE id=%s""", (sub["id"],))
    conn.commit()
    log.info("subscription %s ended: %s", sub["id"], why)


def _record_failure(conn, sub, error):
    """A separate small transaction. subscriptions.next_run_at is deliberately
    NOT advanced here -- only success advances it."""
    try:
        conn.rollback()
        attempts = (sub.get("_attempts") or 0) + 1
        run(conn, "UPDATE subscriptions SET last_error=%s, updated_at=now() WHERE id=%s",
            (str(error)[:1000], sub["id"]))
        run(conn,
            """UPDATE subscription_runs
                  SET status='failed', attempts = attempts + 1, last_error=%s,
                      next_attempt_at = now() + (%s || ' minutes')::interval, updated_at=now()
                WHERE subscription_id=%s AND status='pending'""",
            (str(error)[:1000],
             RETRY_BACKOFF_MINUTES[min(attempts, len(RETRY_BACKOFF_MINUTES) - 1)], sub["id"]))
        # Clear the claim so the period can be retried cleanly.
        run(conn, """DELETE FROM subscription_runs
                      WHERE subscription_id=%s AND status='pending'""", (sub["id"],))
        conn.commit()
    except Exception:
        conn.rollback()
        log.exception("could not record the failure for subscription %s", sub["id"])


def _base_url(conn):
    import config
    return config.PUBLIC_BASE_URL or setting(conn, "site_url", "") or "http://localhost:8090"


def _alert(conn, subject, body):
    to = (setting(conn, "billing_admin_alert_email")
          or setting(conn, "notify_email") or setting(conn, "contact_email"))
    if not to:
        return
    try:
        run(conn,
            """INSERT INTO email_log (kind, to_addr, subject, body_text)
               VALUES ('admin_alert',%s,%s,%s)""", (to, f"[Billing] {subject}", body))
        conn.commit()
    except Exception:
        conn.rollback()
        log.exception("could not queue an admin alert")


# ---------------------------------------------------------------------------
# other jobs
# ---------------------------------------------------------------------------

def drain_email_queue(conn, now):
    import mailer
    settings = {k: setting(conn, k) for k in mailer.SETTING_KEYS}
    return mailer.drain(conn, settings, limit=25)


def expire_stale_sessions(conn, now):
    run(conn,
        """UPDATE payments SET status='canceled', updated_at=now()
            WHERE status='pending' AND session_expires_at IS NOT NULL
              AND session_expires_at < now() - interval '5 minutes'""")
    # Pending rows that never got a session (process died mid-checkout).
    run(conn,
        """UPDATE payments SET status='canceled', updated_at=now()
            WHERE status='pending' AND stripe_checkout_session_id IS NULL
              AND created_at < now() - interval '2 hours'""")
    conn.commit()
    return 0


def retry_stripe_events(conn, now):
    """Stripe gives up retrying after roughly three days. An event stuck in
    'failed' is money you do not know about."""
    import webhooks
    rows = fetch(conn,
        """SELECT * FROM stripe_events
            WHERE status IN ('received','failed') AND attempts < 20
              AND received_at < now() - interval '5 minutes'
            ORDER BY created_at_stripe LIMIT 25""")
    conn.commit()
    if not rows:
        return 0
    done = 0
    import app as app_module
    flask_app = _flask_app(app_module)
    for row in rows:
        try:
            with flask_app.app_context():
                handled = webhooks.dispatch(row["payload"])
            run(conn, """UPDATE stripe_events SET status=%s, processed_at=now(),
                             attempts = attempts + 1 WHERE id=%s""",
                ("processed" if handled else "ignored", row["id"]))
            done += 1
        except Exception as e:
            run(conn, """UPDATE stripe_events SET status='failed', error=%s,
                             attempts = attempts + 1 WHERE id=%s""",
                (str(e)[:1000], row["id"]))
            log.warning("stripe event %s still failing: %s", row["stripe_event_id"], e)
        conn.commit()
    return done


_APP = None


def _flask_app(app_module):
    """A few jobs reuse request-path code (webhooks.dispatch, billing helpers)
    that needs flask.g. One app context is built lazily and reused."""
    global _APP
    if _APP is None:
        _APP = app_module.create_app()
    return _APP


def backfill_charge_fees(conn, now):
    """Deferred out of the webhook so handlers stay inside Stripe's 20s timeout."""
    import stripe_client
    if not stripe_client.is_configured():
        return 0
    rows = fetch(conn,
        """SELECT id, stripe_balance_txn_id FROM payments
            WHERE status='succeeded' AND fee_cents = 0
              AND stripe_balance_txn_id IS NOT NULL LIMIT 20""")
    conn.commit()
    done = 0
    for row in rows:
        try:
            bt = stripe_client.retrieve_balance_transaction(row["stripe_balance_txn_id"])
            run(conn, "UPDATE payments SET fee_cents=%s, updated_at=now() WHERE id=%s",
                (bt.get("fee") or 0, row["id"]))
            conn.commit()
            done += 1
        except Exception:
            conn.rollback()
            log.warning("fee lookup failed for payment %s", row["id"])
    return done


def reconcile_stripe(conn, now):
    """The highest-value control in the whole design.

    If the webhook endpoint was down beyond Stripe's ~3-day retry window, or the
    webhook secret was rotated in the Dashboard but not in .env, payments are
    silently lost. This lists PaymentIntents from the last seven days and
    asserts every one has a local row.
    """
    import stripe_client
    if not stripe_client.is_configured():
        return 0
    since = int((now - timedelta(days=7)).timestamp())
    try:
        intents = stripe_client.list_payment_intents_since(since, limit=100)
    except Exception:
        log.exception("Stripe reconciliation could not list payment intents")
        return 0
    orphans = []
    for pi in intents:
        if pi.get("status") != "succeeded":
            continue
        if (pi.get("metadata") or {}).get("app") != "edgebourne":
            continue
        found = fetch(conn,
            "SELECT id FROM payments WHERE stripe_payment_intent_id = %s AND status='succeeded'",
            (pi["id"],), one=True)
        conn.commit()
        if not found:
            orphans.append(pi)
    if orphans:
        log.error("RECONCILIATION: %d succeeded Stripe payments have no local record", len(orphans))
        _alert(conn, f"{len(orphans)} Stripe payment(s) not recorded locally",
               "These succeeded in Stripe but have no succeeded payment row here:\n\n"
               + "\n".join(f"  {p['id']}  {p.get('amount')} {(p.get('currency') or '').upper()}"
                           for p in orphans)
               + "\n\nCheck the webhook endpoint and STRIPE_WEBHOOK_SECRET.")
    return len(orphans)


def expire_estimates_job(conn, now):
    run(conn,
        """UPDATE estimates SET status='expired', updated_at=now()
            WHERE status='sent' AND valid_until IS NOT NULL AND valid_until < current_date""")
    conn.commit()
    return 0


def send_overdue_reminders(conn, now):
    if setting(conn, "billing_reminder_enabled", "") != "1":
        return 0
    import billing_mail
    raw = setting(conn, "billing_reminder_days", "-3,0,7,14,30")
    try:
        offsets = sorted({int(x.strip()) for x in raw.split(",") if x.strip()})
    except ValueError:
        log.warning("billing_reminder_days is not a list of integers: %r", raw)
        return 0

    company = {k: setting(conn, f"billing_{k}", "") for k in
               ("company_name", "company_email", "company_phone", "company_address",
                "payment_instructions")}
    sent = 0
    for offset in offsets:
        rows = fetch(conn,
            """SELECT i.*, c.email, c.cc_emails, c.contact_name, c.display_name, c.id AS cid
                 FROM invoices i JOIN customers c ON c.id = i.customer_id
                WHERE i.status IN ('open','partial')
                  AND i.due_date = current_date - %s
                  AND c.email <> ''
                  AND NOT EXISTS (
                      SELECT 1 FROM email_log e
                       WHERE e.invoice_id = i.id AND e.kind = 'invoice_reminder'
                         AND e.created_at::date = current_date)""",
            (offset,))
        conn.commit()
        for inv in rows:
            try:
                text, html = billing_mail._render(
                    "invoice", inv=inv, customer=inv, pay_url=f"{_base_url(conn)}/pay/",
                    reminder=offset, company=company)
                subject = (f"Reminder: invoice {inv['number']} "
                           f"{'is overdue' if offset > 0 else 'is due'}")
                run(conn,
                    """INSERT INTO email_log (kind, to_addr, cc_addr, subject, body_text,
                           body_html, customer_id, invoice_id)
                       VALUES ('invoice_reminder',%s,%s,%s,%s,%s,%s,%s)""",
                    (inv["email"], inv["cc_emails"] or "", subject, text, html,
                     inv["cid"], inv["id"]))
                conn.commit()
                sent += 1
            except Exception:
                conn.rollback()
                log.exception("could not queue a reminder for invoice %s", inv["id"])
    return sent


def prune_event_payloads(conn, now):
    """stripe_events.payload carries emails, addresses and card metadata, and
    lands in every pg_dump. Financial tables are NEVER pruned -- only this and
    invoice_views."""
    run(conn,
        """UPDATE stripe_events SET payload = NULL
            WHERE payload IS NOT NULL AND received_at < now() - interval '90 days'""")
    run(conn, "DELETE FROM invoice_views WHERE viewed_at < now() - interval '2 years'")
    conn.commit()
    return 0


# ---------------------------------------------------------------------------
# tick
# ---------------------------------------------------------------------------

JOBS = [
    ("generate_due_invoices", generate_due_invoices, None),
    ("drain_email_queue", drain_email_queue, None),
    ("expire_stale_sessions", expire_stale_sessions, None),
    ("retry_stripe_events", retry_stripe_events, None),
    ("backfill_charge_fees", backfill_charge_fees, None),
    ("expire_estimates", expire_estimates_job, "daily:expire_estimates"),
    ("send_overdue_reminders", send_overdue_reminders, "daily:reminders"),
    ("reconcile_stripe", reconcile_stripe, "daily:reconcile"),
    ("prune_event_payloads", prune_event_payloads, "daily:prune"),
]


def tick(conn, now=None):
    now = now or datetime.now(timezone.utc)
    results = {}
    for name, fn, gate in JOBS:
        if _stop.is_set():
            break
        try:
            if gate and not _daily_gate(conn, gate, now):
                continue
            results[name] = fn(conn, now)
        except Exception:
            conn.rollback()
            log.exception("job %s failed", name)  # one failure never stops the rest
    heartbeat(conn, now, ", ".join(f"{k}={v}" for k, v in results.items() if v))
    return results


def main():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, lambda *_: _stop.set())
    signal.signal(signal.SIGINT, lambda *_: _stop.set())

    once = "--once" in sys.argv
    if not ENABLED and not once:
        log.info("SCHEDULER_ENABLED=0 — idling")
        while not _stop.is_set():
            _stop.wait(60)
        return

    if not wait_for_schema():
        log.error("billing schema never appeared; exiting")
        return
    log.info("scheduler up (tick=%ss, once=%s)", TICK_SECONDS, once)

    while not _stop.is_set():
        started = time.monotonic()
        try:
            with db.standalone() as conn:
                if _try_lock(conn):
                    try:
                        results = tick(conn)
                        if any(results.values()):
                            log.info("tick: %s", {k: v for k, v in results.items() if v})
                    finally:
                        _unlock(conn)
                else:
                    log.debug("another scheduler holds the lock; skipping")
        except Exception:
            log.exception("scheduler tick failed")
        if once:
            break
        _stop.wait(max(1.0, TICK_SECONDS - (time.monotonic() - started)))
    log.info("scheduler stopped")


if __name__ == "__main__":
    main()
