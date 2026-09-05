"""The interest catalogue. Seeded into the `interests` table on first run."""
from __future__ import annotations

# (slug, display name, category)
INTERESTS = [
    ("running",        "Running",            "Sports & Fitness"),
    ("gym",            "Gym",                "Sports & Fitness"),
    ("yoga",           "Yoga",               "Sports & Fitness"),
    ("cycling",        "Cycling",            "Sports & Fitness"),
    ("swimming",       "Swimming",           "Sports & Fitness"),
    ("football",       "Football",           "Sports & Fitness"),
    ("cricket",        "Cricket",            "Sports & Fitness"),
    ("badminton",      "Badminton",          "Sports & Fitness"),
    ("climbing",       "Bouldering",         "Sports & Fitness"),

    ("live-music",     "Live music",         "Music"),
    ("indie",          "Indie",              "Music"),
    ("hip-hop",        "Hip-hop",            "Music"),
    ("classical",      "Classical",          "Music"),
    ("techno",         "Techno",             "Music"),
    ("vinyl",          "Vinyl",              "Music"),
    ("guitar",         "Playing guitar",     "Music"),

    ("coffee",         "Specialty coffee",   "Food & Drink"),
    ("cooking",        "Cooking",            "Food & Drink"),
    ("baking",         "Baking",             "Food & Drink"),
    ("street-food",    "Street food",        "Food & Drink"),
    ("craft-beer",     "Craft beer",         "Food & Drink"),
    ("wine",           "Wine",               "Food & Drink"),
    ("vegetarian",     "Vegetarian food",    "Food & Drink"),
    ("brunch",         "Brunch",             "Food & Drink"),

    ("travel",         "Travel",             "Travel & Outdoors"),
    ("hiking",         "Hiking",             "Travel & Outdoors"),
    ("camping",        "Camping",            "Travel & Outdoors"),
    ("road-trips",     "Road trips",         "Travel & Outdoors"),
    ("beaches",        "Beaches",            "Travel & Outdoors"),
    ("scuba",          "Scuba diving",       "Travel & Outdoors"),

    ("photography",    "Photography",        "Arts & Culture"),
    ("reading",        "Reading",            "Arts & Culture"),
    ("writing",        "Writing",            "Arts & Culture"),
    ("theatre",        "Theatre",            "Arts & Culture"),
    ("film",           "Film",               "Arts & Culture"),
    ("museums",        "Museums",            "Arts & Culture"),
    ("painting",       "Painting",           "Arts & Culture"),
    ("stand-up",       "Stand-up comedy",    "Arts & Culture"),

    ("coding",         "Coding",             "Tech & Making"),
    ("startups",       "Startups",           "Tech & Making"),
    ("gaming",         "Gaming",             "Tech & Making"),
    ("board-games",    "Board games",        "Tech & Making"),
    ("design",         "Design",             "Tech & Making"),
    ("diy",            "DIY & making",       "Tech & Making"),
    ("astronomy",      "Astronomy",          "Tech & Making"),

    ("dogs",           "Dogs",               "Home & Chill"),
    ("cats",           "Cats",               "Home & Chill"),
    ("plants",         "Plants",             "Home & Chill"),
    ("podcasts",       "Podcasts",           "Home & Chill"),
    ("meditation",     "Meditation",         "Home & Chill"),
    ("volunteering",   "Volunteering",       "Home & Chill"),
]

CATEGORY_ORDER = [
    "Sports & Fitness", "Music", "Food & Drink", "Travel & Outdoors",
    "Arts & Culture", "Tech & Making", "Home & Chill",
]

GENDERS = [
    ("woman", "Woman"),
    ("man", "Man"),
    ("non-binary", "Non-binary"),
    ("other", "Other"),
]

INTERESTED_IN = [
    ("women", "Women"),
    ("men", "Men"),
    ("everyone", "Everyone"),
]

GENDER_VALUES = {g[0] for g in GENDERS}
INTERESTED_VALUES = {i[0] for i in INTERESTED_IN}

# which `gender` values satisfy a given `interested_in` preference
PREFERENCE_MATCHES = {
    "women": {"woman"},
    "men": {"man"},
    "everyone": GENDER_VALUES,
}
