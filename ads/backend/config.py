import hashlib
import os


def _secret_key():
    own = os.environ.get("SECRET_KEY")
    if own:
        return own
    # Inside the EdgeBourne stack the key is derived from the site's own SECRET_KEY,
    # so the installer has nothing extra to generate. Changing either makes the
    # secrets stored in Settings unreadable (they must be re-entered).
    base = os.environ.get("BASE_SECRET_KEY")
    if base:
        return hashlib.sha256(b"edgebourne-ads:" + base.encode()).hexdigest()
    return "dev-only-change-me"


SECRET_KEY = _secret_key()

POSTGRES = {
    "host": os.environ.get("POSTGRES_HOST", "postgres"),
    "port": int(os.environ.get("POSTGRES_PORT", "5432")),
    "dbname": os.environ.get("POSTGRES_DB", "ebads"),
    "user": os.environ.get("POSTGRES_USER", "ebads"),
    "password": os.environ.get("POSTGRES_PASSWORD", ""),
}
# Set when the database lives on a Postgres server shared with another app: the
# dashboard connects here first and creates its own database if it is missing.
POSTGRES_BOOTSTRAP_DB = os.environ.get("POSTGRES_BOOTSTRAP_DB", "")

# The website's database and key: when the console's own Email settings are empty,
# lead alerts go out through the website's mailbox (site_mail.py).
SITE_POSTGRES_DB = os.environ.get("SITE_POSTGRES_DB", "")
SITE_SECRET_KEY = os.environ.get("BASE_SECRET_KEY", "")

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "eugene@edgebourne.com")
ADMIN_NAME = os.environ.get("ADMIN_NAME", "Eugene")
# Only used to create the first admin (who must change it on first sign-in).
ADMIN_INITIAL_PASSWORD = os.environ.get("ADMIN_INITIAL_PASSWORD", "")

# Public address of the dashboard, used in lead emails and the webhook hint.
_domain = os.environ.get("DOMAIN", "")
APP_BASE_URL = (os.environ.get("APP_BASE_URL")
                or (f"https://ads.{_domain}" if _domain else "http://localhost:5563")).rstrip("/")

GRAPH_VERSION_DEFAULT = os.environ.get("META_GRAPH_VERSION", "v24.0")
# Local development only: point the Graph client at ads/dev/fake_meta.py.
META_GRAPH_BASE = os.environ.get("META_GRAPH_BASE", "").rstrip("/")
TELEGRAM_API_BASE = os.environ.get("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/")

# Defaults for the Edge Bourne account; editable in Settings.
META_DEFAULTS = {
    "meta_page_id": os.environ.get("META_PAGE_ID", "1404203629446490"),
    "meta_ad_account_id": os.environ.get("META_AD_ACCOUNT_ID", "1025971549903293"),
    "meta_dataset_id": os.environ.get("META_DATASET_ID", "1821497329119793"),
}

# Background workers (webhook processing, hourly sync) can be switched off in tests.
WORKERS_ENABLED = os.environ.get("WORKERS_ENABLED", "1") == "1"
