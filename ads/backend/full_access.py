"""FU-D: full access for the console owner's own conversations (Eugene, 2026-11-12: "Only me, with a re-check").

Pure rules. The unlock lives on one sign-in (user_sessions.full_until), never in the browser; a request asks for full
access only when the flagged owner typed it from an unlocked sign-in (desk_tasks.full_session), and the server decides
again when the Mac claims it (desk_tasks.access). The Mac never infers it: it reads `access` from the claim answer."""
import re
from datetime import timedelta

HOURS = 12
MAX_FAILS = 5
FAIL_WAIT = timedelta(minutes=15)
FULL_KINDS = ("question", "review", "research", "creative")  # typed on the Claude page
# Options that say a request didn't come from the owner's own typing (schedules, alerts, the follow-through after an
# Accept, Meta's advice, a swipe brief drafted from competitors' ads).
# "prefill": the composer was filled from a link (?ask=, Tests' "Make more like this", whose words an admin wrote);
# "research_page": typed on Research, which shows no full access bar (security review).
AUTOMATIC_OPTIONS = ("schedule", "schedule_id", "alert_key", "alert", "accepted", "advice", "brief", "prefill", "research_page")
# Of those, the ones whose words came from outside text: a conversation they started stays on the usual tools.
# (A follow-through's words are Claude's own suggestion from the same conversation, so it doesn't mark the thread;
# a Research question is the owner's own typing, only on a page without the bar.)
THREAD_AUTOMATIC = ("schedule", "schedule_id", "alert_key", "alert", "advice", "brief", "prefill")
# Only the owner's own business: in another account its admins read the answers and its own people write the Meta
# names a run reads, so text from them could steer the terminal's tools (security review).
HOME_ACCOUNT = 1
BRIDGE = (3, 0)  # desk 3.0 runs a full request with the terminal's tools; older helpers would run it sandboxed anyway

NOT_OWNER = "Only the console's owner can turn on full access"
TEMP_PASSWORD = "Choose your own password in Your account first: full access needs a password only you know."
ELSEWHERE = "Full access works only in your own account's conversations, so it ran with the usual tools."
SIGNED_OUT = "Full access had ended (signed out) before your Mac picked this up."
LOCKED = "Full access was locked before your Mac picked this up."
NOT_OWNER_NOW = "Full access is only for the console's owner, so it ran with the usual tools."
OTHERS = "Someone else wrote in this conversation, so it ran with the usual tools."
AUTOMATIC = "This conversation didn't start with your own typing (an automatic run or a link's words), so it ran with the usual tools."
OLD_HELPER = "Your Mac helper needs the update for full access (desk 3.0)."


def flagged_owner(user):
    """The one person who may ever unlock: an active admin of every account with the flag the migration set."""
    return bool(user) and user.get("role") == "admin" and not user.get("account_id") \
        and user.get("full_access_allowed") is True and user.get("is_active", True) is not False


def may_unlock(user):
    """None, or why not. Everyone else hears the same sentence (nothing hints that a flag exists). A temporary password
    (an admin's reset) never unlocks: whoever reset it knows it (security review)."""
    if not flagged_owner(user):
        return NOT_OWNER
    return TEMP_PASSWORD if user.get("must_change_password") else None


def may_lock(user):
    """Lock now needs only the person: locking is always safe."""
    return None if flagged_owner(user) else NOT_OWNER


def unlock_until(now):
    return now + timedelta(hours=HOURS)


def is_on(full_until, now):
    return full_until is not None and full_until > now


def fails_block(fails, fail_at, now):
    """Until when wrong passwords block another try, or None."""
    if (fails or 0) >= MAX_FAILS and fail_at is not None and now - fail_at < FAIL_WAIT:
        return fail_at + FAIL_WAIT
    return None


def next_fails(fails, fail_at, now):
    """The count after one more wrong password: it starts again once the last one is older than the wait."""
    if fail_at is None or now - fail_at >= FAIL_WAIT or (fails or 0) >= MAX_FAILS:
        return 1
    return (fails or 0) + 1


def automatic(options, swipe_ids=()):
    options = options or {}
    return bool(swipe_ids) or any(k in options for k in AUTOMATIC_OPTIONS)


def request_full(user, session_row, kind, options, swipe_ids, now, account_id):
    """At creation (a new request or a reply): True only for the flagged owner's own typed request in his own account,
    from a sign-in of his that is unlocked now. A request body can't say anything here: only these facts count."""
    return (flagged_owner(user) and bool(session_row) and session_row.get("user_id") == user.get("id")
            and is_on(session_row.get("full_until"), now) and kind in FULL_KINDS and not automatic(options, swipe_ids)
            and account_id == HOME_ACCOUNT)


def claim_access(task, session, owner_ok, thread_has_others, bridge_version, now, thread_automatic=False):
    """At claim: ("full", None) or ("sandbox", why). `why` is None for a request never meant to be full, else the
    sentence its turn shows. session: the user_sessions row named by task.full_session (None when gone); owner_ok:
    the request's writer is still the flagged, active owner; thread_has_others: someone else wrote in the conversation;
    thread_automatic: an automatic run (schedule, alert, advice, brief) is part of it."""
    if not task.get("full_session") or task.get("kind") not in FULL_KINDS or automatic(task.get("options")):
        return "sandbox", None
    if task.get("account_id") != HOME_ACCOUNT:
        return "sandbox", ELSEWHERE
    if not session:
        return "sandbox", SIGNED_OUT
    if session.get("user_id") != task.get("created_by") or not is_on(session.get("full_until"), now):
        return "sandbox", LOCKED
    if not owner_ok:
        return "sandbox", NOT_OWNER_NOW
    if thread_has_others:
        return "sandbox", OTHERS
    if thread_automatic:
        return "sandbox", AUTOMATIC
    if tuple(bridge_version) < BRIDGE:
        return "sandbox", OLD_HELPER
    return "full", None


_BROWSERS = (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("FxiOS/", "Firefox"), ("CriOS/", "Chrome"),
             ("Chrome/", "Chrome"), ("Safari/", "Safari"))
_SYSTEMS = (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Macintosh", "Mac"), ("Mac OS X", "Mac"),
            ("Windows", "Windows"), ("CrOS", "a Chromebook"), ("Linux", "Linux"))


def device_words(user_agent):
    """'Chrome on Mac' for the notice that full access was turned on (best effort, plain words)."""
    ua = user_agent or ""
    browser = next((name for key, name in _BROWSERS if key in ua), None)
    system = next((name for key, name in _SYSTEMS if re.search(re.escape(key), ua)), None)
    if not browser and not system:
        return "an unknown browser"
    return f"{browser or 'a browser'} on {system}" if system else browser
