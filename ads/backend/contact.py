"""Phone and email keys (00-PLAN S12): one person's contact details reduced to what matches them, and the
placeholders people type into a form when they don't want to give theirs. Pure; the rules are data.

A placeholder never gets a key, so five leads with test@test.com stay five leads (each flagged), instead of
folding into one family that hides the next one."""
import re

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TEST_LOCALS = {"test", "testing", "tester", "asdf", "qwerty", "abc", "fake", "none", "noemail", "no", "na", "null", "x", "xx", "xxx"}
TEST_DOMAINS = {"example.com", "example.org", "example.net", "test.com", "test.test", "email.com", "domain.com", "none.com"}
TEST_TLDS = {"example", "test", "invalid", "localhost"}
THROWAWAY_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org", "guerrillamailblock.com", "grr.la",
    "sharklasers.com", "10minutemail.com", "10minutemail.net", "20minutemail.com", "yopmail.com", "yopmail.net",
    "trashmail.com", "trashmail.net", "trashmail.de", "maildrop.cc", "tempmail.com", "temp-mail.org", "temp-mail.io",
    "tempmail.net", "tempmailo.com", "getnada.com", "nada.email", "dispostable.com", "mailnesia.com", "mintemail.com",
    "throwawaymail.com", "fakeinbox.com", "spamgourmet.com", "mytemp.email", "mohmal.com", "emailondeck.com",
    "burnermail.io", "inboxkitten.com", "mailcatch.com", "spambox.us", "getairmail.com", "tempinbox.com",
    "discard.email", "moakt.com",
}


def _email(email):
    e = (email or "").strip().lower()
    return e if EMAIL.match(e) else None


def _parts(email):
    e = _email(email)
    if not e:
        return None, None
    local, _, domain = e.rpartition("@")
    return local, domain


def is_test_email(email):
    local, domain = _parts(email)
    if not domain:
        return False
    return local in TEST_LOCALS or domain in TEST_DOMAINS or domain.rsplit(".", 1)[-1] in TEST_TLDS


def is_throwaway_email(email):
    _, domain = _parts(email)
    return bool(domain) and domain in THROWAWAY_DOMAINS


def email_key(email):
    """Lowercased and trimmed; None when missing, malformed or a placeholder. Gmail dots and +tags are kept:
    folding them would merge different people."""
    e = _email(email)
    if not e or is_test_email(e) or is_throwaway_email(e):
        return None
    return e


def _digits(phone):
    return re.sub(r"\D", "", phone or "")


def _run(d, step):
    return len(d) > 1 and all((int(b) - int(a)) % 10 == step % 10 for a, b in zip(d, d[1:]))


def is_fake_phone(phone):
    """A number typed to get past the form: every digit the same, a run (1234567890), under 7 digits, a 555 or
    0/1 area code, or 555-0100..0199 (reserved for films)."""
    d = _digits(phone)
    if not (phone or "").strip():
        return False
    if len(d) < 7 or len(set(d)) == 1 or _run(d, 1) or _run(d, -1):
        return True
    nanp = d[1:] if len(d) == 11 and d[0] == "1" else d if len(d) == 10 else None
    if nanp and (nanp[:3] == "555" or nanp[0] in "01"):
        return True
    return d[-7:-4] == "555" and 100 <= int(d[-4:]) <= 199


def phone_key(phone):
    """Digits only: the last 10 when there are 10 or more, all of them for 8 or 9, None for fewer or a placeholder."""
    d = _digits(phone)
    if len(d) < 8 or is_fake_phone(phone):
        return None
    return d[-10:]
