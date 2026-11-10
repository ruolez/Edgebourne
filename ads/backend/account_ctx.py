"""Which ad account the code is working on (roadmap 7.1). Requests set it from the session; the
worker sets it while it handles each account. The database enforces it: every account-owned
table has row-level security on `account_id`, read from the connection setting `app.account_id`."""
import contextvars
from contextlib import contextmanager

DEFAULT = 1  # Edge Bourne's own account: everything that existed before agency mode
_current = contextvars.ContextVar("account_id", default=DEFAULT)
_all = contextvars.ContextVar("all_accounts", default=False)


def current():
    return _current.get()


def set_current(account_id):
    _current.set(int(account_id))


@contextmanager
def use(account_id):
    token = _current.set(int(account_id))
    try:
        yield
    finally:
        _current.reset(token)


def seeing_all():
    return _all.get()


@contextmanager
def all_accounts():
    """For the few jobs that must look across accounts (the Mac claiming the next task, routing a
    lead webhook to its Page's account, the shared notification queue). Use sparingly."""
    token = _all.set(True)
    try:
        yield
    finally:
        _all.reset(token)
