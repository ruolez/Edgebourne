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

# Absolute public origin, e.g. https://edgebourne.com. Required for building
# customer-facing links (pay/estimate URLs, Stripe success_url) from code that
# has no request context -- the mailer thread and the scheduler process.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

# Stripe secrets live in the environment, never in the settings table: a leaked
# sk_live_ is a different tier of failure from SMTP creds, `settings` rows land
# in every pg_dump backup, and a hijacked admin session must not be able to swap
# the webhook secret for one the attacker controls.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_WEBHOOK_SECRET_PREVIOUS = os.environ.get("STRIPE_WEBHOOK_SECRET_PREVIOUS", "")
