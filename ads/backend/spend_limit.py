"""FU-B: the ad account's spending limit (act_<id> spend_cap), the account-wide ceiling on total spend.

Read live from Meta, changed only after a person's yes (an Accept on Claude's suggestion, or the Settings → Targets
dialog), by an owner or this account's admin. Meta reads the limit in cents and writes it in dollars: both
conversions are in money_rules (spend_cap_cents / spend_cap_param) and nowhere else. Right before a write the limit
is read again and must still be the amount the person was shown; right after, it is read back, and when Meta stored
anything but the intended cents the console puts the previous value back the same way, raises a bad alert and
pauses limit changes until the console's owner clears them. A read-back Meta doesn't answer pauses too, without a
blind put-back (we don't know what is there). spend_cap's action parameter (reset / delete) is never sent."""
import json
import logging
from datetime import datetime, timezone

import account_ctx
import account_info
import db
import meta_client
import money_rules
import settings_store
import words
from util import log_activity

FIELDS = "spend_cap,amount_spent,currency,name"
LOCK = "spend_limit:{account}"
BLOCK_KEY = "spend_limit_block"
CHECK_KEY = "spend_limit_last_check"
READBACK_TIMEOUT = meta_client.READ_TIMEOUT  # a read-back Meta leaves unanswered this long counts as unanswered
HREF = "/settings.html#spend-limit"
log = logging.getLogger(__name__)


def act():
    return f"act_{settings_store.get('meta_ad_account_id')}"


def blocked():
    """The pause after a read-back that didn't match ({at, by_change_id, wanted_cents, got_cents, restored, …}), or None."""
    raw = settings_store.get(BLOCK_KEY)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return {"at": None}


def money(cents, currency=None):
    return "no limit" if cents is None else words.money(cents, currency or account_info.currency())


def paused_words(block):
    when = ""
    try:
        when = f"on {words.day(words.local(datetime.fromisoformat(block['at']), account_info.tz()))} "
    except (KeyError, TypeError, ValueError):
        pass
    return (f"Spending-limit changes are paused: {when}Meta stored a different amount than we sent. "
            "The console's owner checks Ads Manager and clears it in Settings → Targets.")


def _stored(limit_cents, spent_cents):
    """Keep account_snapshot (the frame, Results and the alerts read it) in step with what Meta just said."""
    snap = account_info.snapshot()
    snap.update(spend_cap_cents=limit_cents, amount_spent_cents=spent_cents)
    settings_store.set("account_snapshot", json.dumps(snap))


def rate_cents():
    """The current pace: the average of the last 7 complete days (performance_api.pacing_data)."""
    import performance_api
    return performance_api.pacing_data(None)["rate_cents"]


def _parse(a):
    try:
        limit = money_rules.spend_cap_cents(a.get("spend_cap"))
        spent = int(str(a.get("amount_spent") or 0))
    except ValueError:
        raise meta_client.MetaError(f"Meta sent a spending limit the console can't read ({a.get('spend_cap')!r}), "
                                    "so nothing is changed here. Check it in Ads Manager.") from None
    return limit, spent


def live():
    """One fresh read of act_<id>: {limit_cents, spent_cents, currency, name, rate_cents, blocked, checked_at, act}."""
    a = meta_client.get(act(), fields=FIELDS)
    limit, spent = _parse(a)
    _stored(limit, spent)
    return {"limit_cents": limit, "spent_cents": spent, "currency": (a.get("currency") or account_info.currency()).upper(),
            "name": a.get("name") or "the ad account", "rate_cents": rate_cents(), "blocked": blocked(),
            "checked_at": settings_store.get(CHECK_KEY), "act": act()}


def _plan_from(now, new_cents, remove):
    change = money_rules.spend_limit_change(now["limit_cents"], None if remove else new_cents, now["spent_cents"],
                                            now["rate_cents"], now["currency"])
    problem = paused_words(now["blocked"]) if now["blocked"] else money_rules.spend_limit_problem(change, True, True)
    return {**now, **change, "problem": problem}


def plan(new_cents, remove=False):
    """What the confirmation shows, read fresh: old → new, spent so far, days left now and after, and any refusal
    (a removal or a raise past double shown as allowed here; each is confirmed separately)."""
    return _plan_from(live(), new_cents, remove)


def _record(user, row, action, old, new, ok, error=None, proposal_id=None):
    import ads_api
    ads_api.record(user, "account", row, action, old, new, ok, error=error, proposal_id=proposal_id)
    return db.query("SELECT id FROM meta_changes WHERE action = %s AND entity_id = %s ORDER BY id DESC LIMIT 1",
                    (action, row["id"]), one=True)["id"]


def _pause(change_id, wanted, raw, restored, restored_cents, currency, unread=False):
    """Pause limit changes and raise the bad alert. `raw` is the spend_cap Meta read back, as it came."""
    import alerts
    at = datetime.now(timezone.utc).isoformat()
    try:
        got = money_rules.spend_cap_cents(raw)
        got_raw = None
    except ValueError:
        got, got_raw = None, str(raw)[:40]
    settings_store.set(BLOCK_KEY, json.dumps({"at": at, "by_change_id": change_id, "wanted_cents": wanted, "got_cents": got,
                                              "got_raw": got_raw, "restored": restored, "restored_cents": restored_cents,
                                              "unread": unread}))
    if unread:
        lines = [f"We sent {money(wanted, currency)}; Meta didn't answer when we read it back, so we don't know what it stored. "
                 "Check the limit in Ads Manager → Billing.",
                 "Limit changes are paused until you clear them in Settings → Targets."]
        title = "Couldn't check the account spending limit after changing it"
    else:
        held = "checked: it held" if restored else "but couldn't confirm it held: check Ads Manager"
        lines = [f"We sent {money(wanted, currency)}; Meta stored {money_rules.limit_read_words(raw, currency)}. "
                 f"We put back {money(restored_cents, currency)} ({held}).",
                 "Limit changes are paused until you clear them in Settings → Targets."]
        title = "Meta stored a different spending limit than the console sent"
    alerts.raise_found([{"rule": "spend_limit_mismatch", "key": f"spend_limit_mismatch:{change_id or at}", "level": "bad",
                         "title": title, "lines": lines, "entity_id": "account", "campaign_id": None, "href": HREF,
                         "kind": "event"}])
    log_activity("spend_limit.paused", subject=act(), details={"wanted": wanted, "got": got, "got_raw": got_raw,
                                                                "restored": restored, "unread": unread})


def _send(act_id, cents, currency):
    """THE spend_cap write (a ratchet test holds it): cents always through money_rules.spend_cap_param."""
    meta_client.post(act_id, spend_cap=money_rules.spend_cap_param(cents, currency))


def apply(user, new_cents, *, remove, confirm_remove, from_cents, proposal_id=None, accept_big=False):
    """Change the limit on Meta. (error, info): error None when Meta holds the new limit (read back); else a sentence
    with ads_api's prefix (NOT_SENT: nothing reached Meta; UNKNOWN: don't know what Meta holds; CHECKED: the read-back
    refused it and the old value was put back). info may carry a fresh `plan` when the amounts moved, and `code`
    ("remove" / "big") when the change waits for its own second yes."""
    from ads_api import NOT_SENT
    pause = blocked()
    if pause:
        return NOT_SENT + paused_words(pause), {}
    with db.try_lock(LOCK.format(account=account_ctx.current())) as got_lock:
        if not got_lock:
            return NOT_SENT + "Someone is changing the limit right now. Try again in a moment.", {}
        pause = blocked()  # again under the lock: a change that held it may have just paused limit changes
        if pause:
            return NOT_SENT + paused_words(pause), {}
        try:
            now = live()
        except meta_client.MetaError as exc:
            return NOT_SENT + f"Couldn't read the limit from Meta, so nothing was changed: {exc}", {}
        currency, old = now["currency"], now["limit_cents"]
        if from_cents != old:
            return NOT_SENT + f"The limit on Meta is {money(old, currency)} now. Check the amounts again.", {"plan": _plan_from(now, new_cents, remove)}
        target = None if remove else new_cents
        change = money_rules.spend_limit_change(old, target, now["spent_cents"], now["rate_cents"], currency)
        problem = money_rules.spend_limit_problem(change, confirm_remove, accept_big)
        if problem:
            code = "remove" if change["remove"] and not confirm_remove else "big" if change["big"] and not accept_big else None
            return NOT_SENT + problem, {"plan": _plan_from(now, new_cents, remove), "code": code}
        try:
            money_rules.spend_cap_param(target, currency)
            money_rules.spend_cap_param(old, currency)
        except ValueError as exc:
            return NOT_SENT + f"The console can't write this limit: {exc}", {}
        row = {"id": now["act"], "name": now["name"], "campaign_id": None}
        lost = None
        try:
            _send(now["act"], target, currency)
        except meta_client.MetaError as exc:
            if not exc.unknown:
                _record(user, row, "spend_limit", old, target, False, error=str(exc), proposal_id=proposal_id)
                return str(exc), {}
            lost = exc  # no answer: Meta may have stored it anyway, so it's read back like any other write
        try:
            return _check(user, row, now, target, lost, proposal_id)
        except Exception:
            # Something broke after a write reached Meta and before it was checked: never leave that unpaused.
            try:
                _pause(None, target, None, False, None, currency, unread=True)
            except Exception:  # noqa: BLE001 - the original error is the one to see
                log.exception("spend limit: couldn't pause after an unexpected error")
            raise


def _check(user, row, now, target, lost, proposal_id):
    """The read-back after a write (answered, or `lost` when Meta didn't answer it). The change is recorded only now,
    with what Meta was seen to hold, so History never shows a change Meta didn't keep."""
    from ads_api import CHECKED, UNKNOWN
    currency, old, act_id = now["currency"], now["limit_cents"], now["act"]
    try:
        read = meta_client.get(act_id, fields="spend_cap,amount_spent", timeout=READBACK_TIMEOUT)
    except meta_client.MetaError:
        change_id = _record(user, row, "spend_limit", old, target, False, proposal_id=proposal_id,
                            error="Meta didn't answer when the console read the limit back: not confirmed")
        _pause(change_id, target, None, False, None, currency, unread=True)
        return (UNKNOWN + "Couldn't read the limit back from Meta; check it in Ads Manager. Limit changes are paused until "
                "the console's owner clears them in Settings → Targets."), {}
    raw = read.get("spend_cap")
    if money_rules.readback_ok(target, raw):
        _record(user, row, "spend_limit", old, target, True, proposal_id=proposal_id)
        try:
            _stored(target, int(str(read.get("amount_spent") or now["spent_cents"])))
        except ValueError:
            pass
        settings_store.set(CHECK_KEY, datetime.now(timezone.utc).isoformat())
        return None, {"limit_cents": target}
    if lost and money_rules.readback_ok(old, raw):
        _record(user, row, "spend_limit", old, target, False, error=str(lost), proposal_id=proposal_id)
        return (UNKNOWN + f"Meta didn't answer when the console sent {money(target, currency)}, and it still shows "
                f"{money(old, currency)}. It may still arrive: check Ads Manager before trying again."), {}
    said = money_rules.limit_read_words(raw, currency)
    change_id = _record(user, row, "spend_limit", old, target, False, error=f"Meta stored {said}", proposal_id=proposal_id)
    restored = False
    try:
        _send(act_id, old, currency)
        again = meta_client.get(act_id, fields="spend_cap", timeout=READBACK_TIMEOUT)
        restored = money_rules.readback_ok(old, again.get("spend_cap"))
        _record(user, row, "spend_limit_restore", target, old, restored,
                error=None if restored else f"Meta holds {again.get('spend_cap')!r} after the put-back", proposal_id=proposal_id)
    except meta_client.MetaError as exc:
        _record(user, row, "spend_limit_restore", target, old, False, error=str(exc), proposal_id=proposal_id)
    _pause(change_id, target, raw, restored, old, currency)
    if restored:
        _stored(old, now["spent_cents"])
    held = "" if restored else " (it couldn't confirm the put-back held: check Ads Manager)"
    return (CHECKED + f"Meta stored {said} instead of {money(target, currency)}, so the console put back "
            f"{money(old, currency)}{held} and paused limit changes."), {}


def unblock(user):
    """Owner only (the route checks): limit changes allowed again, the alert closed."""
    pause = blocked()
    settings_store.set(BLOCK_KEY, None)
    db.execute("UPDATE alerts SET resolved_at = now() WHERE rule = 'spend_limit_mismatch' AND resolved_at IS NULL")
    log_activity("spend_limit.unblocked", subject=act(), details={"was": pause})
    return pause


def view(now):
    """The Settings block: the live read plus what the paused note says."""
    pause = now.get("blocked")
    out = {k: now[k] for k in ("limit_cents", "spent_cents", "currency", "name", "rate_cents", "checked_at", "act")}
    out["days_left"] = money_rules.spend_limit_change(now["limit_cents"], now["limit_cents"], now["spent_cents"],
                                                      now["rate_cents"])["days_now"]
    out["blocked"] = None if not pause else {**pause, "words": paused_words(pause)}
    return out
