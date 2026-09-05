-- ---------------------------------------------------------------------------
-- Nearby MVP schema
--   users     : credentials only
--   sessions  : server-side login sessions (opaque cookie token)
--   profiles  : what other people see, 1:1 with users
--   interests : shared catalogue, joined to profiles many-to-many
--   locations : append-only location history, newest row flagged is_current
-- ---------------------------------------------------------------------------

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash  TEXT    NOT NULL,
    is_demo        INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    last_seen_at   TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash   TEXT    PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf_token   TEXT    NOT NULL,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at   TEXT    NOT NULL,
    user_agent   TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS profiles (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    display_name   TEXT    NOT NULL DEFAULT '',
    birthdate      TEXT,                       -- ISO yyyy-mm-dd
    gender         TEXT    NOT NULL DEFAULT '',
    interested_in  TEXT    NOT NULL DEFAULT 'everyone',
    headline       TEXT    NOT NULL DEFAULT '',
    bio            TEXT    NOT NULL DEFAULT '',
    photo          TEXT    NOT NULL DEFAULT '',   -- data: URI, or /avatar/<seed>.svg
    radius_km      INTEGER NOT NULL DEFAULT 25,
    is_complete    INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_profiles_complete ON profiles(is_complete);

CREATE TABLE IF NOT EXISTS interests (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    slug      TEXT NOT NULL UNIQUE,
    name      TEXT NOT NULL,
    category  TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_interests_category ON interests(category, sort_order);

CREATE TABLE IF NOT EXISTS profile_interests (
    profile_id   INTEGER NOT NULL REFERENCES profiles(id)  ON DELETE CASCADE,
    interest_id  INTEGER NOT NULL REFERENCES interests(id) ON DELETE CASCADE,
    PRIMARY KEY (profile_id, interest_id)
);
CREATE INDEX IF NOT EXISTS idx_pi_interest ON profile_interests(interest_id);

CREATE TABLE IF NOT EXISTS locations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    latitude     REAL    NOT NULL,
    longitude    REAL    NOT NULL,
    city         TEXT    NOT NULL DEFAULT '',
    region       TEXT    NOT NULL DEFAULT '',
    country      TEXT    NOT NULL DEFAULT '',
    source       TEXT    NOT NULL DEFAULT 'manual',   -- manual | gps | seed
    is_current   INTEGER NOT NULL DEFAULT 1,
    recorded_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_locations_current
    ON locations(is_current, latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_locations_user
    ON locations(user_id, is_current);

-- ---------------------------------------------------------------------------
-- Interaction layer: likes -> matches -> chat
-- ---------------------------------------------------------------------------

-- One row per decision. is_like = 1 (like) or 0 (pass). A user can only have
-- one standing decision about another user, hence the UNIQUE pair.
CREATE TABLE IF NOT EXISTS likes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    from_user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    to_user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_like       INTEGER NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (from_user_id, to_user_id),
    CHECK (from_user_id <> to_user_id),
    CHECK (is_like IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_likes_inbox  ON likes(to_user_id, is_like);
CREATE INDEX IF NOT EXISTS idx_likes_outbox ON likes(from_user_id, is_like);

-- Created the moment a like becomes mutual. user_a_id is always the smaller id
-- so a pair can only ever produce one row.
CREATE TABLE IF NOT EXISTS matches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_a_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    user_b_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_a_id, user_b_id),
    CHECK (user_a_id < user_b_id)
);
CREATE INDEX IF NOT EXISTS idx_matches_a ON matches(user_a_id);
CREATE INDEX IF NOT EXISTS idx_matches_b ON matches(user_b_id);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id    INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    sender_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    body        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    read_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(match_id, id);
CREATE INDEX IF NOT EXISTS idx_messages_unread ON messages(match_id, sender_id, read_at);
