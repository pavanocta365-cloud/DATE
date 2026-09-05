"""End-to-end smoke test: drives the real server over HTTP.

    cmake -DACTION=check -P CMakeLists.txt
"""
from __future__ import annotations

import json
import re
import sys
import threading
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from http.server import ThreadingHTTPServer

from . import config, db, interactions, models, security, server


class Client:
    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar()),
            NoRedirect())

    def get(self, path):
        return self._open(urllib.request.Request(self.base + path))

    def post(self, path, fields):
        import urllib.parse
        data = urllib.parse.urlencode(fields, doseq=True).encode()
        req = urllib.request.Request(
            self.base + path, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        return self._open(req)

    def post_json(self, path, payload, csrf):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "X-CSRF-Token": csrf})
        return self._open(req)

    def _open(self, req):
        try:
            resp = self.opener.open(req, timeout=10)
            return resp.getcode(), resp.read().decode("utf-8", "replace"), resp.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace"), exc.headers


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _csrf(body):
    m = re.search(r'name="csrf" value="([^"]+)"', body)
    return m.group(1) if m else ""


PASSED, FAILED = [], []


def check(label, condition, detail=""):
    (PASSED if condition else FAILED).append(label)
    mark = "  ok  " if condition else "  FAIL"
    print("%s  %s%s" % (mark, label, ("  <- " + detail) if detail and not condition else ""))


def run() -> int:
    server.build_router()
    db.init_db()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    httpd.daemon_threads = True
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % port
    print("\nNearby self-test against %s\n" % base)

    try:
        c = Client(base)

        code, body, _ = c.get("/")
        check("landing page renders", code == 200 and "actually nearby" in body,
              "status=%s" % code)

        code, _, _ = c.get("/discover")
        check("discovery requires login", code == 303)

        email = "selftest+%d@example.com" % port
        code, body, _ = c.get("/signup")
        check("signup form renders", code == 200)

        code, body, hdr = c.post("/signup", {"email": email, "password": "hunter2pass"})
        check("signup redirects to profile",
              code == 303 and "/profile" in (hdr.get("Location") or ""),
              "status=%s loc=%s" % (code, hdr.get("Location")))

        code, body, _ = c.get("/profile")
        check("profile editor renders for new user", code == 200 and "Your profile" in body)
        token = _csrf(body)
        check("csrf token present in form", bool(token))

        anon = Client(base)
        code, body, _ = anon.post("/signup", {"email": email,
                                              "password": "hunter2pass"})
        check("duplicate email rejected", code == 400 and "already registered" in body,
              "status=%s" % code)
        code, _, hdr = c.post("/signup", {"email": "other@example.com",
                                          "password": "hunter2pass"})
        check("signup while logged in redirects instead of creating a second account",
              code == 303 and not models.email_taken("other@example.com"))

        user = models.user_by_email(email)
        profile = models.profile_for_user(user["id"])
        check("profile row auto-created on signup", profile is not None)
        check("new profile is not discoverable yet",
              profile is not None and profile["is_complete"] == 0)

        interest_ids = [r["id"] for r in db.query(
            "SELECT id FROM interests WHERE slug IN "
            "('coffee','running','film','coding','travel')")]
        check("interest catalogue seeded", len(interest_ids) == 5,
              "found %d" % len(interest_ids))

        code, body, hdr = c.post("/profile", {
            "csrf": token, "display_name": "Self Test", "birthdate": "1994-03-15",
            "gender": "man", "interested_in": "women", "headline": "Testing things",
            "bio": "Automated.", "city": "Bengaluru", "radius_km": "25",
            "interests": [str(i) for i in interest_ids],
        })
        check("profile save redirects to discovery",
              code == 303 and "/discover" in (hdr.get("Location") or ""),
              "status=%s loc=%s body=%s" % (code, hdr.get("Location"), body[:200]))

        profile = models.profile_for_user(user["id"])
        check("profile now discoverable", profile["is_complete"] == 1)
        check("interests persisted",
              len(models.profile_interest_ids(profile["id"])) == 5)
        check("location persisted",
              models.current_location(user["id"]) is not None)

        code, body, _ = c.post("/profile", {
            "csrf": token, "display_name": "Self Test", "birthdate": "2020-01-01",
            "gender": "man", "interested_in": "women", "city": "Bengaluru",
            "radius_km": "25", "interests": [str(interest_ids[0])],
        })
        check("under-18 birthdate rejected", code == 400 and "at least 18" in body)

        code, body, _ = c.post("/profile", {"display_name": "No Token"})
        check("POST without csrf token is refused", code == 403)

        code, body, _ = c.get("/discover")
        check("discovery feed renders", code == 200 and "Nearby" in body)
        check("feed shows candidates", "class=\"card\"" in body,
              "no cards rendered")
        check("feed reports shared interests", "shared" in body)

        code, body, _ = c.get("/discover?radius=5")
        check("radius filter honoured", code == 200 and "5 km" in body)

        from . import matching
        wide = matching.discover(user["id"], radius_km=100)
        tight = matching.discover(user["id"], radius_km=5)
        check("wider radius returns >= candidates",
              wide["total"] >= tight["total"],
              "%d vs %d" % (wide["total"], tight["total"]))
        check("all candidates inside radius",
              all(x["distance_km"] <= 25.001
                  for x in matching.discover(user["id"], radius_km=25)["candidates"]))
        check("candidates respect gender preference",
              all(x["gender"] == "woman" for x in wide["candidates"]))
        check("self never appears in own feed",
              all(x["user_id"] != user["id"] for x in wide["candidates"]))
        scores = [x["score"] for x in wide["candidates"]]
        check("feed is sorted by match score", scores == sorted(scores, reverse=True))

        if wide["candidates"]:
            other = wide["candidates"][0]["user_id"]
            code, body, _ = c.get("/people/%d" % other)
            check("can view another profile", code == 200)
            code, body, _ = c.get("/people/999999")
            check("missing profile 404s", code == 404)

        code, body, _ = c.post_json("/api/location",
                                    {"latitude": 19.076, "longitude": 72.8777}, token)
        check("geolocation endpoint saves coordinates",
              code == 200 and json.loads(body).get("ok") is True)
        loc = models.current_location(user["id"])
        check("new location became current", loc and loc["city"] == "Mumbai")
        check("location history kept",
              (db.scalar("SELECT COUNT(*) FROM locations WHERE user_id = ?",
                         (user["id"],)) or 0) >= 2)

        code, body, _ = c.get("/discover")
        check("feed follows the user to a new city",
              code == 200 and ("Mumbai" in body or "Nobody within" in body))

        # ---- likes, matches, chat ----------------------------------------
        wide = matching.discover(user["id"], radius_km=250)
        target = wide["candidates"][0]["user_id"]

        code, _, hdr = c.post("/decide", {"csrf": token, "user_id": str(target),
                                          "action": "pass", "back": "/discover"})
        check("pass is recorded", code == 303
              and interactions.decision(user["id"], target) == 0)
        after = matching.discover(user["id"], radius_km=250)
        check("passed profile leaves the feed",
              target not in [x["user_id"] for x in after["candidates"]])

        target2 = after["candidates"][0]["user_id"]
        code, _, hdr = c.post("/decide", {"csrf": token, "user_id": str(target2),
                                          "action": "like", "back": "/discover"})
        check("like is recorded", code == 303
              and interactions.decision(user["id"], target2) == 1)
        check("one-sided like is not a match",
              interactions.existing_match_id(user["id"], target2) is None)

        interactions.record_decision(target2, user["id"], True)
        match_id = interactions.existing_match_id(user["id"], target2)
        check("mutual like creates a match", match_id is not None)
        check("match is not duplicated on repeat likes",
              interactions.record_decision(target2, user["id"], True)["match_id"]
              == match_id)

        admirer = wide["candidates"][2]["user_id"]
        interactions.record_decision(admirer, user["id"], True)
        code, body, _ = c.get("/likes")
        check("who-liked-you page renders", code == 200 and "Likes you" in body)
        check("admirer appears on likes page", ('/people/%d' % admirer) in body,
              "admirer %d missing" % admirer)
        check("pending like count is right",
              interactions.pending_likes_count(user["id"]) >= 1)
        check("already-answered likes are not pending",
              target2 not in [p["user_id"] for p in
                              interactions.likes_received(user["id"])])

        code, body, _ = c.get("/matches")
        check("matches page renders", code == 200 and "Matches" in body)
        check("match is listed", ("/chat/%d" % match_id) in body)

        code, body, _ = c.get("/chat/%d" % match_id)
        check("chat page renders", code == 200 and "chat-log" in body)
        code, body, _ = c.post("/chat/%d" % match_id,
                               {"csrf": token, "body": "Hello from the self-test"})
        check("message sends", code == 303)
        code, body, _ = c.get("/chat/%d" % match_id)
        check("message appears in the thread",
              "Hello from the self-test" in body)

        msgs = interactions.messages_for(match_id)
        check("message stored against the match", len(msgs) == 1
              and msgs[0]["sender_id"] == user["id"])

        code, body, _ = c.post("/chat/%d" % match_id, {"csrf": token, "body": "   "})
        check("empty message rejected",
              code == 200 and "Type something first" in body)

        outsider = db.query_one(
            "SELECT id FROM users WHERE is_demo = 1 AND id NOT IN (?, ?) LIMIT 1",
            (user["id"], target2))
        check("chat is private to its two members",
              interactions.get_match(match_id, outsider["id"]) is None)
        code, _, _ = c.get("/chat/999999")
        check("unknown conversation 404s", code == 404)

        interactions.send_message(match_id, target2, "reply from the other side")
        check("unread counted for the recipient",
              interactions.unread_total(user["id"]) == 1)
        c.get("/chat/%d" % match_id)
        check("opening the chat clears unread",
              interactions.unread_total(user["id"]) == 0)

        code, body, _ = c.get("/api/chat/%d?after=0" % match_id)
        check("chat polling endpoint works",
              code == 200 and len(json.loads(body)["messages"]) == 2)

        code, _, _ = c.post("/decide", {"csrf": token, "user_id": str(target2),
                                        "action": "pass", "back": "/discover"})
        check("passing on a match removes it",
              interactions.existing_match_id(user["id"], target2) is None)
        check("its chat is gone too",
              interactions.get_match(match_id, user["id"]) is None)

        code, _, _ = c.post("/decide", {"csrf": token,
                                        "user_id": str(user["id"]),
                                        "action": "like", "back": "/discover"})
        check("cannot like yourself",
              interactions.decision(user["id"], user["id"]) is None)

        code, _, hdr = c.post("/logout", {"csrf": token})
        check("logout redirects home", code == 303)
        code, _, _ = c.get("/discover")
        check("session destroyed after logout", code == 303)

        c2 = Client(base)
        _, body, _ = c2.get("/login")
        code, _, hdr = c2.post("/login", {"email": email, "password": "wrongpass1"})
        check("bad password rejected", code == 400)
        code, _, hdr = c2.post("/login", {"email": email, "password": "hunter2pass"})
        check("login succeeds with correct password", code == 303)
        code, body, _ = c2.get("/discover")
        check("logged back in", code == 200 and "Nearby" in body)

        code, body, _ = c.get("/static/../schema.sql")
        check("static path traversal blocked", code in (403, 404))
        code, body, _ = c.get("/nope")
        check("unknown route 404s", code == 404)

    finally:
        httpd.shutdown()
        httpd.server_close()
        db.execute("DELETE FROM users WHERE email LIKE 'selftest+%'")
        db.execute("DELETE FROM users WHERE email = 'other@example.com'")

    print("\n%d passed, %d failed\n" % (len(PASSED), len(FAILED)))
    if FAILED:
        for name in FAILED:
            print("  failed: %s" % name)
        return 1
    return 0
