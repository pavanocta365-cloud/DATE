"""The discovery feed: who is nearby, best matches first."""
from __future__ import annotations

from .. import config, interactions, matching, models
from ..templates import avatar, chips, esc, flash, layout
from ..web import html, redirect
from .auth import login_required
from .interactions import _tabs, decision_buttons


def register(router):
    router.add("GET", "/discover", login_required(feed))


def _card(candidate, request, back):
    shared = set(candidate["shared_interests"])
    ordered = (candidate["shared_interests"]
               + [i for i in candidate["interests"] if i not in shared])
    badge = ('<span class="badge badge-shared">%d shared</span>'
             % candidate["shared_count"]) if candidate["shared_count"] else ""
    likes_you = ('<span class="badge badge-likes">Likes you</span>'
                 if candidate.get("likes_me") else "")
    age = (" &middot; %d" % candidate["age"]) if candidate["age"] else ""
    return (
        '<article class="card" data-user="%(uid)d">'
        '<a class="card-photo" href="/people/%(uid)d">%(avatar)s'
        '<span class="match">%(pct)d%%</span>%(likesyou)s</a>'
        '<div class="card-body">'
        '<h3><a href="/people/%(uid)d">%(name)s</a>%(age)s</h3>'
        '<p class="card-meta">%(distance)s &middot; %(city)s %(badge)s</p>'
        "%(headline)s"
        "%(chips)s"
        "%(actions)s"
        "</div></article>"
    ) % {
        "uid": candidate["user_id"],
        "avatar": avatar(candidate["photo"], candidate["display_name"]),
        "pct": candidate["match_percent"],
        "name": esc(candidate["display_name"]),
        "age": age,
        "distance": esc(candidate["distance_label"]),
        "city": esc(candidate["city"] or "Nearby"),
        "badge": badge,
        "headline": ('<p class="card-headline">%s</p>'
                     % esc(candidate["headline"])) if candidate["headline"] else "",
        "chips": chips(ordered, shared, limit=4),
        "likesyou": likes_you,
        "actions": decision_buttons(request, candidate["user_id"], back),
    }


def _radius_switcher(active, base="/discover"):
    links = "".join(
        '<a class="pill%s" href="%s?radius=%d">%d km</a>'
        % (" is-active" if r == active else "", base, r, r)
        for r in config.RADIUS_CHOICES)
    return '<div class="pills" role="group" aria-label="Search radius">%s</div>' % links


def _empty_state(reason, radius, gaps, user=None):
    if reason == "no-profile":
        return ('<div class="empty"><h3>Finish your profile first</h3>'
                '<p class="muted">We need a few details before we can look '
                'around.</p><a class="btn" href="/profile">Complete profile</a>'
                "</div>")
    if reason == "no-location":
        return ('<div class="empty"><h3>Where are you?</h3>'
                '<p class="muted">Set a location and we\'ll show you who is '
                'close by.</p><a class="btn" href="/profile">Set my location</a>'
                "</div>")
    if gaps:
        return ('<div class="empty"><h3>Your profile is hidden</h3>'
                '<p class="muted">Finish these and you\'ll appear in other '
                'feeds too: %s.</p><a class="btn" href="/profile">Finish profile'
                "</a></div>" % esc(", ".join(gaps).lower()))
    seen = interactions.acted_on_ids(user["id"]) if user else []
    if seen:
        return ('<div class="empty"><h3>That is everyone within %d km</h3>'
                '<p class="muted">You have been through all %d nearby profiles. '
                'Widen the radius above to see more.</p>'
                '<a class="btn btn-ghost" href="/likes">See who liked you</a>'
                "</div>" % (radius, len(seen)))
    return ('<div class="empty"><h3>Nobody within %d km</h3>'
            '<p class="muted">Try widening the radius above.</p></div>' % radius)


def feed(request):
    user = request.user
    profile = models.profile_for_user(user["id"])
    gaps = models.profile_gaps(user["id"])

    radius = request.get_int("radius", 0) or None
    back = "/discover?radius=%d" % radius if radius else "/discover"
    result = matching.discover(user["id"], radius_km=radius)
    radius = result["radius_km"]
    candidates = result["candidates"]

    notice = ""
    if request.get("saved"):
        notice = "Profile saved. You're visible to people nearby."

    matched_banner = ""
    matched_id = request.get_int("matched", 0)
    if matched_id:
        match = interactions.get_match(matched_id, user["id"])
        if match:
            matched_banner = (
                '<div class="matchbar">%s<div><strong>It\'s a match!</strong>'
                '<p class="muted small">You and %s liked each other.</p></div>'
                '<a class="btn btn-sm" href="/chat/%d">Send a message</a></div>'
                % (avatar(match["other"]["photo"], match["other"]["display_name"]),
                   esc(match["other"]["display_name"]), matched_id))

    banner = ""
    if gaps:
        banner = ('<div class="flash flash-warn">Your profile is hidden from '
                  'others until you %s. <a href="/profile">Fix it</a></div>'
                  % esc(" and ".join(g.lower() for g in gaps)))

    location = result["location"]
    where = models.location_label(location) if location else "no location set"

    if candidates:
        summary = ("<strong>%d</strong> %s within <strong>%d km</strong> of %s"
                   % (result["total"],
                      "person" if result["total"] == 1 else "people",
                      radius, esc(where)))
        if result["my_interests"]:
            summary += ", ranked by distance and shared interests"
        grid = '<div class="grid">%s</div>' % "".join(
            _card(c, request, back) for c in candidates)
    else:
        summary = "Looking within <strong>%d km</strong> of %s" % (radius, esc(where))
        grid = _empty_state(result["reason"], radius, gaps, user)

    more = ""
    if result["total"] > len(candidates):
        more = ('<p class="muted center small">Showing the top %d of %d.</p>'
                % (len(candidates), result["total"]))

    body = (
        '<section class="feed-head">'
        "<div><h1>Nearby</h1>"
        '<p class="muted">%(summary)s</p>%(tabs)s</div>'
        "%(radius)s</section>"
        "%(notice)s%(banner)s%(grid)s%(more)s"
    ) % {
        "summary": summary,
        "tabs": _tabs("discover", user),
        "radius": _radius_switcher(radius),
        "notice": flash(notice, "ok") if notice else "",
        "banner": matched_banner + banner,
        "grid": grid,
        "more": more,
    }
    return html(layout("Discover", body, user, "discover"))
