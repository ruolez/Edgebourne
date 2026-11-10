import logging
import os

import psycopg2
import psycopg2.errors
import psycopg2.extensions
import psycopg2.extras
import psycopg2.sql
from flask import g, has_app_context
from werkzeug.security import generate_password_hash

import account_ctx
import config

log = logging.getLogger(__name__)
APP_ROLE = "ebads_app"  # no superuser rights: row-level security applies to it
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")

psycopg2.extras.register_default_jsonb(loads=__import__("json").loads, globally=True)


def connect():
    """A raw connection with the owner's rights (migrations, advisory locks, all-accounts jobs)."""
    return psycopg2.connect(**config.POSTGRES)


class AppConnection(psycopg2.extensions.connection):
    """Remembers which account the connection is pointed at."""
    account_id = None


def connect_app():
    """A connection limited to one account at a time by row-level security."""
    conn = psycopg2.connect(**config.POSTGRES, connection_factory=AppConnection)
    with conn.cursor() as cur:
        cur.execute(f"SET ROLE {APP_ROLE}")
    conn.commit()
    conn.account_id = None
    return conn


def _scope(conn):
    """Point the connection at the current account before a query (cheap when unchanged)."""
    acct = account_ctx.current()
    if getattr(conn, "account_id", "raw") != acct:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.account_id', %s, false)", (str(acct),))
        conn.account_id = acct


def get_db():
    """Per-request connection inside Flask; a fresh one per call in workers."""
    if has_app_context():
        if "db" not in g:
            g.db = connect_app()
        return g.db
    return None


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def _run(sql, params, fetch):
    if account_ctx.seeing_all():
        conn, owned = connect(), True
    else:
        conn = get_db()
        owned = conn is None
        if owned:
            conn = connect_app()
        _scope(conn)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() if (fetch and cur.description is not None) else None
        conn.commit()
        return rows
    except Exception:
        conn.rollback()
        raise
    finally:
        if owned:
            conn.close()


def query(sql, params=None, one=False):
    rows = _run(sql, params, True) or []
    if one:
        return rows[0] if rows else None
    return rows


def execute(sql, params=None, returning=False):
    rows = _run(sql, params, returning)
    if returning:
        return rows[0] if rows else None
    return None


def ensure_database():
    if not config.POSTGRES_BOOTSTRAP_DB:
        return
    name = config.POSTGRES["dbname"]
    conn = psycopg2.connect(**{**config.POSTGRES, "dbname": config.POSTGRES_BOOTSTRAP_DB})
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
            if cur.fetchone():
                return
            try:
                cur.execute(psycopg2.sql.SQL("CREATE DATABASE {}").format(psycopg2.sql.Identifier(name)))
                log.info("created database %s", name)
            except psycopg2.errors.DuplicateDatabase:
                pass
    finally:
        conn.close()


def run_migrations():
    ensure_database()
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(424242)")
            cur.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                       filename TEXT PRIMARY KEY,
                       applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"""
            )
            cur.execute("SELECT filename FROM schema_migrations")
            applied = {r[0] for r in cur.fetchall()}
            for fname in sorted(os.listdir(MIGRATIONS_DIR)):
                if not fname.endswith(".sql") or fname in applied:
                    continue
                with open(os.path.join(MIGRATIONS_DIR, fname)) as f:
                    cur.execute(f.read())
                cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (fname,))
            cur.execute("SELECT COUNT(*) FROM users")
            if cur.fetchone()[0] == 0:
                if config.ADMIN_INITIAL_PASSWORD:
                    cur.execute(
                        """INSERT INTO users (email, name, password_hash, role, must_change_password)
                           VALUES (%s, %s, %s, 'admin', TRUE)""",
                        (config.ADMIN_EMAIL.lower(), config.ADMIN_NAME,
                         generate_password_hash(config.ADMIN_INITIAL_PASSWORD)),
                    )
                else:
                    log.warning("no users yet and ADMIN_INITIAL_PASSWORD is empty: first admin not created")
            cur.execute("SELECT pg_advisory_unlock(424242)")
        conn.commit()
    finally:
        conn.close()
