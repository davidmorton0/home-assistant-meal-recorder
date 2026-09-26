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
- Adds a "Meals" dashboard built from standard cards.

## Installing

1. In HACS, add this repository as a custom repository with the category
   **Integration**, install **Meal Recorder**, and restart Home Assistant.
2. Go to **Settings → Devices & services → Add integration → Meal Recorder**.
   Set the username and password the client will use, and the default person —
   the person items are filed under when a request does not name one.
3. Add the other people in the integration's **Configure** dialog. Adding a
   person creates their entities, picks up any CSV files already stored for
   them, and adds their tab to the dashboard.

The **Meals** dashboard is created during that first setup, and after that the
only thing written to it is a new person's tab. A tab is made once and never
remade, so your edits — and any tab you delete — stand, and a later version's
dashboard improvements do not reach an existing install. If a
dashboard already exists at `/meal-recorder`, it is left exactly as it is and
the generated configuration is written to `config/meal_recorder/dashboard.json`
instead, for you to paste into a dashboard's raw configuration editor.

## Recording items

```sh
curl -u meals:secret \
  -H 'Content-Type: application/json' \
  -d '{"items":[{"created_at":"2026-09-24T08:15:00+01:00","person":"David","name":"Porridge with milk","meal":"breakfast","portion":"1 bowl","mass":250,"kcal":310,"protein":10.5,"carbs":54.0,"fat":6.2}]}' \
  https://ha.example.com/api/meal_recorder/items
```

A bare JSON list is accepted in place of `{"items": [...]}`.

| Field | Rule |
|---|---|
| `created_at` | ISO 8601. Without an offset it is read in Home Assistant's time zone. |
| `person` | Optional. Omitted means the default person. The person must have been added in the integration. |
| `name` | Short text, required. |
| `meal` | `breakfast`, `lunch`, `dinner` or `snack`. |
| `portion` | Short free text, may be empty. |
| `mass`, `kcal`, `protein`, `carbs`, `fat` | Numbers, not negative. Masses in grams. |

A batch is all or nothing: if any item is invalid, nothing is stored and the
reply says which items were wrong.

| Status | Meaning |
|---|---|
| 201 | Stored. The reply gives the count and the identifiers. |
| 400 | The payload or an item is invalid. |
| 401 | Wrong or missing credentials. |
| 409 | The person has not been added in the integration. |
| 413 | The request or the batch is too large. |
| 500 | Writing failed; details are in the Home Assistant log. |

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
| `sensor.meals_<person>_today_kcal` and the three macros | Today's totals. Home Assistant keeps these as long-term statistics, and the month chart is drawn from them — so the chart starts at installation, and days that only exist in the CSV files are not on it. |
| `sensor.meals_<person>_month` | The selected month's kcal, with totals, averages and days logged in its attributes. |
| `date.meals_day_shown` | The day the Day view shows. One control, shared by everyone. |

The day and month entities follow the date control, so their attributes are not
recorded. If you want to keep their state changes out of your database as well,
exclude them in your `recorder:` configuration.

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
