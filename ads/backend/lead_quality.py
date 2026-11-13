"""Lead quality (L2): the highest stage a lead reached, why leads are lost, repeats and junk. Pure, no database.

Which leads count, everywhere (00-PLAN S13): `counted()` = not a test and not a repeat (the same person asking
again within 90 days while their first lead is open counts once). How far they got: `qualified()` / `won()` /
`contacted()` read `max_stage`, the highest stage the lead reached, so a prospect who qualified and then said no
still counts toward cost per qualified lead. A ratchet test keeps every count of leads on these fragments."""
import re

import contact
import words

FUNNEL = ("new", "contacted", "qualified", "won")
RANK = {s: i for i, s in enumerate(FUNNEL)}
STAGE_WORDS = {"new": "New", "contacted": "Contacted", "qualified": "Qualified", "won": "Won", "lost": "Lost"}

LOST_REASONS = (            # key, label, hint (the dialog's order)
    ("no_response", "No response", "Never answered calls or emails"),
    ("not_fit", "Not a fit", "Not the kind of business we help"),
    ("too_small", "Too small", "Too early or too small for this"),
    ("price", "Price", "Said it costs too much"),
    ("went_elsewhere", "Went with someone else", "Chose another company or did it in-house"),
    ("spam", "Spam or fake", "Fake details, a bot, or someone selling to us"),
    ("duplicate", "Duplicate", "Same person as another lead"),
    ("other", "Other", "Say why in the note"),
)
REASON_KEYS = tuple(k for k, _, _ in LOST_REASONS)
REASON_LABELS = {k: label for k, label, _ in LOST_REASONS}
REAL_PERSON = {"not_fit", "too_small", "price", "went_elsewhere"}
NOT_A_NEW_CHANCE = {"spam", "duplicate"}   # a fill after these is still a repeat
REPEAT_DAYS = 90
MIN_LEADS = 3            # = concepts.MIN_LEADS
SPEND_TIMES = 2          # = concepts.SPEND_TIMES
ANSWER_GROUPS_MAX = 12
NOTE_MAX = 500
PAGE_KEY, PAGE_LABEL = "page", "From the Page (no ad)"


# ---------------------------------------------------------------- SQL fragments (the one definition)

def counted(a="l"):
    return f"NOT {a}.is_test AND {a}.repeat_of IS NULL"


def qualified(a="l"):
    return f"{a}.max_stage IN ('qualified','won')"


def won(a="l"):
    return f"{a}.max_stage = 'won'"


def contacted(a="l"):
    return f"{a}.max_stage <> 'new'"   # stage-based (00-PLAN C5): a call nobody answered is a try, not contact


# ---------------------------------------------------------------- highest stage

def raise_max(current_max, new_status):
    """The highest stage after a move: Lost (or anything outside the funnel) never lowers it."""
    current_max = current_max if current_max in RANK else "new"
    return new_status if RANK.get(new_status, -1) > RANK[current_max] else current_max


def max_from_history(stages, contacted=False):
    """The Python twin of migration 040's backfill."""
    best = "contacted" if contacted else "new"
    for s in stages:
        best = raise_max(best, s)
    return best


def undo_max(max_now, change):
    """Back to `max_before` only while nothing has raised it since this move."""
    if change.get("max_after") and max_now == change["max_after"] and change.get("max_before") in RANK:
        return change["max_before"]
    return max_now


def clean_lost(status, reason, note):
    """(reason, note, error) for a stage move or a changed reason. Not Lost → nothing kept."""
    if status != "lost":
        return None, None, None
    if reason is not None and reason not in REASON_KEYS:
        return None, None, "Pick one of the reasons"
    note = str(note or "").strip()[:NOTE_MAX] or None
    if reason is None:
        return None, None, None
    return reason, note, None


# ---------------------------------------------------------------- junk

FLAG_CODES = ("fake_phone", "test_email", "throwaway_email", "short_name", "test_words", "same_answers")
FLAG_WORDS = {
    "fake_phone": "the phone number looks made up",
    "test_email": "the email is a test address",
    "throwaway_email": "the email is a throwaway address",
    "short_name": "the name is a single letter",
    "test_words": "the name or an answer says “test”",
    "same_answers": "every answer is the same",
}
TEST_WORDS = re.compile(r"\b(test|testing|asdf|qwerty|lorem|fake|dummy)\b", re.I)
CONTACT_FIELDS = {"full_name", "first_name", "last_name", "email", "work_email", "phone_number", "phone"}
PLAIN_ANSWERS = {"yes", "no", "n/a", "na"}


def _answer_values(answers):
    """The non-contact answers, each one string."""
    out = []
    for a in answers or []:
        if str(a.get("name") or "").strip().lower() in CONTACT_FIELDS:
            continue
        out.append(", ".join(str(v) for v in a.get("values") or [] if v not in (None, "")).strip())
    return out


def _short_name(name):
    name = (name or "").strip()
    if not name:
        return False
    letters = [re.sub(r"[^A-Za-zÀ-ÿ]", "", p) for p in name.split()]
    return all(len(p) <= 1 for p in letters)


def _same_answers(values):
    vals = [v.strip().lower() for v in values]
    if len(vals) < 2 or len(set(vals)) != 1:
        return False
    v = vals[0]
    return len(v) >= 3 and v not in PLAIN_ANSWERS and not re.fullmatch(r"[\d.,\s]+", v)


def flags(lead):
    """What makes a lead look fake, in FLAG_CODES order. Hints only: they never hide a lead or stop an alert."""
    values = _answer_values(lead.get("answers"))
    found = {
        "fake_phone": contact.is_fake_phone(lead.get("phone")),
        "test_email": contact.is_test_email(lead.get("email")),
        "throwaway_email": contact.is_throwaway_email(lead.get("email")),
        "short_name": _short_name(lead.get("full_name")),
        "test_words": any(TEST_WORDS.search(t or "") for t in [lead.get("full_name")] + values),
        "same_answers": _same_answers(values),
    }
    return [c for c in FLAG_CODES if found[c]]


def _and(parts):
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def flag_text(codes):
    """One plain sentence: 'The phone number looks made up and the email is a test address.'"""
    parts = [FLAG_WORDS[c] for c in codes if c in FLAG_WORDS]
    if not parts:
        return ""
    text = _and(parts)
    return text[0].upper() + text[1:] + "."


def is_junk(lead):
    """The only definition of junk (00-PLAN C8): marked spam, or flagged, not dismissed, never got past New and
    not lost as a real person."""
    if lead.get("lost_reason") == "spam":
        return True
    return bool(lead.get("junk_flags")) and not lead.get("junk_dismissed") and lead.get("max_stage", "new") == "new" \
        and lead.get("lost_reason") not in REAL_PERSON


# ---------------------------------------------------------------- repeats

def match_kind(original):
    """A new fill from someone whose first lead is open (or was spam or a duplicate) is a repeat; after a Won or a
    real Lost it is a new chance: returning."""
    if original.get("status") == "won":
        return "returning"
    if original.get("status") == "lost" and original.get("lost_reason") not in NOT_A_NEW_CHANCE:
        return "returning"
    return "repeat"


def _name(lead):
    return (lead.get("full_name") or "").strip() or "Someone"


def asked_again(lead, root, owner_name, can_see_root):
    """(subject, first line) of the 'Asked again' alert."""
    business = lead.get("business_type") or "business not given"
    source = lead.get("ad_name") or "the Page, no ad"
    first = f"{_name(lead)} asked again (from {source})."
    if not can_see_root:
        return f"Asked again: {_name(lead)}, {business}", f"{first} They asked before in another campaign."
    owner = f"is with {owner_name}" if owner_name else "has no owner yet"
    return (f"Asked again: {_name(lead)}, {business}",
            f"{first} Their first request {owner}, stage {STAGE_WORDS.get(root.get('status'), 'New')}.")


def reason_words(reason):
    return REASON_LABELS.get(reason) or "no reason given"


def asked_before(root, tz):
    """The returning lead's line: 'Asked before: Sep 2, Lost (No response).' / 'Already a client: Won on Sep 9.'"""
    if root.get("status") == "won":
        at = root.get("status_changed_at") or root["created_time"]
        return f"Already a client: Won on {words.day(at.astimezone(tz))}."
    day = words.day(root["created_time"].astimezone(tz))
    if root.get("status") == "lost":
        return f"Asked before: {day}, Lost ({reason_words(root.get('lost_reason'))})."
    return f"Asked before: {day}, {STAGE_WORDS.get(root.get('status'), 'New')}."


# ---------------------------------------------------------------- lead quality by ad, form and answer

def _answer(lead, question):
    for a in lead.get("answers") or []:
        if a.get("name") == question:
            return ", ".join(str(v) for v in a.get("values") or [] if v not in (None, "")).strip()
    return ""


def group_key(lead, by, question=None):
    """(key, label) of the row this lead belongs to."""
    if by == "form":
        fid = lead.get("form_id")
        return (fid, lead.get("form_name") or f"Form {fid}") if fid else ("none", "No form")
    if by == "answer":
        value = _answer(lead, question)
        return (value.lower(), value) if value else ("", "Not answered")
    if not lead.get("ad_id"):
        return PAGE_KEY, PAGE_LABEL
    return lead["ad_id"], lead.get("ad_name") or f"Ad {lead['ad_id']}"


def lost_counts(leads):
    """{reason: n} for counted Lost leads, in LOST_REASONS order, 'none' for no reason given; only reasons seen."""
    seen = {}
    for l in leads:
        if l.get("is_test") or l.get("repeat_of") or l.get("status") != "lost":
            continue
        k = l.get("lost_reason") if l.get("lost_reason") in REASON_KEYS else "none"
        seen[k] = seen.get(k, 0) + 1
    return {k: seen[k] for k in REASON_KEYS + ("none",) if k in seen}


def form_spend(leads, ad_spend):
    """{form id: spend} from the ads whose leads all came through one form (Meta reports spend per ad, never per
    form; an ad whose leads came through two forms or none is left out)."""
    forms = {}
    for l in leads:
        if l.get("ad_id") and l.get("form_id"):
            forms.setdefault(l["ad_id"], set()).add(l["form_id"])
    out = {}
    for ad, fs in forms.items():
        if len(fs) == 1 and ad in ad_spend:
            f = next(iter(fs))
            out[f] = out.get(f, 0) + ad_spend[ad]
    return out


def _rate(n, d):
    return round(n / d, 4) if d else None


def _row(key, label, by):
    return {"key": key, "label": label, "is_page": by == "ad" and key == PAGE_KEY, "fills": 0, "leads": 0, "repeats": 0,
            "junk": 0, "qualified": 0, "won": 0, "_lost": []}


def summarize(leads, spend, by, question, target_cents, meta_leads=None, total_spend_cents=None, labels=None):
    """Rows per ad / form / answer, totals, the cheapest qualified row. `spend` = {key: cents} (ads and forms; never
    answers); `labels` names rows that have spend but no leads."""
    rows = {}
    counted_leads = [l for l in leads if not l.get("is_test")]
    for l in counted_leads:
        key, label = group_key(l, by, question)
        r = rows.get(key)
        if r is None:
            r = rows[key] = _row(key, label, by)
        elif by == "form" and l.get("form_name"):
            r["label"] = l["form_name"]     # the latest name wins (leads come oldest first)
        r["fills"] += 1
        if l.get("repeat_of"):
            r["repeats"] += 1
            continue
        r["leads"] += 1
        r["junk"] += int(is_junk(l))
        r["qualified"] += int(l.get("max_stage") in ("qualified", "won"))
        r["won"] += int(l.get("max_stage") == "won")
        r["_lost"].append(l)
    ok = not (by == "answer" and len(rows) > ANSWER_GROUPS_MAX)
    if by != "answer":
        for key, cents in (spend or {}).items():
            if cents and key not in rows:
                rows[key] = _row(key, (labels or {}).get(key) or (f"Form {key}" if by == "form" else f"Ad {key}"), by)
    out = []
    for r in rows.values():
        lost = lost_counts(r.pop("_lost"))
        cents = None if by == "answer" or r["is_page"] else int((spend or {}).get(r["key"]) or 0)
        enough_spend = cents is not None and (not target_cents or cents >= SPEND_TIMES * target_cents)
        out.append({**r, "lost": lost, "spend_cents": cents, "qualified_rate": _rate(r["qualified"], r["leads"]),
                    "junk_rate": _rate(r["junk"], r["leads"]),
                    "cpq_cents": round(cents / r["qualified"]) if cents is not None and r["qualified"] else None,
                    "rates_enough": r["leads"] >= MIN_LEADS,
                    "cpq_enough": r["qualified"] >= MIN_LEADS and enough_spend})
    out.sort(key=lambda r: (r["is_page"], not r["cpq_enough"], r["cpq_cents"] if r["cpq_enough"] else 0, -r["leads"], r["label"].lower()))
    judged = [r for r in out if r["cpq_enough"]]
    best = min(judged, key=lambda r: r["cpq_cents"])["key"] if len(judged) >= 2 else None
    totals = {k: sum(r[k] for r in out) for k in ("fills", "leads", "repeats", "junk", "qualified", "won")}
    total = int(total_spend_cents if total_spend_cents is not None else sum((spend or {}).values()))
    real = totals["leads"] - totals["junk"]
    totals.update(spend_cents=total, meta_leads=meta_leads,
                  cpl_meta_cents=round(total / meta_leads) if meta_leads else None,
                  cpl_real_cents=round(total / real) if real > 0 and total else None)
    return {"by": by, "question": question, "target_cents": target_cents, "rows": out if ok else [], "totals": totals,
            "best": best if ok else None, "answer_question_ok": ok}


NOUN = {"ad": "an ad", "form": "a form"}


def verdict(summary, target_cents, currency="USD"):
    """The one line above the table: {name (bold, or None), text}."""
    if summary["by"] == "answer":
        if not summary["answer_question_ok"]:
            return {"name": None, "text": "This question has typed answers, so they can't be grouped. Pick a question with set choices."}
        if summary["rows"]:
            return {"name": None, "text": "Spend can't be split by answer, so cost per qualified lead shows for ads and forms only."}
    if not summary["rows"]:
        return {"name": None, "text": "No leads in this period yet."}
    if summary.get("best"):
        best = next(r for r in summary["rows"] if r["key"] == summary["best"])
        return {"name": best["label"], "text": f"brings qualified leads cheapest: {words.money(best['cpq_cents'], currency)} each."}
    noun = NOUN.get(summary["by"], "an ad")
    if target_cents:
        return {"name": None, "text": f"Too early to compare: {noun} needs {MIN_LEADS} qualified leads and twice the "
                                      f"{words.money(target_cents, currency)} target in spend before its cost per qualified lead means much."}
    return {"name": None, "text": f"Too early to compare: {noun} needs {MIN_LEADS} qualified leads first. "
                                  "Set a target in Settings → Targets to judge against it."}


def junk_note(totals, currency="USD"):
    """'4 of 31 leads look like junk and 2 were repeats. Meta counts all of them, so …'"""
    junk, repeats, fills = totals["junk"], totals["repeats"], totals["fills"]
    if not junk and not repeats:
        return "No junk or repeats in this period."
    if junk:
        text = f"{junk} of {fills} leads {'looks' if junk == 1 else 'look'} like junk"
        if repeats:
            text += f" and {repeats} {'was a repeat' if repeats == 1 else 'were repeats'}"
    else:
        text = f"{repeats} of {fills} leads {'was a repeat' if repeats == 1 else 'were repeats'}"
    text += "."
    meta, real = totals.get("cpl_meta_cents"), totals.get("cpl_real_cents")
    if meta and real and meta < real:
        text += (f" Meta counts all of them, so its cost per lead ({words.money(meta, currency)}) is lower than the cost per "
                 f"real lead ({words.money(real, currency)}).")
    return text


def snapshot(leads):
    """For Claude's snapshot: per ad, counts only (never names, emails, phones, answers or notes)."""
    rows = {}
    for l in leads:
        if l.get("is_test"):
            continue
        key = l.get("ad_id")
        r = rows.setdefault(key, {"ad_id": key, "ad_name": l.get("ad_name") or ("From the Page (no ad)" if not key else None),
                                  "leads": 0, "repeats": 0, "junk": 0, "qualified": 0, "won": 0, "_l": [], "junk_flags": {}})
        r["ad_name"] = r["ad_name"] or l.get("ad_name")
        if l.get("repeat_of"):
            r["repeats"] += 1
            continue
        r["leads"] += 1
        r["junk"] += int(is_junk(l))
        r["qualified"] += int(l.get("max_stage") in ("qualified", "won"))
        r["won"] += int(l.get("max_stage") == "won")
        r["_l"].append(l)
        for c in l.get("junk_flags") or []:
            r["junk_flags"][c] = r["junk_flags"].get(c, 0) + 1
    out = []
    for r in sorted(rows.values(), key=lambda r: (-r["leads"], str(r["ad_name"]))):
        r["lost"] = lost_counts(r.pop("_l"))
        r["junk_flags"] = r.pop("junk_flags")
        out.append(r)
    totals = {k: sum(r[k] for r in out) for k in ("leads", "repeats", "junk", "qualified", "won")}
    totals["lost"] = lost_counts(leads)
    return out, totals


SNAPSHOT_NOTES = ("Qualified and won count the highest stage a lead reached. Repeats (the same email or phone within 90 days "
                  "while the first lead is open) are counted once. Junk = marked spam, or flagged as looking fake and never contacted.")
