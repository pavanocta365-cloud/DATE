"""Profile creation, editing, photo and location."""
from __future__ import annotations

from datetime import date

from .. import config, models
from ..avatars import avatar_url
from ..geo import CITIES, CITY_BY_NAME, nearest_city
from ..interests_data import (GENDERS, GENDER_VALUES, INTERESTED_IN,
                              INTERESTED_VALUES)
from ..templates import (avatar, chips, csrf_input, errors_block, esc, field,
                         flash, layout, select, textarea)
from ..web import html, json_response, redirect
from .auth import login_required


def register(router):
    router.add("GET", "/profile", login_required(edit_form))
    router.add("POST", "/profile", login_required(edit_submit))
    router.add("POST", "/api/location", login_required(api_location))
    router.add("GET", "/people/{user_id}", login_required(view_profile))


# --- edit ------------------------------------------------------------------
def _interest_picker(selected_ids):
    blocks = []
    for category, items in models.interests_by_category():
        boxes = "".join(
            '<label class="pick"><input type="checkbox" name="interests" '
            'value="%d"%s><span>%s</span></label>'
            % (item["id"], " checked" if item["id"] in selected_ids else "",
               esc(item["name"]))
            for item in items)
        blocks.append('<div class="pick-group"><h4>%s</h4><div class="pick-row">%s'
                      "</div></div>" % (esc(category), boxes))
    return "".join(blocks)


def _city_options():
    opts = [("", "Choose a city…")]
    opts += [(c[0], "%s%s" % (c[0], ", " + c[2] if c[2] else "")) for c in CITIES]
    return opts


def edit_form(request, errors=(), values=None, notice=""):
    user_id = request.user["id"]
    profile = models.profile_for_user(user_id)
    location = models.current_location(user_id)
    selected = set(models.profile_interest_ids(profile["id"]))

    values = values or {
        "display_name": profile["display_name"],
        "birthdate": profile["birthdate"] or "",
        "gender": profile["gender"],
        "interested_in": profile["interested_in"] or "everyone",
        "headline": profile["headline"],
        "bio": profile["bio"],
        "radius_km": str(profile["radius_km"] or config.DEFAULT_RADIUS_KM),
        "city": location["city"] if location else "",
    }
    if "interests" in (values or {}):
        selected = set(values["interests"])

    gaps = models.profile_gaps(user_id)
    photo = profile["photo"] or avatar_url("u%d" % user_id)

    if request.get("welcome"):
        notice = notice or ("Account created. Fill this in and you'll show up "
                            "in other people's feeds.")

    max_birthdate = date.today().replace(year=date.today().year - config.MIN_AGE)
    location_line = models.location_label(location) if location else "Not set yet"

    progress = ""
    if gaps:
        progress = ('<div class="flash flash-warn"><strong>Before you can be '
                    'discovered:</strong><ul class="bare">%s</ul></div>'
                    % "".join("<li>%s</li>" % esc(g) for g in gaps))

    body = (
        '<section class="panel">'
        '<div class="panel-head"><div>'
        '<h1>Your profile</h1>'
        '<p class="muted">This is what people nearby will see.</p></div>'
        '%(preview)s</div>'
        "%(notice)s%(errors)s%(progress)s"
        '<form method="post" action="/profile" class="stack" id="profile-form">'
        "%(csrf)s"
        '<input type="hidden" name="photo" id="photo-data" value="%(photo_val)s">'

        '<fieldset class="group"><legend>Photo</legend>'
        '<div class="photo-row">%(avatar)s'
        '<div class="stack tight">'
        '<input class="input" type="file" id="photo-input" accept="image/*">'
        '<span class="hint">Resized in your browser before upload. '
        'Leave it blank to keep the generated avatar.</span>'
        '<button class="btn btn-ghost btn-sm" type="button" id="photo-clear">'
        'Reset to generated avatar</button>'
        "</div></div></fieldset>"

        '<fieldset class="group"><legend>The basics</legend>'
        '<div class="grid-2">%(name)s%(dob)s</div>'
        '<div class="grid-2">%(gender)s%(pref)s</div>'
        "%(headline)s%(bio)s</fieldset>"

        '<fieldset class="group"><legend>Location</legend>'
        '<p class="muted small">Current: <strong id="loc-label">%(loc)s</strong></p>'
        '<div class="grid-2">%(city)s%(radius)s</div>'
        '<input type="hidden" name="latitude" id="lat" value="">'
        '<input type="hidden" name="longitude" id="lng" value="">'
        '<button class="btn btn-ghost btn-sm" type="button" id="geo-btn">'
        'Use my current location</button>'
        '<span class="hint" id="geo-status"></span>'
        "</fieldset>"

        '<fieldset class="group"><legend>Interests '
        '<span class="muted small">(pick %(min)d&ndash;%(max)d)</span></legend>'
        '<p class="hint" id="interest-count"></p>%(picker)s</fieldset>'

        '<div class="actions">'
        '<button class="btn btn-lg" type="submit">Save profile</button>'
        '<a class="btn btn-ghost btn-lg" href="/discover">Go to discovery</a>'
        "</div></form></section>"
    ) % {
        "preview": '<div class="photo-preview">%s</div>' % avatar(photo, values["display_name"] or "You", "lg"),
        "notice": flash(notice, "ok") if notice else "",
        "errors": errors_block(errors),
        "progress": progress,
        "csrf": csrf_input(request.user),
        "photo_val": esc(profile["photo"] or ""),
        "avatar": avatar(photo, "Your photo", "md"),
        "name": field("Display name", "display_name", values["display_name"],
                      placeholder="How you want to be known", required=True,
                      maxlength=60),
        "dob": field("Date of birth", "birthdate", values["birthdate"],
                     type_="date", required=True,
                     hint="You must be %d or older." % config.MIN_AGE,
                     extra='max="%s"' % max_birthdate.isoformat()),
        "gender": select("I am a", "gender",
                         [("", "Select…")] + GENDERS, values["gender"]),
        "pref": select("Show me", "interested_in", INTERESTED_IN,
                       values["interested_in"]),
        "headline": field("Headline", "headline", values["headline"],
                          placeholder="One line that sounds like you",
                          maxlength=90),
        "bio": textarea("About you", "bio", values["bio"], rows=4,
                        placeholder="A few sentences. What's your week look like?",
                        maxlength=600),
        "loc": esc(location_line),
        "city": select("City", "city", _city_options(), values["city"],
                       hint="Or use the button below for exact coordinates."),
        "radius": select("Discovery radius", "radius_km",
                         [(r, "%d km" % r) for r in config.RADIUS_CHOICES],
                         values["radius_km"]),
        "min": config.MIN_INTERESTS,
        "max": config.MAX_INTERESTS,
        "picker": _interest_picker(selected),
    }
    return html(layout("Your profile", body, request.user, "profile"),
                status=400 if errors else 200)


def edit_submit(request):
    user_id = request.user["id"]
    profile = models.profile_for_user(user_id)

    display_name = request.field("display_name")[:60]
    birthdate = request.field("birthdate")
    gender = request.field("gender")
    interested_in = request.field("interested_in") or "everyone"
    headline = request.field("headline")[:90]
    bio = request.field("bio")[:600]
    photo = request.field("photo")
    city_name = request.field("city")
    lat_raw = request.field("latitude")
    lng_raw = request.field("longitude")

    try:
        radius = int(request.field("radius_km") or config.DEFAULT_RADIUS_KM)
    except ValueError:
        radius = config.DEFAULT_RADIUS_KM
    radius = max(1, min(config.MAX_RADIUS_KM, radius))

    interest_ids = []
    for raw in request.field_list("interests"):
        try:
            interest_ids.append(int(raw))
        except ValueError:
            pass

    errors = []
    if not display_name:
        errors.append("Add a display name.")
    born = models.parse_birthdate(birthdate)
    if birthdate and born is None:
        errors.append("That date of birth isn't a valid date.")
    elif born is not None:
        age = models.age_from_birthdate(born)
        if age is None or age < config.MIN_AGE:
            errors.append("You must be at least %d." % config.MIN_AGE)
        elif age > config.MAX_AGE:
            errors.append("Check your date of birth.")
    if gender and gender not in GENDER_VALUES:
        errors.append("Pick a valid option for how you identify.")
    if interested_in not in INTERESTED_VALUES:
        errors.append("Pick who you'd like to see.")
    if len(interest_ids) > config.MAX_INTERESTS:
        errors.append("Pick at most %d interests." % config.MAX_INTERESTS)
    if photo and not (photo.startswith("data:image/")
                      or photo.startswith("/avatar/")):
        errors.append("That photo format isn't supported.")
    if photo and len(photo) > config.MAX_PHOTO_BYTES:
        errors.append("That photo is too large - try a smaller one.")

    # Coordinates win over the city dropdown when both are present.
    new_location = None
    if lat_raw and lng_raw:
        try:
            lat, lng = float(lat_raw), float(lng_raw)
            if -90 <= lat <= 90 and -180 <= lng <= 180:
                match = nearest_city(lat, lng)
                new_location = (lat, lng,
                                match[0] if match else "",
                                match[1] if match else "",
                                match[2] if match else "", "gps")
            else:
                errors.append("Those coordinates are out of range.")
        except ValueError:
            errors.append("Those coordinates aren't valid numbers.")
    elif city_name:
        city = CITY_BY_NAME.get(city_name)
        if city is None:
            errors.append("Pick a city from the list.")
        else:
            new_location = (city[3], city[4], city[0], city[1], city[2], "manual")

    if errors:
        values = {
            "display_name": display_name, "birthdate": birthdate,
            "gender": gender, "interested_in": interested_in,
            "headline": headline, "bio": bio, "radius_km": str(radius),
            "city": city_name, "interests": interest_ids,
        }
        return edit_form(request, errors, values)

    models.update_profile(
        user_id, display_name=display_name, birthdate=birthdate or None,
        gender=gender, interested_in=interested_in, headline=headline, bio=bio,
        photo=photo or profile["photo"] or avatar_url("u%d" % user_id),
        radius_km=radius)
    models.set_profile_interests(profile["id"], interest_ids)

    if new_location:
        models.set_location(user_id, new_location[0], new_location[1],
                            city=new_location[2], region=new_location[3],
                            country=new_location[4], source=new_location[5])

    complete = models.recompute_completeness(user_id)
    if complete:
        return redirect("/discover?saved=1")
    return edit_form(request, notice="Saved. A couple of things are still missing.")


# --- location endpoint (browser geolocation) -------------------------------
def api_location(request):
    payload = request.json_body()
    try:
        lat = float(payload.get("latitude"))
        lng = float(payload.get("longitude"))
    except (TypeError, ValueError):
        return json_response({"error": "latitude and longitude required"}, 400)
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return json_response({"error": "coordinates out of range"}, 400)

    match = nearest_city(lat, lng)
    models.set_location(request.user["id"], lat, lng,
                        city=match[0] if match else "",
                        region=match[1] if match else "",
                        country=match[2] if match else "", source="gps")
    models.recompute_completeness(request.user["id"])
    row = models.current_location(request.user["id"])
    return json_response({"ok": True, "label": models.location_label(row),
                          "latitude": lat, "longitude": lng})


# --- read-only view of someone else ----------------------------------------
def view_profile(request):
    try:
        target_id = int(request.params["user_id"])
    except (KeyError, ValueError):
        return redirect("/discover")

    profile = models.profile_by_user_id(target_id)
    if profile is None or not profile["is_complete"]:
        from ..web import error_page
        return error_page(404, "Profile not found",
                          "That profile doesn't exist or isn't public yet.")
    if target_id == request.user["id"]:
        return redirect("/profile")

    me = models.profile_for_user(request.user["id"])
    mine = set(models.profile_interest_names(me["id"]))
    theirs = models.profile_interest_names(profile["id"])
    shared = mine & set(theirs)

    my_location = models.current_location(request.user["id"])
    their_location = models.current_location(target_id)
    distance_line = ""
    if my_location and their_location:
        from ..geo import format_distance, haversine_km
        km = haversine_km(my_location["latitude"], my_location["longitude"],
                          their_location["latitude"], their_location["longitude"])
        distance_line = format_distance(km)

    age = models.age_from_birthdate(profile["birthdate"])
    meta = " &middot; ".join(x for x in [
        ("%d" % age) if age else "",
        models.location_label(their_location),
        distance_line] if x)

    body = (
        '<p class="backlink"><a href="/discover">&larr; Back to discovery</a></p>'
        '<section class="panel profile-view">'
        '<div class="profile-hero">%(avatar)s<div>'
        "<h1>%(name)s</h1>"
        '<p class="muted">%(meta)s</p>'
        "%(headline)s</div></div>"
        "%(bio)s"
        '<h3 class="section-title">Interests</h3>%(chips)s'
        "%(sharednote)s"
        "</section>"
    ) % {
        "avatar": avatar(profile["photo"], profile["display_name"], "xl"),
        "name": esc(profile["display_name"]),
        "meta": meta,
        "headline": ('<p class="headline">%s</p>' % esc(profile["headline"]))
                    if profile["headline"] else "",
        "bio": ('<p class="bio">%s</p>' % esc(profile["bio"]))
               if profile["bio"] else "",
        "chips": chips(theirs, shared),
        "sharednote": ('<p class="muted small">You both like %s.</p>'
                       % esc(", ".join(sorted(shared)))) if shared else
                      '<p class="muted small">No interests in common yet.</p>',
    }
    return html(layout(profile["display_name"], body, request.user, "discover"))
