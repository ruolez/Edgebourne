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
