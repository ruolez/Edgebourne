"""Lead quality (L2), the database side: keys and flags at insert, the repeat match and links, hand links and
unlinks, the leads of a window for Results, and the one-off pass over older leads. The rules are in the pure
`lead_quality` and `contact` modules.

Every match carries an explicit `account_id` predicate as well as row-level security (the worker's owner paths
bypass RLS), runs under `pg_advisory_xact_lock(hashtext('lead-match'), account)` inside the insert's transaction
(two fills from one person at once: the second becomes the repeat), and the composite foreign keys refuse a link
across accounts."""
import logging

import account_ctx
import account_info
import contact
import db
import lead_history
import lead_quality as lq
import settings_store
from util import log_activity

log = logging.getLogger(__name__)

BACKFILL_FLAG = "lead_quality_backfill_v1"
BATCH = 200
WINDOW = f"interval '{lq.REPEAT_DAYS} days'"


def repeat_check_on():
    return settings_store.get("lead_repeat_check") != "0"


def junk_flags_on():
    return settings_store.get("lead_junk_flags") != "0"


def prepare(parsed, field_data, is_test):
    """{email_key, phone_key, junk_flags} for a lead about to be stored (test leads: none)."""
    if is_test:
        return {"email_key": None, "phone_key": None, "junk_flags": []}
    return {"email_key": contact.email_key(parsed.get("email")), "phone_key": contact.phone_key(parsed.get("phone")),
            "junk_flags": lq.flags({**parsed, "answers": field_data}) if junk_flags_on() else []}


def lock(cur):
    cur.execute("SELECT pg_advisory_xact_lock(hashtext('lead-match'), %s)", (account_ctx.current(),))


ROOT_COLS = "id, status, lost_reason, max_stage, owner_id, campaign_id, created_time, status_changed_at, account_id"
KEYS = """((%(email_key)s::text IS NOT NULL AND {a}.email_key = %(email_key)s)
           OR (%(phone_key)s::text IS NOT NULL AND {a}.phone_key = %(phone_key)s))"""


def _match(cur, lead):
    """The root (first lead) of the most recent earlier lead with the same email or phone within 90 days."""
    cur.execute(
        f"""SELECT COALESCE(o.repeat_of, o.id) AS root_id FROM leads o
            WHERE o.id <> %(id)s AND NOT o.is_test AND o.account_id = %(acct)s
            AND (o.created_time, o.id) < (%(created)s, %(id)s) AND o.created_time > %(created)s - {WINDOW}
            AND {KEYS.format(a='o')}
            ORDER BY o.created_time DESC, o.id DESC LIMIT 1""", lead)
    row = cur.fetchone()
    if not row:
        return None
    cur.execute(f"SELECT {ROOT_COLS} FROM leads WHERE id = %s AND account_id = %s", (row["root_id"], lead["acct"]))
    return cur.fetchone()


def _attach(cur, lead_id, root, source, acct):
    """Link one lead to a root: a repeat folds into it, a returning lead only points at it. Returns the kind."""
    kind = lq.match_kind(root)
    if kind == "repeat":
        cur.execute("""UPDATE leads SET repeat_of = %s, earlier_lead_id = %s, repeat_source = %s
                       WHERE id = %s AND account_id = %s RETURNING max_stage""", (root["id"], root["id"], source, lead_id, acct))
        moved = cur.fetchone()
        # Its own repeats follow it to the root, and the person's progress isn't lost from the counts.
        cur.execute("""UPDATE leads SET repeat_of = %s, earlier_lead_id = %s WHERE repeat_of = %s AND account_id = %s""",
                    (root["id"], root["id"], lead_id, acct))
        if moved and lq.raise_max(root["max_stage"], moved["max_stage"]) != root["max_stage"]:
            cur.execute("UPDATE leads SET max_stage = %s, max_stage_at = now() WHERE id = %s AND account_id = %s",
                        (moved["max_stage"], root["id"], acct))
            root["max_stage"] = moved["max_stage"]
    else:
        cur.execute("UPDATE leads SET earlier_lead_id = %s, repeat_source = %s WHERE id = %s AND account_id = %s",
                    (root["id"], source, lead_id, acct))
    return kind


def link_in(cur, lead, check):
    """Inside the insert's transaction (lock held): match a stored lead and link it, then link newer leads that
    were stored before it (a catch-up can store an older lead late). Returns the history events to record once
    committed: [(lead_id, kind, details)]. lead: {id, created, email_key, phone_key}. `check`: the Spot repeats
    setting, read before the transaction opened (nothing but `cur` may touch the database in here)."""
    if not check or not (lead.get("email_key") or lead.get("phone_key")):
        return []
    lead = {**lead, "acct": account_ctx.current()}
    events = []
    root = _match(cur, lead)
    if root:
        kind = _attach(cur, lead["id"], root, "auto", lead["acct"])
        events.append((lead["id"], kind, {"of": root["id"]}))
        if kind == "returning":
            root = None
    if root is None:  # this lead is the first of its person (or a new chance): later fills fold into it
        cur.execute(f"SELECT {ROOT_COLS} FROM leads WHERE id = %s AND account_id = %s", (lead["id"], lead["acct"]))
        root = cur.fetchone()
    cur.execute(
        f"""SELECT n.id FROM leads n
            WHERE n.account_id = %(acct)s AND NOT n.is_test AND n.id <> %(id)s AND n.id <> %(root)s
            AND n.repeat_of IS NULL AND n.earlier_lead_id IS NULL AND NOT n.repeat_checked
            AND (n.created_time, n.id) > (%(created)s, %(id)s) AND n.created_time < %(created)s + {WINDOW}
            AND {KEYS.format(a='n')} ORDER BY n.created_time, n.id""", {**lead, "root": root["id"]})
    for n in cur.fetchall():
        kind = _attach(cur, n["id"], root, "auto", lead["acct"])
        events.append((n["id"], kind, {"of": root["id"], "late": True}))
    return events


def record(events, actor="system", mirror=True):
    for lead_id, kind, details in events:
        lead_history.record(lead_id, kind, details=details, actor=actor, mirror=mirror)
        if kind == "repeat":  # the first lead's history says so too (its page is where the person is worked)
            lead_history.record(details["of"], "repeat", details={"repeat": lead_id}, actor=actor, mirror=False)


class Refused(ValueError):
    pass


def hand_link(a, b):
    """'Same person as…': the older person stays the first lead, the newer one (and its repeats) fold into it.
    a, b: visible lead rows. Returns (root id, folded id)."""
    if a["id"] == b["id"]:
        raise Refused("That's the same lead")
    acct = account_ctx.current()
    with db.transaction() as cur:
        lock(cur)
        roots = []
        for x in (a, b):
            cur.execute(f"SELECT {ROOT_COLS} FROM leads WHERE id = %s AND account_id = %s", (x.get("repeat_of") or x["id"], acct))
            roots.append(cur.fetchone())
        if not all(roots):
            raise Refused("One of these leads is gone")
        if roots[0]["id"] == roots[1]["id"]:
            raise Refused("They're already linked")
        root, newer = sorted(roots, key=lambda r: (r["created_time"], r["id"]))
        cur.execute("""UPDATE leads SET repeat_of = %s, earlier_lead_id = %s, repeat_source = 'hand', repeat_checked = FALSE
                       WHERE id = %s AND account_id = %s RETURNING max_stage""", (root["id"], root["id"], newer["id"], acct))
        moved = cur.fetchone()
        cur.execute("UPDATE leads SET repeat_of = %s, earlier_lead_id = %s WHERE repeat_of = %s AND account_id = %s",
                    (root["id"], root["id"], newer["id"], acct))
        raised = lq.raise_max(root["max_stage"], moved["max_stage"])
        if raised != root["max_stage"]:
            cur.execute("UPDATE leads SET max_stage = %s, max_stage_at = now() WHERE id = %s AND account_id = %s", (raised, root["id"], acct))
    lead_history.record(newer["id"], "linked", details={"of": root["id"], "max_before": root["max_stage"], "max_after": raised})
    lead_history.record(root["id"], "linked", details={"repeat": newer["id"]}, mirror=False)
    return root["id"], newer["id"]


def unlink(lead):
    """'Not the same person': a normal lead again, counted on its own, never linked again by itself. The first
    lead's highest stage stays (an admin can correct it)."""
    if not lead.get("repeat_of") and not lead.get("earlier_lead_id"):
        raise Refused("This lead isn't linked to another one")
    db.execute("""UPDATE leads SET repeat_of = NULL, earlier_lead_id = NULL, repeat_source = NULL, repeat_checked = TRUE
                  WHERE id = %s""", (lead["id"],))
    lead_history.record(lead["id"], "unlinked", details={"of": lead.get("repeat_of") or lead.get("earlier_lead_id")})


LEAD_COLS = """l.id, l.created_time, l.ad_id, l.ad_name, l.form_id, l.form_name, l.answers, l.repeat_of, l.max_stage, l.status,
               l.lost_reason, l.junk_flags, l.junk_dismissed, l.is_organic, l.is_test, l.campaign_id"""


def leads_for_window(campaign_ids, start, end, campaign_id=None):
    """Real leads (repeats included) that arrived on these account days, oldest first; campaign_ids None = all."""
    clauses, params = ["NOT l.is_test", "(l.created_time AT TIME ZONE %s)::date BETWEEN %s AND %s"], [account_info.tz_name(), start, end]
    if campaign_ids is not None:
        clauses.append("l.campaign_id = ANY(%s)")
        params.append(campaign_ids)
    if campaign_id:
        clauses.append("l.campaign_id = %s")
        params.append(campaign_id)
    return db.query(f"SELECT {LEAD_COLS} FROM leads l WHERE {' AND '.join(clauses)} ORDER BY l.created_time, l.id", params)


def backfill_once(force=False):
    """The leads stored before L2 get their keys and flags, oldest first, and past repeats are linked: no alerts, no
    Meta events. 200 per pass so a big account never holds the worker; once an account is done, one activity line
    says what was found and the pass is a no-op from then on (every new lead is checked when it is stored).
    `force`: the dev seed, whose rows are inserted by hand."""
    if settings_store.get(BACKFILL_FLAG) and not force:
        return 0
    rows = db.query("""SELECT id, created_time, full_name, email, phone, answers, is_test FROM leads
                       WHERE NOT quality_checked ORDER BY created_time, id LIMIT %s""", (BATCH,))
    check = repeat_check_on()
    for r in rows:
        prep = prepare(r, r["answers"], r["is_test"])
        with db.transaction() as cur:
            lock(cur)
            cur.execute("""UPDATE leads SET email_key = %s, phone_key = %s, junk_flags = %s, quality_checked = TRUE
                           WHERE id = %s AND NOT quality_checked RETURNING id, repeat_of, earlier_lead_id, repeat_checked""",
                        (prep["email_key"], prep["phone_key"], prep["junk_flags"], r["id"]))
            row = cur.fetchone()
            events = []
            if row and not r["is_test"] and not (row["repeat_of"] or row["earlier_lead_id"] or row["repeat_checked"]):
                events = link_in(cur, {"id": r["id"], "created": r["created_time"], **prep}, check)
        record(events, mirror=False)
    if len(rows) < BATCH and not settings_store.get(BACKFILL_FLAG):
        n = db.query("""SELECT COUNT(*) /* every fill */ AS leads, COUNT(*) FILTER (WHERE repeat_of IS NOT NULL) AS repeats,
                               COUNT(*) FILTER (WHERE earlier_lead_id IS NOT NULL AND repeat_of IS NULL) AS returning,
                               COUNT(*) FILTER (WHERE junk_flags <> '{}') AS flagged FROM leads WHERE NOT is_test""", one=True)
        log_activity("leads.quality_backfill", actor="system", details={k: int(v) for k, v in n.items()})
        settings_store.set(BACKFILL_FLAG, "1")
    return len(rows)
