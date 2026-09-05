"""A very small request/response + routing layer over http.server.

Deliberately tiny: enough structure to keep views readable, no framework.
"""
from __future__ import annotations

import json
import re
import urllib.parse
from http.cookies import SimpleCookie
from typing import Callable, Dict, List, Optional, Tuple

from . import config


class Request:
    def __init__(self, method, path, query, headers, body, client_addr):
        self.method = method
        self.path = path
        self.query = query              # Dict[str, List[str]]
        self.headers = headers
        self.body = body                # bytes
        self.client_addr = client_addr
        self.params: Dict[str, str] = {}
        self.session = None             # sqlite3.Row or None
        self.user = None                # dict or None
        self._form: Optional[Dict[str, List[str]]] = None

    # -- query / form access ------------------------------------------------
    def get(self, name: str, default: str = "") -> str:
        vals = self.query.get(name)
        return vals[0] if vals else default

    def get_int(self, name: str, default: int) -> int:
        try:
            return int(self.get(name, ""))
        except (TypeError, ValueError):
            return default

    @property
    def form(self) -> Dict[str, List[str]]:
        if self._form is None:
            ctype = self.headers.get("Content-Type", "")
            if ctype.startswith("application/json"):
                try:
                    data = json.loads(self.body.decode("utf-8") or "{}")
                except ValueError:
                    data = {}
                self._form = {k: [v if isinstance(v, str) else json.dumps(v)]
                              for k, v in (data or {}).items()}
            else:
                self._form = urllib.parse.parse_qs(
                    self.body.decode("utf-8", "replace"), keep_blank_values=True)
        return self._form

    def field(self, name: str, default: str = "") -> str:
        vals = self.form.get(name)
        return vals[0].strip() if vals else default

    def field_list(self, name: str) -> List[str]:
        return [v for v in self.form.get(name, []) if v != ""]

    def json_body(self) -> dict:
        try:
            return json.loads(self.body.decode("utf-8") or "{}")
        except ValueError:
            return {}

    @property
    def cookies(self) -> SimpleCookie:
        jar = SimpleCookie()
        raw = self.headers.get("Cookie")
        if raw:
            try:
                jar.load(raw)
            except Exception:
                pass
        return jar

    def cookie(self, name: str) -> Optional[str]:
        morsel = self.cookies.get(name)
        return morsel.value if morsel else None

    @property
    def wants_json(self) -> bool:
        return "application/json" in self.headers.get("Accept", "")


class Response:
    def __init__(self, body=b"", status=200, content_type="text/html; charset=utf-8",
                 headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.body = body
        self.status = status
        self.headers: List[Tuple[str, str]] = list(headers or [])
        if content_type:
            self.headers.append(("Content-Type", content_type))

    def set_cookie(self, name, value, max_age=None, http_only=True, path="/"):
        parts = ["%s=%s" % (name, value), "Path=%s" % path, "SameSite=Lax"]
        if max_age is not None:
            parts.append("Max-Age=%d" % max_age)
        if http_only:
            parts.append("HttpOnly")
        self.headers.append(("Set-Cookie", "; ".join(parts)))
        return self

    def clear_cookie(self, name, path="/"):
        return self.set_cookie(name, "", max_age=0, path=path)


def html(markup: str, status: int = 200) -> Response:
    return Response(markup, status=status)


def redirect(location: str, status: int = 303) -> Response:
    return Response(b"", status=status, content_type=None,
                    headers=[("Location", location)])


def json_response(payload, status: int = 200) -> Response:
    return Response(json.dumps(payload), status=status,
                    content_type="application/json; charset=utf-8")


class Router:
    def __init__(self):
        self.routes: List[Tuple[str, "re.Pattern", Callable]] = []

    def add(self, method: str, pattern: str, handler: Callable) -> None:
        regex = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern)
        self.routes.append((method.upper(), re.compile("^%s$" % regex), handler))

    def route(self, method: str, pattern: str):
        def decorator(fn):
            self.add(method, pattern, fn)
            return fn
        return decorator

    def get(self, pattern):
        return self.route("GET", pattern)

    def post(self, pattern):
        return self.route("POST", pattern)

    def resolve(self, method: str, path: str):
        """Returns (handler, params) or (None, allowed_methods)."""
        allowed = set()
        for verb, regex, handler in self.routes:
            match = regex.match(path)
            if match:
                if verb == method:
                    return handler, match.groupdict()
                allowed.add(verb)
        return None, allowed


def error_page(status: int, title: str, message: str) -> Response:
    from .templates import minimal_page
    return html(minimal_page(status, title, message), status=status)
