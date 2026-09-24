"""Constants for the Meal Recorder integration."""

DOMAIN = "meal_recorder"

# Config entry data
CONF_USERNAME = "username"
CONF_PASSWORD_HASH = "password_hash"
CONF_DEFAULT_PERSON = "default_person"
CONF_PERSONS = "persons"
CONF_DASHBOARD_VIEWS = "dashboard_views"

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
    "carbs",
    "fat",
]

MEALS = ["breakfast", "lunch", "dinner", "snack"]
NUTRIENTS = ["kcal", "protein", "carbs", "fat"]

# Ingest caps
MAX_BODY_BYTES = 1024 * 1024
MAX_ITEMS = 1000
MAX_NAME_LEN = 200
MAX_PORTION_LEN = 100
MAX_PERSON_LEN = 100

# Signals
SIGNAL_DATA_UPDATED = f"{DOMAIN}_data_updated"
SIGNAL_PERSON_ADDED = f"{DOMAIN}_person_added"
