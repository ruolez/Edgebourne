"""Turning Meta lead data into rows, and telling people about new ones."""
import html
import json
import logging
from datetime import datetime, timedelta, timezone

import config
import crm_events
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


TESTING_TOOL_VALUE = "<test lead"  # the Testing Tool fills every answer with "<test lead: dummy data for …>"


def is_test_lead(data):
    """Leads from Meta's Lead Ads Testing Tool carry no ad (unless one was picked there) and dummy
    answers. A form filled in without an ad (a Page post, a shared link) carries none either, but
    Meta marks it is_organic: a real person. Whether Testing Tool leads also come marked organic
    isn't known, so the dummy answers decide first."""
    dummy = any(str(v).startswith(TESTING_TOOL_VALUE)
                for f in data.get("field_data") or [] for v in f.get("values") or [])
    return dummy or (not data.get("ad_id") and not data.get("is_organic"))


def without_nul(value):
    """Postgres refuses NUL characters in text and JSON, and a typed form answer can carry one."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [without_nul(v) for v in value]
    if isinstance(value, dict):
        return {without_nul(k): without_nul(v) for k, v in value.items()}
    return value


def store_lead(data):
    """Insert a lead from Graph API data, not yet announced. Returns (lead_id, created_new)."""
    data = without_nul(data)
    is_test = is_test_lead(data)
    parsed = parse_field_data(data.get("field_data"))
    row = db.execute(
        """INSERT INTO leads (meta_lead_id, created_time, form_id, ad_id, ad_name,
                              adset_id, campaign_id, campaign_name, full_name, email, phone,
                              business_type, answers, is_test, is_organic, alerted_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL)
           ON CONFLICT (meta_lead_id) DO NOTHING
           RETURNING id""",
        (str(data["id"]), _parse_time(data.get("created_time")), data.get("form_id"),
         data.get("ad_id"), data.get("ad_name"), data.get("adset_id"), data.get("campaign_id"),
         data.get("campaign_name"), parsed["full_name"], parsed["email"], parsed["phone"],
         parsed["business_type"], json.dumps(data.get("field_data") or []), is_test, bool(data.get("is_organic"))),
        returning=True,
    )
    if row:
        if not is_test:
            crm_events.enqueue(row["id"], "new", _parse_time(data.get("created_time")))
        return row["id"], True
    existing = db.query("SELECT id FROM leads WHERE meta_lead_id = %s", (str(data["id"]),), one=True)
    # Not visible here: the lead id is unique across accounts and another account already has it.
    return (existing["id"] if existing else None), False


def fetch_and_store(leadgen_id, page_token=None):
    token = page_token or meta_client.page_token()
    data = meta_client.get(str(leadgen_id), token=token, fields=LEAD_FIELDS)
    lead_id, created = store_lead(data)
    if lead_id is not None:  # also when the catch-up stored it first and never got to announce it
        announce(lead_id)
    return lead_id, created


def recipients_for(lead):
    """The lead's people (staff_for) who want new-lead emails."""
    return [r["email"] for r in _staff(lead["campaign_id"]) if r["notify_new_leads"]]


def render_email(lead):
    name = lead["full_name"] or "Someone"
    business = lead["business_type"] or "business not given"
    link = __import__("notify").link(f"/leads.html#lead={lead['id']}")
    test = " (test lead)" if lead["is_test"] else ""
    ad = lead["ad_name"] or ("none, filled in without an ad" if lead.get("is_organic") else "-")
    subject = f"New lead{test}: {name}, {business}"
    lines = [
        f"{name} asked for a free intro call{test}.",
        "",
        f"Phone:    {lead['phone'] or '-'}",
        f"Email:    {lead['email'] or '-'}",
        f"Business: {business}",
        f"From ad:  {ad}",
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
            ("From ad", e(ad)),
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


def _staff(campaign_id):
    import account_ctx
    import notify as notify_mod
    rows = db.query(
        """SELECT DISTINCT u.id, u.name, u.email, u.account_id, u.notify_new_leads FROM users u
           LEFT JOIN campaign_members cm ON cm.user_id = u.id AND cm.campaign_id = %s
           WHERE u.is_active AND (u.role = 'admin' OR cm.campaign_id IS NOT NULL)
           ORDER BY u.name""",
        (campaign_id,),
    )
    return [r for r in rows if notify_mod.serves(r, account_ctx.current())]


def staff_for(campaign_id):
    """Who works on this campaign: the console's owners, this account's admins and the members
    assigned to it (campaign_members is per account under row-level security)."""
    return [{"id": r["id"], "name": r["name"]} for r in _staff(campaign_id)]


def recipient_ids(lead):
    return [r["id"] for r in staff_for(lead["campaign_id"])]


def alert_phones(lead):
    """A phone alert for everyone who gets the lead email: Telegram when they linked it, otherwise
    a push to each of their devices with notifications on. The email goes out as well."""
    import notify
    import push
    title, lines = notify.lead_alert(lead)
    url = notify.link(f"/leads.html#lead={lead['id']}")
    ids = recipient_ids(lead)
    by_tg = set(notify.telegram_people(ids))
    by_push = push.has_devices(ids)
    wanted = {r["id"] for r in db.query("SELECT id FROM users WHERE id = ANY(%s) AND notify_new_leads", (ids,))} if ids else set()
    for uid in ids:
        channel = "telegram" if uid in by_tg else "push" if uid in by_push and uid in wanted else None
        if channel:
            notify.queue(uid, channel, "lead", title, lines, url, "Open the lead", ref=str(lead["id"]),
                         dedupe_key=f"lead:{lead['id']}:{channel}:{uid}")


def queue_emails(lead):
    """The new-lead email, one per person who wants it (nobody sees who else gets the lead), sent
    and retried by the notification queue."""
    import notify
    if not mailer.configured():
        return
    subject, text, body_html = render_email(lead)
    for r in _staff(lead["campaign_id"]):
        if r["notify_new_leads"]:
            notify.queue(r["id"], "email", "lead", subject, text.split("\n"), ref=str(lead["id"]), html=body_html,
                         dedupe_key=f"lead:{lead['id']}:email:{r['id']}")


ANNOUNCE_WITHIN = timedelta(hours=24)


def announce(lead_id):
    """Tell the team about a stored lead once, whichever path stored it (a webhook, the catch-up,
    Refresh): the email, the phone alerts and the automatic reply. Each is queued under a key that
    can't be queued twice, so when a step fails the next pass (announce_pending) does it again and
    nobody hears twice. alerted_at is claimed last, and only the pass that claims it writes the
    history line. Leads over a day old (the catch-up reads 30 days back) are not announced."""
    import replies
    lead = db.query("SELECT * FROM leads WHERE id = %s AND alerted_at IS NULL AND created_time > now() - %s",
                    (lead_id, ANNOUNCE_WITHIN), one=True)
    if not lead:
        return False
    failed = False
    for name, step in (("email", queue_emails), ("phone alerts", alert_phones), ("automatic reply", replies.queue_auto)):
        try:
            step(lead)
        except Exception:
            failed = True
            log.exception("lead %s: couldn't queue the %s", lead_id, name)
    if failed or not db.execute("UPDATE leads SET alerted_at = now() WHERE id = %s AND alerted_at IS NULL RETURNING id",
                                (lead_id,), returning=True):
        return False
    log_activity("lead.received", subject=str(lead_id), actor="meta",
                 details={"ad": lead["ad_name"], "test": lead["is_test"], "organic": lead["is_organic"]})
    return True


def announce_pending():
    """Stored leads still waiting to be announced: a step failed, or the pass stopped half way."""
    rows = db.query("SELECT id FROM leads WHERE alerted_at IS NULL AND created_time > now() - %s ORDER BY id LIMIT 50",
                    (ANNOUNCE_WITHIN,))
    return sum(1 for r in rows if announce(r["id"]))


GIVE_UP_AFTER = timedelta(hours=24)
META_OBJECT_NOT_FOUND = 100
NOT_FOUND_OR_NO_ACCESS = 33  # Meta's subcode for "doesn't exist or can't be loaded due to missing permissions"
RETRY_MINUTES = (1, 5, 15, 60)
SAMPLE_LEADGEN_ID = "444444444444"  # the lead in Meta's webhook "Test" sample: it never exists
SAMPLE_PING_NOTE = "Meta's webhook Test sample: there is no lead to fetch"


def is_sample_ping(leadgen_id):
    return str(leadgen_id) == SAMPLE_LEADGEN_ID


def event_gives_up(code, received_at, now, subcode=None):
    """A delivery whose lead Meta says doesn't exist (e.g. the webhook Test button's sample) never will.
    Subcode 33 may also mean the Page token lost access to leads, which can be fixed: tried for a day."""
    return (code == META_OBJECT_NOT_FOUND and subcode != NOT_FOUND_OR_NO_ACCESS) or now - received_at > GIVE_UP_AFTER


def event_retry_at(attempts, now):
    """When a lead ping that failed `attempts` times is tried again."""
    return now + timedelta(minutes=RETRY_MINUTES[min(attempts, len(RETRY_MINUTES)) - 1])


def stops_batch(code):
    """Errors that hold for every lead (the token, permissions, Meta's rate limit, the network): the
    rest of the batch waits for the next pass instead of asking Meta once per lead."""
    return (code in meta_client.TOKEN_CODES or code in meta_client.RATE_CODES or code in ("cooldown", "network")
            or code == 10 or (isinstance(code, int) and 200 <= code < 300))


def process_pending_events(force=False):
    """Fetch the lead for every webhook delivery not yet processed whose retry is due (all of them
    with `force`, Settings' Try again)."""
    pending = db.query(
        "SELECT id, leadgen_id, received_at, attempts FROM webhook_events WHERE processed_at IS NULL AND leadgen_id IS NOT NULL "
        "AND (%s OR next_attempt_at <= now()) ORDER BY id LIMIT 50", (force,)
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
        if is_sample_ping(ev["leadgen_id"]):
            db.execute("UPDATE webhook_events SET processed_at = now(), error = %s WHERE id = %s", (SAMPLE_PING_NOTE, ev["id"]))
            continue
        try:
            lead_id, _ = fetch_and_store(ev["leadgen_id"], page_token=token)
        except Exception as exc:  # anything, so one bad event can't hold up the ones behind it
            meta = isinstance(exc, meta_client.MetaError)
            error = str(exc) if meta else f"Couldn't store this lead ({type(exc).__name__})"
            if not meta:
                log.exception("webhook event %s: couldn't store the lead", ev["id"])
            code = exc.code if meta else None
            now = datetime.now(timezone.utc)
            if event_gives_up(code, ev["received_at"], now, exc.subcode if meta else None):
                db.execute("UPDATE webhook_events SET processed_at = now(), error = %s WHERE id = %s",
                           (f"Gave up: {error}", ev["id"]))
                log_activity("webhook.dropped", subject=ev["leadgen_id"], actor="system", details={"error": error})
            else:
                attempts = ev["attempts"] + 1
                db.execute("UPDATE webhook_events SET error = %s, attempts = %s, next_attempt_at = %s WHERE id = %s",
                           (error, attempts, event_retry_at(attempts, now), ev["id"]))
                if stops_batch(code):
                    break
            continue
        if lead_id is None:
            db.execute("UPDATE webhook_events SET processed_at = now(), error = %s WHERE id = %s",
                       ("This lead is already filed under another account", ev["id"]))
            continue
        db.execute("UPDATE webhook_events SET processed_at = now(), error = NULL WHERE id = %s", (ev["id"],))
        done += 1
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
            lead_id, created = store_lead(data)
            if created:
                new += 1
                db.execute("UPDATE leads SET form_name = %s WHERE id = %s", (form["name"], lead_id))
            if lead_id is not None:
                announce(lead_id)
    return new
