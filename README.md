# Meal Recorder

A Home Assistant custom integration that records meals sent from a client on
the internet, stores them as CSV, and shows them on a Day and a Month
dashboard.

## What it does

- Adds an endpoint to Home Assistant, protected by HTTP Basic auth, that
  accepts a batch of food items.
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

## Recording items

```sh
curl -u meals:secret \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"id":"0b6f3c1e-8a2d-4f1e-9c3b-5d7a2e4f6a10","created_at":"2026-09-24T08:15:00+01:00","person":"David","name":"Porridge with milk","meal":"breakfast","portion":"1 bowl","mass":250,"kcal":310,"protein":10.5,"carbohydrate":54.0,"fat":6.2}]}' \
  https://ha.example.com/api/meal_recorder/items
```

A bare JSON list is accepted in place of `{"items": [...]}`.

| Field | Rule |
|---|---|
| `id` | A UUID the client makes, required. An id that is already stored, or repeated in the batch, is refused, so resending a batch does not store it twice. |
| `created_at` | ISO 8601. Without an offset it is read in Home Assistant's time zone. |
| `person` | Required. The person must have been added in the integration. |
| `name` | Short text, required. |
| `meal` | `breakfast`, `lunch`, `dinner` or `snack`. |
| `portion` | Short free text, may be empty. |
| `mass`, `kcal`, `protein`, `carbohydrate`, `fat` | Numbers, not negative. Masses in grams. |

A batch is all or nothing: if any item is invalid, nothing is stored and the
reply says which items were wrong.

| Status | Meaning |
|---|---|
| 201 | Stored. The reply gives the count and the identifiers. |
| 400 | The payload or an item is invalid. |
| 401 | Wrong or missing credentials. |
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
is there — including days filled in or corrected later. They are rewritten on
every change, at midnight, and at startup.

| Statistic | Unit |
|---|---|
| `meal_recorder:<person>_kcal` | kcal |
| `meal_recorder:<person>_protein`, `_carbohydrate`, `_fat` | g |

`<person>` is the folder name: lower case, spaces as underscores. They are
statistics, not entities, so only a statistics-graph card can draw them.

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
The files are the record of truth: edit one by hand and the change is picked up
on the next read. The folder is under `config`, so backups include it.

## Development

```sh
poetry install
poetry run pytest tests -q
```

The validation, storage, aggregation and hashing tests run without Home
Assistant installed; the endpoint and config flow tests need it.
