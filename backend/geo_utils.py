import math
import time
import urllib.request
import urllib.parse
import json

EARTH_RADIUS_M = 6371000

# ---------------------------------------------------------------------------
# Live landmark lookup (OpenStreetMap Overpass API).
#
# Why this exists: location_criticality() below only ever scores a report
# against whatever rows are in the `landmarks` table, and that table is
# seeded with ~12 hardcoded points around Kolkata (see
# database._seed_landmarks_if_empty — its own comment literally says "a real
# deployment would pull these from OpenStreetMap instead of hardcoding").
# Anywhere outside a few hundred metres of those 12 points, there are zero
# nearby landmarks, so location_criticality_score is always 0 — not because
# any model is "wrong", there's no ML/LLM involved here at all, it's a plain
# distance-weighted formula, but because it had no real data to work with
# for any location other than that one demo city.
#
# get_landmarks_near() fixes that by querying Overpass for real
# schools/hospitals/bus stops/markets/traffic signals within range of the
# report's actual coordinates, anywhere in the world. Falls back to the
# seeded DB landmarks (and then to an empty list) if Overpass is unreachable
# or slow, so a flaky third-party API can never break complaint submission —
# same "never hard-depend on the remote call" pattern used for YOLO and
# reverse-geocoding elsewhere in this file.
# ---------------------------------------------------------------------------

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 8  # seconds — this runs synchronously in the complaint pipeline
_OSM_CACHE: dict = {}  # (lat_rounded, lon_rounded) -> (fetched_at_epoch, landmarks)
_OSM_CACHE_TTL = 60 * 60 * 6  # 6 hours — infrastructure landmarks don't move

# OSM tag -> (our "kind" label, criticality weight). Weights mirror the ones
# used in the original seeded demo data (hospitals highest, bus stops lowest).
_OSM_TAG_MAP = {
    ("amenity", "hospital"): ("hospital", 1.3),
    ("amenity", "clinic"): ("hospital", 1.1),
    ("amenity", "school"): ("school", 1.0),
    ("amenity", "college"): ("school", 1.0),
    ("amenity", "university"): ("school", 1.0),
    ("amenity", "marketplace"): ("market", 0.8),
    ("shop", "supermarket"): ("market", 0.7),
    ("highway", "bus_stop"): ("bus_stop", 0.6),
    ("public_transport", "station"): ("bus_stop", 0.7),
    ("railway", "station"): ("bus_stop", 0.9),
    ("highway", "traffic_signals"): ("intersection", 0.9),
}


def _overpass_query(lat, lon, radius_m=1000) -> str:
    clauses = "".join(
        f'node["{tag}"="{value}"](around:{radius_m},{lat},{lon});'
        for tag, value in _OSM_TAG_MAP
    )
    return f"[out:json][timeout:{OVERPASS_TIMEOUT}];({clauses});out body;"


def fetch_osm_landmarks(lat, lon, radius_m=1000) -> list | None:
    """Live landmark lookup via OpenStreetMap Overpass, cached per ~100m cell.
    Returns None (signal to fall back) on any network/parse failure — never
    raises into the complaint pipeline."""
    cache_key = (round(lat, 3), round(lon, 3))
    cached = _OSM_CACHE.get(cache_key)
    if cached and (time.time() - cached[0]) < _OSM_CACHE_TTL:
        return cached[1]

    try:
        query = _overpass_query(lat, lon, radius_m)
        data_bytes = urllib.parse.urlencode({"data": query}).encode()
        req = urllib.request.Request(
            OVERPASS_URL, data=data_bytes, headers={"User-Agent": "jandrishti-priority-engine"}
        )
        with urllib.request.urlopen(req, timeout=OVERPASS_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode())
    except Exception:
        return None

    landmarks = []
    for el in payload.get("elements", []):
        tags = el.get("tags", {})
        el_lat, el_lon = el.get("lat"), el.get("lon")
        if el_lat is None or el_lon is None:
            continue
        for (tag, value), (kind, weight) in _OSM_TAG_MAP.items():
            if tags.get(tag) == value:
                landmarks.append(
                    {
                        "name": tags.get("name") or kind.replace("_", " ").title(),
                        "kind": kind,
                        "latitude": el_lat,
                        "longitude": el_lon,
                        "weight": weight,
                    }
                )
                break

    _OSM_CACHE[cache_key] = (time.time(), landmarks)
    return landmarks


def get_landmarks_near(conn, lat, lon) -> list:
    """The single entry point run_pipeline()/main.py should use to get
    landmarks for a given report location: try live OSM data first (works
    anywhere), fall back to whatever's seeded in the local `landmarks` table
    (works offline, and still covers the original Kolkata demo data)."""
    osm = fetch_osm_landmarks(lat, lon)
    if osm is not None and len(osm) > 0:
        return osm
    return [dict(r) for r in conn.execute("SELECT * FROM landmarks").fetchall()]


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def location_criticality(lat, lon, landmarks) -> tuple[float, list]:
    """
    Combine proximity to critical facilities (school/hospital/bus stop/market/intersection)
    into a 0-100 score. Closer + higher-weight landmarks push the score up; anything beyond
    ~1km is treated as not meaningfully affecting this complaint's location importance.
    """
    nearby = []
    score = 0.0
    for lm in landmarks:
        d = haversine_m(lat, lon, lm["latitude"], lm["longitude"])
        if d <= 1000:
            # inverse-distance contribution, capped, scaled by landmark importance
            proximity = max(0.0, 1.0 - d / 1000)
            contribution = proximity * lm["weight"] * 55  # tuned so 1-2 close landmarks -> high score
            score += contribution
            if d <= 300:
                nearby.append({"name": lm["name"], "kind": lm["kind"], "distance_m": round(d)})
    nearby.sort(key=lambda n: n["distance_m"])
    return min(100.0, round(score, 1)), nearby[:4]


def reverse_geocode(lat, lon) -> str:
    """Best-effort reverse geocode via OpenStreetMap Nominatim. Falls back to raw
    coordinates if the network call fails (e.g. no internet access, rate limited) —
    the rest of the pipeline never depends on this succeeding."""
    try:
        url = (
            f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}&zoom=17"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "infra-priority-engine-hackathon"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode())
            return data.get("display_name", f"{lat:.5f}, {lon:.5f}")
    except Exception:
        return f"{lat:.5f}, {lon:.5f}"
