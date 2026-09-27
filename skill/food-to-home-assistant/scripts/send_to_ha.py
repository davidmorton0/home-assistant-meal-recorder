#!/usr/bin/env python3
"""Send a meal to the Meal Recorder integration in Home Assistant.

Usage: python send_to_ha.py meal.json [--dry-run]

meal.json:
{
  "meal": "dinner",                          # breakfast | lunch | dinner | snack
  "created_at": "2026-09-24T18:30:00+01:00", # optional, defaults to now
  "person": "David",                         # optional, defaults to HA's default person
  "items": [
    {"name": "...", "portion": "...", "mass": 212, "kcal": 460,
     "protein": 8, "carbs": 55, "fat": 21}   # "id" is added by this script

  ]
}
"""
import base64
import json
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CONFIG = Path(__file__).resolve().parent.parent / "config.json"
ENDPOINT = "/api/meal_recorder/items"
MEALS = ["breakfast", "lunch", "dinner", "snack"]
NUMBERS = ["mass", "kcal", "protein", "carbs", "fat"]
LIMITS = {"name": 200, "portion": 100, "person": 100}


def build_items(meal):
    """Turn the meal file into the integration's item list, checking the same rules it does."""
    problems = []
    meal_type = str(meal.get("meal", "")).strip().lower()
    if meal_type not in MEALS:
        problems.append(f"meal must be one of {', '.join(MEALS)}")

    created_at = meal.get("created_at") or datetime.now(ZoneInfo("Europe/London")).isoformat(timespec="seconds")
    try:
        datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        problems.append("created_at is not a valid ISO 8601 timestamp")

    person = (meal.get("person") or "").strip()
    if len(person) > LIMITS["person"]:
        problems.append(f"person must be at most {LIMITS['person']} characters")

    raw_items = meal.get("items") or []
    if not raw_items:
        problems.append("no items")

    items = []
    for i, raw in enumerate(raw_items):
        name = str(raw.get("name", "")).strip()
        portion = str(raw.get("portion", "") or "").strip()
        if not name:
            problems.append(f"item {i}: name is empty")
        if len(name) > LIMITS["name"]:
            problems.append(f"item {i}: name longer than {LIMITS['name']} characters")
        if len(portion) > LIMITS["portion"]:
            problems.append(f"item {i}: portion longer than {LIMITS['portion']} characters")
        item = {"id": raw.get("id"), "created_at": created_at, "name": name,
                "meal": meal_type, "portion": portion}
        if person:
            item["person"] = person
        for field in NUMBERS:
            value = raw.get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                problems.append(f"item {i}: {field} must be a number")
            elif value < 0:
                problems.append(f"item {i}: {field} must not be negative")
            else:
                value = round(float(value), 1)
                item[field] = int(value) if value.is_integer() else value
        items.append(item)
    return items, problems


def main():
    args = sys.argv[1:]
    dry = "--dry-run" in args
    files = [a for a in args if a != "--dry-run"]
    if len(files) != 1:
        print(__doc__)
        sys.exit(2)

    meal_file = Path(files[0])
    meal = json.loads(meal_file.read_text())
    if not dry:
        # Each item keeps its id in the meal file, so sending the file again is
        # refused as a duplicate instead of storing the meal twice.
        for raw in meal.get("items") or []:
            if isinstance(raw, dict) and not raw.get("id"):
                raw["id"] = str(uuid.uuid4())
        meal_file.write_text(json.dumps(meal, indent=2))
    items, problems = build_items(meal)
    if problems:
        print("ERROR: not sent, the meal file has problems:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)

    payload = {"items": items}
    total = round(sum(i["kcal"] for i in items))
    if dry:
        print(json.dumps(payload, indent=2))
        print(f"DRY RUN: {len(items)} items, {total} kcal, not sent")
        return

    cfg = json.loads(CONFIG.read_text())
    base = cfg.get("base_url", "").rstrip("/")
    user, pw = cfg.get("username", ""), cfg.get("password", "")
    if not base or "YOUR-DOMAIN" in base or not user or not pw or "CHANGE-ME" in pw:
        print("ERROR: base_url, username and password in config.json are not set.")
        sys.exit(1)

    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    req = urllib.request.Request(
        base + ENDPOINT,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Basic {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read() or b"{}")
            print(f"SENT: HTTP {resp.status}, stored {body.get('stored')} items, {total} kcal")
            print(f"IDS: {', '.join(body.get('ids', []))}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except ValueError:
            body = {}
        meanings = {
            400: "the payload or an item is invalid",
            401: "wrong or missing username/password",
            409: "an item was already stored, or that person has not been added in the integration",
            413: "request or batch too large",
            500: "Home Assistant could not write the file; see its log",
            503: "the integration is not loaded",
        }
        print(f"ERROR: HTTP {e.code}, {meanings.get(e.code, e.reason)}. Nothing was stored.")
        if body:
            print(f"DETAILS: {json.dumps(body)}")
        deny = e.headers.get("x-deny-reason")
        if deny:
            print(f"BLOCKED BY SANDBOX NETWORK: {deny}")
        sys.exit(1)
    except (urllib.error.URLError, TimeoutError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, (TimeoutError,)) or "timed out" in str(reason):
            print(f"ERROR: Home Assistant did not reply in time ({reason}).")
            print("It may or may not have been stored. Do NOT resend automatically: "
                  "retries are not deduplicated. Check the Meals dashboard first.")
        else:
            print(f"ERROR: could not connect to Home Assistant ({reason}). Nothing was stored.")
        sys.exit(1)


if __name__ == "__main__":
    main()
