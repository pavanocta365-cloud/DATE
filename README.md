# Nearby

A location-based dating web app. The full MVP loop: register → build a profile →
see relevant people nearby → like/pass → match → chat.

## Run it

```
cmake -P CMakeLists.txt
```

Then open <http://localhost:8000>.

That single command finds Python, creates and seeds the SQLite database on the
first run, and starts the server. There is **nothing to install** — the app runs
on the Python standard library alone (Python 3.8+). No venv, no pip, no network.

### Other commands

```
cmake -DPORT=9000   -P CMakeLists.txt    # different port
cmake -DHOST=0.0.0.0 -P CMakeLists.txt   # expose on your LAN
cmake -DACTION=seed  -P CMakeLists.txt   # build + seed the DB, don't serve
cmake -DACTION=reset -P CMakeLists.txt   # wipe the DB, reseed, then serve
cmake -DACTION=check -P CMakeLists.txt   # 64-assertion end-to-end self-test
```

The conventional out-of-source flow works too:

```
cmake -S . -B build && cmake --build build --target run
```

## Signing in

The database is seeded with **136 demo profiles**, plus ~1,100 likes, ~140
matches and ~75 messages between them. Any demo email works with the password
`password123` — the startup banner prints one to copy.

Accounts with plenty to look at:

| account | waiting likes | matches |
|---|---|---|
| `kabir.sethi@example.com` | 5 | 3 |
| `ishaan.sharma@example.com` | 4 | 3 |
| `maya.menon@example.com` | 5 | 1 |

Or **create your own account** — set your city to **Bengaluru** (where most demo
profiles are) and a handful of nearby profiles will like you, so Likes-you and
the match → chat flow are reachable from a single account. That behaviour is
`SEED_INCOMING_LIKES` in `app/config.py`; set it to `0` to switch it off.

To drive a real two-sided conversation, log in as two different accounts in two
browser profiles (or one normal + one incognito window), like each other, and
chat. Messages poll every 4 seconds, so both windows update on their own.

## The core loop

1. **Register** — email + password. Sessions are server-side rows keyed by an
   opaque cookie token; only a SHA-256 of the token is stored.
2. **Build a profile** — photo, name, date of birth, how you identify, who you
   want to see, a headline, a bio, a discovery radius, and at least 3 interests.
   Set a location by picking a city or tapping *Use my current location*.
3. **Discover** — everyone inside your radius, ranked best-first.
4. **Like or pass** — each decision is final until you change it, and the person
   drops out of your feed either way.
5. **Match** — when two people like each other, a match is created and a chat
   opens. Passing on a match tears it down, chat included.
6. **Chat** — one thread per match, with unread counts in the nav.

A profile stays hidden from other people's feeds until it's complete. The
profile page always lists exactly what's still missing.

## How matching works

`app/matching.py`, in five steps:

1. **Bounding box** — a cheap lat/lon window in SQL narrows the candidate set
   using an index before any trigonometry runs.
2. **Exact distance** — haversine, registered as a SQLite function from Python
   so we don't depend on SQLite being built with the optional math functions.
3. **Filters** — mutual gender preference, complete profiles only, never
   yourself, and never anyone you have already liked or passed.
4. **Score** each survivor:

   ```
   proximity  = 1 - sqrt(distance / radius)        # 1.0 next door, 0.0 at the edge
   interests  = shared / sqrt(len(mine) * len(theirs))   # cosine-style overlap
   score      = 0.55 * proximity + 0.45 * interests
   ```

   The `sqrt` on proximity keeps 2 km meaningfully better than 8 km even when
   the radius is wide. The cosine-style interest term rewards genuine overlap
   without penalising people who list a lot of interests. If you haven't picked
   any interests yet, ranking falls back to pure distance.
5. **Sort** by score, then by distance as the tie-break.

Weights live in `app/config.py` (`W_PROXIMITY`, `W_INTERESTS`).

## Schema

`app/schema.sql`

| table | purpose |
|---|---|
| `users` | credentials only — email, password hash |
| `sessions` | server-side login sessions, with a per-session CSRF token |
| `profiles` | 1:1 with users; what other people see |
| `interests` | shared catalogue (51 interests, 7 categories) |
| `profile_interests` | many-to-many join |
| `locations` | append-only history; the newest row per user is `is_current` |
| `likes` | one standing like/pass decision per ordered pair |
| `matches` | created on mutual like; `user_a_id < user_b_id` so a pair is unique |
| `messages` | chat, one thread per match, with `read_at` for unread counts |

Locations are append-only rather than a column on `profiles`, so movement over
time is already recorded.

## Layout

```
CMakeLists.txt        single-command entry point (dual mode: script + project)
run.py                CLI: run | seed | reset | check
app/
  config.py           all tunables
  schema.sql          the database
  db.py               connections (one per thread), query helpers
  security.py         scrypt hashing, sessions, CSRF
  geo.py              haversine, bounding box, city catalogue
  models.py           users, profiles, interests, locations
  matching.py         the discovery ranking
  interactions.py     likes, matches, chat
  seed.py             136 deterministic demo profiles + their interactions
  avatars.py          offline SVG avatars (no network, no image files)
  web.py              tiny request/response/router layer
  templates.py        HTML as plain functions
  server.py           dispatch, session loading, CSRF enforcement
  selftest.py         end-to-end HTTP test
  views/              auth.py, profile.py, discover.py, interactions.py, assets.py
  static/             styles.css, app.js
```

## Notes

- Passwords are hashed with **scrypt** (n=16384), falling back to PBKDF2-SHA256
  if scrypt isn't available in the local OpenSSL build.
- Every `POST` is CSRF-checked against a per-session token.
- Photos are resized to 640px in the browser and stored as data URIs, so there
  is no upload directory to manage. Demo profiles use generated SVG avatars.
- The forms all work without JavaScript; `app.js` only adds the interest cap,
  the photo resizer and the geolocation button.
- `http.server` is fine for this demo. For real traffic, put the app behind a
  proper WSGI/ASGI server.

## Interaction rules worth knowing

- A like/pass is one **standing decision** per ordered pair — re-deciding
  updates the existing row rather than stacking up history.
- A match exists **exactly when** both sides have `is_like = 1`. There is no way
  to have a match without two likes, or two likes without a match.
- `user_a_id < user_b_id` is enforced by a `CHECK`, so the same pair can never
  produce two match rows regardless of who likes first.
- Chat is reachable only through `get_match(match_id, user_id)`, which returns
  nothing unless the caller is one of the two members — verified by the
  self-test.
- Passing on someone you matched with deletes the match, and `ON DELETE CASCADE`
  takes the messages with it.

## Not built

Verification and blocking are still out of scope.
