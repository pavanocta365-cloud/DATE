"""Nearby discovery: radius filter, then rank by proximity + shared interests.

Pipeline
    1. bounding-box prefilter in SQL      (cheap, index-assisted)
    2. exact haversine in SQL             (via the registered `haversine` fn)
    3. mutual gender-preference filter
    4. drop anyone already liked or passed
    5. score = W_PROXIMITY * proximity + W_INTERESTS * interest_similarity
    6. sort by score, then by distance
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from . import config, db, models
from .geo import bounding_box, format_distance
from .interests_data import PREFERENCE_MATCHES


def _proximity_score(distance_km: float, radius_km: float) -> float:
    """1.0 at your doorstep, 0.0 at the edge of the radius.

    sqrt-shaped so that the difference between 2 km and 8 km still matters
    when the radius is wide.
    """
    if radius_km <= 0:
        return 0.0
    ratio = min(1.0, max(0.0, distance_km / radius_km))
    return 1.0 - math.sqrt(ratio)


def _interest_score(mine: set, theirs: set) -> float:
    """Cosine-style overlap: rewards real overlap without punishing breadth."""
    if not mine or not theirs:
        return 0.0
    shared = len(mine & theirs)
    if shared == 0:
        return 0.0
    return shared / math.sqrt(len(mine) * len(theirs))


def _preference_clause(interested_in: str):
    genders = PREFERENCE_MATCHES.get(interested_in) or PREFERENCE_MATCHES["everyone"]
    genders = sorted(genders)
    return " AND p.gender IN (%s)" % ",".join("?" * len(genders)), genders


def discover(user_id: int, radius_km: Optional[int] = None,
             limit: int = None, offset: int = 0,
             include_decided: bool = False) -> Dict:
    """Return ranked candidates near `user_id`, plus the context used.

    People you have already liked or passed are excluded unless
    `include_decided` is set (used by tests and by the ranking explainer).
    """
    limit = limit or config.DISCOVER_PAGE_SIZE
    me_profile = models.profile_for_user(user_id)
    me_location = models.current_location(user_id)

    result = {
        "candidates": [], "radius_km": radius_km or config.DEFAULT_RADIUS_KM,
        "total": 0, "location": me_location, "reason": None,
        "my_interests": [],
    }
    if me_profile is None:
        result["reason"] = "no-profile"
        return result
    if me_location is None:
        result["reason"] = "no-location"
        return result

    radius_km = int(radius_km or me_profile["radius_km"] or config.DEFAULT_RADIUS_KM)
    radius_km = max(1, min(config.MAX_RADIUS_KM, radius_km))
    result["radius_km"] = radius_km

    my_interest_names = models.profile_interest_names(me_profile["id"])
    mine = set(my_interest_names)
    result["my_interests"] = my_interest_names

    lat, lon = me_location["latitude"], me_location["longitude"]
    min_lat, max_lat, min_lon, max_lon, use_lon = bounding_box(lat, lon, radius_km)

    pref_sql, pref_params = _preference_clause(me_profile["interested_in"])

    sql = (
        "SELECT * FROM ("
        "  SELECT p.id AS profile_id, u.id AS user_id, p.display_name, p.birthdate,"
        "         p.gender, p.headline, p.bio, p.photo, u.last_seen_at,"
        "         l.city, l.region, l.country, l.latitude, l.longitude,"
        "         haversine(?, ?, l.latitude, l.longitude) AS distance_km"
        "    FROM profiles p"
        "    JOIN users u     ON u.id = p.user_id"
        "    JOIN locations l ON l.user_id = p.user_id AND l.is_current = 1"
        "   WHERE p.user_id <> ?"
        "     AND p.is_complete = 1"
        "     AND l.latitude BETWEEN ? AND ?"
    )
    params: List = [lat, lon, user_id, min_lat, max_lat]
    if use_lon:
        sql += "     AND l.longitude BETWEEN ? AND ?"
        params += [min_lon, max_lon]
    sql += pref_sql
    params += pref_params
    if not include_decided:
        sql += ("     AND NOT EXISTS (SELECT 1 FROM likes lk"
                "          WHERE lk.from_user_id = ? AND lk.to_user_id = p.user_id)")
        params.append(user_id)
    sql += ") WHERE distance_km IS NOT NULL AND distance_km <= ?"
    params.append(float(radius_km))

    rows = db.query(sql, params)
    if not rows:
        result["reason"] = "empty"
        return result

    names_by_profile = models.interest_names_for_profiles(
        [r["profile_id"] for r in rows])

    # One query for "has this person already liked me?" instead of one per card.
    admirers = {r["from_user_id"] for r in db.query(
        "SELECT from_user_id FROM likes WHERE to_user_id = ? AND is_like = 1",
        (user_id,))}

    candidates = []
    for row in rows:
        their_names = names_by_profile.get(row["profile_id"], [])
        theirs = set(their_names)
        shared = sorted(mine & theirs)

        proximity = _proximity_score(row["distance_km"], radius_km)
        interest = _interest_score(mine, theirs)
        if mine:
            score = config.W_PROXIMITY * proximity + config.W_INTERESTS * interest
        else:
            # Nothing to compare against yet - rank purely on how close they are.
            score = proximity

        candidates.append({
            "user_id": row["user_id"],
            "profile_id": row["profile_id"],
            "display_name": row["display_name"],
            "age": models.age_from_birthdate(row["birthdate"]),
            "gender": row["gender"],
            "headline": row["headline"],
            "bio": row["bio"],
            "photo": row["photo"],
            "city": row["city"],
            "region": row["region"],
            "country": row["country"],
            "distance_km": row["distance_km"],
            "distance_label": format_distance(row["distance_km"]),
            "interests": their_names,
            "shared_interests": shared,
            "shared_count": len(shared),
            "proximity_score": proximity,
            "interest_score": interest,
            "score": score,
            "match_percent": int(round(score * 100)),
            "likes_me": row["user_id"] in admirers,
        })

    candidates.sort(key=lambda c: (-c["score"], c["distance_km"]))
    result["total"] = len(candidates)
    result["candidates"] = candidates[offset:offset + limit]
    if not result["candidates"]:
        result["reason"] = "empty"
    return result


def explain(candidate: Dict) -> str:
    """One line describing why this profile surfaced where it did."""
    bits = [candidate["distance_label"]]
    n = candidate["shared_count"]
    if n:
        bits.append("%d shared interest%s" % (n, "" if n == 1 else "s"))
    return " &middot; ".join(bits)
