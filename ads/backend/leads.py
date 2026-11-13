"""Turning Meta lead data into rows, and telling people about new ones."""
import html
import json
import logging
from datetime import datetime, timedelta, timezone

import config
import crm_events
import db
import lead_history
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


# Where a lead came from, as the Leads list narrows it (?campaign= / ?adset= / ?ad= / ?form=).
SOURCE_COLUMNS = (("campaign", "campaign_id"), ("adset", "adset_id"), ("ad", "ad_id"), ("form", "form_id"))


def source_filter(args):
    """(clauses, params) for the named sources; empty values and other keys add nothing."""
    named = [(col, str(args.get(key))) for key, col in SOURCE_COLUMNS if args.get(key)]
    return [f"l.{col} = %s" for col, _ in named], [value for _, value in named]


def source_named(args):
    """(kind, id) of an ad set or form filter, which the list's campaign / ad picker can't show, else None."""
    for key in ("adset", "form"):
        if args.get(key):
            return key, str(args[key])
    return None


def store_lead(data):
    """Insert a lead from Graph API data, not yet announced. Returns (lead_id, created_new). In the same transaction,
    under a per-account lock, it is matched against the person's earlier leads (L2): a repeat or a returning lead is
    linked before anyone is told about it, so every path (webhook, catch-up, Refresh) classifies it the same way."""
    import lead_quality_store as lqs
    data = without_nul(data)
    is_test = is_test_lead(data)
    parsed = parse_field_data(data.get("field_data"))
    prep = lqs.prepare(parsed, data.get("field_data"), is_test)
    created = _parse_time(data.get("created_time"))
    check = not is_test and lqs.repeat_check_on()
    with db.transaction() as cur:
        lqs.lock(cur)
        cur.execute(
            """INSERT INTO leads (meta_lead_id, created_time, form_id, ad_id, ad_name,
                                  adset_id, campaign_id, campaign_name, full_name, email, phone,
                                  business_type, answers, is_test, is_organic, alerted_at,
                                  email_key, phone_key, junk_flags, quality_checked)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,TRUE)
               ON CONFLICT (meta_lead_id) DO NOTHING
               RETURNING id""",
            (str(data["id"]), created, data.get("form_id"),
             data.get("ad_id"), data.get("ad_name"), data.get("adset_id"), data.get("campaign_id"),
             data.get("campaign_name"), parsed["full_name"], parsed["email"], parsed["phone"],
             parsed["business_type"], json.dumps(data.get("field_data") or []), is_test, bool(data.get("is_organic")),
             prep["email_key"], prep["phone_key"], prep["junk_flags"]))
        row = cur.fetchone()
        links = lqs.link_in(cur, {"id": row["id"], "created": created, **prep}, check) if row and not is_test else []
    if row:
        if not is_test:
            crm_events.enqueue(row["id"], "new", _parse_time(data.get("created_time")))
        # The first line of its history (never pruned); `announce` writes the activity line once it is told about.
        lead_history.record(row["id"], "received", actor="meta", at=created, mirror=False,
                            details={"ad": data.get("ad_name"), "test": is_test, "organic": bool(data.get("is_organic"))})
        lqs.record(links)
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


def _email_html(title_html, rows, link, link_label, footer):
    e = html.escape
    cells = "".join(
        f"<tr><td style='padding:4px 16px 4px 0;color:#5b6b78'>{e(k)}</td>"
        f"<td style='padding:4px 0'>{v}</td></tr>" for k, v in rows)
    return ("<div style='font-family:-apple-system,Segoe UI,sans-serif;color:#15212b;max-width:520px'>"
            f"{title_html}<table style='font-size:15px;border-collapse:collapse'>{cells}</table>"
            f"<p style='margin:20px 0'><a href='{e(link)}' style='background:#15212b;color:#fff;"
            f"padding:10px 16px;border-radius:8px;text-decoration:none'>{e(link_label)}</a></p>"
            f"<p style='color:#5b6b78;font-size:13px'>{e(footer)}</p></div>")


def _contact_rows(lead, ad):
    e = html.escape
    return (("Phone", f"<a href='tel:{e(lead['phone'] or '')}'>{e(lead['phone'] or '-')}</a>"),
            ("Email", f"<a href='mailto:{e(lead['email'] or '')}'>{e(lead['email'] or '-')}</a>"),
            ("Business", e(lead["business_type"] or "business not given")), ("From ad", e(ad)))


def render_email(lead, context_line=None):
    """The new-lead email. context_line: a returning lead's "Asked before: …" (L2). A lead that looks like junk
    still alerts, and says so in the subject."""
    name = lead["full_name"] or "Someone"
    business = lead["business_type"] or "business not given"
    link = __import__("notify").link(f"/leads.html#lead={lead['id']}")
    test = " (test lead)" if lead["is_test"] else ""
    junk = " (looks like junk)" if lead.get("junk_flags") and not lead["is_test"] else ""
    ad = lead["ad_name"] or ("none, filled in without an ad" if lead.get("is_organic") else "-")
    subject = f"New lead{test}{junk}: {name}, {business}"
    footer = "Call within the hour if you can. Leads that hear back fast are the ones that turn into calls."
    extra = [context_line] if context_line else []
    if junk:
        extra.append(f"This looks like junk: {__import__('lead_quality').flag_text(lead['junk_flags'])}")
    lines = [f"{name} asked for a free intro call{test}.", *extra, "",
             f"Phone:    {lead['phone'] or '-'}", f"Email:    {lead['email'] or '-'}", f"Business: {business}", f"From ad:  {ad}",
             "", f"Open the lead: {link}", "", footer]
    e = html.escape
    title = (f"<p style='font-size:18px;margin:0 0 12px'><b>{e(name)}</b> asked for a free intro call{e(test)}.</p>"
             + "".join(f"<p style='margin:0 0 12px'>{e(x)}</p>" for x in extra))
    return subject, "\n".join(lines), _email_html(title, _contact_rows(lead, ad), link, "Open the lead", footer)


def render_repeat_email(lead, root, can_see_root, owner_name):
    """'Asked again: Maria Lopez, Wholesale bakery': no automatic reply went out, and the work goes on the first lead.
    A person who can't see the first lead's campaign learns only that they asked before."""
    import lead_quality
    import notify
    subject, first = lead_quality.asked_again(lead, root, owner_name, can_see_root)
    ad = lead["ad_name"] or "none, filled in without an ad"
    target = root["id"] if can_see_root else lead["id"]
    link = notify.link(f"/leads.html#lead={target}")
    label = "Open the first lead" if can_see_root else "Open the lead"
    footer = "No automatic reply went out: they got one the first time. Work it on the first lead; this one doesn't count twice."
    lines = [first, "", f"Phone:    {lead['phone'] or '-'}", f"Email:    {lead['email'] or '-'}", f"From ad:  {ad}", "",
             f"{label}: {link}", "", footer]
    rows = _contact_rows(lead, ad)
    return subject, "\n".join(lines), _email_html(f"<p style='font-size:18px;margin:0 0 12px'>{html.escape(first)}</p>",
                                                  (rows[0], rows[1], rows[3]), link, label, footer)


def repeat_recipients(lead, root):
    """The repeat's usual people plus the first lead's owner (active, wanting lead emails, of this account), each
    with whether they can see the first lead's campaign."""
    import notify as notify_mod
    people = {r["id"]: r for r in _staff(lead["campaign_id"])}
    if root.get("owner_id") and root["owner_id"] not in people:
        o = db.query("SELECT id, name, email, account_id, notify_new_leads, role FROM users WHERE id = %s AND is_active",
                     (root["owner_id"],), one=True)
        if o and notify_mod.serves(o, __import__("account_ctx").current()):
            people[o["id"]] = o
    ids = list(people)
    roles = {r["id"]: r for r in db.query(
        """SELECT u.id, u.role, EXISTS (SELECT 1 FROM campaign_members cm WHERE cm.user_id = u.id AND cm.campaign_id = %s) AS member
           FROM users u WHERE u.id = ANY(%s)""", (root.get("campaign_id"), ids))} if ids else {}
    out = []
    for uid, p in people.items():
        r = roles.get(uid) or {}
        see = r.get("role") == "admin" or bool(r.get("member")) or uid == root.get("owner_id") or root.get("campaign_id") == lead["campaign_id"]
        out.append({**p, "can_see_root": see})
    return out


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


def alert_phones(lead, context_line=None, root=None):
    """A phone alert for everyone who gets the lead email: Telegram when they linked it, otherwise
    a push to each of their devices with notifications on. The email goes out as well. With `root` the
    lead is a repeat: "Asked again: Maria Lopez", to the usual people plus the first lead's owner."""
    import lead_quality
    import notify
    import push
    if root:
        people = {p["id"]: p for p in repeat_recipients(lead, root)}
        owner = _owner_name(root)
        ids = list(people)
    else:
        title, lines = notify.lead_alert(lead)
        if context_line:
            lines = [context_line] + lines
        ids = recipient_ids(lead)
    by_tg = set(notify.telegram_people(ids))
    by_push = push.has_devices(ids)
    wanted = {r["id"] for r in db.query("SELECT id FROM users WHERE id = ANY(%s) AND notify_new_leads", (ids,))} if ids else set()
    for uid in ids:
        channel = "telegram" if uid in by_tg else "push" if uid in by_push and uid in wanted else None
        if not channel:
            continue
        url, label = notify.link(f"/leads.html#lead={lead['id']}"), "Open the lead"
        if root:
            see = people[uid]["can_see_root"]
            title = f"Asked again: {lead.get('full_name') or 'Someone'}"
            lines = [lead_quality.asked_again(lead, root, owner, see)[1]]
            if see:
                url, label = notify.link(f"/leads.html#lead={root['id']}"), "Open the first lead"
        notify.queue(uid, channel, "lead", title, lines, url, label, ref=str(lead["id"]),
                     dedupe_key=f"lead:{lead['id']}:{channel}:{uid}")


def _owner_name(root):
    if not root.get("owner_id"):
        return None
    row = db.query("SELECT name FROM users WHERE id = %s", (root["owner_id"],), one=True)
    return row["name"] if row else None


def queue_emails(lead, context_line=None, root=None):
    """The new-lead email, one per person who wants it (nobody sees who else gets the lead), sent
    and retried by the notification queue. With `root` it is the "Asked again" email of a repeat."""
    import notify
    if not mailer.configured():
        return
    if root:
        owner = _owner_name(root)
        for r in repeat_recipients(lead, root):
            if r["notify_new_leads"]:
                subject, text, body_html = render_repeat_email(lead, root, r["can_see_root"], owner)
                notify.queue(r["id"], "email", "lead", subject, text.split("\n"), ref=str(lead["id"]), html=body_html,
                             dedupe_key=f"lead:{lead['id']}:email:{r['id']}")
        return
    subject, text, body_html = render_email(lead, context_line)
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
    # L2: a repeat tells the team "Asked again" (no automatic reply, no reminders); a returning lead is a new chance
    # with a line about the first time.
    import account_info
    import lead_quality
    first = lead.get("repeat_of") or lead.get("earlier_lead_id")
    root = db.query("SELECT * FROM leads WHERE id = %s", (first,), one=True) if first else None
    if lead.get("repeat_of") and root:
        steps = (("email", lambda l: queue_emails(l, root=root)), ("phone alerts", lambda l: alert_phones(l, root=root)))
    else:
        context = lead_quality.asked_before(root, account_info.tz()) if root else None
        steps = (("email", lambda l: queue_emails(l, context)), ("phone alerts", lambda l: alert_phones(l, context)),
                 ("automatic reply", replies.queue_auto))
    failed = False
    for name, step in steps:
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
