"""Data access for users, profiles, interests and locations."""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional

from . import config, db
from .interests_data import (CATEGORY_ORDER, GENDER_VALUES, INTERESTED_VALUES,
                             INTERESTS)


# --- users -----------------------------------------------------------------
def create_user(email: str, password_hash: str, is_demo: int = 0) -> int:
    cur = db.execute(
        "INSERT INTO users (email, password_hash, is_demo) VALUES (?, ?, ?)",
        (email, password_hash, is_demo))
    user_id = int(cur.lastrowid)
    db.execute("INSERT INTO profiles (user_id) VALUES (?)", (user_id,))
    return user_id


def user_by_email(email: str):
    return db.query_one("SELECT * FROM users WHERE email = ?", (email,))


def email_taken(email: str) -> bool:
    return db.query_one("SELECT 1 FROM users WHERE email = ?", (email,)) is not None


def touch_last_seen(user_id: int) -> None:
    db.execute("UPDATE users SET last_seen_at = datetime('now') WHERE id = ?",
               (user_id,))


# --- interests -------------------------------------------------------------
def ensure_interest_catalogue() -> None:
    existing = {r["slug"] for r in db.query("SELECT slug FROM interests")}
    rows = [(slug, name, cat, i)
            for i, (slug, name, cat) in enumerate(INTERESTS) if slug not in existing]
    if rows:
        db.executemany(
            "INSERT INTO interests (slug, name, category, sort_order)"
            " VALUES (?, ?, ?, ?)", rows)


def all_interests() -> List[dict]:
    rows = db.query("SELECT id, slug, name, category FROM interests"
                    " ORDER BY sort_order")
    return [dict(r) for r in rows]


def interests_by_category() -> List[tuple]:
    grouped: Dict[str, List[dict]] = {}
    for item in all_interests():
        grouped.setdefault(item["category"], []).append(item)
    return [(cat, grouped[cat]) for cat in CATEGORY_ORDER if cat in grouped]


def profile_interest_ids(profile_id: int) -> List[int]:
    return [r["interest_id"] for r in db.query(
        "SELECT interest_id FROM profile_interests WHERE profile_id = ?",
        (profile_id,))]


def profile_interest_names(profile_id: int) -> List[str]:
    return [r["name"] for r in db.query(
        "SELECT i.name FROM profile_interests pi"
        " JOIN interests i ON i.id = pi.interest_id"
        " WHERE pi.profile_id = ? ORDER BY i.sort_order", (profile_id,))]


def set_profile_interests(profile_id: int, interest_ids) -> None:
    wanted = list(dict.fromkeys(int(i) for i in interest_ids))[:config.MAX_INTERESTS]
    db.execute("DELETE FROM profile_interests WHERE profile_id = ?", (profile_id,))
    if wanted:
        db.executemany(
            "INSERT OR IGNORE INTO profile_interests (profile_id, interest_id)"
            " VALUES (?, ?)", [(profile_id, i) for i in wanted])


def interest_names_for_profiles(profile_ids) -> Dict[int, List[str]]:
    """One query for a page of candidates instead of N."""
    ids = list(profile_ids)
    if not ids:
        return {}
    placeholders = ",".join("?" * len(ids))
    rows = db.query(
        "SELECT pi.profile_id, i.name FROM profile_interests pi"
        " JOIN interests i ON i.id = pi.interest_id"
        " WHERE pi.profile_id IN (%s) ORDER BY i.sort_order" % placeholders, ids)
    out: Dict[int, List[str]] = {}
    for row in rows:
        out.setdefault(row["profile_id"], []).append(row["name"])
    return out


# --- profiles --------------------------------------------------------------
def profile_for_user(user_id: int):
    return db.query_one("SELECT * FROM profiles WHERE user_id = ?", (user_id,))


def profile_by_user_id(user_id: int):
    return db.query_one(
        "SELECT p.*, u.email, u.last_seen_at FROM profiles p"
        " JOIN users u ON u.id = p.user_id WHERE p.user_id = ?", (user_id,))


def update_profile(user_id: int, **fields) -> None:
    allowed = ("display_name", "birthdate", "gender", "interested_in",
               "headline", "bio", "photo", "radius_km", "is_complete")
    sets, params = [], []
    for key, value in fields.items():
        if key in allowed:
            sets.append("%s = ?" % key)
            params.append(value)
    if not sets:
        return
    sets.append("updated_at = datetime('now')")
    params.append(user_id)
    db.execute("UPDATE profiles SET %s WHERE user_id = ?" % ", ".join(sets), params)


def recompute_completeness(user_id: int) -> bool:
    profile = profile_for_user(user_id)
    if profile is None:
        return False
    n_interests = db.scalar(
        "SELECT COUNT(*) FROM profile_interests WHERE profile_id = ?",
        (profile["id"],)) or 0
    complete = bool(
        profile["display_name"].strip()
        and profile["birthdate"]
        and profile["gender"] in GENDER_VALUES
        and profile["interested_in"] in INTERESTED_VALUES
        and n_interests >= config.MIN_INTERESTS
        and current_location(user_id) is not None
    )
    became_complete = complete and not profile["is_complete"]
    db.execute("UPDATE profiles SET is_complete = ? WHERE user_id = ?",
               (1 if complete else 0, user_id))

    if became_complete and not db.scalar(
            "SELECT is_demo FROM users WHERE id = ?", (user_id,)):
        from . import seed
        seed.seed_likes_for(user_id)
    return complete


def profile_gaps(user_id: int) -> List[str]:
    """Human-readable list of what still blocks discovery."""
    profile = profile_for_user(user_id)
    gaps = []
    if profile is None:
        return ["Create your profile."]
    if not profile["display_name"].strip():
        gaps.append("Add your name")
    if not profile["birthdate"]:
        gaps.append("Add your date of birth")
    if profile["gender"] not in GENDER_VALUES:
        gaps.append("Say how you identify")
    n = db.scalar("SELECT COUNT(*) FROM profile_interests WHERE profile_id = ?",
                  (profile["id"],)) or 0
    if n < config.MIN_INTERESTS:
        gaps.append("Pick at least %d interests" % config.MIN_INTERESTS)
    if current_location(user_id) is None:
        gaps.append("Set your location")
    return gaps


# --- age -------------------------------------------------------------------
def parse_birthdate(text: str) -> Optional[date]:
    try:
        return datetime.strptime((text or "").strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def age_from_birthdate(birthdate) -> Optional[int]:
    born = birthdate if isinstance(birthdate, date) else parse_birthdate(birthdate)
    if born is None:
        return None
    today = date.today()
    return today.year - born.year - (
        (today.month, today.day) < (born.month, born.day))


# --- locations -------------------------------------------------------------
def current_location(user_id: int):
    return db.query_one(
        "SELECT * FROM locations WHERE user_id = ? AND is_current = 1"
        " ORDER BY recorded_at DESC, id DESC LIMIT 1", (user_id,))


def set_location(user_id: int, latitude: float, longitude: float,
                 city: str = "", region: str = "", country: str = "",
                 source: str = "manual") -> None:
    """Append to history and make the new row the current one."""
    db.execute("UPDATE locations SET is_current = 0 WHERE user_id = ?", (user_id,))
    db.execute(
        "INSERT INTO locations (user_id, latitude, longitude, city, region,"
        " country, source, is_current) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        (user_id, float(latitude), float(longitude), city, region, country, source))


def location_label(row) -> str:
    if row is None:
        return "No location set"
    bits = [b for b in (row["city"], row["region"], row["country"]) if b]
    seen, out = set(), []
    for b in bits:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return ", ".join(out[:2]) if out else "%.3f, %.3f" % (row["latitude"],
                                                          row["longitude"])
