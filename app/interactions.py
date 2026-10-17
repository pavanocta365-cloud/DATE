"""Likes, matches and chat.

The rules, in one place:
  * a like or pass is a single standing decision (UNIQUE from/to pair)
  * a match exists exactly when both users have is_like = 1 on each other
  * chat is only reachable through a match both users belong to
"""
from __future__ import annotations

from typing import Dict, List, Optional

from . import db, models

MAX_MESSAGE_LEN = 2000


# --- pair helpers ----------------------------------------------------------
def _pair(a: int, b: int):
    return (a, b) if a < b else (b, a)


def decision(from_user_id: int, to_user_id: int) -> Optional[int]:
    """1 if liked, 0 if passed, None if undecided."""
    row = db.query_one(
        "SELECT is_like FROM likes WHERE from_user_id = ? AND to_user_id = ?",
        (from_user_id, to_user_id))
    return None if row is None else int(row["is_like"])


def acted_on_ids(user_id: int) -> List[int]:
    return [r["to_user_id"] for r in db.query(
        "SELECT to_user_id FROM likes WHERE from_user_id = ?", (user_id,))]


# --- likes -----------------------------------------------------------------
def record_decision(from_user_id: int, to_user_id: int, is_like: bool) -> Dict:
    """Store a like/pass. Returns {'match_id': int|None, 'changed': bool}.

    Idempotent: repeating the same decision is a no-op. Passing on someone you
    had matched with removes the match (and its chat) - that is the only way a
    match is torn down.
    """
    if from_user_id == to_user_id:
        return {"match_id": None, "changed": False, "error": "self"}
    if models.profile_by_user_id(to_user_id) is None:
        return {"match_id": None, "changed": False, "error": "no-such-user"}

    previous = decision(from_user_id, to_user_id)
    value = 1 if is_like else 0
    if previous == value:
        return {"match_id": existing_match_id(from_user_id, to_user_id),
                "changed": False}

    db.execute(
        "INSERT INTO likes (from_user_id, to_user_id, is_like) VALUES (?, ?, ?)"
        " ON CONFLICT(from_user_id, to_user_id)"
        " DO UPDATE SET is_like = excluded.is_like,"
        "               created_at = datetime('now')",
        (from_user_id, to_user_id, value))

    if not is_like:
        _drop_match(from_user_id, to_user_id)
        return {"match_id": None, "changed": True}

    if decision(to_user_id, from_user_id) == 1:
        return {"match_id": _create_match(from_user_id, to_user_id), "changed": True}
    return {"match_id": None, "changed": True}


def _create_match(a: int, b: int) -> int:
    low, high = _pair(a, b)
    db.execute("INSERT OR IGNORE INTO matches (user_a_id, user_b_id)"
               " VALUES (?, ?)", (low, high))
    return int(db.scalar(
        "SELECT id FROM matches WHERE user_a_id = ? AND user_b_id = ?",
        (low, high)))


def _drop_match(a: int, b: int) -> None:
    low, high = _pair(a, b)
    db.execute("DELETE FROM matches WHERE user_a_id = ? AND user_b_id = ?",
               (low, high))


def existing_match_id(a: int, b: int) -> Optional[int]:
    low, high = _pair(a, b)
    return db.scalar("SELECT id FROM matches WHERE user_a_id = ? AND user_b_id = ?",
                     (low, high))


# --- "who liked you" -------------------------------------------------------
def _admirer_sql(where_extra: str) -> str:
    return (
        "SELECT u.id AS user_id, p.id AS profile_id, p.display_name, p.birthdate,"
        "       p.headline, p.photo, l.city, l.latitude, l.longitude,"
        "       lk.created_at AS liked_at"
        "  FROM likes lk"
        "  JOIN users u    ON u.id = lk.from_user_id"
        "  JOIN profiles p ON p.user_id = u.id"
        "  LEFT JOIN locations l ON l.user_id = u.id AND l.is_current = 1"
        " WHERE lk.to_user_id = ? AND lk.is_like = 1 AND p.is_complete = 1"
        + where_extra +
        " ORDER BY lk.created_at DESC, lk.id DESC")


def likes_received(user_id: int, pending_only: bool = True) -> List[Dict]:
    """People who liked you. `pending_only` hides ones you've already answered."""
    extra = (" AND NOT EXISTS (SELECT 1 FROM likes mine"
             " WHERE mine.from_user_id = ? AND mine.to_user_id = lk.from_user_id)"
             ) if pending_only else ""
    params = (user_id, user_id) if pending_only else (user_id,)
    rows = db.query(_admirer_sql(extra), params)
    if not rows:
        return []
    # Resolve the viewer once and every admirer's interests in one query,
    # rather than re-reading both for each row.
    viewer = _viewer_context(user_id)
    by_profile = models.interest_names_for_profiles(
        [r["profile_id"] for r in rows])
    return [_decorate(user_id, row, viewer, by_profile) for row in rows]


def pending_likes_count(user_id: int) -> int:
    return int(db.scalar(
        "SELECT COUNT(*) FROM likes lk"
        "  JOIN profiles p ON p.user_id = lk.from_user_id"
        " WHERE lk.to_user_id = ? AND lk.is_like = 1 AND p.is_complete = 1"
        "   AND NOT EXISTS (SELECT 1 FROM likes mine"
        "        WHERE mine.from_user_id = ? AND mine.to_user_id = lk.from_user_id)",
        (user_id, user_id)) or 0)


def _viewer_context(viewer_id: int) -> Dict:
    """The viewer's own location and interests - identical for every row."""
    profile = models.profile_for_user(viewer_id)
    return {
        "location": models.current_location(viewer_id),
        "interests": set(models.profile_interest_names(profile["id"]))
                     if profile else set(),
    }


def _decorate(viewer_id: int, row, viewer: Optional[Dict] = None,
              interests_by_profile: Optional[Dict] = None) -> Dict:
    """Attach age, distance and shared interests to a person row.

    `viewer` and `interests_by_profile` let a caller decorating a whole page
    resolve both once up front; omitting them falls back to per-row lookups.
    """
    from .geo import format_distance, haversine_km
    if viewer is None:
        viewer = _viewer_context(viewer_id)
    me_location = viewer["location"]

    distance = None
    if me_location and row["latitude"] is not None:
        distance = haversine_km(me_location["latitude"], me_location["longitude"],
                                row["latitude"], row["longitude"])

    mine = viewer["interests"]
    if interests_by_profile is None:
        theirs = models.profile_interest_names(row["profile_id"])
    else:
        theirs = interests_by_profile.get(row["profile_id"], [])
    shared = sorted(mine & set(theirs))

    return {
        "user_id": row["user_id"],
        "profile_id": row["profile_id"],
        "display_name": row["display_name"],
        "age": models.age_from_birthdate(row["birthdate"]),
        "headline": row["headline"],
        "photo": row["photo"],
        "city": row["city"] or "",
        "distance_km": distance,
        "distance_label": format_distance(distance) if distance is not None
                          else "Distance unknown",
        "interests": theirs,
        "shared_interests": shared,
        "shared_count": len(shared),
        "liked_at": row["liked_at"] if "liked_at" in row.keys() else None,
    }


# --- matches ---------------------------------------------------------------
def matches_for(user_id: int) -> List[Dict]:
    # One query for the lot. The profile join replaces a per-row lookup (and,
    # being inner, drops matches whose profile has gone - what the old
    # `if other is None: continue` did); the last message and unread count
    # ride along as correlated subqueries against idx_messages_thread and
    # idx_messages_unread.
    rows = db.query(
        "SELECT m.id AS match_id, m.created_at, p.user_id AS other_id,"
        "       p.display_name, p.birthdate, p.photo, p.headline,"
        "       (SELECT body FROM messages x WHERE x.match_id = m.id"
        "         ORDER BY x.id DESC LIMIT 1) AS last_message,"
        "       (SELECT sender_id FROM messages x WHERE x.match_id = m.id"
        "         ORDER BY x.id DESC LIMIT 1) AS last_sender_id,"
        "       (SELECT created_at FROM messages x WHERE x.match_id = m.id"
        "         ORDER BY x.id DESC LIMIT 1) AS last_at,"
        "       (SELECT COUNT(*) FROM messages x WHERE x.match_id = m.id"
        "         AND x.sender_id <> ? AND x.read_at IS NULL) AS unread"
        "  FROM matches m"
        "  JOIN profiles p ON p.user_id ="
        "       CASE WHEN m.user_a_id = ? THEN m.user_b_id ELSE m.user_a_id END"
        " WHERE m.user_a_id = ? OR m.user_b_id = ?"
        " ORDER BY m.created_at DESC, m.id DESC",
        (user_id, user_id, user_id, user_id))

    out = []
    for row in rows:
        out.append({
            "match_id": row["match_id"],
            "created_at": row["created_at"],
            "user_id": row["other_id"],
            "display_name": row["display_name"],
            "age": models.age_from_birthdate(row["birthdate"]),
            "photo": row["photo"],
            "headline": row["headline"],
            "last_message": row["last_message"],
            "last_sender_id": row["last_sender_id"],
            "last_at": row["last_at"],
            "unread": int(row["unread"] or 0),
        })
    # Most recently active conversations first; brand-new matches count as active.
    out.sort(key=lambda m: (m["last_at"] or m["created_at"]), reverse=True)
    return out


def match_count(user_id: int) -> int:
    return int(db.scalar(
        "SELECT COUNT(*) FROM matches WHERE user_a_id = ? OR user_b_id = ?",
        (user_id, user_id)) or 0)


def get_match(match_id: int, user_id: int) -> Optional[Dict]:
    """Returns the match only if `user_id` is one of its two members."""
    row = db.query_one(
        "SELECT * FROM matches WHERE id = ? AND (user_a_id = ? OR user_b_id = ?)",
        (match_id, user_id, user_id))
    if row is None:
        return None
    other_id = row["user_b_id"] if row["user_a_id"] == user_id else row["user_a_id"]
    other = models.profile_by_user_id(other_id)
    if other is None:
        return None
    return {"match_id": row["id"], "created_at": row["created_at"],
            "other_id": other_id, "other": other}


# --- chat ------------------------------------------------------------------
def messages_for(match_id: int, after_id: int = 0, limit: int = 300) -> List[Dict]:
    rows = db.query(
        "SELECT id, sender_id, body, created_at, read_at FROM messages"
        " WHERE match_id = ? AND id > ? ORDER BY id LIMIT ?",
        (match_id, after_id, limit))
    return [dict(r) for r in rows]


def send_message(match_id: int, sender_id: int, body: str) -> Optional[Dict]:
    body = (body or "").strip()
    if not body:
        return None
    body = body[:MAX_MESSAGE_LEN]
    cur = db.execute(
        "INSERT INTO messages (match_id, sender_id, body) VALUES (?, ?, ?)",
        (match_id, sender_id, body))
    row = db.query_one("SELECT id, sender_id, body, created_at FROM messages"
                       " WHERE id = ?", (cur.lastrowid,))
    return dict(row) if row else None


def mark_read(match_id: int, reader_id: int) -> None:
    db.execute(
        "UPDATE messages SET read_at = datetime('now')"
        " WHERE match_id = ? AND sender_id <> ? AND read_at IS NULL",
        (match_id, reader_id))


def unread_total(user_id: int) -> int:
    return int(db.scalar(
        "SELECT COUNT(*) FROM messages m JOIN matches mt ON mt.id = m.match_id"
        " WHERE (mt.user_a_id = ? OR mt.user_b_id = ?)"
        "   AND m.sender_id <> ? AND m.read_at IS NULL",
        (user_id, user_id, user_id)) or 0)
