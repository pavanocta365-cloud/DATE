"""Deterministic demo data so the discovery feed is useful on first run."""
from __future__ import annotations

import math
import random
from datetime import date

from . import config, db, interactions, models, security
from .avatars import avatar_url
from .geo import CITY_BY_NAME

SEED = 20240917

WOMEN = ["Aditi", "Ananya", "Ishita", "Meera", "Nandini", "Priya", "Riya",
         "Sanya", "Tara", "Kavya", "Diya", "Aisha", "Neha", "Shreya", "Anjali",
         "Pooja", "Rhea", "Sneha", "Trisha", "Vaishnavi", "Zoya", "Lakshmi",
         "Chloe", "Maya", "Elena", "Naomi"]
MEN = ["Aarav", "Arjun", "Dev", "Ishaan", "Kabir", "Karan", "Nikhil", "Rohan",
       "Rahul", "Siddharth", "Varun", "Vikram", "Aditya", "Manav", "Pranav",
       "Rishi", "Sameer", "Yash", "Tanmay", "Harsh", "Omar", "Daniel",
       "Lucas", "Noah"]
ENBY = ["Kiran", "Ayan", "Jai", "Noor", "Sam", "Ali", "Robin", "Alex"]
SURNAMES = ["Sharma", "Menon", "Iyer", "Nair", "Rao", "Kulkarni", "Desai",
            "Bhatia", "Kapoor", "Chatterjee", "Banerjee", "Gupta", "Reddy",
            "Naidu", "Pillai", "Joshi", "Malhotra", "Sethi", "Verma", "Shah",
            "Dsouza", "Fernandes", "Khan", "Mehta", "Sinha", "Bose"]

HEADLINES = [
    "Here for good coffee and better conversation",
    "Weekday spreadsheets, weekend trails",
    "Ask me about my last road trip",
    "Probably at a gig right now",
    "Low-key competitive at board games",
    "Trying every filter coffee in the city",
    "Sunrise runs, late-night playlists",
    "Will bring snacks",
    "Looking for a partner in crime for supper clubs",
    "Two cats and a lot of opinions about films",
    "Building something small and stubborn",
    "Happiest with a book and bad weather",
    "New to the city, show me the good spots",
    "Long walks, longer debates",
    "Recovering perfectionist, decent cook",
]

BIO_TEMPLATES = [
    "{first} here. {a} most mornings, {b} most evenings. I like plans that "
    "start vague and end well.",
    "Grew up elsewhere, settled here for the food. Big on {a}, slowly getting "
    "better at {b}. Tell me something you're obsessed with.",
    "{a} is the hobby, {b} is the personality. I text back quickly and I'm "
    "genuinely bad at small talk.",
    "Spend my weekends on {a}. Weeknights are for {b} or doing absolutely "
    "nothing. Looking for someone easy to be quiet with.",
    "Currently: too much {a}, not enough sleep. Would happily be dragged into "
    "{b} by the right person.",
    "I make a very good cup of coffee and a very average joke. Into {a} and "
    "{b}. Let's go somewhere with no phone signal.",
    "Equal parts {a} and {b}. I plan trips I don't take and cook meals I "
    "over-season. Show me your camera roll.",
    "{a} keeps me sane, {b} keeps me interesting. Looking for something "
    "unhurried.",
]

# Interests are not equally popular in real user bases; weighting them is what
# makes "shared interests" a meaningful ranking signal instead of noise.
POPULARITY = {
    "travel": 9, "coffee": 8, "live-music": 8, "film": 8, "reading": 7,
    "gym": 7, "cooking": 7, "gaming": 6, "dogs": 6, "hiking": 6,
    "photography": 6, "running": 6, "podcasts": 5, "street-food": 5,
    "brunch": 5, "cricket": 5, "indie": 5, "yoga": 5, "board-games": 4,
    "coding": 4, "startups": 4, "craft-beer": 4, "plants": 4, "cats": 4,
    "cycling": 4, "badminton": 4, "road-trips": 4, "stand-up": 4,
}
DEFAULT_POPULARITY = 2

# city -> (weight, spread_km) - spread controls how far from centre people sit
CITY_MIX = [
    ("Bengaluru", 48, 18.0),
    ("Mumbai", 18, 20.0),
    ("Delhi", 10, 24.0),
    ("Gurugram", 6, 14.0),
    ("Hyderabad", 12, 20.0),
    ("Pune", 9, 18.0),
    ("Chennai", 8, 20.0),
    ("Kolkata", 5, 18.0),
    ("Goa", 3, 20.0),
    ("Kochi", 3, 14.0),
    ("London", 4, 18.0),
    ("San Francisco", 4, 16.0),
    ("Singapore", 3, 12.0),
    ("Berlin", 3, 14.0),
]


def _offset_point(lat, lon, distance_km, bearing_deg):
    """Move a point distance_km along a bearing (equirectangular is fine here)."""
    bearing = math.radians(bearing_deg)
    dlat = (distance_km * math.cos(bearing)) / 110.574
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    dlon = (distance_km * math.sin(bearing)) / (111.320 * cos_lat)
    return lat + dlat, lon + dlon


def _birthdate(rng, age):
    year = date.today().year - age
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return "%04d-%02d-%02d" % (year, month, day)


def is_empty() -> bool:
    return (db.scalar("SELECT COUNT(*) FROM users") or 0) == 0


def seed_if_empty() -> int:
    """Seed the interest catalogue always; demo profiles only when empty."""
    models.ensure_interest_catalogue()
    if not is_empty():
        return 0
    created = seed_profiles()
    seed_demo_interactions()
    return created


def seed_demo_interactions() -> None:
    """Give the demo population some likes, matches and a few messages.

    Without this the Matches and Likes-you pages are empty until two real
    accounts interact, which makes the app hard to evaluate.
    """
    rng = random.Random(SEED + 1)
    users = [r["id"] for r in db.query(
        "SELECT id FROM users WHERE is_demo = 1 ORDER BY id")]
    if len(users) < 4:
        return

    openers = [
        "Hey! Your profile made me laugh.",
        "Okay, we clearly have the same taste in music.",
        "Hi :) what's your go-to spot around here?",
        "Finally someone else who likes that.",
        "Hey, how's the week treating you?",
    ]

    # Pass 1: everyone swipes on a handful of others.
    for user_id in users:
        for other in rng.sample(users, min(len(users), rng.randint(4, 9))):
            if other == user_id:
                continue
            interactions.record_decision(user_id, other, rng.random() < 0.55)

    # Pass 2: people answer most of the likes they received - roughly two in
    # five like back, which is what produces matches. A quarter are left
    # deliberately unanswered so every demo account has a populated
    # "Likes you" page to look at.
    incoming = db.query(
        "SELECT from_user_id, to_user_id FROM likes WHERE is_like = 1")
    for row in incoming:
        receiver, sender = row["to_user_id"], row["from_user_id"]
        if interactions.decision(receiver, sender) is not None:
            continue
        if rng.random() < 0.45:
            continue
        interactions.record_decision(receiver, sender, rng.random() < 0.53)

    # Pass 3: about half the matches have an opening line.
    for match in db.query("SELECT id, user_a_id, user_b_id FROM matches"):
        if rng.random() < 0.55:
            sender = rng.choice([match["user_a_id"], match["user_b_id"]])
            interactions.send_message(match["id"], sender, rng.choice(openers))


def seed_likes_for(user_id: int, limit: int = None) -> int:
    """Have a few plausible nearby demo profiles like `user_id`.

    Called once, the first time a real account becomes discoverable.
    """
    limit = config.SEED_INCOMING_LIKES if limit is None else limit
    if not limit:
        return 0
    from . import matching
    result = matching.discover(user_id, radius_km=config.MAX_RADIUS_KM,
                               limit=limit * 3, include_decided=True)
    rng = random.Random(SEED + user_id)
    pool = [c["user_id"] for c in result["candidates"]]
    rng.shuffle(pool)
    sent = 0
    for other in pool[:limit]:
        if db.query_one("SELECT 1 FROM users WHERE id = ? AND is_demo = 1",
                        (other,)) is None:
            continue
        if interactions.decision(other, user_id) is not None:
            continue
        interactions.record_decision(other, user_id, True)
        sent += 1
    return sent


def seed_profiles() -> int:
    rng = random.Random(SEED)
    interests = models.all_interests()
    by_category = {}
    for item in interests:
        by_category.setdefault(item["category"], []).append(item)
    categories = list(by_category)
    weights = [POPULARITY.get(i["slug"], DEFAULT_POPULARITY) for i in interests]

    # One hash for every demo account: scrypt is intentionally slow.
    shared_hash = security.hash_password(config.SEED_PASSWORD)

    plan = []
    for city_name, weight, spread in CITY_MIX:
        plan.extend([(city_name, spread)] * weight)
    rng.shuffle(plan)

    used_emails = set()
    created = 0

    for index, (city_name, spread) in enumerate(plan):
        city = CITY_BY_NAME[city_name]

        roll = rng.random()
        if roll < 0.46:
            gender, pool = "woman", WOMEN
        elif roll < 0.92:
            gender, pool = "man", MEN
        else:
            gender, pool = "non-binary", ENBY

        first = rng.choice(pool)
        last = rng.choice(SURNAMES)
        name = "%s %s" % (first, last)

        base = "%s.%s" % (first.lower(), last.lower())
        email = "%s@example.com" % base
        suffix = 2
        while email in used_emails:
            email = "%s%d@example.com" % (base, suffix)
            suffix += 1
        used_emails.add(email)

        if gender == "woman":
            interested_in = "men" if rng.random() < 0.82 else "everyone"
        elif gender == "man":
            interested_in = "women" if rng.random() < 0.82 else "everyone"
        else:
            interested_in = "everyone"

        # One "anchor" category gives each person a theme; the rest is drawn
        # from a popularity-weighted pool so overlaps between people are common.
        anchor = rng.choice(categories)
        anchor_pool = by_category[anchor]
        chosen = {}
        for item in rng.sample(anchor_pool, min(len(anchor_pool), rng.randint(1, 2))):
            chosen[item["id"]] = item

        target = rng.randint(5, config.MAX_INTERESTS)
        guard = 0
        while len(chosen) < target and guard < 60:
            guard += 1
            item = rng.choices(interests, weights=weights, k=1)[0]
            chosen[item["id"]] = item
        chosen = list(chosen.values())

        names = [c["name"].lower() for c in chosen]
        bio = rng.choice(BIO_TEMPLATES).format(
            first=first, a=names[0], b=names[1] if len(names) > 1 else names[0])

        user_id = models.create_user(email, shared_hash, is_demo=1)
        profile = models.profile_for_user(user_id)

        models.update_profile(
            user_id,
            display_name=name,
            birthdate=_birthdate(rng, rng.randint(21, 41)),
            gender=gender,
            interested_in=interested_in,
            headline=rng.choice(HEADLINES),
            bio=bio,
            photo=avatar_url("%s-%d" % (base, index)),
            radius_km=rng.choice(config.RADIUS_CHOICES),
        )
        models.set_profile_interests(profile["id"], [c["id"] for c in chosen])

        # Denser near the centre than a uniform disc, but still spread out -
        # exponent 0.65 sits between "uniform by area" (0.5) and centre-heavy.
        distance = round(0.2 + spread * (rng.random() ** 0.65), 3)
        lat, lon = _offset_point(city[3], city[4], distance, rng.uniform(0, 360))
        models.set_location(user_id, lat, lon, city=city[0], region=city[1],
                            country=city[2], source="seed")

        models.recompute_completeness(user_id)
        created += 1

    return created
