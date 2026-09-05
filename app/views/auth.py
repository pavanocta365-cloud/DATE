"""Signup, login, logout."""
from __future__ import annotations

from .. import config, models, security
from ..templates import (csrf_input, errors_block, esc, field, layout)
from ..web import html, redirect


def register(router):
    router.add("GET", "/", landing)
    router.add("GET", "/signup", signup_form)
    router.add("POST", "/signup", signup_submit)
    router.add("GET", "/login", login_form)
    router.add("POST", "/login", login_submit)
    router.add("POST", "/logout", logout)


def _safe_next(raw: str) -> str:
    """Only allow same-site relative redirects."""
    if raw.startswith("/") and not raw.startswith("//"):
        return raw
    return "/discover"


# --- landing ---------------------------------------------------------------
def landing(request):
    if request.user:
        return redirect("/discover")
    body = (
        '<section class="hero">'
        '<p class="eyebrow">Location-based dating &mdash; MVP</p>'
        '<h1 class="hero-title">Meet people who are<br><span class="grad">'
        'actually nearby</span></h1>'
        '<p class="lede">Build a profile, pick what you are into, and see who is '
        'close by &mdash; ranked by distance and the interests you share.</p>'
        '<div class="hero-actions">'
        '<a class="btn btn-lg" href="/signup">Create an account</a>'
        '<a class="btn btn-ghost btn-lg" href="/login">I already have one</a>'
        "</div>"
        '<div class="steps">'
        '<div class="step"><span class="step-n">1</span><h3>Register</h3>'
        '<p>Email and a password. Sessions are kept server-side.</p></div>'
        '<div class="step"><span class="step-n">2</span><h3>Build a profile</h3>'
        '<p>Photo, the basics, and at least %d interests.</p></div>'
        '<div class="step"><span class="step-n">3</span><h3>See who is near</h3>'
        '<p>Everyone inside your radius, best matches first.</p></div>'
        "</div>"
        '<p class="muted small">Seeded with demo profiles. Sign in to any of them '
        'with the password <code>%s</code>.</p>'
        "</section>"
    ) % (config.MIN_INTERESTS, esc(config.SEED_PASSWORD))
    return html(layout("Meet people nearby", body, None, "", body_class="landing"))


# --- signup ----------------------------------------------------------------
def _auth_shell(title, subtitle, action, submit_label, alt_html, errors, email):
    return (
        '<section class="panel narrow">'
        '<h1>%s</h1><p class="muted">%s</p>'
        "%s"
        '<form method="post" action="%s" class="stack" autocomplete="on">'
        "%s%s"
        '<button class="btn btn-block btn-lg" type="submit">%s</button>'
        "</form>"
        '<p class="muted center small">%s</p>'
        "</section>"
    ) % (
        esc(title), esc(subtitle), errors_block(errors), esc(action),
        field("Email", "email", email, type_="email",
              placeholder="you@example.com", required=True,
              extra='autocomplete="email"'),
        field("Password", "password", "", type_="password",
              placeholder="At least 8 characters", required=True,
              extra='autocomplete="current-password"'),
        esc(submit_label), alt_html,
    )


def signup_form(request, errors=(), email=""):
    if request.user:
        return redirect("/discover")
    body = _auth_shell(
        "Create your account", "Takes about a minute.", "/signup", "Sign up",
        'Already registered? <a href="/login">Log in</a>.', errors, email)
    return html(layout("Sign up", body, None), status=400 if errors else 200)


def signup_submit(request):
    if request.user:
        return redirect("/discover")
    email = security.normalise_email(request.field("email"))
    password = request.form.get("password", [""])[0]

    errors = [e for e in (security.email_error(email),
                          security.password_error(password)) if e]
    if not errors and models.email_taken(email):
        errors.append("That email is already registered. Try logging in.")
    if errors:
        return signup_form(request, errors, email)

    user_id = models.create_user(email, security.hash_password(password))
    token = security.create_session(user_id, request.headers.get("User-Agent", ""))
    models.touch_last_seen(user_id)
    response = redirect("/profile?welcome=1")
    response.set_cookie(config.SESSION_COOKIE, token,
                        max_age=config.SESSION_TTL_DAYS * 86400)
    return response


# --- login -----------------------------------------------------------------
def login_form(request, errors=(), email=""):
    if request.user:
        return redirect("/discover")
    hint = ('<span class="muted small">Demo accounts use the password '
            '<code>%s</code>.</span><br>' % esc(config.SEED_PASSWORD))
    body = _auth_shell(
        "Welcome back", "Log in to pick up where you left off.", "/login",
        "Log in", hint + 'New here? <a href="/signup">Create an account</a>.',
        errors, email)
    return html(layout("Log in", body, None), status=400 if errors else 200)


def login_submit(request):
    if request.user:
        return redirect("/discover")
    email = security.normalise_email(request.field("email"))
    password = request.form.get("password", [""])[0]
    user = models.user_by_email(email) if email else None

    # Same message either way: don't leak which emails exist.
    if user is None or not security.verify_password(password, user["password_hash"]):
        return login_form(request, ["Email or password isn't right."], email)

    token = security.create_session(user["id"], request.headers.get("User-Agent", ""))
    models.touch_last_seen(user["id"])
    profile = models.profile_for_user(user["id"])
    destination = "/discover" if profile and profile["is_complete"] else "/profile"
    response = redirect(_safe_next(request.get("next", destination)))
    response.set_cookie(config.SESSION_COOKIE, token,
                        max_age=config.SESSION_TTL_DAYS * 86400)
    return response


def logout(request):
    security.destroy_session(request.cookie(config.SESSION_COOKIE))
    response = redirect("/")
    response.clear_cookie(config.SESSION_COOKIE)
    return response


# --- guard -----------------------------------------------------------------
def login_required(handler):
    def wrapper(request):
        if not request.user:
            from urllib.parse import quote
            return redirect("/login?next=%s" % quote(request.path))
        return handler(request)
    return wrapper
