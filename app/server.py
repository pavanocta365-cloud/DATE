"""HTTP server wiring: dispatch, session loading, CSRF, error handling."""
from __future__ import annotations

import socket
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, db, interactions, models, security
from .web import Request, Response, Router, error_page, redirect

router = Router()


def build_router() -> Router:
    from .views import (assets, auth, discover, interactions,  # noqa: F401
                        profile)
    for module in (assets, auth, profile, discover, interactions):
        module.register(router)
    return router


SAFE_METHODS = ("GET", "HEAD")


class Handler(BaseHTTPRequestHandler):
    server_version = "Nearby/%s" % "0.1"
    protocol_version = "HTTP/1.1"

    # -- plumbing -----------------------------------------------------------
    def log_message(self, fmt, *args):
        sys.stderr.write("  %s %s\n" % (self.address_string(), fmt % args))

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return b""
        if length <= 0:
            return b""
        if length > config.MAX_REQUEST_BYTES:
            return b""
        return self.rfile.read(length)

    def _send(self, response: Response) -> None:
        body = response.body or b""
        self.send_response(response.status)
        for key, value in response.headers:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    # -- dispatch -----------------------------------------------------------
    def _dispatch(self, method: str) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        if len(path) > 1 and path.endswith("/"):
            self._send(redirect(path.rstrip("/") + (
                "?" + parsed.query if parsed.query else ""), status=308))
            return

        request = Request(
            method=method,
            path=path,
            query=urllib.parse.parse_qs(parsed.query, keep_blank_values=True),
            headers=self.headers,
            body=self._read_body() if method not in SAFE_METHODS else b"",
            client_addr=self.client_address[0] if self.client_address else "",
        )

        try:
            self._attach_session(request)
            handler, params = router.resolve(method, path)
            if handler is None:
                if params:  # matched a path but not this verb
                    self._send(error_page(405, "Method not allowed",
                                          "That address doesn't accept %s." % method))
                else:
                    self._send(error_page(404, "Page not found",
                                          "There's nothing at %s." % path))
                return

            if method == "POST" and not self._csrf_ok(request):
                self._send(error_page(
                    403, "Session expired",
                    "Your form token didn't match. Reload the page and try again."))
                return

            request.params = params
            result = handler(request)
            self._send(result if isinstance(result, Response) else Response(result))
        except BrokenPipeError:
            pass
        except Exception:
            traceback.print_exc()
            self._send(error_page(500, "Something went wrong",
                                  "The server hit an unexpected error."))

    def _attach_session(self, request: Request) -> None:
        session = security.load_session(request.cookie(config.SESSION_COOKIE))
        request.session = session
        if session is None:
            return
        user_id = session["user_id"]
        profile = models.profile_for_user(user_id)
        request.user = {
            "id": user_id,
            "email": session["email"],
            "csrf": session["csrf_token"],
            "display_name": profile["display_name"] if profile else "",
            "photo": profile["photo"] if profile else "",
            "is_complete": bool(profile["is_complete"]) if profile else False,
            # Drive the nav badges. Cheap indexed counts.
            "pending_likes": interactions.pending_likes_count(user_id),
            "unread": interactions.unread_total(user_id),
        }

    def _csrf_ok(self, request: Request) -> bool:
        # Endpoints reachable before a session exists carry no token.
        if request.path in ("/login", "/signup"):
            return True
        submitted = request.field("csrf") or request.headers.get("X-CSRF-Token", "")
        return security.csrf_ok(request.session, submitted)

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_POST(self):
        self._dispatch("POST")


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    build_router()
    db.init_db()
    security.purge_expired_sessions()

    try:
        httpd = ThreadingHTTPServer((host, port), Handler)
    except OSError as exc:
        if getattr(exc, "errno", None) in (48, 98):
            print("\nPort %d is already in use. Try:\n"
                  "    cmake -DPORT=%d -P CMakeLists.txt\n" % (port, port + 1))
            raise SystemExit(1)
        raise
    httpd.daemon_threads = True

    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0", "") else host
    print("")
    print("  %s is running" % config.APP_NAME)
    print("  ->  http://%s:%d" % (shown, port))
    print("")
    print("  Demo logins: any seeded address, password '%s'" % config.SEED_PASSWORD)
    sample = db.query_one(
        "SELECT email FROM users WHERE is_demo = 1 ORDER BY id LIMIT 1")
    if sample:
        print("  e.g. %s / %s" % (sample["email"], config.SEED_PASSWORD))
    print("")
    print("  Ctrl-C to stop.")
    print("")
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
