import os
import uuid
import shutil
from datetime import datetime, timedelta
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — env vars can still be set manually

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import database
import cv_module
import geo_utils
import priority_engine
import duplicate_detection
import auth_utils
import email_utils

BASE_DIR = os.path.dirname(__file__)
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
# Frontend now lives in its own top-level folder, as a sibling of backend/,
# so the API layer and the web UI are cleanly separated (the API doesn't need
# the frontend to run — e.g. in tests or if the frontend is later deployed
# separately/statically — and the frontend only ever talks to /api/*).
FRONTEND_DIR = os.path.normpath(os.path.join(BASE_DIR, "..", "frontend"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Infrastructure Priority Engine")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def now_iso() -> str:
    # Always store UTC with an explicit 'Z' suffix. Without it, browsers parse the
    # timestamp as *local* time instead of UTC, which silently skews every "time
    # ago" / "reported X hours ago" display on the frontend.
    return datetime.utcnow().isoformat() + "Z"


@app.on_event("startup")
def startup():
    if not os.path.exists(database.DB_PATH):
        database.init_db(reset=True)
    conn = database.get_conn()
    try:
        database.ensure_schema_upgrades(conn)
    finally:
        conn.close()


def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Best-effort auth: returns the user payload if a valid Bearer token was sent,
    otherwise None. Endpoints that use this treat login as optional (e.g. filing a
    complaint anonymously is still allowed) unless they explicitly require it."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    return auth_utils.verify_token(token)


def require_user(authorization: Optional[str] = Header(None)) -> dict:
    payload = get_current_user(authorization)
    if not payload:
        raise HTTPException(401, "Please log in to continue.")
    return payload


def get_current_officer(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """Same shape as get_current_user, but only returns a payload for tokens
    issued by /api/officer/auth/login (role == 'officer' or 'admin'). A citizen's
    token is valid but has role 'citizen', so it's correctly rejected here —
    citizen and officer sessions never grant each other's access, even though
    both are plain bearer tokens signed with the same secret."""
    payload = get_current_user(authorization)
    if not payload or payload.get("role") not in ("officer", "admin"):
        return None
    return payload


def require_officer(authorization: Optional[str] = Header(None)) -> dict:
    payload = get_current_officer(authorization)
    if not payload:
        raise HTTPException(401, "Please sign in on the government portal to continue.")
    return payload


# ---------------------------------------------------------------------------
# Core pipeline: turns raw citizen input into a scored, classified complaint.
# ---------------------------------------------------------------------------
def run_pipeline(conn, category, description, citizen_severity, lat, lon, image_path):
    landmarks = [dict(r) for r in conn.execute("SELECT * FROM landmarks").fetchall()]
    loc_score, nearby = geo_utils.location_criticality(lat, lon, landmarks)

    cv_result = (
        cv_module.analyze_image(image_path, category)
        if image_path
        else {"detected_class": None, "confidence": 0.0, "defect_count": 0,
              "damage_area_pct": 0.0, "valid": True, "notes": "No image provided."}
    )

    incident_id, dup_count, primary_id = duplicate_detection.find_incident_cluster(
        conn, category, lat, lon
    )
    is_new_incident = incident_id is None
    affected_citizens = max(1, dup_count + 1)

    # historical recurrence: how many past (any-status) complaints exist near this spot
    past = conn.execute(
        """SELECT category FROM complaints
           WHERE ABS(latitude - ?) < 0.003 AND ABS(longitude - ?) < 0.003""",
        (lat, lon),
    ).fetchall()
    past_incident_count = len(past)
    same_category_count = sum(1 for p in past if p["category"] == category)

    severity = priority_engine.compute_severity(cv_result, citizen_severity)
    public_impact = priority_engine.compute_public_impact(dup_count, nearby, category)
    safety_risk = priority_engine.compute_safety_risk(category, severity, loc_score)
    hist_recur = priority_engine.compute_historical_recurrence(past_incident_count, same_category_count)
    future_risk = priority_engine.compute_future_risk(hist_recur, severity)

    scores = {
        "severity_score": severity,
        "public_impact_score": public_impact,
        "safety_risk_score": safety_risk,
        "location_criticality_score": loc_score,
        "historical_recurrence_score": hist_recur,
        "future_risk_score": future_risk,
    }
    result = priority_engine.compute_priority(scores)
    department = priority_engine.route_department(category)

    return {
        **scores,
        **result,
        "department": department,
        "cv": cv_result,
        "nearby_landmarks": nearby,
        "incident_id": incident_id,
        "is_new_incident": is_new_incident,
        "affected_citizens": affected_citizens,
        "primary_id": primary_id,
    }


@app.post("/api/complaints")
async def submit_complaint(
    category: str = Form(...),
    description: str = Form(""),
    citizen_severity: Optional[str] = Form(None),
    latitude: float = Form(...),
    longitude: float = Form(...),
    reporter_id: Optional[str] = Form("anonymous"),
    image: Optional[UploadFile] = File(None),
    authorization: Optional[str] = Header(None),
):
    current_user = get_current_user(authorization)
    user_id = current_user["uid"] if current_user else None
    if current_user and (not reporter_id or reporter_id == "anonymous"):
        reporter_id = current_user["email"]

    conn = database.get_conn()
    try:
        complaint_id = "INF-" + datetime.utcnow().strftime("%Y%m") + "-" + uuid.uuid4().hex[:6].upper()

        image_path = None
        if image is not None and image.filename:
            ext = os.path.splitext(image.filename)[1] or ".jpg"
            image_filename = complaint_id + ext
            image_path = os.path.join(UPLOAD_DIR, image_filename)
            with open(image_path, "wb") as f:
                shutil.copyfileobj(image.file, f)
        else:
            image_filename = None

        address = geo_utils.reverse_geocode(latitude, longitude)
        p = run_pipeline(conn, category, description, citizen_severity, latitude, longitude, image_path)

        incident_id = p["incident_id"] or complaint_id
        is_primary = 1 if p["is_new_incident"] else 0

        conn.execute(
            """INSERT INTO complaints (
                id, created_at, user_id, category, description, citizen_severity, latitude, longitude,
                address, image_path, reporter_id,
                detected_class, cv_confidence, defect_count, damage_area_pct, cv_valid, cv_notes,
                severity_score, public_impact_score, location_criticality_score,
                historical_recurrence_score, safety_risk_score, future_risk_score,
                priority_score, priority_level, department, sla_hours,
                incident_id, is_primary, affected_citizens, status
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                complaint_id, now_iso(), user_id, category, description, citizen_severity,
                latitude, longitude, address, image_filename, reporter_id,
                p["cv"]["detected_class"], p["cv"]["confidence"], p["cv"]["defect_count"],
                p["cv"]["damage_area_pct"], 1 if p["cv"]["valid"] else 0, p["cv"]["notes"],
                p["severity_score"], p["public_impact_score"], p["location_criticality_score"],
                p["historical_recurrence_score"], p["safety_risk_score"], p["future_risk_score"],
                p["priority_score"], p["priority_level"], p["department"], p["sla_hours"],
                incident_id, is_primary, p["affected_citizens"], "RECEIVED",
            ),
        )

        # a new duplicate can legitimately raise the incident's public impact / priority
        if not p["is_new_incident"] and p["primary_id"]:
            priority_engine.recompute_primary_on_new_duplicate(
                conn, p["primary_id"], p["affected_citizens"] - 1, p["nearby_landmarks"], category
            )
        conn.commit()

        row = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
        return {"complaint": dict(row), "nearby_landmarks": p["nearby_landmarks"],
                "joined_existing_incident": not p["is_new_incident"]}
    finally:
        conn.close()


def _attach_reporter_names(conn, rows: list) -> list:
    """Best-effort: if a complaint's reporter_id matches a registered citizen's
    email, attach their display name as reporter_name so the government
    dashboard can show "registered by <name>" instead of just an email/
    "anonymous". Anonymous or unregistered reporters simply get no name."""
    emails = {r["reporter_id"] for r in rows if r.get("reporter_id") and r["reporter_id"] != "anonymous"}
    if not emails:
        for r in rows:
            r["reporter_name"] = None
        return rows
    placeholders = ",".join("?" for _ in emails)
    name_rows = conn.execute(
        f"SELECT email, name FROM users WHERE email IN ({placeholders})", list(emails)
    ).fetchall()
    name_by_email = {n["email"]: n["name"] for n in name_rows}
    for r in rows:
        r["reporter_name"] = name_by_email.get(r.get("reporter_id"))
    return rows


@app.get("/api/complaints")
def list_complaints(
    status: Optional[str] = None,
    category: Optional[str] = None,
    priority_level: Optional[str] = None,
    reporter_id: Optional[str] = None,
    sort: str = "priority_desc",
    only_primary: bool = True,
):
    conn = database.get_conn()
    try:
        q = "SELECT * FROM complaints WHERE 1=1"
        args = []
        if status:
            q += " AND status = ?"
            args.append(status)
        if category:
            q += " AND category = ?"
            args.append(category)
        if priority_level:
            q += " AND priority_level = ?"
            args.append(priority_level)
        if reporter_id:
            q += " AND reporter_id = ?"
            args.append(reporter_id)
        if only_primary:
            q += " AND is_primary = 1"
        q += {
            "priority_desc": " ORDER BY priority_score DESC",
            "recent": " ORDER BY created_at DESC",
        }.get(sort, " ORDER BY priority_score DESC")
        rows = [dict(r) for r in conn.execute(q, args).fetchall()]
        return _attach_reporter_names(conn, rows)
    finally:
        conn.close()


@app.get("/api/complaints/{complaint_id}")
def get_complaint(complaint_id: str):
    conn = database.get_conn()
    try:
        row = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Complaint not found")
        d = dict(row)
        _attach_reporter_names(conn, [d])
        landmarks = [dict(r) for r in conn.execute("SELECT * FROM landmarks").fetchall()]
        _, nearby = geo_utils.location_criticality(d["latitude"], d["longitude"], landmarks)
        d["nearby_landmarks"] = nearby
        if d["incident_id"]:
            siblings = conn.execute(
                "SELECT id, created_at, reporter_id FROM complaints WHERE incident_id = ? AND id != ?",
                (d["incident_id"], complaint_id),
            ).fetchall()
            d["linked_reports"] = [dict(s) for s in siblings]
        return d
    finally:
        conn.close()


@app.post("/api/complaints/{complaint_id}/upvote")
def upvote_complaint(complaint_id: str, x_voter_key: str = Header(None)):
    """Citizens confirm an issue is real / still happening. One confirmation per
    device (tracked via a random client-generated key, not an account — matches
    anonymous complaint filing), enforced server-side in upvotes_log so repeated
    clicks — or a client that ignores its own disabled button — can't inflate the
    score. Feeds into public_impact_score through the same transparent weighted
    formula — see priority_engine.recompute_on_upvote."""
    voter_key = (x_voter_key or "").strip()
    if not voter_key:
        raise HTTPException(400, "Missing voter key.")
    conn = database.get_conn()
    try:
        row = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Complaint not found")

        already = conn.execute(
            "SELECT 1 FROM upvotes_log WHERE complaint_id = ? AND voter_key = ?",
            (complaint_id, voter_key),
        ).fetchone()
        if already:
            raise HTTPException(409, "This device has already confirmed this report.")

        conn.execute(
            "INSERT INTO upvotes_log (complaint_id, voter_key, created_at) VALUES (?, ?, ?)",
            (complaint_id, voter_key, now_iso()),
        )
        landmarks = [dict(r) for r in conn.execute("SELECT * FROM landmarks").fetchall()]
        _, nearby = geo_utils.location_criticality(row["latitude"], row["longitude"], landmarks)
        priority_engine.recompute_on_upvote(conn, complaint_id, nearby)
        conn.commit()
        updated = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
        return dict(updated)
    finally:
        conn.close()


STATUS_NOTIFICATION_TITLES = {
    "ASSIGNED": "Your report was assigned",
    "IN_PROGRESS": "Work has started on your report",
    "RESOLVED": "Your report was marked resolved",
    "REOPENED": "Your report was reopened",
}


@app.patch("/api/complaints/{complaint_id}/status")
def update_status(
    complaint_id: str,
    status: str = Form(...),
    assigned_worker: Optional[str] = Form(None),
    officer: dict = Depends(require_officer),
):
    """Government-only (see require_officer). Changing a complaint's status —
    especially marking it RESOLVED — also notifies the citizen who filed it:
    an in-app notification row is always written (so it shows up in their
    CivicVoice bell regardless of email setup), and a real email is attempted
    on top of that if SMTP is configured (see email_utils.send_status_email)."""
    valid_statuses = {"RECEIVED", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "REOPENED"}
    if status not in valid_statuses:
        raise HTTPException(400, f"status must be one of {valid_statuses}")
    conn = database.get_conn()
    try:
        existing = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "Complaint not found")

        resolved_at = now_iso() if status == "RESOLVED" else None
        conn.execute(
            "UPDATE complaints SET status = ?, assigned_worker = COALESCE(?, assigned_worker), resolved_at = ? WHERE id = ?",
            (status, assigned_worker, resolved_at, complaint_id),
        )

        notified = False
        reporter_id = existing["reporter_id"]
        if status != existing["status"] and reporter_id and reporter_id != "anonymous":
            title = STATUS_NOTIFICATION_TITLES.get(status, "Your report status was updated")
            status_label = status.replace("_", " ").title()
            message = f"{complaint_id} ({existing['category']}) is now {status_label}, updated by {officer['name']}."
            conn.execute(
                "INSERT INTO notifications (id, reporter_id, complaint_id, title, message, created_at, is_read) VALUES (?,?,?,?,?,?,0)",
                ("NOTIF-" + uuid.uuid4().hex[:10].upper(), reporter_id, complaint_id, title, message, now_iso()),
            )
            notified = True
            # Best-effort real email on top of the in-app notification — never
            # blocks or fails the status update itself if SMTP isn't configured.
            try:
                email_utils.send_status_email(reporter_id, complaint_id, existing["category"], status, officer["name"])
            except Exception as e:
                print(f"[main] status email failed (non-fatal): {e}")

        conn.commit()
        row = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
        d = dict(row)
        d["citizen_notified"] = notified
        return d
    finally:
        conn.close()


@app.get("/api/stats")
def get_stats():
    conn = database.get_conn()
    try:
        by_level = {r["priority_level"]: r["c"] for r in conn.execute(
            "SELECT priority_level, COUNT(*) c FROM complaints WHERE is_primary=1 GROUP BY priority_level"
        ).fetchall()}
        by_category = {r["category"]: r["c"] for r in conn.execute(
            "SELECT category, COUNT(*) c FROM complaints WHERE is_primary=1 GROUP BY category"
        ).fetchall()}
        by_department = {r["department"]: r["c"] for r in conn.execute(
            "SELECT department, COUNT(*) c FROM complaints WHERE is_primary=1 AND status != 'RESOLVED' GROUP BY department"
        ).fetchall()}
        by_status = {r["status"]: r["c"] for r in conn.execute(
            "SELECT status, COUNT(*) c FROM complaints WHERE is_primary=1 GROUP BY status"
        ).fetchall()}
        total = conn.execute("SELECT COUNT(*) c FROM complaints WHERE is_primary=1").fetchone()["c"]
        total_affected = conn.execute("SELECT SUM(affected_citizens) c FROM complaints WHERE is_primary=1").fetchone()["c"] or 0
        avg_priority = conn.execute("SELECT AVG(priority_score) a FROM complaints WHERE is_primary=1").fetchone()["a"] or 0
        return {
            "total_incidents": total,
            "total_affected_citizens": total_affected,
            "avg_priority_score": round(avg_priority, 1),
            "by_level": {lvl: by_level.get(lvl, 0) for lvl in ["Critical", "High", "Medium", "Low"]},
            "by_category": by_category,
            "by_department": by_department,
            "by_status": by_status,
        }
    finally:
        conn.close()


@app.get("/api/landmarks")
def get_landmarks():
    conn = database.get_conn()
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM landmarks").fetchall()]
    finally:
        conn.close()


@app.get("/api/categories")
def get_categories():
    return list(priority_engine.DEPARTMENT_MAP.keys())


# ---------------------------------------------------------------------------
# Auth — register / login / forgot-password / reset-password / me
# ---------------------------------------------------------------------------
def _user_public(row) -> dict:
    d = dict(row)
    return {"id": d["id"], "name": d["name"], "email": d["email"], "created_at": d["created_at"]}


@app.post("/api/auth/register")
def register(name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    if len(password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    if not name.strip() or "@" not in email:
        raise HTTPException(400, "Please provide a valid name and email.")
    conn = database.get_conn()
    try:
        existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise HTTPException(409, "An account with this email already exists.")
        user_id = "USR-" + uuid.uuid4().hex[:10].upper()
        password_hash, salt = auth_utils.hash_password(password)
        conn.execute(
            "INSERT INTO users (id, name, email, password_hash, salt, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, name.strip(), email, password_hash, salt, now_iso()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        token = auth_utils.create_token(user_id, email)
        return {"token": token, "user": _user_public(row)}
    finally:
        conn.close()


@app.post("/api/auth/login")
def login(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    conn = database.get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row or not auth_utils.verify_password(password, row["password_hash"], row["salt"]):
            raise HTTPException(401, "Incorrect email or password.")
        token = auth_utils.create_token(row["id"], row["email"])
        return {"token": token, "user": _user_public(row)}
    finally:
        conn.close()


@app.get("/api/auth/me")
def me(authorization: Optional[str] = Header(None)):
    payload = get_current_user(authorization)
    if not payload:
        raise HTTPException(401, "Not logged in.")
    conn = database.get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (payload["uid"],)).fetchone()
        if not row:
            raise HTTPException(401, "Session no longer valid.")
        return _user_public(row)
    finally:
        conn.close()


@app.post("/api/auth/forgot-password")
def forgot_password(email: str = Form(...)):
    email = email.strip().lower()
    conn = database.get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if not row:
            # Being explicit here (rather than a generic "if this email exists…"
            # non-committal message) is a deliberate usability call for this
            # prototype: it was previously confusing citizens into thinking the
            # reset flow was broken when they'd simply mistyped their email or
            # hadn't registered yet.
            return {"message": "No account found with that email. Double-check it, or register a new account.", "found": False}
        reset_token = auth_utils.new_reset_token()
        expires = (datetime.utcnow() + timedelta(minutes=30)).isoformat() + "Z"
        conn.execute(
            "UPDATE users SET reset_token = ?, reset_token_expires = ? WHERE id = ?",
            (reset_token, expires, row["id"]),
        )
        conn.commit()

        emailed = email_utils.send_reset_email(email, reset_token, row["name"])
        if emailed:
            # Real email sent — don't also leak the token in the API response.
            return {
                "message": f"Reset instructions sent to {email}. Check your inbox (and spam folder).",
                "found": True,
                "emailed": True,
            }
        # No email service configured (or sending failed) — fall back to the
        # demo-mode behavior of returning the token directly.
        return {
            "message": "Reset token generated (demo mode — email isn't configured, so here's the token directly).",
            "reset_token": reset_token,
            "expires_at": expires,
            "found": True,
            "emailed": False,
        }
    finally:
        conn.close()


@app.post("/api/auth/reset-password")
def reset_password(token: str = Form(...), new_password: str = Form(...)):
    if len(new_password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters.")
    conn = database.get_conn()
    try:
        row = conn.execute("SELECT * FROM users WHERE reset_token = ?", (token,)).fetchone()
        if not row:
            raise HTTPException(400, "Invalid or expired reset token.")
        if not row["reset_token_expires"] or row["reset_token_expires"].rstrip("Z") < datetime.utcnow().isoformat():
            raise HTTPException(400, "This reset token has expired. Please request a new one.")
        password_hash, salt = auth_utils.hash_password(new_password)
        conn.execute(
            "UPDATE users SET password_hash = ?, salt = ?, reset_token = NULL, reset_token_expires = NULL WHERE id = ?",
            (password_hash, salt, row["id"]),
        )
        conn.commit()
        return {"message": "Password updated successfully. You can now log in."}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Government-side auth — completely separate login from citizens (own table,
# own token role). No self-registration: accounts are provisioned ahead of
# time (see database.seed_default_officers) the way a real government portal
# would issue accounts to its own staff rather than letting anyone sign up.
# ---------------------------------------------------------------------------
def _officer_public(row) -> dict:
    d = dict(row)
    return {"id": d["id"], "name": d["name"], "email": d["email"], "department": d["department"], "role": d["role"]}


@app.post("/api/officer/auth/login")
def officer_login(email: str = Form(...), password: str = Form(...)):
    email = email.strip().lower()
    conn = database.get_conn()
    try:
        row = conn.execute("SELECT * FROM officers WHERE email = ?", (email,)).fetchone()
        if not row or not auth_utils.verify_password(password, row["password_hash"], row["salt"]):
            raise HTTPException(401, "Incorrect email or password.")
        token = auth_utils.create_token(
            row["id"], row["email"], role=row["role"], name=row["name"], department=row["department"]
        )
        return {"token": token, "officer": _officer_public(row)}
    finally:
        conn.close()


@app.get("/api/officer/auth/me")
def officer_me(officer: dict = Depends(require_officer)):
    conn = database.get_conn()
    try:
        row = conn.execute("SELECT * FROM officers WHERE id = ?", (officer["uid"],)).fetchone()
        if not row:
            raise HTTPException(401, "Session no longer valid.")
        return _officer_public(row)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Departments overview — for the government dashboard's "Departments" tab:
# every department, its open/in-progress/resolved counts, and the specific
# tasks (complaints) currently being worked in it.
# ---------------------------------------------------------------------------
@app.get("/api/departments")
def list_departments(officer: dict = Depends(require_officer)):
    conn = database.get_conn()
    try:
        departments = sorted(set(priority_engine.DEPARTMENT_MAP.values()))
        result = []
        for dept in departments:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM complaints WHERE department = ? AND is_primary = 1 ORDER BY priority_score DESC",
                (dept,),
            ).fetchall()]
            rows = _attach_reporter_names(conn, rows)
            by_status = {}
            for r in rows:
                by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            active_tasks = [r for r in rows if r["status"] in ("RECEIVED", "ASSIGNED", "IN_PROGRESS")]
            officers_here = [dict(o) for o in conn.execute(
                "SELECT id, name, email FROM officers WHERE department = ?", (dept,)
            ).fetchall()]
            result.append({
                "department": dept,
                "total": len(rows),
                "by_status": by_status,
                "officers": officers_here,
                "active_tasks": active_tasks[:25],
            })
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Citizen-facing notifications — populated when an officer changes a
# complaint's status (see /api/complaints/{id}/status PATCH above).
# ---------------------------------------------------------------------------
@app.get("/api/notifications")
def list_notifications(current_user: dict = Depends(require_user)):
    conn = database.get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE reporter_id = ? ORDER BY created_at DESC LIMIT 50",
            (current_user["email"],),
        ).fetchall()
        unread = conn.execute(
            "SELECT COUNT(*) c FROM notifications WHERE reporter_id = ? AND is_read = 0",
            (current_user["email"],),
        ).fetchone()["c"]
        return {"notifications": [dict(r) for r in rows], "unread_count": unread}
    finally:
        conn.close()


@app.patch("/api/notifications/read")
def mark_notifications_read(current_user: dict = Depends(require_user)):
    conn = database.get_conn()
    try:
        conn.execute("UPDATE notifications SET is_read = 1 WHERE reporter_id = ?", (current_user["email"],))
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@app.post("/api/admin/seed")
def seed(n: int = 150, reset: bool = True):
    import seed_data
    count = seed_data.run(n=n, reset=reset)
    return {"seeded": count}


@app.get("/uploads/{filename}")
def get_upload(filename: str):
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(404)
    return FileResponse(path)


# ---------------------------------------------------------------------------
# Static frontend — served from the sibling frontend/ folder. The API (this
# file and everything it imports) has zero knowledge of frontend internals
# beyond this one mount, so the frontend could be deployed separately (e.g.
# a static host / CDN) against this same API with no backend changes.
# ---------------------------------------------------------------------------
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
