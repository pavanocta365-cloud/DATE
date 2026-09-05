"""Static files and generated avatars."""
from __future__ import annotations

import mimetypes
from pathlib import Path

from .. import config
from ..avatars import render_svg
from ..web import Response, error_page

_CACHE = "public, max-age=3600"


def register(router):
    router.add("GET", "/static/{path}", serve_static)
    router.add("GET", "/avatar/{name}", serve_avatar)
    router.add("GET", "/healthz", lambda req: Response("ok", content_type="text/plain"))


def serve_static(request):
    rel = request.params.get("path", "")
    target = (config.STATIC_DIR / rel).resolve()
    try:
        target.relative_to(config.STATIC_DIR.resolve())
    except ValueError:
        return error_page(403, "Forbidden", "That path isn't allowed.")
    if not target.is_file():
        return error_page(404, "Not found", "No such asset.")
    ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    if ctype.startswith("text/") or ctype in ("application/javascript",
                                              "image/svg+xml"):
        ctype += "; charset=utf-8"
    return Response(target.read_bytes(), content_type=ctype,
                    headers=[("Cache-Control", _CACHE)])


def serve_avatar(request):
    name = request.params.get("name", "")
    if not name.endswith(".svg"):
        return error_page(404, "Not found", "Avatars are served as .svg")
    seed = name[:-4]
    label = request.get("n", "")
    return Response(render_svg(seed, label), content_type="image/svg+xml; charset=utf-8",
                    headers=[("Cache-Control", _CACHE)])
