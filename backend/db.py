import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from flask import g
from werkzeug.security import generate_password_hash

import config

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


def connect():
    return psycopg2.connect(**config.POSTGRES)


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    g.pop("_tx_depth", None)
    if db is not None:
        if not db.closed:
            # Anything still uncommitted at teardown is a bug (a request that died
            # mid-transaction); discard it rather than letting psycopg2 decide.
            db.rollback()
        db.close()


@contextmanager
def standalone():
    """A connection independent of flask.g, for processes with no app context
    (the scheduler). The caller owns commit/rollback."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def _autocommit():
    """Commit, unless we're inside an explicit transaction() block.

    Every helper below calls this instead of get_db().commit(). Outside a
    transaction() the behaviour is identical to statement-per-commit, so no
    existing caller changes.
    """
    if not g.get("_tx_depth", 0):
        get_db().commit()


@contextmanager
def transaction():
    """Run a block of db.query()/db.execute() calls as ONE atomic transaction.

        with db.transaction():
            inv = db.execute("INSERT INTO invoices ... RETURNING *", p, returning=True)
            db.execute_values("INSERT INTO invoice_lines ... VALUES %s", rows)

    Commits on clean exit, rolls back on any exception (which then propagates).
    Nested blocks are real nesting via SAVEPOINTs, so a helper that opens its own
    transaction() still composes correctly when called from a bigger one.

    Do NOT call db.rollback() inside a block -- raise instead.
    """
    conn = get_db()
    depth = g.get("_tx_depth", 0)

    if depth == 0:
        # A previous statement may have failed and left the connection in an
        # aborted transaction; start from a known-clean state. No-op when healthy.
        conn.rollback()
        g._tx_depth = 1
        try:
            yield conn
        except BaseException:  # worker timeouts / SystemExit must roll back too
            conn.rollback()
            raise
        else:
            conn.commit()
        finally:
            g._tx_depth = 0
        return

    name = "sp_%d" % depth  # int-derived, so not injectable
    with conn.cursor() as cur:
        cur.execute("SAVEPOINT " + name)
    g._tx_depth = depth + 1
    try:
        yield conn
    except BaseException:
        with conn.cursor() as cur:
            cur.execute("ROLLBACK TO SAVEPOINT " + name)
        raise
    else:
        with conn.cursor() as cur:
            cur.execute("RELEASE SAVEPOINT " + name)
    finally:
        g._tx_depth = depth


def rollback():
    """Discard a failed statement's work. The existing UniqueViolation handlers
    rely on this. Inside transaction() it is a bug: the block already rolls back
    on exception, and rolling back here would abandon half a unit of work while
    the block goes on to commit the rest."""
    if g.get("_tx_depth", 0):
        raise RuntimeError(
            "db.rollback() called inside db.transaction(); raise the exception "
            "instead and let the transaction block roll back."
        )
    if "db" in g:
        g.db.rollback()


def query(sql, params=None, one=False):
    with get_db().cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        if cur.description is None:
            rows = None
        else:
            rows = cur.fetchall()
    _autocommit()
    if rows is None:
        return None
    return (rows[0] if rows else None) if one else rows


def execute(sql, params=None, returning=False):
    with get_db().cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone() if returning else None
    _autocommit()
    return row


def execute_values(sql, rows, template=None):
    """Bulk insert (invoice lines, ledger pairs) in one round-trip.
    `sql` must contain a single %s placeholder standing in for the VALUES list."""
    if not rows:
        return
    with get_db().cursor() as cur:
        psycopg2.extras.execute_values(cur, sql, rows, template=template)
    _autocommit()


def get_setting(key, default=None):
    row = query("SELECT value FROM settings WHERE key = %s", (key,), one=True)
    return row["value"] if row and row["value"] not in (None, "") else default


def set_setting(key, value):
    execute(
        """INSERT INTO settings (key, value) VALUES (%s, %s)
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()""",
        (key, value),
    )


def run_migrations():
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS schema_migrations (
                       filename TEXT PRIMARY KEY,
                       applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                   )"""
            )
            cur.execute("SELECT filename FROM schema_migrations")
            applied = {r[0] for r in cur.fetchall()}
            for fname in sorted(os.listdir(MIGRATIONS_DIR)):
                if not fname.endswith(".sql") or fname in applied:
                    continue
                with open(os.path.join(MIGRATIONS_DIR, fname)) as f:
                    cur.execute(f.read())
                cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (fname,))
        conn.commit()
        _seed_admin(conn)
    finally:
        conn.close()


def _seed_admin(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM users")
        if cur.fetchone()[0] == 0:
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, 'admin')",
                ("admin", generate_password_hash(config.ADMIN_INITIAL_PASSWORD)),
            )
    conn.commit()
