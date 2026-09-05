"""Like / pass, who liked you, matches, and chat."""
from __future__ import annotations

from .. import interactions, models
from ..templates import (avatar, chips, csrf_input, esc, flash, layout,
                         relative_time)
from ..web import error_page, html, json_response, redirect
from .auth import login_required


def register(router):
    router.add("POST", "/decide", login_required(decide))
    router.add("GET", "/likes", login_required(likes_page))
    router.add("GET", "/matches", login_required(matches_page))
    router.add("GET", "/chat/{match_id}", login_required(chat_page))
    router.add("POST", "/chat/{match_id}", login_required(chat_send))
    router.add("GET", "/api/chat/{match_id}", login_required(chat_poll))


def _safe_back(raw: str, fallback: str = "/discover") -> str:
    return raw if raw.startswith("/") and not raw.startswith("//") else fallback


# --- like / pass -----------------------------------------------------------
def decide(request):
    """Handles both the plain form POST and the fetch() from app.js."""
    try:
        target_id = int(request.field("user_id"))
    except (TypeError, ValueError):
        return json_response({"error": "user_id required"}, 400) \
            if request.wants_json else redirect("/discover")

    action = request.field("action")
    if action not in ("like", "pass"):
        return json_response({"error": "action must be like or pass"}, 400) \
            if request.wants_json else redirect("/discover")

    result = interactions.record_decision(
        request.user["id"], target_id, action == "like")

    if request.wants_json:
        payload = {"ok": "error" not in result,
                   "matched": bool(result.get("match_id")),
                   "match_id": result.get("match_id"),
                   "pending_likes": interactions.pending_likes_count(request.user["id"]),
                   "matches": interactions.match_count(request.user["id"])}
        if result.get("match_id"):
            other = models.profile_by_user_id(target_id)
            payload["name"] = other["display_name"] if other else ""
            payload["photo"] = other["photo"] if other else ""
        return json_response(payload, 200 if "error" not in result else 400)

    back = _safe_back(request.field("back"))
    if result.get("match_id"):
        return redirect("%s%smatched=%d" % (
            back, "&" if "?" in back else "?", result["match_id"]))
    return redirect(back)


# --- who liked you ---------------------------------------------------------
def _person_card(person, request, back):
    shared = set(person["shared_interests"])
    ordered = (person["shared_interests"]
               + [i for i in person["interests"] if i not in shared])
    age = (" &middot; %d" % person["age"]) if person["age"] else ""
    return (
        '<article class="card" data-user="%(uid)d">'
        '<a class="card-photo" href="/people/%(uid)d">%(avatar)s</a>'
        '<div class="card-body">'
        '<h3><a href="/people/%(uid)d">%(name)s</a>%(age)s</h3>'
        '<p class="card-meta">%(distance)s%(when)s</p>'
        "%(headline)s%(chips)s"
        "%(actions)s"
        "</div></article>"
    ) % {
        "uid": person["user_id"],
        "avatar": avatar(person["photo"], person["display_name"]),
        "name": esc(person["display_name"]),
        "age": age,
        "distance": esc(person["distance_label"]),
        "when": (" &middot; liked you %s" % esc(relative_time(person["liked_at"])))
                if person.get("liked_at") else "",
        "headline": ('<p class="card-headline">%s</p>' % esc(person["headline"]))
                    if person["headline"] else "",
        "chips": chips(ordered, shared, limit=4),
        "actions": decision_buttons(request, person["user_id"], back,
                                    like_label="Like back"),
    }


def decision_buttons(request, target_id, back, like_label="Like"):
    return (
        '<div class="decide">'
        '<form method="post" action="/decide" class="inline-form">'
        '%(csrf)s<input type="hidden" name="user_id" value="%(uid)d">'
        '<input type="hidden" name="back" value="%(back)s">'
        '<button class="btn btn-ghost btn-sm act" name="action" value="pass" '
        'data-action="pass" data-user="%(uid)d" type="submit">Pass</button>'
        '<button class="btn btn-sm act" name="action" value="like" '
        'data-action="like" data-user="%(uid)d" type="submit">%(like)s</button>'
        "</form></div>"
    ) % {"csrf": csrf_input(request.user), "uid": target_id,
         "back": esc(back), "like": esc(like_label)}


def likes_page(request):
    user = request.user
    pending = interactions.likes_received(user["id"], pending_only=True)
    back = "/likes"

    if pending:
        grid = '<div class="grid">%s</div>' % "".join(
            _person_card(p, request, back) for p in pending)
    else:
        grid = ('<div class="empty"><h3>No new likes yet</h3>'
                '<p class="muted">When someone likes you, they show up here. '
                'Like them back and it becomes a match.</p>'
                '<a class="btn" href="/discover">Browse nearby</a></div>')

    body = (
        '<section class="feed-head"><div>'
        "<h1>Likes you</h1>"
        '<p class="muted">%s</p></div>%s</section>%s'
    ) % (
        ("<strong>%d</strong> %s waiting on your answer"
         % (len(pending), "person" if len(pending) == 1 else "people"))
        if pending else "Nobody new right now.",
        _tabs("likes", user),
        grid,
    )
    return html(layout("Likes you", body, user, "likes"))


# --- matches ---------------------------------------------------------------
def _tabs(active, user):
    counts = {"likes": interactions.pending_likes_count(user["id"]),
              "matches": interactions.match_count(user["id"])}
    items = []
    for key, label, href in (("discover", "Discover", "/discover"),
                             ("likes", "Likes you", "/likes"),
                             ("matches", "Matches", "/matches")):
        badge = ('<span class="tab-badge">%d</span>' % counts[key]) \
            if counts.get(key) else ""
        items.append('<a class="pill%s" href="%s">%s%s</a>'
                     % (" is-active" if key == active else "", href,
                        esc(label), badge))
    return '<div class="pills">%s</div>' % "".join(items)


def matches_page(request):
    user = request.user
    rows = interactions.matches_for(user["id"])

    if rows:
        items = []
        for m in rows:
            if m["last_message"]:
                prefix = "You: " if m["last_sender_id"] == user["id"] else ""
                preview = esc(prefix + m["last_message"][:70])
                if len(m["last_message"]) > 70:
                    preview += "&hellip;"
            else:
                preview = '<span class="muted">Say hello &mdash; no messages yet</span>'
            items.append(
                '<a class="thread" href="/chat/%(mid)d">%(avatar)s'
                '<div class="thread-body"><div class="thread-top">'
                '<strong>%(name)s</strong><span class="thread-time">%(when)s</span>'
                "</div>"
                '<p class="thread-preview">%(preview)s</p></div>%(badge)s</a>'
                % {"mid": m["match_id"],
                   "avatar": avatar(m["photo"], m["display_name"]),
                   "name": esc(m["display_name"]),
                   "when": esc(relative_time(m["last_at"] or m["created_at"])),
                   "preview": preview,
                   "badge": ('<span class="unread">%d</span>' % m["unread"])
                            if m["unread"] else ""})
        listing = '<div class="threads">%s</div>' % "".join(items)
    else:
        listing = ('<div class="empty"><h3>No matches yet</h3>'
                   '<p class="muted">A match happens when you and someone else '
                   'both like each other. Then you can chat.</p>'
                   '<a class="btn" href="/discover">Browse nearby</a></div>')

    body = (
        '<section class="feed-head"><div><h1>Matches</h1>'
        '<p class="muted">%s</p></div>%s</section>%s'
    ) % (("<strong>%d</strong> %s" % (len(rows),
                                      "conversation" if len(rows) == 1
                                      else "conversations"))
         if rows else "Mutual likes land here.",
         _tabs("matches", user), listing)
    return html(layout("Matches", body, user, "matches"))


# --- chat ------------------------------------------------------------------
def _load_match(request):
    try:
        match_id = int(request.params["match_id"])
    except (KeyError, ValueError):
        return None
    return interactions.get_match(match_id, request.user["id"])


def _bubble(message, me_id):
    mine = message["sender_id"] == me_id
    return ('<div class="msg %s" data-id="%d"><p>%s</p>'
            '<time>%s</time></div>'
            % ("mine" if mine else "theirs", message["id"],
               esc(message["body"]).replace("\n", "<br>"),
               esc(relative_time(message["created_at"]))))


def chat_page(request, error=""):
    match = _load_match(request)
    if match is None:
        return error_page(404, "Conversation not found",
                          "That conversation doesn't exist, or isn't yours.")

    user = request.user
    interactions.mark_read(match["match_id"], user["id"])
    messages = interactions.messages_for(match["match_id"])
    other = match["other"]

    thread = "".join(_bubble(m, user["id"]) for m in messages) or (
        '<div class="chat-empty"><p class="muted">You matched %s. '
        "Start the conversation.</p></div>"
        % esc(relative_time(match["created_at"])))

    body = (
        '<p class="backlink"><a href="/matches">&larr; All matches</a></p>'
        '<section class="chat">'
        '<header class="chat-head">'
        '<a href="/people/%(uid)d" class="chat-who">%(avatar)s'
        "<div><strong>%(name)s</strong>"
        '<span class="muted small">%(headline)s</span></div></a></header>'
        '<div class="chat-log" id="chat-log" data-match="%(mid)d" '
        'data-last="%(last)d">%(thread)s</div>'
        "%(error)s"
        '<form method="post" action="/chat/%(mid)d" class="chat-form" id="chat-form">'
        "%(csrf)s"
        '<input class="input" type="text" name="body" id="chat-input" '
        'placeholder="Write a message&hellip;" maxlength="%(maxlen)d" '
        'autocomplete="off" required>'
        '<button class="btn" type="submit">Send</button>'
        "</form></section>"
    ) % {
        "uid": match["other_id"],
        "avatar": avatar(other["photo"], other["display_name"]),
        "name": esc(other["display_name"]),
        "headline": esc(other["headline"] or ""),
        "mid": match["match_id"],
        "last": messages[-1]["id"] if messages else 0,
        "thread": thread,
        "error": flash(error, "error") if error else "",
        "csrf": csrf_input(user),
        "maxlen": interactions.MAX_MESSAGE_LEN,
    }
    return html(layout("Chat with %s" % other["display_name"], body, user,
                       "matches"))


def chat_send(request):
    match = _load_match(request)
    if match is None:
        return error_page(404, "Conversation not found",
                          "That conversation doesn't exist, or isn't yours.")

    body = request.field("body")
    message = interactions.send_message(match["match_id"], request.user["id"], body)

    if request.wants_json:
        if message is None:
            return json_response({"error": "empty message"}, 400)
        return json_response({"ok": True, "message": message})
    if message is None:
        return chat_page(request, error="Type something first.")
    return redirect("/chat/%d" % match["match_id"])


def chat_poll(request):
    """Long-poll-lite: the client asks for anything newer than `after`."""
    match = _load_match(request)
    if match is None:
        return json_response({"error": "not found"}, 404)
    after = request.get_int("after", 0)
    messages = interactions.messages_for(match["match_id"], after_id=after)
    interactions.mark_read(match["match_id"], request.user["id"])
    return json_response({"ok": True, "me": request.user["id"],
                          "messages": messages})
