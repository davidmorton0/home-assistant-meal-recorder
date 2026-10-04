# Meal Recorder

A Home Assistant custom integration that records meals sent from a client on
the internet, stores them as CSV, and shows them on a Day and a Month
dashboard.

## What it does

- Adds a REST endpoint to Home Assistant, protected by HTTP Basic auth, for
  listing, storing, replacing and deleting food items.
- Stores them as CSV: a folder per person, a file per month
  (`config/meal_recorder/<person>/MM_YYYY.csv`).
- Publishes each person's day and month figures as entities.
- Adds a "Meals" page to the sidebar: person, month and day pickers, buttons to step a
  day or a month, and a card listing the day's items with add, edit and delete.

## Installing

1. In HACS, add this repository as a custom repository with the category
   **Integration**, install **Meal Recorder**, and restart Home Assistant.
2. Go to **Settings → Devices & services → Add integration → Meal Recorder**.
   Set the username and password the client will use, and the first person.
3. Add the other people in the integration's **Configure** dialog. Adding a
   person creates their entities, picks up any CSV files already stored for
   them, and adds them to the dashboard's person picker.

The integration adds a **Meals** page to the sidebar. It is part of the
integration, so it changes when the integration is updated and cannot be edited
in the UI; to lay things out your own way, build a dashboard from the entities
below and the item card (`custom:meal-recorder-card`).

## The REST endpoint

| Method | Path | What it does |
|---|---|---|
| `GET` | `/api/meal_recorder/items` | List items. |
| `POST` | `/api/meal_recorder/items` | Store one item or a batch. |
| `GET` | `/api/meal_recorder/items/{id}` | Read one item. |
| `PUT` | `/api/meal_recorder/items/{id}` | Replace one item. |
| `DELETE` | `/api/meal_recorder/items/{id}` | Delete one item. |

Every method takes the same HTTP Basic credentials, set when the integration was
added.

### Storing items

```sh
curl -u meals:secret \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"id":"0b6f3c1e-8a2d-4f1e-9c3b-5d7a2e4f6a10","created_at":"2026-09-24T08:15:00+01:00","person":"David","name":"Porridge with milk","meal":"breakfast","portion":"1 bowl","mass":250,"kcal":310,"protein":10.5,"carbohydrate":54.0,"fat":6.2}]}' \
  https://ha.example.com/api/meal_recorder/items
```

A bare JSON list, or a single item on its own, is accepted in place of
`{"items": [...]}`. One item stored gives a `Location` header holding its path.

| Field | Rule |
|---|---|
| `id` | A UUID the client makes, required. An id that is already stored, or repeated in the batch, is refused, so resending a batch does not store it twice. |
| `created_at` | ISO 8601. Without an offset it is read as a local time; with one it is moved to Home Assistant's time zone. |
| `person` | Required. The person must have been added in the integration. |
| `name` | Short text, required. |
| `meal` | `breakfast`, `lunch`, `dinner` or `snack`. |
| `portion` | Short free text, may be empty. |
| `mass`, `kcal`, `protein`, `carbohydrate`, `fat` | Numbers, not negative. Masses in grams. |

A batch is all or nothing: if any item is invalid, nothing is stored and the
reply says which items were wrong.

### Listing items

```sh
curl -u meals:secret 'https://ha.example.com/api/meal_recorder/items?person=David&date=2026-09-24'
```

| Parameter | Rule |
|---|---|
| `person` | Required. A person who has been added. |
| `date` | A day, `YYYY-MM-DD`. |
| `month` | A whole month, `YYYY-MM`. Not with `date`. |

Without `date` or `month`, today is listed. The reply holds `items`, `count` and
the `from` and `to` days it covers; each item holds the fields above, plus
`received_at`, the time its row was written. Times come back as they are
stored: local, with no offset. One person's items are listed at a time: ask
again for each person.

### Replacing and deleting an item

```sh
curl -u meals:secret -X PUT \
  -H 'Content-Type: application/json' \
  -d '{"created_at":"2026-09-24T08:15:00+01:00","name":"Porridge with soya milk","meal":"breakfast","portion":"1 bowl","mass":250,"kcal":280,"protein":9,"carbohydrate":52,"fat":5}' \
  https://ha.example.com/api/meal_recorder/items/0b6f3c1e-8a2d-4f1e-9c3b-5d7a2e4f6a10

curl -u meals:secret -X DELETE \
  https://ha.example.com/api/meal_recorder/items/0b6f3c1e-8a2d-4f1e-9c3b-5d7a2e4f6a10
```

`PUT` takes one item and replaces every field of the stored one, which keeps its
id and its person. `received_at` is the time the row was written, so it is set
again on every change. An `id` or `person` in the
body must match the stored item. Changing `created_at` to another month moves
the item to that month's file. The reply holds the item as it is now stored.

### Replies

| Status | Meaning |
|---|---|
| 200 | The item, or the list, is in the reply. |
| 201 | Stored. The reply gives the count and the identifiers. |
| 204 | Deleted. |
| 400 | The payload, an item or a list parameter is invalid. `person_required`: a list request named no person. |
| 401 | Wrong or missing credentials. |
| 404 | `not_found`: no item has that id. `unknown_person`: a `person` filter names someone who has not been added. |
| 409 | `duplicate_id`: an item's id is already stored (the reply lists them). `unknown_person`: the person has not been added in the integration. |
| 413 | The request or the batch is too large. |
| 500 | Writing failed; details are in the Home Assistant log. |

## Editing items

The Meals page shows one person's day, picked with the person, month and day
pickers or the buttons that step a day or a month. Its item list is a card that
comes with the integration (`custom:meal-recorder-card`), usable on any dashboard: each item has an edit
and a delete button, delete asks first, and **Add item** opens a form with the
date and time, so past days can be filled in. The card calls the
`meal_recorder.add_item`, `update_item` and `delete_item` actions, which check
items with the same rules as the endpoint.

## Food preferences for the skill

The food photo skill (`skill/food-to-home-assistant`) has a **User preferences**
section in its `SKILL.md`. Fill it in, in your installed copy of the skill, so
Claude identifies food and estimates nutrition the way you eat:

| Section | What to write |
|---|---|
| Dietary preferences | Vegan, vegetarian, or other diets. |
| Usual shops | The shops you buy from, so products can be identified. |
| Common items | Things you have often, such as your usual breakfasts or coffee. |
| Names for common meals | A name and what it contains, e.g. "my usual work lunch — cheese sandwich, apple, crisps". |

Replace the bracketed examples with your own. Sections can be left empty.

## Security

**Serve it over TLS.** Basic auth sends the same username and password on every
request, so on plain HTTP anyone who captures one request has the credential
for good. Any way of reaching Home Assistant from the internet works — Nabu
Casa, a port forward with a certificate, or a tunnel.

Only a hash of the password is stored. Wrong passwords go through Home
Assistant's own login-ban handling, so repeated attempts are banned and
notified like any other failed login. The credential records only: it cannot
read anything back.

## Entities

Per person:

| Entity | Holds |
|---|---|
| `sensor.meals_<person>_day` | The selected day's kcal, with the items grouped by meal and the totals in its attributes. |
| `sensor.meals_<person>_today_kcal` and the three macros | Today's totals, kept by Home Assistant as long-term statistics. |
| `sensor.meals_<person>_month` | The selected month's kcal, with totals, averages and days logged in its attributes. |
| `date.meals_day_shown` | The day the per-person Day and Month entities describe. |
| `select.meals_person`, `select.meals_year`, `select.meals_month`, `select.meals_day` | The person and day the dashboard shows. Shared by everyone, kept across restarts. |
| `button.meals_previous_day`, `_next_day`, `_previous_week`, `_next_week`, `_previous_month`, `_next_month` | Step the day shown. |
| `sensor.meals_day` | The day shown: its kcal, with every item and the totals in its attributes. |

The day and month entities follow the date control, so their attributes are not
recorded. If you want to keep their state changes out of your database as well,
exclude them in your `recorder:` configuration.

## Graphs

Each person's daily totals are also written to Home Assistant's long-term
statistics, from the CSV files rather than the sensors, so every recorded day
is there — including days filled in or corrected later. They are rewritten from
the changed day to today when an item is added, edited or deleted; from the
week shown to today when the Meals page shows a week that has a file; and for
today at midnight and at startup. A file edited by hand reaches the statistics
when its week is shown on the Meals page.

| Statistic | Unit |
|---|---|
| `meal_recorder:<person>_kcal` | kcal |
| `meal_recorder:<person>_protein`, `_carbohydrate`, `_fat` | g |

`<person>` is the folder name: lower case, spaces as underscores. They are
statistics, not entities, so only a statistics-graph card can draw them.

### Resetting statistics

To rewrite a person's statistics from the files, from a week to today, run
this in **Developer tools → Actions**, with the folder name and the Monday the
week starts on:

```yaml
action: meal_recorder.update_week_statistics
data:
  folder: david
  start: "2026-08-24"
```

Then move the graph to another week and back. Nothing is rewritten when the
person has no file for any day of that week.

A dashboard to paste into the raw configuration editor (dashboard → pencil →
three dots → **Raw configuration editor**), replacing `david` with the folder
name:

```yaml
title: Meals
views:
  - title: Week
    path: week
    cards:
      - type: energy-date-selection
      - type: statistics-graph
        title: kcal per day
        entities:
          - meal_recorder:david_kcal
        period: day
        stat_types:
          - change
        chart_type: bar
        energy_date_selection: true
      - type: statistics-graph
        title: Macros per day (g)
        entities:
          - meal_recorder:david_protein
          - meal_recorder:david_carbohydrate
          - meal_recorder:david_fat
        period: day
        stat_types:
          - change
        chart_type: bar
        energy_date_selection: true
  - title: Last 30 days
    path: month
    cards:
      - type: statistics-graph
        title: kcal per day
        entities:
          - meal_recorder:david_kcal
        period: day
        days_to_show: 30
        stat_types:
          - change
        chart_type: bar
      - type: statistics-graph
        title: Macros per day (g)
        entities:
          - meal_recorder:david_protein
          - meal_recorder:david_carbohydrate
          - meal_recorder:david_fat
        period: day
        days_to_show: 30
        stat_types:
          - change
        chart_type: bar
```

On the **Week** view, choose Week on the date card and step back with its
arrows. The **Last 30 days** view is fixed and needs no date card.

Watch out for these:

- `energy_date_selection: true` with no date card on the view shows today only.
- `days_to_show` is ignored once `energy_date_selection` is on.
- `change` and `state` both give a day's own amount; `sum` is the running total.
- The Energy dashboard does not have to be set up for the date card to work.
- A graph names its statistics, so each person needs their own cards.

## The data

`config/meal_recorder/<person>/MM_YYYY.csv`, one row per item, with a header
row. The person is not repeated in the rows — the folder says whose they are.

`created_at` and `received_at` hold the local clock reading, to the second,
with no UTC offset: `2026-09-24T08:15:00`. A time sent with an offset is moved
to Home Assistant's time zone before it is written, so the file always shows
the time on the wall. `received_at` is the time the row was written, set again
whenever the row is changed. Files written before this format carry an offset;
it is dropped as they are read, keeping the clock reading they hold, so old and
new rows sit in one file.
The files are the record of truth: edit one by hand and the change is picked up
on the next read. The folder is under `config`, so backups include it.

## Development

```sh
poetry install
poetry run pytest tests -q
```

The validation, storage, aggregation and hashing tests run without Home
Assistant installed; the endpoint and config flow tests need it.
