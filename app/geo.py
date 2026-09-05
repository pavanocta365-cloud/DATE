"""Great-circle distance plus the city catalogue used for manual location."""
from __future__ import annotations

import math
from typing import Optional, Tuple

EARTH_RADIUS_KM = 6371.0088
_KM_PER_DEG_LAT = 110.574
_KM_PER_DEG_LON_AT_EQUATOR = 111.320


def haversine_km(lat1, lon1, lat2, lon2) -> Optional[float]:
    """Distance in km between two WGS84 points. None if any input is NULL."""
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dphi = p2 - p1
    dlambda = math.radians(float(lon2) - float(lon1))
    a = (math.sin(dphi / 2.0) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2.0) ** 2)
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, a)))


def bounding_box(lat: float, lon: float, radius_km: float):
    """Cheap lat/lon window used to prefilter before the exact distance test.

    Returns (min_lat, max_lat, min_lon, max_lon, use_lon_filter). The longitude
    filter is skipped near the poles or when the window crosses the
    antimeridian, where a simple BETWEEN would silently drop rows.
    """
    lat_delta = radius_km / _KM_PER_DEG_LAT
    min_lat = max(-90.0, lat - lat_delta)
    max_lat = min(90.0, lat + lat_delta)

    cos_lat = math.cos(math.radians(lat))
    if cos_lat <= 0.01:
        return min_lat, max_lat, -180.0, 180.0, False

    lon_delta = radius_km / (_KM_PER_DEG_LON_AT_EQUATOR * cos_lat)
    if lon_delta >= 180.0:
        return min_lat, max_lat, -180.0, 180.0, False

    min_lon = lon - lon_delta
    max_lon = lon + lon_delta
    if min_lon < -180.0 or max_lon > 180.0:
        return min_lat, max_lat, -180.0, 180.0, False
    return min_lat, max_lat, min_lon, max_lon, True


def format_distance(km: Optional[float]) -> str:
    if km is None:
        return "unknown"
    if km < 1.0:
        return "%d m away" % max(50, int(round(km * 1000 / 50.0)) * 50)
    if km < 10.0:
        return "%.1f km away" % km
    return "%d km away" % round(km)


# name, region, country, lat, lon
CITIES: Tuple[Tuple[str, str, str, float, float], ...] = (
    ("Bengaluru",  "Karnataka",   "India", 12.9716, 77.5946),
    ("Mumbai",     "Maharashtra", "India", 19.0760, 72.8777),
    ("Delhi",      "Delhi",       "India", 28.6139, 77.2090),
    ("Gurugram",   "Haryana",     "India", 28.4595, 77.0266),
    ("Hyderabad",  "Telangana",   "India", 17.3850, 78.4867),
    ("Pune",       "Maharashtra", "India", 18.5204, 73.8567),
    ("Chennai",    "Tamil Nadu",  "India", 13.0827, 80.2707),
    ("Kolkata",    "West Bengal", "India", 22.5726, 88.3639),
    ("Ahmedabad",  "Gujarat",     "India", 23.0225, 72.5714),
    ("Jaipur",     "Rajasthan",   "India", 26.9124, 75.7873),
    ("Kochi",      "Kerala",      "India", 9.9312,  76.2673),
    ("Goa",        "Goa",         "India", 15.2993, 74.1240),
    ("London",     "England",     "United Kingdom", 51.5072, -0.1276),
    ("New York",   "New York",    "United States",  40.7128, -74.0060),
    ("San Francisco", "California", "United States", 37.7749, -122.4194),
    ("Singapore",  "",            "Singapore", 1.3521, 103.8198),
    ("Dubai",      "Dubai",       "United Arab Emirates", 25.2048, 55.2708),
    ("Berlin",     "Berlin",      "Germany", 52.5200, 13.4050),
)

CITY_BY_NAME = {c[0]: c for c in CITIES}


def nearest_city(lat: float, lon: float):
    """Best-effort reverse geocode against the built-in catalogue."""
    best, best_km = None, None
    for city in CITIES:
        d = haversine_km(lat, lon, city[3], city[4])
        if best_km is None or d < best_km:
            best, best_km = city, d
    if best_km is not None and best_km <= 150.0:
        return best
    return None
