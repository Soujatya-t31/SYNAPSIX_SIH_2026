-- Government Infrastructure Priority Engine — schema
-- SQLite for hackathon speed; every table maps cleanly onto the PostgreSQL/PostGIS
-- schema described in the spec if this needs to graduate later.

CREATE TABLE IF NOT EXISTS landmarks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,          -- school | hospital | bus_stop | market | intersection
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0   -- how much this landmark matters for criticality
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    created_at TEXT NOT NULL,
    reset_token TEXT,
    reset_token_expires TEXT
);

CREATE TABLE IF NOT EXISTS upvotes_log (
    complaint_id TEXT NOT NULL,
    voter_key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (complaint_id, voter_key)
);

CREATE TABLE IF NOT EXISTS complaints (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    user_id TEXT,               -- optional link to the logged-in citizen who filed this

    -- citizen input
    category TEXT NOT NULL,
    description TEXT,
    citizen_severity TEXT,        -- optional self-report, weak signal only
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    address TEXT,
    image_path TEXT,
    reporter_id TEXT,

    -- CV output
    detected_class TEXT,
    cv_confidence REAL,
    defect_count INTEGER,
    damage_area_pct REAL,
    cv_valid INTEGER DEFAULT 1,     -- did the image plausibly match the claimed category?
    cv_notes TEXT,

    -- context features (0-100 unless noted)
    severity_score REAL,
    public_impact_score REAL,
    location_criticality_score REAL,
    historical_recurrence_score REAL,
    safety_risk_score REAL,
    future_risk_score REAL,

    -- output
    priority_score REAL,
    priority_level TEXT,           -- Critical | High | Medium | Low
    department TEXT,
    sla_hours INTEGER,

    -- duplicate / incident clustering
    incident_id TEXT,              -- id of the canonical incident this complaint belongs to
    is_primary INTEGER DEFAULT 1,  -- 1 if this complaint is the incident's representative record
    affected_citizens INTEGER DEFAULT 1,
    upvotes INTEGER DEFAULT 0,     -- citizens confirming "yes, this is really happening"

    -- lifecycle
    status TEXT DEFAULT 'RECEIVED', -- RECEIVED | ASSIGNED | IN_PROGRESS | RESOLVED | REOPENED
    assigned_worker TEXT,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_complaints_incident ON complaints(incident_id);
CREATE INDEX IF NOT EXISTS idx_complaints_priority ON complaints(priority_score);
CREATE INDEX IF NOT EXISTS idx_complaints_category ON complaints(category);
CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);

-- Government-side accounts. Separate table from `users` (citizens) on purpose —
-- different login page, different auth token role, and never mixed into the
-- citizen signup/login flow.
CREATE TABLE IF NOT EXISTS officers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    department TEXT NOT NULL,     -- one of priority_engine.DEPARTMENT_MAP's values, or 'All Departments' for admins
    role TEXT NOT NULL DEFAULT 'officer',  -- 'admin' (sees every department) | 'officer' (scoped to one department)
    created_at TEXT NOT NULL
);

-- In-app notifications sent to citizens (e.g. "your complaint was resolved").
-- Tied to reporter_id (email, matches complaints.reporter_id) rather than user_id
-- so anonymous-but-later-registered flows still work the same way the rest of
-- the app already keys reports off reporter_id/email.
CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    reporter_id TEXT NOT NULL,
    complaint_id TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_read INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_notifications_reporter ON notifications(reporter_id);
