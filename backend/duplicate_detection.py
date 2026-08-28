"""
Duplicate detection / incident clustering (spec section 6B).

If multiple citizens report the same underlying problem near each other, they should
collapse into one incident with an "affected citizens" count, not N separate tasks.
"""

from datetime import datetime, timedelta
from geo_utils import haversine_m

RADIUS_M = 200
WINDOW_DAYS = 45


def find_incident_cluster(conn, category: str, lat: float, lon: float):
    """Look for an existing open incident of the same category within RADIUS_M and
    WINDOW_DAYS. Returns (incident_id, duplicate_count, primary_complaint_id) or
    (None, 0, None) if this is a new incident."""
    cutoff = (datetime.utcnow() - timedelta(days=WINDOW_DAYS)).isoformat()
    rows = conn.execute(
        """SELECT id, incident_id, latitude, longitude, is_primary
           FROM complaints
           WHERE category = ? AND created_at >= ? AND status != 'RESOLVED'""",
        (category, cutoff),
    ).fetchall()

    matches = [r for r in rows if haversine_m(lat, lon, r["latitude"], r["longitude"]) <= RADIUS_M]
    if not matches:
        return None, 0, None

    # incident id = the incident_id of the earliest match in this cluster (stable anchor)
    incident_id = next((r["incident_id"] for r in matches if r["incident_id"]), None)
    primary = next((r["id"] for r in matches if r["is_primary"]), matches[0]["id"])
    return incident_id, len(matches), primary
