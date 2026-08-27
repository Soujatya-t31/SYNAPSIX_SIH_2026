import math
import urllib.request
import json

EARTH_RADIUS_M = 6371000


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
