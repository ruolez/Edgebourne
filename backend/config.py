import os

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
ADMIN_INITIAL_PASSWORD = os.environ.get("ADMIN_INITIAL_PASSWORD", "admin")

POSTGRES = {
    "host": os.environ.get("POSTGRES_HOST", "localhost"),
    "port": int(os.environ.get("POSTGRES_PORT", "5432")),
    "dbname": os.environ.get("POSTGRES_DB", "edgebourne"),
    "user": os.environ.get("POSTGRES_USER", "edgebourne"),
    "password": os.environ.get("POSTGRES_PASSWORD", ""),
}

UPLOADS_DIR = os.environ.get("UPLOADS_DIR", "/data/uploads")
MAX_CONTENT_LENGTH = 10 * 1024 * 1024

# Absolute public origin, e.g. https://edgebourne.com. Needed to build
# customer-facing links (pay/estimate URLs, Stripe success_url) from code with no
# request context -- the mailer thread and the scheduler process.
#
# These may all be left blank: the admin UI stores them in `settings`, encrypted
# at rest (secrets_store.py). Setting them here still WINS, so an operator who
# would rather manage keys outside the app can, and existing installs are
# unaffected. Read them through stripe_client / site_base_url(), never directly.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_WEBHOOK_SECRET_PREVIOUS = os.environ.get("STRIPE_WEBHOOK_SECRET_PREVIOUS", "")


def site_base_url(fallback=""):
    """Env first, then the `site_url` admin setting, then the caller's fallback
    (a request-derived origin, where one exists)."""
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    try:
        import secrets_store  # its _read works with or without an app context

        value = (secrets_store._read("site_url") or "").rstrip("/")
        if value:
            return value
    except Exception:
        pass
    return fallback.rstrip("/")
