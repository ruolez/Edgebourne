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


from contextlib import contextmanager


@contextmanager
def try_lock(name):
    """A Postgres advisory lock held for the block: yields False when someone else holds it (a second
    click on the same thing while Meta is still answering the first)."""
    import zlib
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(%s)", (zlib.crc32(name.encode()) + 900000000,))
            yield cur.fetchone()[0]
    finally:
        conn.close()


_reused = __import__("contextvars").ContextVar("db_reused", default=None)


@contextmanager
def reusing():
    """Outside a request (the worker), share one app connection for the block instead of opening one
    per query: a sync writes hundreds of rows, on a Postgres with 50 connections shared with the website."""
    if _reused.get() is not None:
        yield
        return
    conn = connect_app()
    token = _reused.set(conn)
    try:
        yield
    finally:
        _reused.reset(token)
        conn.close()


def get_db():
    """Per-request connection inside Flask; the shared one inside reusing(); else None (one per call)."""
    if has_app_context():
        if "db" not in g:
            g.db = connect_app()
        return g.db
    return _reused.get()


def close_db(_exc=None):
    for name in ("db", "db_owner"):
        conn = g.pop(name, None)
        if conn is not None:
            conn.close()


def _owner_conn():
    """For all_accounts() work: one owner connection per request (the Mac's long poll looks for work
    every second, audit A3-128); outside a request a fresh one per call. Returns (conn, close_after)."""
    if has_app_context():
        if "db_owner" not in g:
            g.db_owner = connect()
        return g.db_owner, False
    return connect(), True


def _pick():
    """(connection, close_after) for one statement or transaction. Refused while a transaction() block is open on
    the same connection: committing there would commit half the block and release its locks."""
    if account_ctx.seeing_all():
        conn, owned = _owner_conn()
    else:
        conn = get_db()
        owned = conn is None
        if owned:
            conn = connect_app()
    if conn in _open_tx.get():
        raise TransactionOpen("a db.transaction() block is open on this connection")
    if not account_ctx.seeing_all():
        _scope(conn)
    return conn, owned


class TransactionOpen(RuntimeError):
    """A db helper was called on a connection that has a transaction() block open."""


_open_tx = __import__("contextvars").ContextVar("db_open_tx", default=frozenset())


def _run(sql, params, fetch):
    conn, owned = _pick()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() if (fetch and cur.description is not None) else None
        conn.commit()
        return rows
    except Exception:
        conn.rollback()
        if isinstance(conn, AppConnection):
            conn.account_id = None  # the rollback undid set_config: point it again next time
        raise
    finally:
        if owned:
            conn.close()


class NothingChanged(Exception):
    """A required step of run_in_transaction returned no rows; the whole transaction was rolled back."""

    def __init__(self, step):
        super().__init__(f"step {step} changed nothing")
        self.step = step


def run_in_transaction(steps):
    """Run several statements on one connection in one transaction (e.g. SELECT … FOR UPDATE, then an
    upsert). steps = [(sql, params)] or [(sql, params, True)] for a step that must return a row, or the
    whole transaction rolls back with NothingChanged(step index). Returns each step's rows (None when it
    returns nothing)."""
    conn, owned = _pick()
    try:
        out = []
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            for n, (sql, params, *required) in enumerate(steps):
                cur.execute(sql, params)
                out.append(cur.fetchall() if cur.description is not None else None)
                if required and required[0] and not out[-1]:
                    raise NothingChanged(n)
        conn.commit()
        return out
    except Exception:
        conn.rollback()
        if isinstance(conn, AppConnection):
            conn.account_id = None
        raise
    finally:
        if owned:
            conn.close()


@contextmanager
def transaction():
    """One transaction for a block that decides as it goes (take a lock, insert, look up, link): yields a cursor
    (rows as dicts) on the same connection the other helpers would use; commits at the end, rolls back on any
    error. Nothing else may touch the database inside the block: db.query/execute commit on their own, which would
    commit half of it and release its transaction locks, so they raise TransactionOpen here instead."""
    conn, owned = _pick()
    token = _open_tx.set(_open_tx.get() | {conn})
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        conn.commit()
    except BaseException:
        conn.rollback()
        if isinstance(conn, AppConnection):
            conn.account_id = None
        raise
    finally:
        _open_tx.reset(token)
        if owned:
            conn.close()


def query(sql, params=None, one=False):
    rows = _run(sql, params, True) or []
    if one:
        return rows[0] if rows else None
    return rows


def now():
    """The database's clock (rows are stamped with it, so comparisons stay on one clock)."""
    return query("SELECT now() AS t", one=True)["t"]


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


# Roles live outside the database, so pg_dump leaves this one out: a database restored on a new
# server would have every table but no ebads_app, and every request would fail. Recreated on boot.
APP_ROLE_SQL = f"""
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
        CREATE ROLE {APP_ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END $$;
DO $$ BEGIN
    EXECUTE format('GRANT {APP_ROLE} TO %I', current_user);
EXCEPTION WHEN insufficient_privilege OR invalid_grant_operation THEN
    RAISE NOTICE 'could not grant {APP_ROLE} to %', current_user;
END $$;
GRANT USAGE ON SCHEMA public TO {APP_ROLE};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE};
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE};
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {APP_ROLE};
"""


def settle_full_access(cur):
    """FU-D: the one person who may turn on full access is the console's owner named by ADMIN_EMAIL (Eugene), never
    just whoever has the lowest id (migration 044's first guess could be a bootstrap or developer login). When that
    email is an active admin of every account, the flag moves to him alone; otherwise it stays as it is. The holder
    is logged at every start, so the Update's log says who it is."""
    email = (config.ADMIN_EMAIL or "").strip().lower()
    cur.execute("""SELECT id FROM users WHERE lower(email) = %s AND role = 'admin' AND account_id IS NULL AND is_active""", (email,))
    named = cur.fetchone()
    if named:
        cur.execute("UPDATE users SET full_access_allowed = (id = %s) WHERE full_access_allowed OR id = %s", (named[0], named[0]))
    else:
        log.warning("full access: ADMIN_EMAIL %s isn't an active admin of every account; the flag stays where it is", email or "(empty)")
    cur.execute("SELECT id, email FROM users WHERE full_access_allowed ORDER BY id")
    holders = cur.fetchall()
    log.warning("full access may be turned on by: %s", ", ".join(f"#{i} {e}" for i, e in holders) or "nobody")


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
            cur.execute(APP_ROLE_SQL)
            cur.execute("SELECT COUNT(*) FROM users")
            if cur.fetchone()[0] == 0:
                if config.ADMIN_INITIAL_PASSWORD:
                    # The first owner of a new install is the one who may turn on full access (FU-D, migration 044).
                    cur.execute(
                        """INSERT INTO users (email, name, password_hash, role, must_change_password, full_access_allowed)
                           VALUES (%s, %s, %s, 'admin', TRUE, TRUE)""",
                        (config.ADMIN_EMAIL.lower(), config.ADMIN_NAME,
                         generate_password_hash(config.ADMIN_INITIAL_PASSWORD)),
                    )
                else:
                    log.warning("no users yet and ADMIN_INITIAL_PASSWORD is empty: first admin not created")
            settle_full_access(cur)
            cur.execute("SELECT pg_advisory_unlock(424242)")
        conn.commit()
    finally:
        conn.close()
