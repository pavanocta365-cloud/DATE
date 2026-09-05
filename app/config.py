"""Runtime configuration. Everything has a working default."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
STATIC_DIR = APP_DIR / "static"
DATA_DIR = Path(os.environ.get("NEARBY_DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "nearby.db"
SCHEMA_PATH = APP_DIR / "schema.sql"

APP_NAME = "Nearby"
SESSION_COOKIE = "nearby_session"
SESSION_TTL_DAYS = 14

# Discovery defaults
DEFAULT_RADIUS_KM = 25
RADIUS_CHOICES = [5, 10, 25, 50, 100, 250]
MAX_RADIUS_KM = 250
DISCOVER_PAGE_SIZE = 24

# Ranking weights (must sum to 1.0)
W_PROXIMITY = 0.55
W_INTERESTS = 0.45

# Profile rules
MIN_AGE = 18
MAX_AGE = 99
MIN_INTERESTS = 3
MAX_INTERESTS = 10
MAX_PHOTO_BYTES = 3 * 1024 * 1024      # 3 MB data URI ceiling
MAX_REQUEST_BYTES = 8 * 1024 * 1024

SEED_PASSWORD = "password123"          # every demo profile shares this

# Demo behaviour: when a real user first completes their profile, a few nearby
# demo profiles "like" them so the Likes-you page and the match -> chat flow are
# reachable from a single account. Set to 0 to turn this off entirely.
SEED_INCOMING_LIKES = 6
