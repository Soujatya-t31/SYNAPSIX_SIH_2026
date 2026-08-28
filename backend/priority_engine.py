"""
Priority Engine — transparent, weighted scoring (spec section 14).

Deliberately NOT a black-box ML model for the hackathon build: every sub-score is
computed from an explicit, inspectable rule, and the final score is a documented
weighted sum. This is the "Phase 1" model the spec calls for; Phase 2 (Random
Forest/XGBoost trained on real resolution outcomes) is future work — see README.

    Priority Score =
        0.30 * Severity
      + 0.20 * Public Impact
      + 0.15 * Safety Risk
      + 0.15 * Location Criticality
      + 0.10 * Historical Recurrence
      + 0.10 * Future Risk
"""

WEIGHTS = {
    "severity_score": 0.30,
    "public_impact_score": 0.20,
    "safety_risk_score": 0.15,
    "location_criticality_score": 0.15,
    "historical_recurrence_score": 0.10,
    "future_risk_score": 0.10,
}

DEPARTMENT_MAP = {
    "Pothole": "Road & Infrastructure",
    "Road Crack": "Road & Infrastructure",
    "Broken Streetlight": "Electrical Department",
    "Garbage Overflow": "Waste Management",
    "Water Leakage": "Water Supply Department",
    "Drainage Issue": "Water Supply Department",
    "Damaged Footpath": "Road & Infrastructure",
    "Traffic Signal": "Electrical Department",
    "Public Toilet": "Public Health Department",
    "Bridge": "Road & Infrastructure",
    "Public Building": "General Maintenance",
    "Other": "General Maintenance",
}

# Categories where poor visibility/road surface risk translates more directly into
# accident risk (used by compute_safety_risk).
HIGH_ACCIDENT_RISK_CATEGORIES = {"Pothole", "Road Crack", "Broken Streetlight", "Traffic Signal", "Bridge", "Damaged Footpath"}

SLA_HOURS = {"Critical": 24, "High": 72, "Medium": 168, "Low": 336}  # 1d / 3d / 7d / 14d

CITIZEN_SEVERITY_BONUS = {"Dangerous": 12, "Moderate": 5, "Minor": 0, None: 0, "": 0}


def compute_severity(cv: dict, citizen_severity: str | None) -> float:
    """Physical seriousness of the damage: CV confidence + damage area + defect count,
    with a small nudge from the citizen's own severity flag (a weak signal only, never
    the primary driver — per spec section 3)."""
    if not cv.get("valid", False):
        # Unverified complaints get a low-but-nonzero severity so they still surface
        # for manual review instead of disappearing.
        base = 15.0
    else:
        conf = cv.get("confidence", 0) * 100
        area = min(cv.get("damage_area_pct", 0), 40) * 1.5  # cap contribution, avoid runaway
        count = min(cv.get("defect_count", 0), 8) * 4
        base = 0.4 * conf + 0.35 * area + 0.25 * count
    bonus = CITIZEN_SEVERITY_BONUS.get(citizen_severity, 0)
    return round(min(100.0, base + bonus), 1)


def compute_public_impact(duplicate_count: int, nearby_landmarks: list, category: str, upvotes: int = 0) -> float:
    """How many people this plausibly affects: duplicate reports (proxy for how many
    citizens noticed/were bothered by it), nearby high-footfall facilities, and
    citizen upvotes ("yes, this is real / still happening") — a lighter-weight
    confirmation signal than filing a full duplicate report, capped lower so a small
    number of clicks can't dominate the score the way genuine duplicate filings do."""
    dup_component = min(60.0, duplicate_count * 12)  # 5 duplicates already near-maxes this out
    landmark_component = min(40.0, sum(8 for _ in nearby_landmarks))
    upvote_component = min(20.0, upvotes * 2)
    return round(min(100.0, dup_component + landmark_component + upvote_component), 1)


def compute_safety_risk(category: str, severity_score: float, location_criticality: float) -> float:
    """Estimated accident/injury risk. Categories with direct road-safety implications
    scale more strongly with severity + location than low-risk categories like garbage."""
    if category in HIGH_ACCIDENT_RISK_CATEGORIES:
        risk = 0.55 * severity_score + 0.45 * location_criticality
    else:
        risk = 0.25 * severity_score + 0.20 * location_criticality
    return round(min(100.0, risk), 1)


def compute_historical_recurrence(past_incident_count: int, same_category_count: int) -> float:
    """Recurring failures at the same location score higher — a permanent fix is
    likely overdue (spec section 12)."""
    score = min(100.0, past_incident_count * 18 + same_category_count * 10)
    return round(score, 1)


def compute_future_risk(historical_recurrence: float, severity_score: float) -> float:
    """Simple, honestly-labeled deterioration proxy — NOT a trained time-series forecast.
    Recurring + already-severe issues are treated as more likely to worsen soon.
    (Spec section 13 describes a full predictive model; that requires real historical
    resolution data we don't have yet, so this stays a transparent heuristic and is
    flagged as such in the dashboard — see README 'What's real vs roadmap'.)"""
    score = 0.6 * historical_recurrence + 0.4 * severity_score
    return round(min(100.0, score), 1)


def classify(score: float) -> str:
    if score >= 76:
        return "Critical"
    if score >= 51:
        return "High"
    if score >= 26:
        return "Medium"
    return "Low"


def compute_priority(scores: dict) -> dict:
    total = sum(scores[k] * w for k, w in WEIGHTS.items())
    total = round(min(100.0, total), 1)
    level = classify(total)
    return {"priority_score": total, "priority_level": level, "sla_hours": SLA_HOURS[level]}


def route_department(category: str) -> str:
    return DEPARTMENT_MAP.get(category, "General Maintenance")


def recompute_primary_on_new_duplicate(conn, primary_id: str, dup_count: int, nearby_landmarks: list, category: str):
    """When a new report joins an existing incident, the incident's public impact
    (and therefore its overall priority) can legitimately go up — more affected
    citizens is real signal, not noise. Re-run the same weighted formula with the
    updated public_impact_score rather than leaving the primary's score frozen at
    whatever it was when it was the only report."""
    primary = conn.execute("SELECT * FROM complaints WHERE id = ?", (primary_id,)).fetchone()
    if not primary:
        return
    existing_upvotes = primary["upvotes"] if "upvotes" in primary.keys() and primary["upvotes"] else 0
    public_impact = compute_public_impact(dup_count, nearby_landmarks, category, upvotes=existing_upvotes)
    scores = {
        "severity_score": primary["severity_score"],
        "public_impact_score": public_impact,
        "safety_risk_score": primary["safety_risk_score"],
        "location_criticality_score": primary["location_criticality_score"],
        "historical_recurrence_score": primary["historical_recurrence_score"],
        "future_risk_score": primary["future_risk_score"],
    }
    result = compute_priority(scores)
    conn.execute(
        """UPDATE complaints
           SET public_impact_score = ?, priority_score = ?, priority_level = ?,
               sla_hours = ?, affected_citizens = ?
           WHERE id = ?""",
        (public_impact, result["priority_score"], result["priority_level"],
         result["sla_hours"], dup_count + 1, primary_id),
    )


def recompute_on_upvote(conn, complaint_id: str, nearby_landmarks: list):
    """A citizen confirmed this issue is real / still happening. Bumps upvotes and
    lets that feed into public_impact_score -> priority_score, same weighted formula,
    fully transparent (visible as its own bar in the score breakdown)."""
    row = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
    if not row:
        return None
    new_upvotes = (row["upvotes"] or 0) + 1
    dup_count = max(0, (row["affected_citizens"] or 1) - 1)
    public_impact = compute_public_impact(dup_count, nearby_landmarks, row["category"], upvotes=new_upvotes)
    scores = {
        "severity_score": row["severity_score"],
        "public_impact_score": public_impact,
        "safety_risk_score": row["safety_risk_score"],
        "location_criticality_score": row["location_criticality_score"],
        "historical_recurrence_score": row["historical_recurrence_score"],
        "future_risk_score": row["future_risk_score"],
    }
    result = compute_priority(scores)
    conn.execute(
        """UPDATE complaints
           SET upvotes = ?, public_impact_score = ?, priority_score = ?,
               priority_level = ?, sla_hours = ?
           WHERE id = ?""",
        (new_upvotes, public_impact, result["priority_score"], result["priority_level"],
         result["sla_hours"], complaint_id),
    )
    return new_upvotes
