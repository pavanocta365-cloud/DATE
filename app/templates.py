"""Server-rendered HTML. Plain functions returning strings - no template engine."""
from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Iterable, List, Optional

from . import config


def esc(value) -> str:
    return escape("" if value is None else str(value), quote=True)


def attr(name: str, value) -> str:
    return "" if value in (None, "", False) else ' %s="%s"' % (name, esc(value))


def layout(title: str, body: str, user: Optional[dict] = None,
           active: str = "", head_extra: str = "", body_class: str = "") -> str:
    return (
        "<!doctype html><html lang=\"en\"><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>%(title)s &middot; %(app)s</title>"
        "<link rel=\"stylesheet\" href=\"/static/styles.css\">"
        "<link rel=\"icon\" href=\"/static/favicon.svg\">"
        "%(head)s"
        "</head><body%(bodyclass)s>"
        "%(nav)s"
        "<main class=\"shell\">%(body)s</main>"
        "<footer class=\"foot\">%(app)s &mdash; MVP build. Demo data only.</footer>"
        "<script src=\"/static/app.js\" defer></script>"
        "</body></html>"
    ) % {
        "title": esc(title),
        "app": esc(config.APP_NAME),
        "head": head_extra,
        "bodyclass": attr("class", body_class),
        "nav": navbar(user, active),
        "body": body,
    }


def relative_time(stamp) -> str:
    """'just now' / '20m ago' / '3d ago' from a SQLite UTC timestamp."""
    if not stamp:
        return ""
    try:
        when = datetime.strptime(str(stamp)[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc)
    except ValueError:
        return str(stamp)
    seconds = (datetime.now(timezone.utc) - when).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return "%dm ago" % (seconds // 60)
    if seconds < 86400:
        return "%dh ago" % (seconds // 3600)
    if seconds < 86400 * 7:
        return "%dd ago" % (seconds // 86400)
    return when.strftime("%d %b")


def navbar(user: Optional[dict], active: str) -> str:
    if user:
        links = [("/discover", "Discover", "discover", 0),
                 ("/likes", "Likes you", "likes", user.get("pending_likes", 0)),
                 ("/matches", "Matches", "matches", user.get("unread", 0)),
                 ("/profile", "My profile", "profile", 0)]
        items = "".join(
            '<a class="navlink%s" href="%s">%s%s</a>'
            % (" is-active" if key == active else "", href, esc(label),
               ('<span class="nav-badge">%d</span>' % count) if count else "")
            for href, label, key, count in links)
        right = (
            '<form method="post" action="/logout" class="inline">'
            '<input type="hidden" name="csrf" value="%s">'
            '<button class="navlink navbtn" type="submit">Log out</button>'
            "</form>" % esc(user.get("csrf", ""))
        )
    else:
        items = ""
        right = ('<a class="navlink" href="/login">Log in</a>'
                 '<a class="btn btn-sm" href="/signup">Sign up</a>')
    return (
        '<header class="nav"><div class="nav-inner">'
        '<a class="brand" href="/"><span class="brand-dot"></span>%s</a>'
        '<nav class="nav-links">%s</nav>'
        '<div class="nav-right">%s</div>'
        "</div></header>"
    ) % (esc(config.APP_NAME), items, right)


def minimal_page(status: int, title: str, message: str) -> str:
    body = ('<section class="panel narrow center">'
            '<p class="eyebrow">Error %d</p><h1>%s</h1><p class="muted">%s</p>'
            '<p><a class="btn" href="/">Back to start</a></p></section>'
            % (status, esc(title), esc(message)))
    return layout(title, body)


# --- small components ------------------------------------------------------
def flash(message: str, kind: str = "info") -> str:
    if not message:
        return ""
    return '<div class="flash flash-%s">%s</div>' % (esc(kind), esc(message))


def errors_block(errors: Iterable[str]) -> str:
    errors = [e for e in errors if e]
    if not errors:
        return ""
    items = "".join("<li>%s</li>" % esc(e) for e in errors)
    return '<div class="flash flash-error"><ul class="bare">%s</ul></div>' % items


def field(label: str, name: str, value: str = "", type_: str = "text",
          placeholder: str = "", required: bool = False, hint: str = "",
          maxlength: Optional[int] = None, extra: str = "") -> str:
    return (
        '<label class="field"><span class="field-label">%s</span>'
        '<input class="input" type="%s" name="%s" value="%s"%s%s%s%s>%s</label>'
    ) % (
        esc(label), esc(type_), esc(name), esc(value),
        attr("placeholder", placeholder),
        " required" if required else "",
        attr("maxlength", maxlength),
        (" " + extra) if extra else "",
        '<span class="hint">%s</span>' % esc(hint) if hint else "",
    )


def textarea(label: str, name: str, value: str = "", rows: int = 4,
             placeholder: str = "", maxlength: Optional[int] = None,
             hint: str = "") -> str:
    return (
        '<label class="field"><span class="field-label">%s</span>'
        '<textarea class="input" name="%s" rows="%d"%s%s>%s</textarea>%s</label>'
    ) % (
        esc(label), esc(name), rows,
        attr("placeholder", placeholder), attr("maxlength", maxlength),
        esc(value),
        '<span class="hint">%s</span>' % esc(hint) if hint else "",
    )


def select(label: str, name: str, options, value: str = "", hint: str = "") -> str:
    opts = "".join(
        '<option value="%s"%s>%s</option>'
        % (esc(val), " selected" if str(val) == str(value) else "", esc(text))
        for val, text in options)
    return (
        '<label class="field"><span class="field-label">%s</span>'
        '<select class="input" name="%s">%s</select>%s</label>'
    ) % (esc(label), esc(name), opts,
         '<span class="hint">%s</span>' % esc(hint) if hint else "")


def chip(text: str, shared: bool = False) -> str:
    return '<span class="chip%s">%s</span>' % (" chip-shared" if shared else "",
                                               esc(text))


def chips(names: Iterable[str], shared: Optional[set] = None, limit: int = 0) -> str:
    names = list(names)
    shown = names[:limit] if limit else names
    out = "".join(chip(n, bool(shared and n in shared)) for n in shown)
    if limit and len(names) > limit:
        out += '<span class="chip chip-more">+%d</span>' % (len(names) - limit)
    return '<div class="chips">%s</div>' % out


def csrf_input(user: Optional[dict]) -> str:
    return '<input type="hidden" name="csrf" value="%s">' % esc(
        (user or {}).get("csrf", ""))


def avatar(src: str, name: str, size: str = "") -> str:
    cls = "avatar" + (" avatar-" + size if size else "")
    if not src:
        return '<div class="%s avatar-empty">%s</div>' % (cls, esc((name or "?")[:1].upper()))
    return '<img class="%s" src="%s" alt="%s" loading="lazy">' % (
        cls, esc(src), esc(name))
