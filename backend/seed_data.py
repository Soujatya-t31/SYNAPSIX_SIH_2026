"""
Generates realistic demo data so the dashboard isn't empty at demo time.

Important: this does NOT fabricate priority scores. It synthesizes plausible raw
inputs (a CV reading, a citizen severity flag, a location, a timestamp) and then
runs them through the exact same priority_engine / geo_utils / duplicate_detection
code the live API uses. If you distrust a score on the dashboard, the same formula
produced it as would for a real citizen submission.
"""

import random
import uuid
from datetime import datetime, timedelta

import database
import geo_utils
import priority_engine
import duplicate_detection

random.seed(42)

CATEGORIES = list(priority_engine.DEPARTMENT_MAP.keys())

# Bounding box roughly covering Kolkata metro, used for scattering demo complaints.
BOUNDS = {"lat_min": 22.45, "lat_max": 22.62, "lon_min": 88.28, "lon_max": 88.45}

CITIZEN_SEVERITIES = ["Dangerous", "Dangerous", "Moderate", "Moderate", "Minor", None]

DESCRIPTIONS = {
    "Pothole": ["Large pothole in the middle of the road", "Deep pothole causing traffic to swerve",
                "Multiple potholes near the junction", "Pothole filling with water after rain"],
    "Road Crack": ["Long crack running across the lane", "Road surface breaking apart",
                   "Cracks widening after monsoon"],
    "Broken Streetlight": ["Streetlight not working for a week", "Pole leaning, light flickering",
                            "Entire stretch of road dark at night"],
    "Garbage Overflow": ["Bin overflowing for 3 days", "Garbage spilling onto the road",
                          "Illegal dumping near the corner"],
    "Water Leakage": ["Pipe leaking continuously onto the road", "Water pooling from underground leak"],
    "Drainage Issue": ["Drain blocked, water not flowing", "Waterlogging after light rain"],
    "Damaged Footpath": ["Footpath tiles broken and uneven", "Footpath caved in near the drain"],
    "Traffic Signal": ["Signal stuck on red for 20 minutes", "Signal not working at busy crossing"],
    "Public Toilet": ["Public toilet unusable, no water", "Toilet door broken"],
    "Bridge": ["Railing damaged on the footbridge", "Visible crack on the bridge pillar"],
    "Public Building": ["Ceiling plaster falling in community hall", "Boundary wall collapsed"],
    "Other": ["Infrastructure issue needs attention"],
}


def random_point(hotspot=None):
    if hotspot and random.random() < 0.65:
        return (
            hotspot["latitude"] + random.uniform(-0.0008, 0.0008),
            hotspot["longitude"] + random.uniform(-0.0008, 0.0008),
        )
    return (
        random.uniform(BOUNDS["lat_min"], BOUNDS["lat_max"]),
        random.uniform(BOUNDS["lon_min"], BOUNDS["lon_max"]),
    )


def synth_cv(category):
    valid = random.random() > 0.08  # ~8% low-confidence / needs-review, realistic noise
    confidence = round(random.uniform(0.55, 0.99) if valid else random.uniform(0.2, 0.5), 3)
    defect_count = random.randint(1, 8) if valid else random.randint(0, 1)
    damage_area_pct = round(random.uniform(5, 60) if valid else random.uniform(0, 5), 1)
    return {
        "detected_class": category if valid else f"uncertain ({category}?)",
        "confidence": confidence,
        "defect_count": defect_count,
        "damage_area_pct": damage_area_pct,
        "valid": valid,
        "notes": "Simulated CV reading (seed data).",
    }


def insert_complaint(conn, landmarks, ts, category, citizen_severity, lat, lon, cv_result, status_override=None):
    complaint_id = "INF-" + ts.strftime("%Y%m") + "-" + uuid.uuid4().hex[:6].upper()
    description = random.choice(DESCRIPTIONS.get(category, DESCRIPTIONS["Other"]))

    loc_score, nearby = geo_utils.location_criticality(lat, lon, landmarks)
    incident_id, dup_count, primary_id = duplicate_detection.find_incident_cluster(conn, category, lat, lon)
    is_new_incident = incident_id is None
    affected_citizens = max(1, dup_count + 1)

    past = conn.execute(
        "SELECT category FROM complaints WHERE ABS(latitude-?)<0.003 AND ABS(longitude-?)<0.003",
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
        "severity_score": severity, "public_impact_score": public_impact,
        "safety_risk_score": safety_risk, "location_criticality_score": loc_score,
        "historical_recurrence_score": hist_recur, "future_risk_score": future_risk,
    }
    result = priority_engine.compute_priority(scores)
    department = priority_engine.route_department(category)
    final_incident_id = incident_id or complaint_id
    is_primary = 1 if is_new_incident else 0

    now = datetime.utcnow()
    age_days = (now - ts).days
    if status_override:
        status = status_override
    elif age_days > 30 and random.random() < 0.6:
        status = "RESOLVED"
    elif age_days > 10 and random.random() < 0.4:
        status = random.choice(["ASSIGNED", "IN_PROGRESS"])
    else:
        status = "RECEIVED"
    resolved_at = (ts + timedelta(days=random.uniform(1, 20))).isoformat() if status == "RESOLVED" else None

    conn.execute(
        """INSERT INTO complaints (
            id, created_at, category, description, citizen_severity, latitude, longitude,
            address, image_path, reporter_id,
            detected_class, cv_confidence, defect_count, damage_area_pct, cv_valid, cv_notes,
            severity_score, public_impact_score, location_criticality_score,
            historical_recurrence_score, safety_risk_score, future_risk_score,
            priority_score, priority_level, department, sla_hours,
            incident_id, is_primary, affected_citizens, status, resolved_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            complaint_id, ts.isoformat(), category, description, citizen_severity, lat, lon,
            f"{lat:.5f}, {lon:.5f}", None, f"citizen_{random.randint(1000,9999)}",
            cv_result["detected_class"], cv_result["confidence"], cv_result["defect_count"],
            cv_result["damage_area_pct"], 1 if cv_result["valid"] else 0, cv_result["notes"],
            severity, public_impact, loc_score, hist_recur, safety_risk, future_risk,
            result["priority_score"], result["priority_level"], department, result["sla_hours"],
            final_incident_id, is_primary, affected_citizens, status, resolved_at,
        ),
    )
    if not is_new_incident and primary_id:
        priority_engine.recompute_primary_on_new_duplicate(conn, primary_id, dup_count, nearby, category)
    return result["priority_level"]


# 15 real, spread-out locations across Bhubaneswar, Odisha, used to seed a
# small batch of demo complaints there (the rest of the demo data above is
# scattered around Kolkata via BOUNDS/hotspots, left untouched).
BHUBANESWAR_LOCATIONS = [
    ("Master Canteen Square", 20.2700, 85.8400),
    ("Kalpana Square", 20.2760, 85.8360),
    ("Rajmahal Square", 20.2712, 85.8317),
    ("Vani Vihar", 20.2925, 85.8245),
    ("Patia Square", 20.3554, 85.8188),
    ("Chandrasekharpur", 20.3441, 85.8189),
    ("Jaydev Vihar Square", 20.2986, 85.8115),
    ("Bhubaneswar Railway Station", 20.2679, 85.8412),
    ("Kalinga Stadium", 20.2860, 85.8390),
    ("Infocity Square", 20.3487, 85.8203),
    ("Nandankanan Road", 20.3937, 85.8177),
    ("Baramunda Bus Stand", 20.2871, 85.7935),
    ("AIIMS Bhubaneswar", 20.1875, 85.7772),
    ("Sishu Bhawan Square", 20.2688, 85.8358),
    ("Old Town (Lingaraj Temple Road)", 20.2377, 85.8315),
]


def seed_bhubaneswar_incidents(conn, landmarks, now):
    """15 demo complaints, one per real Bhubaneswar, Odisha location above —
    run through the exact same pipeline/priority formula as every other
    complaint here, just anchored to a different city."""
    for _name, lat, lon in BHUBANESWAR_LOCATIONS:
        category = random.choice(CATEGORIES)
        citizen_severity = random.choice(CITIZEN_SEVERITIES)
        cv_result = synth_cv(category)
        ts = now - timedelta(days=random.uniform(0, 40), hours=random.uniform(0, 23))
        jitter_lat = lat + random.uniform(-0.0006, 0.0006)
        jitter_lon = lon + random.uniform(-0.0006, 0.0006)
        insert_complaint(conn, landmarks, ts, category, citizen_severity, jitter_lat, jitter_lon, cv_result)


def seed_flagship_incidents(conn, landmarks, now, count=9):
    """A handful of deliberately severe, high-traffic, multiply-reported incidents —
    e.g. a real dangerous pothole right by a school gate reported by 6 different
    residents this week. These are realistic worst-case scenarios, not fabricated
    scores: they run through the exact same formula, just with inputs that a genuinely
    bad, high-footfall incident would plausibly produce."""
    risky_categories = list(priority_engine.HIGH_ACCIDENT_RISK_CATEGORIES)
    critical_landmarks = [lm for lm in landmarks if lm["kind"] in ("school", "hospital", "intersection")]
    for i in range(count):
        category = random.choice(risky_categories)
        anchor = random.choice(critical_landmarks)
        n_reports = random.randint(4, 9)
        base_day = random.uniform(0, 6)  # all within the last week
        for r in range(n_reports):
            ts = now - timedelta(days=base_day - r * 0.3, hours=random.uniform(0, 20))
            lat = anchor["latitude"] + random.uniform(-0.0004, 0.0004)
            lon = anchor["longitude"] + random.uniform(-0.0004, 0.0004)
            cv_result = {
                "detected_class": category,
                "confidence": round(random.uniform(0.85, 0.98), 3),
                "defect_count": random.randint(4, 8),
                "damage_area_pct": round(random.uniform(35, 65), 1),
                "valid": True,
                "notes": "Simulated CV reading (seed data, flagship incident).",
            }
            citizen_severity = random.choice(["Dangerous", "Dangerous", "Moderate"])
            insert_complaint(conn, landmarks, ts, category, citizen_severity, lat, lon, cv_result,
                              status_override="RECEIVED" if r == n_reports - 1 else None)


def run(n=150, reset=True):
    if database.USE_POSTGRES and reset:
        print("[seed_data] DATABASE_URL is set (Postgres mode) — ignoring reset=True. "
              "The shared production database is never auto-wiped by this script; "
              "this will just add demo complaints on top of whatever's already there. "
              "Use database.reset_postgres_schema() explicitly if you really want to wipe it.")
    database.init_db(reset=reset)
    conn = database.get_conn()
    landmarks = [dict(r) for r in conn.execute("SELECT * FROM landmarks").fetchall()]
    now = datetime.utcnow()

    # Build a chronological list of (timestamp, category) events so duplicate/historical
    # logic accumulates naturally, same as it would happen in production.
    events = []
    for _ in range(n):
        days_ago = random.betavariate(1.5, 4) * 60  # skewed toward more recent
        ts = now - timedelta(days=days_ago, hours=random.uniform(0, 23))
        category = random.choices(CATEGORIES, weights=[5, 3, 4, 4, 2, 2, 3, 2, 1, 1, 1, 1])[0]
        events.append((ts, category))
    events.sort(key=lambda e: e[0])

    # A handful of recurring "hotspot" locations so duplicate clustering has something
    # real to find (mirrors the spec's "50 reports within 200m" example, scaled down).
    hotspots = random.sample(landmarks, k=5)
    hotspot_for_category = {}

    inserted = 0
    for ts, category in events:
        hotspot = None
        if random.random() < 0.5:
            hotspot = hotspot_for_category.setdefault(category, random.choice(hotspots))
        lat, lon = random_point(hotspot)
        citizen_severity = random.choice(CITIZEN_SEVERITIES)
        cv_result = synth_cv(category)
        insert_complaint(conn, landmarks, ts, category, citizen_severity, lat, lon, cv_result)
        inserted += 1

    seed_flagship_incidents(conn, landmarks, now, count=13)
    seed_bhubaneswar_incidents(conn, landmarks, now)

    conn.commit()
    conn.close()
    return inserted


if __name__ == "__main__":
    count = run(n=150, reset=True)
    print(f"Seeded {count} complaints.")
