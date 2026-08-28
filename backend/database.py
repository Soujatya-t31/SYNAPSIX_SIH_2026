import sqlite3
import os
import uuid

DB_PATH = os.path.join(os.path.dirname(__file__), "infra.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")
SCHEMA_PG_PATH = os.path.join(os.path.dirname(__file__), "schema_postgres.sql")

# ---------------------------------------------------------------------------
# Database backend selection.
#
# Local dev (no DATABASE_URL set): SQLite file on disk, zero setup, exactly the
# behavior this project always had.
#
# Deployed (DATABASE_URL set, e.g. postgres://user:pass@host/db): a real shared
# Postgres database, so every device/teammate hitting the deployed backend sees
# the same reports instead of each machine having its own local infra.db file.
#
# Everywhere else in this codebase (main.py, seed_data.py, priority_engine.py,
# duplicate_detection.py) just does conn.execute(sql, params), .fetchone(),
# .fetchall(), row["col"], .commit(), .close() — completely unaware of which
# backend is active. PGConnection below wraps psycopg2 to present that exact
# same interface, so none of those call sites needed to change.
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.startswith("postgres://") or DATABASE_URL.startswith("postgresql://")

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras


def _qmark_to_pg(sql: str) -> str:
    # Every query in this codebase uses "?" placeholders (sqlite3 style).
    # psycopg2 expects "%s". No query anywhere embeds a literal "?" in the SQL
    # text itself (all "?" are bind placeholders), so a blind replace is safe —
    # verified by grepping the whole codebase before relying on this.
    return sql.replace("?", "%s")


class _PGResult:
    """Wraps a psycopg2 cursor so callers can keep using the sqlite3-style
    .fetchone() / .fetchall() they already use everywhere."""
    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class PGConnection:
    """sqlite3.Connection-compatible wrapper around a psycopg2 connection.
    Supports exactly the subset of the API this codebase actually uses:
    execute, executemany, executescript, commit, close — with dict-style
    row["col"] access via RealDictCursor (matching sqlite3.Row's behavior,
    including .keys(), which priority_engine.py relies on)."""

    def __init__(self, dsn):
        self._conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)

    def execute(self, sql, params=()):
        cur = self._conn.cursor()
        cur.execute(_qmark_to_pg(sql), tuple(params))
        return _PGResult(cur)

    def executemany(self, sql, seq_of_params):
        cur = self._conn.cursor()
        cur.executemany(_qmark_to_pg(sql), [tuple(p) for p in seq_of_params])
        return _PGResult(cur)

    def executescript(self, sql):
        # psycopg2 supports multi-statement execute() for parameter-free DDL,
        # which is all schema_postgres.sql contains.
        cur = self._conn.cursor()
        cur.execute(sql)
        return _PGResult(cur)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def rollback(self):
        self._conn.rollback()


# Seeded government-side accounts — one admin (sees every department across the
# whole city) plus one officer per department. Password is the same for all of
# them in this prototype so it's easy to demo; a real deployment would provision
# these individually and force a reset on first login.
DEFAULT_OFFICER_PASSWORD = "govdemo123"
DEFAULT_OFFICERS = [
    ("City Administrator", "admin@jandrishti.gov", "All Departments", "admin"),
    ("Road & Infra Officer", "roads@jandrishti.gov", "Road & Infrastructure", "officer"),
    ("Electrical Dept Officer", "electrical@jandrishti.gov", "Electrical Department", "officer"),
    ("Waste Mgmt Officer", "waste@jandrishti.gov", "Waste Management", "officer"),
    ("Water Supply Officer", "water@jandrishti.gov", "Water Supply Department", "officer"),
    ("Public Health Officer", "health@jandrishti.gov", "Public Health Department", "officer"),
    ("General Maintenance Officer", "maintenance@jandrishti.gov", "General Maintenance", "officer"),
]


def get_conn():
    if USE_POSTGRES:
        return PGConnection(DATABASE_URL)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset: bool = False):
    if USE_POSTGRES:
        # Postgres is the shared, persistent store — never auto-wipe it just
        # because a script passed reset=True (that flag only makes sense for
        # the throwaway local SQLite file). Explicit reset must go through
        # reset_postgres_schema() below, on purpose, so nobody nukes the shared
        # deployed database by running seed_data.py out of habit.
        conn = get_conn()
        with open(SCHEMA_PG_PATH) as f:
            conn.executescript(f.read())
        conn.commit()
        _seed_landmarks_if_empty(conn)
        conn.close()
        return

    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = get_conn()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    _seed_landmarks_if_empty(conn)
    conn.close()


def _seed_landmarks_if_empty(conn):
    # Seed a small set of demo landmarks (Kolkata area, matches the spec's example).
    # A real deployment would pull these from OpenStreetMap/PostGIS instead of hardcoding.
    count = conn.execute("SELECT COUNT(*) c FROM landmarks").fetchone()["c"]
    if count == 0:
        landmarks = [
            ("St. Xavier's School", "school", 22.5535, 88.3512, 1.0),
            ("Loreto Convent", "school", 22.5470, 88.3480, 1.0),
            ("SSKM Hospital", "hospital", 22.5390, 88.3430, 1.3),
            ("AMRI Hospital", "hospital", 22.5180, 88.3930, 1.3),
            ("Park Street Bus Stop", "bus_stop", 22.5520, 88.3520, 0.6),
            ("Esplanade Bus Terminus", "bus_stop", 22.5650, 88.3510, 0.7),
            ("Gariahat Market", "market", 22.5190, 88.3670, 0.8),
            ("New Market", "market", 22.5610, 88.3510, 0.8),
            ("Park Street - AJC Bose Rd Intersection", "intersection", 22.5490, 88.3550, 0.9),
            ("Sealdah Station", "intersection", 22.5680, 88.3710, 1.1),
            ("Salt Lake Sector V", "intersection", 22.5760, 88.4310, 0.9),
            ("Howrah Bridge Approach", "intersection", 22.5850, 88.3460, 1.0),
        ]
        conn.executemany(
            "INSERT INTO landmarks (name, kind, latitude, longitude, weight) VALUES (?,?,?,?,?)",
            landmarks,
        )
        conn.commit()


def reset_postgres_schema():
    """Explicit, deliberate wipe-and-recreate for the shared Postgres database.
    Not called automatically anywhere — run it yourself (see README) the one
    time you want to blow away the deployed database and start clean."""
    if not USE_POSTGRES:
        raise RuntimeError("DATABASE_URL isn't set to a postgres:// URL — nothing to reset.")
    conn = get_conn()
    conn.execute(
        "DROP TABLE IF EXISTS notifications, officers, upvotes_log, complaints, users, landmarks CASCADE"
    )
    conn.commit()
    conn.close()
    init_db(reset=False)


def seed_default_officers(conn):
    """Idempotent: only inserts officer accounts that don't already exist yet, so
    it's safe to call on every startup and won't stomp a password an officer has
    since changed."""
    import auth_utils
    from datetime import datetime

    for name, email, department, role in DEFAULT_OFFICERS:
        existing = conn.execute("SELECT id FROM officers WHERE email = ?", (email,)).fetchone()
        if existing:
            continue
        officer_id = "GOV-" + uuid.uuid4().hex[:10].upper()
        password_hash, salt = auth_utils.hash_password(DEFAULT_OFFICER_PASSWORD)
        conn.execute(
            "INSERT INTO officers (id, name, email, password_hash, salt, department, role, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (officer_id, name, email, password_hash, salt, department, role, datetime.utcnow().isoformat() + "Z"),
        )
    conn.commit()


def ensure_schema_upgrades(conn):
    """
    Additive, non-destructive migrations — safe to run on every startup, including
    against an existing infra.db that predates the users table / user_id column.
    """
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reset_token TEXT,
            reset_token_expires TEXT
        )"""
    )
    if USE_POSTGRES:
        cols = [r["name"] for r in conn.execute(
            "SELECT column_name AS name FROM information_schema.columns WHERE table_name = 'complaints'"
        ).fetchall()]
    else:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(complaints)").fetchall()]
    if "user_id" not in cols:
        conn.execute("ALTER TABLE complaints ADD COLUMN user_id TEXT")
    if "upvotes" not in cols:
        conn.execute("ALTER TABLE complaints ADD COLUMN upvotes INTEGER DEFAULT 0")

    conn.execute(
        """CREATE TABLE IF NOT EXISTS upvotes_log (
            complaint_id TEXT NOT NULL,
            voter_key TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (complaint_id, voter_key)
        )"""
    )

    conn.execute(
        """CREATE TABLE IF NOT EXISTS officers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            department TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'officer',
            created_at TEXT NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            reporter_id TEXT NOT NULL,
            complaint_id TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            is_read INTEGER DEFAULT 0
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_reporter ON notifications(reporter_id)")
    seed_default_officers(conn)

    # One-time cleanup: complaints submitted before the cross-platform path fix may
    # have the full Windows path (e.g. "C:\...\uploads\INF-xxx.jpg") stored instead
    # of just the filename, which breaks their image display. Normalize any leftover
    # rows so old test data heals itself instead of staying permanently broken.
    import re
    rows = conn.execute("SELECT id, image_path FROM complaints WHERE image_path IS NOT NULL").fetchall()
    for row in rows:
        original = row["image_path"]
        filename = re.split(r"[\\/]", original)[-1]
        if filename and filename != original:
            conn.execute("UPDATE complaints SET image_path = ? WHERE id = ?", (filename, row["id"]))

    conn.commit()


if __name__ == "__main__":
    init_db(reset=True)
    print(f"Initialized DB at {DB_PATH}")
