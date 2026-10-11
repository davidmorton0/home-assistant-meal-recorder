"""Constants for the Meal Recorder integration."""

DOMAIN = "meal_recorder"

# Config entry data
CONF_USERNAME = "username"
CONF_PASSWORD_HASH = "password_hash"
CONF_PERSONS = "persons"

# Storage
STORAGE_DIR = "meal_recorder"
CSV_COLUMNS = [
    "id",
    "created_at",
    "received_at",
    "name",
    "meal",
    "portion",
    "mass",
    "kcal",
    "protein",
    "carbohydrate",
    "fat",
]

MEALS = ["breakfast", "lunch", "dinner", "snack"]
NUTRIENTS = ["kcal", "protein", "carbohydrate", "fat"]

# Daily intake targets, drawn on the page's charts. A person who has not set
# their own gets these, the values the charts have always drawn.
DEFAULT_INTAKE_PRESET = "custom"
DEFAULT_INTAKES = {"kcal": 2000, "protein": 50, "carbohydrate": 260, "fat": 70}
MAX_INTAKE = 100000
MAX_PRESET_LEN = 50

# Ingest caps
MAX_BODY_BYTES = 1024 * 1024
MAX_ITEMS = 1000
MAX_NAME_LEN = 200
MAX_PORTION_LEN = 100
MAX_PERSON_LEN = 100

# Signals
SIGNAL_DATA_UPDATED = f"{DOMAIN}_data_updated"
SIGNAL_PERSON_ADDED = f"{DOMAIN}_person_added"
SIGNAL_VIEW_UPDATED = f"{DOMAIN}_view_updated"
