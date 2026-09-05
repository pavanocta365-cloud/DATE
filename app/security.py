"""Password hashing and server-side session handling."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from . import config, db

# --- password hashing ------------------------------------------------------
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_PBKDF2_ROUNDS = 260000


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def _have_scrypt() -> bool:
    try:
        hashlib.scrypt(b"x", salt=b"y", n=2, r=1, p=1, dklen=16)
        return True
    except Exception:
        return False


_SCRYPT_OK = _have_scrypt()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    if _SCRYPT_OK:
        dk = hashlib.scrypt(password.encode("utf-8"), salt=salt,
                            n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32)
        return "scrypt$%d$%d$%d$%s$%s" % (
            _SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _b64(salt), _b64(dk))
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                             salt, _PBKDF2_ROUNDS, dklen=32)
    return "pbkdf2$%d$%s$%s" % (_PBKDF2_ROUNDS, _b64(salt), _b64(dk))


def verify_password(password: str, stored: str) -> bool:
    try:
        parts = stored.split("$")
        if parts[0] == "scrypt":
            n, r, p, salt_b64, hash_b64 = parts[1:6]
            dk = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt_b64),
                                n=int(n), r=int(r), p=int(p), dklen=32)
        elif parts[0] == "pbkdf2":
            rounds, salt_b64, hash_b64 = parts[1:4]
            dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                     _unb64(salt_b64), int(rounds), dklen=32)
        else:
            return False
        return hmac.compare_digest(dk, _unb64(hash_b64))
    except Exception:
        return False


# --- validation ------------------------------------------------------------
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def email_error(email: str) -> Optional[str]:
    if not email:
        return "Enter your email address."
    if len(email) > 254 or not _EMAIL_RE.match(email):
        return "That doesn't look like a valid email address."
    return None


def password_error(password: str) -> Optional[str]:
    if not password:
        return "Choose a password."
    if len(password) < 8:
        return "Passwords need at least 8 characters."
    if len(password) > 200:
        return "That password is too long."
    return None


# --- sessions --------------------------------------------------------------
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def create_session(user_id: int, user_agent: str = "") -> str:
    """Returns the raw cookie token; only its hash is stored."""
    token = secrets.token_urlsafe(32)
    expires = _utc_now() + timedelta(days=config.SESSION_TTL_DAYS)
    db.execute(
        "INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at, user_agent)"
        " VALUES (?, ?, ?, ?, ?)",
        (_hash_token(token), user_id, secrets.token_urlsafe(24),
         _iso(expires), (user_agent or "")[:200]),
    )
    return token


def load_session(token: Optional[str]):
    if not token:
        return None
    row = db.query_one(
        "SELECT s.token_hash, s.user_id, s.csrf_token, s.expires_at,"
        "       u.email, u.is_demo"
        "  FROM sessions s JOIN users u ON u.id = s.user_id"
        " WHERE s.token_hash = ?",
        (_hash_token(token),),
    )
    if row is None:
        return None
    if row["expires_at"] < _iso(_utc_now()):
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (row["token_hash"],))
        return None
    return row


def destroy_session(token: Optional[str]) -> None:
    if token:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))


def purge_expired_sessions() -> None:
    db.execute("DELETE FROM sessions WHERE expires_at < ?", (_iso(_utc_now()),))


def csrf_ok(session, submitted: str) -> bool:
    if session is None or not submitted:
        return False
    return hmac.compare_digest(str(session["csrf_token"]), str(submitted))
