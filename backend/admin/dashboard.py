from datetime import datetime, timedelta, timezone

from flask import render_template

import db

from . import bp

# Past this the scheduler is presumed dead and recurring invoices are not being
# generated. Surfaced as a red banner -- otherwise a dead scheduler is invisible
# for a month, and a month of unbilled retainers is invisible with it.
HEARTBEAT_STALE_MINUTES = 10


@bp.get("")
@bp.get("/")
def dashboard():
    stats = db.query(
        """SELECT
             (SELECT COUNT(*) FROM leads WHERE NOT is_read) AS unread,
             (SELECT COUNT(*) FROM leads) AS leads,
             (SELECT COUNT(*) FROM services WHERE is_published) AS services,
             (SELECT COUNT(*) FROM case_studies WHERE is_published) AS work,
             (SELECT COUNT(*) FROM posts WHERE is_published) AS posts,
             (SELECT COUNT(*) FROM pages WHERE is_published) AS pages""",
        one=True,
    )
    recent = db.query("SELECT * FROM leads ORDER BY created_at DESC LIMIT 10")

    money = overdue = payments = beat = None
    if db.get_setting("billing_enabled", "1") == "1":
        try:
            # One round-trip of scalar subqueries, matching the existing shape.
            money = db.query(
                """SELECT
                     (SELECT COALESCE(SUM(balance_due_cents), 0) FROM invoices
                       WHERE status IN ('open','partial'))                        AS outstanding,
                     (SELECT COALESCE(SUM(balance_due_cents), 0) FROM invoices
                       WHERE status IN ('open','partial')
                         AND due_date < current_date)                             AS overdue_cents,
                     (SELECT COUNT(*) FROM invoices
                       WHERE status IN ('open','partial')
                         AND due_date < current_date)                             AS overdue_n,
                     -- method='credit' is excluded: applying credit moves money
                     -- that was already collected, so counting it again would
                     -- overstate cash received.
                     (SELECT COALESCE(SUM(amount_cents), 0) FROM payments
                       WHERE status = 'succeeded' AND method <> 'credit'
                         AND received_on >= date_trunc('month', current_date))    AS collected_mtd,
                     (SELECT COUNT(*) FROM invoices WHERE status = 'draft')       AS drafts,
                     (SELECT COALESCE(SUM(total_cents), 0) FROM estimates
                       WHERE status = 'sent')                                     AS pipeline,
                     (SELECT COUNT(*) FROM estimates WHERE status = 'sent')       AS open_estimates,
                     (SELECT COUNT(*) FROM projects WHERE status = 'active')      AS active_projects,
                     (SELECT COUNT(*) FROM email_log
                       WHERE status IN ('failed','permanently_failed'))           AS failed_emails,
                     (SELECT COUNT(*) FROM payments WHERE needs_review)           AS needs_review,
                     (SELECT COUNT(*) FROM subscriptions WHERE status = 'active') AS retainers""",
                one=True,
            )
            overdue = db.query(
                """SELECT i.*, c.display_name AS customer_name,
                          current_date - i.due_date AS days_late
                     FROM invoices i JOIN customers c ON c.id = i.customer_id
                    WHERE i.status IN ('open','partial') AND i.due_date < current_date
                    ORDER BY i.due_date LIMIT 8"""
            )
            payments = db.query(
                """SELECT p.*, c.display_name AS customer_name, i.number AS invoice_number
                     FROM payments p
                     JOIN customers c ON c.id = p.customer_id
                     LEFT JOIN invoices i ON i.id = p.invoice_id
                    WHERE p.status = 'succeeded'
                    ORDER BY p.received_on DESC, p.id DESC LIMIT 8"""
            )
            beat = db.query("SELECT * FROM scheduler_state WHERE key = 'tick'", one=True)
            if beat and beat["last_run_at"]:
                age = datetime.now(timezone.utc) - beat["last_run_at"]
                beat = dict(beat,
                            stale=age > timedelta(minutes=HEARTBEAT_STALE_MINUTES),
                            minutes=int(age.total_seconds() // 60))
        except Exception:
            # A partially-migrated box must still render the content dashboard.
            db.rollback()
            money = None

    return render_template("admin/dashboard.html", stats=stats, recent=recent,
                           money=money, overdue=overdue, payments=payments,
                           heartbeat=beat)
