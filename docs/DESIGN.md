# Meal Recorder for Home Assistant — Design Document

Status: Draft
Date: 2026-09-24

## 1. Summary

Meal Recorder is a Home Assistant custom integration, installable through HACS. A client on the internet posts food items to it over HTTP; it stores them as CSV, one file per month, and shows them on a Day dashboard and a Month dashboard.

## 2. Requirements

| # | Requirement |
|---|-------------|
| R1 | Endpoint on Home Assistant, reachable from the internet, using Basic auth |
| R2 | Endpoint accepts a list of items: created at, person, name, meal (breakfast/lunch/dinner/snack), portion, mass, kcal, protein, carbs, fat |
| R3 | Items stored in CSV, one file per month |
| R4 | Day dashboard: one day, items grouped by meal, totals per meal and per day |
| R5 | Month dashboard: graph of total kcal and other nutritional totals per day |
| R6 | Installable through HACS |
| R7 | Use the existing git repository in this folder (not yet pushed or linked to a remote) |

## 3. Exposing the endpoint (R1)

The integration adds one endpoint to the web server Home Assistant already runs. Reaching it from the internet is whatever the user already does to reach Home Assistant; the integration does not change that.

- **It must be served over TLS.** Basic auth sends the same username and password on every request, so on plain HTTP anyone who captures one request has the credential for good. The README will say so.
- **The integration checks the credential itself**, because Home Assistant's own API accepts only bearer tokens and would reject the request before the integration saw it.
- **Only a hash of the password is stored**, since configuration data is kept in plain text.
- **Wrong passwords go to Home Assistant's login-ban handling**, so repeated attempts get the same ban and notification as failed logins to Home Assistant itself.
- **The credential records only.** It cannot read anything back, so a client that is compromised gives away the ability to add items, not the history.
- **Oversized requests are refused** before anything is parsed, by a cap on the request size and on the number of items in a batch.

## 4. Recording items (R2)

A client sends a batch of items to the endpoint.

1. Every item is checked against the field rules below. If any item fails, nothing is stored and the reply says which items were wrong and why. A batch is all or nothing, so a client never has to work out how much of its batch went in.
2. Each accepted item is given an identifier and a received-at time.
3. The person and the created-at time decide which file an item belongs to — the person's folder, and the month read in Home Assistant's time zone. Items are grouped that way and appended to those files. A batch naming someone who has not been added is refused, so a typed name cannot quietly start a new person.
4. The reply confirms how many items were stored, or reports a storage failure, which is also logged.

Retries are not deduplicated, so a client that retries after a timeout can create a duplicate row.

### Fields

| Field | Rule |
|-------|------|
| created at | ISO 8601; without an offset it is read in Home Assistant's time zone |
| person | short text; omitted means the default person set when the integration is configured |
| name | short text |
| meal | breakfast, lunch, dinner or snack |
| portion | short free text, e.g. "1 cup" |
| mass, kcal, protein, carbs, fat | numbers, not negative; masses in grams |

All fields except person are required. A batch is a JSON list of items:

```json
{
  "items": [
    {
      "created_at": "2026-09-24T08:15:00+01:00",
      "person": "David",
      "name": "Porridge with milk",
      "meal": "breakfast",
      "portion": "1 bowl",
      "mass": 250,
      "kcal": 310,
      "protein": 10.5,
      "carbs": 54.0,
      "fat": 6.2
    }
  ]
}
```

## 5. Storage (R3)

One directory under the Home Assistant configuration folder, so backups include it, with a folder per person inside it and one file per month in each:

```
meal_recorder/
  david/
    09_2026.csv
    10_2026.csv
  sam/
    10_2026.csv
```

The folder is named after the person, normalised to be usable as a folder name: lower-cased, spaces turned into underscores, anything else dropped. The integration keeps each folder's person name in its own configuration, so a new person whose name normalises onto an existing person's folder is refused when they are added, rather than two people's items quietly merging into one file. The file is named MM_YYYY.csv, and the month comes from the item's created-at time in Home Assistant's time zone, not UTC. A file has a header row and one row per item, holding the fields above plus the identifier and the received-at time. The person is not repeated in the rows, because the folder already says whose they are — so a file moved out of its folder no longer says who it belongs to.

One person's data can be archived, moved or deleted on its own, and a month's file stops growing once the month ends.

Rows are appended in arrival order and sorted on read. Writes are serialised, so batches arriving at once cannot interleave. A malformed row is skipped and logged rather than failing the whole file.

The CSV files are the record of truth. Everything shown in Home Assistant is derived from them, and a file edited by hand is picked up on the next read.

## 6. Publishing to Home Assistant

1. For each person, the integration reads the month file in that person's folder, takes the selected day's rows, groups them by meal, and adds up each meal and the day.
2. It publishes these as entities, one set per person, so one person's figures never include another's:

| Entity | Holds |
|--------|-------|
| Day | State is the day's kcal. Its attributes hold that day's items grouped by meal — time, name, portion, mass and the four nutrition figures — and the totals per meal and for the day. |
| Daily totals (four) | Plain numbers for kcal, protein, carbs and fat. These always describe today. |
| Month | State is the month's kcal. Its attributes hold the month's totals, averages and the number of days with items. |
| Date control | The day the Day entity describes. One control, shared by everyone. |

   An entity's state is a short piece of text, which is why a day's item list goes in attributes rather than in the state, and the totals are separate numeric entities rather than attributes: Home Assistant records numbers over time, and that recorded history is what a chart can draw.
3. Changing the date control makes the integration re-read and re-publish the Day entity for every person.
4. People are created in the integration, not by the requests. Adding one gives them entities, picks up any files already stored for them, and adds their view to the dashboard.
5. Home Assistant records the four daily totals over time, and the month chart is drawn from that record. This is why they always describe today rather than the selected day: if they followed the date control, picking a day last month would be recorded as today's intake and the chart's history would be wrong. The Day and Month entities do follow the control, so their attributes are not recorded, and the README says how to keep their states out of the database too.

Because this lives in entities rather than in a per-user view, the day being viewed is shared between users and devices, and every person's data is visible to everyone with a Home Assistant login. Tying a view to the person logged in would need each card to know who is looking, which standard cards cannot do; it can be revisited later.

## 7. Dashboards (R4, R5)

The integration ships a dashboard as a starting point. It is an ordinary Home Assistant dashboard built from standard cards, so the user can rearrange it, restyle it, delete parts of it, or copy pieces into a dashboard they already have. Every card reads an entity from §6 — no card talks to the integration directly, which is why there is no custom frontend code and nothing extra to install.

- **Day.** One tab per person, each showing one day, chosen with the date control, defaulting to today. Items grouped by meal in the order breakfast, lunch, dinner, snack, each row showing time, name, portion, mass and the four nutrition figures, with totals per meal and for the day. A meal with nothing in it is shown as empty rather than hidden, so a missed meal is visible.
- **Month.** In the same tab, one month for that person: a chart of daily kcal and macronutrient totals across the month, and the month's totals and averages. Averages are over days that have items, so days that were never logged do not drag them down. A day with no items reads as absent rather than as a genuine zero.

Numbers are rounded for display; the stored values keep whatever precision the client sent. The month chart shows the daily totals as Home Assistant has recorded them. Those are kept indefinitely, but they only start when the integration is installed, so days that exist only in the CSV files — earlier ones, or ones edited by hand afterwards — are missing from the chart.

## 8. Installation and setup (R6, R7)

1. The repository is added to HACS as a custom repository and the integration installed from it, then Home Assistant is restarted. Once the repository is in the HACS default store this becomes a plain search-and-install; getting there needs the repository to be public, which the local repository (R7) is not yet — it has no remote.
2. The integration is added from Home Assistant's integrations page, where the user sets the username and password the client will use and the name of the first person, who is also the person items are filed under when a request does not name one. Further people are added the same way, in the integration's options. There is no YAML configuration.
3. On first run it creates its storage folder, publishes its entities, and adds its dashboard.
4. The user makes Home Assistant reachable from the internet (§3) and points the client at the endpoint with those credentials.
5. The password can be changed later from the integration's options; the client then has to be updated. Removing the integration leaves the CSV files in place.
6. The dashboard is created at setup, and only if nothing is there already — a dashboard the user has at that address is never written over. After that the only thing written to it is a new person's view, appended when that person is added. A view is made once and never remade, so edits and deletions stand, and a new version's dashboard improvements do not reach an existing install.

## 9. Not included

Editing or deleting items, food lookup or nutrient calculation, and per-person access control.
