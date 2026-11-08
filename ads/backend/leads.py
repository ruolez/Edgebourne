"""Turning Meta lead data into rows, and telling people about new ones."""
import html
import json
import logging
from datetime import datetime, timezone

import config
import db
import mailer
import meta_client
from util import log_activity

log = logging.getLogger(__name__)

LEAD_FIELDS = ("id,created_time,ad_id,ad_name,adset_id,campaign_id,campaign_name,form_id,"
               "field_data,is_organic")

STANDARD = {
    "full_name": "full_name",
    "first_name": "first_name",
    "last_name": "last_name",
    "email": "email",
    "work_email": "email",
    "phone_number": "phone",
    "phone": "phone",
}


def parse_field_data(field_data):
    """Map Meta's field_data list onto our columns. The first answer that is
    not a standard contact field is treated as the business-type question."""
    out = {"full_name": None, "email": None, "phone": None, "business_type": None}
    first = last = None
    for item in field_data or []:
        name = (item.get("name") or "").strip().lower()
        values = item.get("values") or []
        value = ", ".join(str(v) for v in values if v not in (None, "")).strip() or None
        target = STANDARD.get(name)
        if target == "first_name":
            first = value
        elif target == "last_name":
            last = value
        elif target:
            out[target] = out[target] or value
        elif out["business_type"] is None and value:
            out["business_type"] = value
    if not out["full_name"] and (first or last):
        out["full_name"] = " ".join(p for p in (first, last) if p)
    return out


def _parse_time(value):
    if not value:
        return datetime.now(timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")


def store_lead(data, is_test=False):
    """Insert a lead from Graph API data. Returns (lead_id, created_new)."""
    parsed = parse_field_data(data.get("field_data"))
    form_name = None
    row = db.execute(
        """INSERT INTO leads (meta_lead_id, created_time, form_id, form_name, ad_id, ad_name,
                              adset_id, campaign_id, campaign_name, full_name, email, phone,
                              business_type, answers, is_test)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (meta_lead_id) DO NOTHING
           RETURNING id""",
        (str(data["id"]), _parse_time(data.get("created_time")), data.get("form_id"), form_name,
         data.get("ad_id"), data.get("ad_name"), data.get("adset_id"), data.get("campaign_id"),
         data.get("campaign_name"), parsed["full_name"], parsed["email"], parsed["phone"],
         parsed["business_type"], json.dumps(data.get("field_data") or []), is_test),
        returning=True,
    )
    if row:
        return row["id"], True
    existing = db.query("SELECT id FROM leads WHERE meta_lead_id = %s", (str(data["id"]),), one=True)
    return existing["id"], False


def fetch_and_store(leadgen_id, page_token=None):
    token = page_token or meta_client.page_token()
    data = meta_client.get(str(leadgen_id), token=token, fields=LEAD_FIELDS)
    is_test = not data.get("ad_id")  # Lead Ads Testing Tool leads carry no ad
    lead_id, created = store_lead(data, is_test=is_test)
    if created:
        log_activity("lead.received", subject=str(lead_id), actor="meta",
                     details={"ad": data.get("ad_name"), "test": is_test})
        notify(lead_id)
    return lead_id, created


def recipients_for(lead):
    """Admins plus teammates assigned to the lead's campaign, if they want emails."""
    rows = db.query(
        """SELECT DISTINCT u.email FROM users u
           LEFT JOIN campaign_members cm ON cm.user_id = u.id
           WHERE u.is_active AND u.notify_new_leads
             AND (u.role = 'admin' OR cm.campaign_id = %s)""",
        (lead["campaign_id"],),
    )
    return [r["email"] for r in rows]


def render_email(lead):
    name = lead["full_name"] or "Someone"
    business = lead["business_type"] or "business not given"
    link = f"{config.APP_BASE_URL}/leads.html#lead={lead['id']}"
    test = " (test lead)" if lead["is_test"] else ""
    subject = f"New lead{test}: {name}, {business}"
    lines = [
        f"{name} asked for a free intro call{test}.",
        "",
        f"Phone:    {lead['phone'] or '-'}",
        f"Email:    {lead['email'] or '-'}",
        f"Business: {business}",
        f"From ad:  {lead['ad_name'] or '-'}",
        "",
        f"Open the lead: {link}",
        "",
        "Call within the hour if you can. Leads that hear back fast are the ones that turn into calls.",
    ]
    e = html.escape
    rows = "".join(
        f"<tr><td style='padding:4px 16px 4px 0;color:#5b6b78'>{e(k)}</td>"
        f"<td style='padding:4px 0'>{v}</td></tr>"
        for k, v in (
            ("Phone", f"<a href='tel:{e(lead['phone'] or '')}'>{e(lead['phone'] or '-')}</a>"),
            ("Email", f"<a href='mailto:{e(lead['email'] or '')}'>{e(lead['email'] or '-')}</a>"),
            ("Business", e(business)),
            ("From ad", e(lead["ad_name"] or "-")),
        )
    )
    body_html = (
        "<div style='font-family:-apple-system,Segoe UI,sans-serif;color:#15212b;max-width:520px'>"
        f"<p style='font-size:18px;margin:0 0 12px'><b>{e(name)}</b> asked for a free intro call{e(test)}.</p>"
        f"<table style='font-size:15px;border-collapse:collapse'>{rows}</table>"
        f"<p style='margin:20px 0'><a href='{e(link)}' style='background:#15212b;color:#fff;"
        "padding:10px 16px;border-radius:8px;text-decoration:none'>Open the lead</a></p>"
        "<p style='color:#5b6b78;font-size:13px'>Call within the hour if you can. Leads that hear "
        "back fast are the ones that turn into calls.</p></div>"
    )
    return subject, "\n".join(lines), body_html


def notify(lead_id):
    lead = db.query("SELECT * FROM leads WHERE id = %s", (lead_id,), one=True)
    if not lead or not mailer.configured():
        return False
    to = recipients_for(lead)
    if not to:
        return False
    subject, text, body_html = render_email(lead)
    try:
        mailer.send(to, subject, text, body_html)
    except mailer.MailError as exc:
        log.warning("lead %s email failed: %s", lead_id, exc)
        log_activity("lead.email_failed", subject=str(lead_id), actor="system",
                     details={"error": str(exc)})
        return False
    db.execute("UPDATE leads SET emailed_at = now() WHERE id = %s", (lead_id,))
    return True


def process_pending_events():
    """Fetch the lead for every webhook delivery not yet processed."""
    pending = db.query(
        "SELECT id, leadgen_id FROM webhook_events WHERE processed_at IS NULL AND leadgen_id IS NOT NULL "
        "ORDER BY id LIMIT 50"
    )
    if not pending:
        return 0
    try:
        token = meta_client.page_token()
    except meta_client.MetaError as exc:
        for ev in pending:
            db.execute("UPDATE webhook_events SET error = %s WHERE id = %s", (str(exc), ev["id"]))
        return 0
    done = 0
    for ev in pending:
        try:
            fetch_and_store(ev["leadgen_id"], page_token=token)
            db.execute("UPDATE webhook_events SET processed_at = now(), error = NULL WHERE id = %s",
                       (ev["id"],))
            done += 1
        except meta_client.MetaError as exc:
            db.execute("UPDATE webhook_events SET error = %s WHERE id = %s", (str(exc), ev["id"]))
    return done


def backfill(days=30):
    """Pull recent leads straight from every form on the Page (catch-up)."""
    page_id = __import__("settings_store").get("meta_page_id")
    token = meta_client.page_token(page_id)
    since = int(datetime.now(timezone.utc).timestamp()) - days * 86400
    new = 0
    for form in meta_client.paged(f"{page_id}/leadgen_forms", token=token, fields="id,name", limit=100):
        filtering = json.dumps([{"field": "time_created", "operator": "GREATER_THAN", "value": since}])
        for data in meta_client.paged(f"{form['id']}/leads", token=token, fields=LEAD_FIELDS,
                                      filtering=filtering, limit=100):
            data.setdefault("form_id", form["id"])
            lead_id, created = store_lead(data, is_test=not data.get("ad_id"))
            if created:
                new += 1
                db.execute("UPDATE leads SET form_name = %s WHERE id = %s", (form["name"], lead_id))
    return new
