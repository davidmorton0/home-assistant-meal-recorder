#!/usr/bin/env python3
"""Store, list, correct and delete meals in the Meal Recorder integration.

It talks to the integration's REST endpoint, /api/meal_recorder/items.

Usage:
  python send_to_ha.py send meal.json [--dry-run]   store a meal
  python send_to_ha.py list [--person NAME] [--date YYYY-MM-DD | --month YYYY-MM]
                                                    list items, one person at a time
  python send_to_ha.py get ID                       read one stored item
  python send_to_ha.py update ID meal.json          replace one stored item
  python send_to_ha.py delete ID                    delete one stored item

meal.json, for send and update:
{
  "meal": "dinner",                          # breakfast | lunch | dinner | snack
  "created_at": "2026-09-24T18:30:00+01:00", # optional, defaults to now
  "person": "David",                         # optional, defaults to "person" in config.json
  "items": [
    {"name": "...", "portion": "...", "mass": 212, "kcal": 460,
     "protein": 8, "carbohydrate": 55, "fat": 21}   # "id" is added by this script
  ]
}

update takes a meal file holding exactly one item, and replaces every field of
the stored item with it. The item keeps its id and its person.
"""
import argparse
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CONFIG = Path(__file__).resolve().parent.parent / "config.json"
ENDPOINT = "/api/meal_recorder/items"
MEALS = ["breakfast", "lunch", "dinner", "snack"]
NUMBERS = ["mass", "kcal", "protein", "carbohydrate", "fat"]
LIMITS = {"name": 200, "portion": 100, "person": 100}


def build_items(meal, own_name=""):
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

    person = (meal.get("person") or own_name or "").strip()
    if not person or person == "YOUR-NAME":
        problems.append("no person: set person in the meal file or in config.json")
    elif len(person) > LIMITS["person"]:
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
        item = {"id": raw.get("id"), "created_at": created_at, "person": person,
                "name": name, "meal": meal_type, "portion": portion}
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


def load_config():
    cfg = json.loads(CONFIG.read_text())
    base = cfg.get("base_url", "").rstrip("/")
    user, pw = cfg.get("username", ""), cfg.get("password", "")
    if not base or "YOUR-DOMAIN" in base or not user or not pw or "CHANGE-ME" in pw:
        print("ERROR: base_url, username and password in config.json are not set.")
        sys.exit(1)
    return cfg, base, user, pw


def read_meal(path, cfg):
    """The items in a meal file, or exit saying what is wrong with it."""
    items, problems = build_items(json.loads(Path(path).read_text()), cfg.get("person", ""))
    if problems:
        print("ERROR: not sent, the meal file has problems:")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)
    return items


def request(method, path, payload=None, note=""):
    """Call the endpoint. Returns (status, body); prints and exits on failure."""
    cfg, base, user, pw = load_config()
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except ValueError:
            body = {}
        meanings = {
            400: "the payload, an item or a filter is invalid",
            401: "wrong or missing username/password",
            404: "no item has that id, or that person has not been added",
            405: "that method is not allowed on that path",
            409: "an item was already stored, or that person has not been added in the integration",
            413: "request or batch too large",
            500: "Home Assistant could not write the file; see its log",
            503: "the integration is not loaded",
        }
        print(f"ERROR: HTTP {e.code}, {meanings.get(e.code, e.reason)}. Nothing was changed.")
        if body:
            print(f"DETAILS: {json.dumps(body)}")
        deny = e.headers.get("x-deny-reason")
        if deny:
            print(f"BLOCKED BY SANDBOX NETWORK: {deny}")
        sys.exit(1)
    except (urllib.error.URLError, TimeoutError) as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason):
            print(f"ERROR: Home Assistant did not reply in time ({reason}).")
            if note:
                print(note)
        else:
            print(f"ERROR: could not connect to Home Assistant ({reason}). Nothing was changed.")
        sys.exit(1)


def show(item):
    """One stored item on one line."""
    created = item.get("created_at", "")[:16].replace("T", " ")
    portion = f" ({item['portion']})" if item.get("portion") else ""
    print(f"{created}  {item.get('meal', ''):9}  {item.get('name', '')}{portion}"
          f"  {item.get('kcal')} kcal  {item.get('id')}")


def do_send(args):
    cfg, *_ = load_config()
    meal_file = Path(args.meal_file)
    meal = json.loads(meal_file.read_text())
    if not args.dry_run:
        # Each item keeps its id in the meal file, so sending the file again is
        # refused as a duplicate instead of storing the meal twice.
        for raw in meal.get("items") or []:
            if isinstance(raw, dict) and not raw.get("id"):
                raw["id"] = str(uuid.uuid4())
        meal_file.write_text(json.dumps(meal, indent=2))

    items, problems = build_items(meal, cfg.get("person", ""))
    if problems:
        print("ERROR: not sent, the meal file has problems:")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)

    total = round(sum(item["kcal"] for item in items))
    if args.dry_run:
        print(json.dumps({"items": items}, indent=2))
        print(f"DRY RUN: {len(items)} items, {total} kcal, not sent")
        return

    ids = ", ".join(item["id"] for item in items)
    status, body = request(
        "POST", ENDPOINT, {"items": items},
        note="It may or may not have been stored. Check with: "
             f"send_to_ha.py get {items[0]['id']}",
    )
    print(f"SENT: HTTP {status}, stored {body.get('stored')} items, {total} kcal")
    print(f"IDS: {ids}")


def do_list(args):
    cfg, *_ = load_config()
    # The endpoint lists one person at a time, so without --person it is the
    # user's own name from config.json.
    query = [f"person={urllib.parse.quote(args.person or cfg.get('person', ''))}"]
    if args.date:
        query.append(f"date={args.date}")
    if args.month:
        query.append(f"month={args.month}")
    path = ENDPOINT + ("?" + "&".join(query) if query else "")
    _, body = request("GET", path)
    for item in body.get("items", []):
        show(item)
    total = round(sum(item.get("kcal", 0) for item in body.get("items", [])))
    print(f"{body.get('count', 0)} items, {total} kcal, {body.get('from')} to {body.get('to')}")


def do_get(args):
    _, body = request("GET", f"{ENDPOINT}/{args.id}")
    show(body)
    print(json.dumps(body, indent=2))


def do_update(args):
    cfg, *_ = load_config()
    items = read_meal(args.meal_file, cfg)
    if len(items) != 1:
        print(f"ERROR: update needs a meal file holding one item, this one holds {len(items)}.")
        sys.exit(1)
    # The stored item keeps its id and its person, so neither is sent.
    item = {key: value for key, value in items[0].items() if key not in ("id", "person")}
    status, body = request(
        "PUT", f"{ENDPOINT}/{args.id}", item,
        note=f"It may or may not have been changed. Check with: send_to_ha.py get {args.id}",
    )
    print(f"UPDATED: HTTP {status}")
    show(body)


def do_delete(args):
    status, _ = request(
        "DELETE", f"{ENDPOINT}/{args.id}",
        note=f"It may or may not have been deleted. Check with: send_to_ha.py get {args.id}",
    )
    print(f"DELETED: HTTP {status}, {args.id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command")

    send = commands.add_parser("send", help="store a meal")
    send.add_argument("meal_file")
    send.add_argument("--dry-run", action="store_true")
    send.set_defaults(run=do_send)

    listing = commands.add_parser("list", help="list stored items")
    listing.add_argument("--person", help="defaults to person in config.json")
    listing.add_argument("--date", help="a day, YYYY-MM-DD")
    listing.add_argument("--month", help="a month, YYYY-MM")
    listing.set_defaults(run=do_list)

    get = commands.add_parser("get", help="read one stored item")
    get.add_argument("id")
    get.set_defaults(run=do_get)

    update = commands.add_parser("update", help="replace one stored item")
    update.add_argument("id")
    update.add_argument("meal_file")
    update.set_defaults(run=do_update)

    delete = commands.add_parser("delete", help="delete one stored item")
    delete.add_argument("id")
    delete.set_defaults(run=do_delete)

    # A meal file on its own still sends it, as earlier versions did.
    argv = sys.argv[1:]
    if argv and argv[0] not in commands.choices and not argv[0].startswith("-"):
        argv = ["send", *argv]
    args = parser.parse_args(argv)
    if not getattr(args, "run", None):
        parser.print_help()
        sys.exit(2)
    args.run(args)


if __name__ == "__main__":
    main()
