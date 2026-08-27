import sqlite3
import os
import uuid

DB_PATH = os.path.join(os.path.dirname(__file__), "infra.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

# Seeded government-side accounts — one admin (sees every department across the
# whole city) plus one officer per department. Password is the same for all of
# them in this prototype so it's easy to demo; a real deployment would provision
# these individually and force a reset on first login.
DEFAULT_OFFICER_PASSWORD = "govdemo123"
DEFAULT_OFFICERS = [
    ("City Administrator", "admin@civicvoice.gov", "All Departments", "admin"),
    ("Road & Infra Officer", "roads@civicvoice.gov", "Road & Infrastructure", "officer"),
    ("Electrical Dept Officer", "electrical@civicvoice.gov", "Electrical Department", "officer"),
    ("Waste Mgmt Officer", "waste@civicvoice.gov", "Waste Management", "officer"),
    ("Water Supply Officer", "water@civicvoice.gov", "Water Supply Department", "officer"),
    ("Public Health Officer", "health@civicvoice.gov", "Public Health Department", "officer"),
    ("General Maintenance Officer", "maintenance@civicvoice.gov", "General Maintenance", "officer"),
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(reset: bool = False):
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = get_conn()
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()

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
    conn.close()


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
