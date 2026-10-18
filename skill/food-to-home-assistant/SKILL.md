---
name: food-to-home-assistant
description: Log food to the Meal Recorder integration in the user's Home Assistant, with calories, protein, carbohydrate and fat, from a photo, an earlier entry or a common item saved in project memory; also read back, correct and delete stored entries. Use whenever the user shares a photo of food, names something to log ("my usual porridge", "same as yesterday"), or asks what they've eaten or to change or delete an entry, even without mentioning Home Assistant.
---

# Food photo → Home Assistant

The user takes a photo of what they're eating, or names something they've had before. You work out what's on the plate and its nutrition, then send it to their Home Assistant so it can be logged and totalled there. Entries already stored can be listed, corrected and deleted as well (step 5), so a wrong entry is fixed afterwards rather than held back for checking first.

## User preferences

The user fills these in. Use them when identifying food and estimating nutrition.

### Dietary preferences

(e.g. vegan, vegetarian)

### Usual shops

(shops the user buys from, to help identify products)

### Common items and meals

Stored in project memory, in the formats in "Common items" and "Common meals" below, not here.

### Found foods sheet

A Google Sheet titled "Found foods" that holds branded products and foods found by earlier lookups (step 2). Its link is stored in project memory as `Found foods sheet: <link>`. It has three tabs:

| Tab | Columns | Holds |
|---|---|---|
| `Foods` | name, kcal, protein, carbohydrate, fat, source, added, count | One food per row, values per 100 g. `count` is how many times it has been logged. |
| `Sites` | site, type, found, not found, last used, notes | Every website used for a lookup, with how often it had the values. `type` is supermarket, manufacturer or other. |
| `Search` | A1: search terms; row 2: headers; A3: the search formula | The fast lookup: writing terms into A1 makes A3 list the matching `Foods` rows. |

Before the first lookup in a conversation, set it up:

1. **Tools:** load the Google Drive and Google Sheets tools. If the Sheets tools are missing, ask the user once to turn on the Google Sheets connector for this project (Drive alone can't add rows), and carry on without the sheet until they do.
2. **Link:** use the link in project memory. If there is none, search Drive for a spreadsheet titled "Found foods". If exactly one matches, use it; if several match, ask which one; if none match, create it with Drive `create_file` (`contentMimeType: application/vnd.google-apps.spreadsheet`, title "Found foods"). Save its link in project memory and tell the user, with the link.
3. **Tabs:** read the tab names with `get_spreadsheet` (`fields: ["sheets.properties"]`). Add any missing tab and write its header row as in the table. In `Search`, row 2 is `row, name, kcal, protein, carbohydrate, fat, source, added, count`, and A3 holds this formula (write it with `update_formulas`):

   ```
   =IF($A$1="","",IFERROR(ARRAY_CONSTRAIN(SORT(FILTER({ROW(Foods!A2:A),Foods!A2:H},REGEXMATCH(LOWER(Foods!A2:A),LOWER($A$1))),9,FALSE),30,9),"no match"))
   ```

   It lists up to 30 matching rows, most-logged first, with each row's number in `Foods` in the first column.

## Step 1: Identify the food

The food can come from three places, and one meal can mix them:

- **A photo:** identify it as below.
- **A remembered item**, something already logged ("same as yesterday's breakfast", "the curry from Tuesday"): see "Remembered items" below.
- **A common item or meal** saved in project memory ("my usual porridge", "work lunch"): see "Common items" and "Common meals" below.

Remembered and common items already have their nutrition, so skip step 2 for them.

For a photo, look at the photo and list each distinct item with an estimated portion (grams or a household measure like "1 medium potato"). Use visual cues for size: plate diameter (a standard dinner plate is about 26–27 cm), cutlery, and how much of the plate each item covers.

### Remembered items

1. Work out the date the user means ("yesterday", "Tuesday") and run `list --date YYYY-MM-DD` (step 5). Use `--month` if they only give a rough time.
2. Pick the items that match what they described, using the meal and the name. If several could match, ask which one.
3. `list` only shows kcal, so run `get <id>` for each chosen item to get its `name`, `portion`, `mass`, `kcal`, `protein`, `carbohydrate` and `fat`.
4. Copy those fields into a new meal file. Leave out `id` (the script gives new ones; reusing an old id is refused as a duplicate) and leave out `created_at` unless the user says when they ate it. Scale every number if the user says the amount differed ("half of yesterday's curry").

### Common items

Common items are saved in project memory, one memory entry per item, in this format:

```
Common item: Porridge
Also called: my porridge, usual breakfast
Name: Porridge (Tesco oats, Alpro soya milk)
Portion: 1 bowl
Meal: breakfast
Variables:
  oats = 40 g
  milk = 200 ml
Per 100 g or ml:
  oats: kcal 375, protein 11, carbohydrate 60, fat 8
  milk: kcal 39, protein 3.3, carbohydrate 2.5, fat 1.8
```

- Each variable is the amount of one ingredient, with its usual value as the default. The user can change it when logging ("porridge with 60 g oats"); otherwise use the default.
- Each nutrient = the sum over variables of amount × per-100 value ÷ 100. `mass` = the sum of the amounts (treat 1 ml as 1 g). Round as in step 2.
- If a variable changes the size, say so in `portion` (e.g. "1 bowl, 60 g oats").
- An item with a fixed size has one variable for the whole item (e.g. `bar = 45 g`) with its label values per 100 g.
- `Meal` is the usual meal; use the time of day or what the user says if it differs.
### Common meals

A common meal is a group of common items logged together. It is saved in project memory as its own entry, one entry per meal, in this format:

```
Common meal: Work lunch
Also called: my usual lunch, office lunch
Meal: lunch
Items:
  Hummus wrap
  Apple
  Porridge: oats = 30 g, milk = 150 ml
```

- Each line under `Items` is the `Common item` name of an entry that already exists. Save any missing item as a common item first.
- A line can set variables for that item in this meal (`Porridge: oats = 30 g`). Variables not set use the item's defaults.
- The same item twice means two rows; list it twice rather than doubling its variables.
- When logging, work out each item as in "Common items" and send them all in one meal file, one row per item, with the meal from `Meal`. The user can change or drop items when logging ("work lunch without the apple"), and the saved meal stays as it is.

### Saving and changing common items and meals

When the user asks to save something ("remember this as my usual porridge", "save this as work lunch"), write a memory entry in the matching format: a common item from one food's ingredients, a common meal from several foods. Use label values where the user has named products. Show the entry to the user once it's saved. To change one, edit its existing entry rather than adding another.

## Step 2: Estimate nutrition per item

For each item estimate mass (grams), kcal, protein, carbohydrate and fat (grams).

Look every item up, whether the user named it or you identified it from a photo. Sort the items into two kinds:

- **Named products:** a brand or product the user named, or one you can read on the packaging in a photo ("Tesco vegetable quarter pounders").
- **Basic items:** generic foods and ingredients (boiled potatoes, apple, rice).

Then look them up in this order, all of a meal's items together at each stage, and stop for an item as soon as it is found:

1. **Basic items only, `foods/cofid.csv`:** the UK government food tables, values per 100 g. Search for all basic items in one command, e.g. `grep -i -E 'potatoes, old, boiled|apples, eating' foods/cofid.csv`. Basic items not found go on to stage 2 with the named products.
2. **The found foods sheet, `Foods` tab:** write all the items' search terms into `Search!A1` as one pattern (`update_values`, e.g. `quarter pounder|soya milk`), then read `Search!A3:I32` with `get_values`. Send the stage 1 search in the same response as the write. When several rows fit, pick the one logged most (the rows come most-logged first) unless another is clearly a closer match.
3. **Open Food Facts:** for items still not found, run every search in one command: `python /path/to/skill/scripts/food_search.py "vegetable quarter pounders" "soya milk unsweetened" --brand tesco` (leave out `--brand` for other brands or basic items). It prints the top 5 UK matches with values per 100 g and the product URL. If it prints "BLOCKED BY SANDBOX NETWORK", tell the user once to add `search.openfoodfacts.org` to the allowed domains for code execution, and go on to stage 4.
4. **Websites:** for items still not found, read the `Sites` tab first, then try in this order: the supermarket's site (from "Usual shops"), the manufacturer's site, then any other site that gives the label values. Prefer sites with more `found`, and skip a site whose `not found` is well above its `found`. Send the searches for all items as parallel tool calls in one response. After each site is tried, update its row in `Sites` (add 1 to `found` or `not found`, set `last used` to today) or append a new row for a new site.

After stage 3 or 4 finds a food, append it to `Foods` with `append_values` (range `Foods!A1`): the name with its brand, the four values per 100 g as numbers, the source URL, today's date as text with a leading apostrophe (`'2026-10-18`, so it isn't turned into a date), and count 1. After logging an item found in the sheet, set its `count` (`Foods!H<row>`, using the row number from `Search`) to one more than before. If nothing is found at any stage, estimate the values. Without the Sheets tools, skip stage 2 and the writes, and log the meal anyway.

Scale the per-100 g values to the portion. Label values beat visual guesses, so prefer a found product's values whenever a product is named.
- If the user tells you about ingredient swaps (margarine instead of butter, soya milk, nutritional yeast instead of cheese, vegan versions), re-estimate those items. Swaps like these can change a dish's calories a lot, so don't just keep the old number.
- Note cooking fat if relevant (about 100 kcal per tablespoon of oil or spread).
- Round sensibly: kcal to the nearest 5, macros to whole grams. These are estimates and false precision misleads.

## Step 3: Send straight away, unless the food is genuinely unclear

Stored items can be corrected afterwards (step 5), so for most meals go straight to step 4 and send without asking.

Ask first only when there is significant uncertainty about what the food is: for example, you can't tell what an item is, or a hidden detail (a filling, a sauce, whether it's a vegan version) would change the numbers a lot. Uncertain portion sizes alone are not a reason to ask. If you do ask, keep it to one short question about the uncertain item, then send.

Don't introduce terms or acronyms without defining them.

## Step 4: Send to Home Assistant

The user's Home Assistant runs the Meal Recorder integration (https://github.com/davidmorton0/home-assistant-meal-recorder), which stores each food item as a row in a monthly diary file and shows it on a Meals dashboard.

Write a meal file and run the send script:

```json
{
  "meal": "dinner",
  "items": [
    {"name": "Tesco vegetable quarter pounder", "portion": "2 burgers", "mass": 212, "kcal": 460, "protein": 8, "carbohydrate": 55, "fat": 21},
    {"name": "Jacket potato with margarine", "portion": "1 medium-large", "mass": 260, "kcal": 290, "protein": 6, "carbohydrate": 50, "fat": 8}
  ]
}
```

- `meal` is one of breakfast, lunch, dinner, snack. Infer it from the time of day or what the user said; ask only if it's genuinely unclear.
- `mass` is the portion weight in grams and is required for every item, so always estimate it.
- `portion` is a household measure ("2 burgers", "1 bowl"). If the amount is only a mass ("150 g"), set `portion` to `""`: the mass is already in `mass`, and repeating it shows the weight twice.
- Nutrient numbers: `kcal`, and `protein`, `carbohydrate`, `fat` in grams. Numbers only, never text.
- `name` up to 200 characters, `portion` up to 100. Put brand and key swaps in the name (e.g. "Vegan cauliflower cheese (soya milk)"), because there is no notes field.
- `created_at` (optional): an ISO 8601 time with offset, e.g. `2026-09-24T13:00:00+01:00`. Omit it when the user is logging a meal as they eat it, and the script uses the current time. Set it when they say when they ate (e.g. "this was lunch yesterday").
- `person` (optional): only if the user says the meal is someone else's. Omitted means the `person` in `config.json`, the user's own name. Every item is sent with a person; Home Assistant refuses items without one.

```bash
python /path/to/skill/scripts/send_to_ha.py send meal.json
```

The script gives each item an id and saves it into the meal file before sending. `--dry-run` checks the file and prints what would be sent without sending. The script reads the Home Assistant address, username, password and the user's name (`person`) from `config.json` in the skill folder.

A batch is all or nothing: if any item is rejected, nothing is stored.

### If sending fails

Report what the script printed, plainly. By cause:

- **"BLOCKED BY SANDBOX NETWORK":** the user's Home Assistant domain isn't in the allowed domains list for code execution in Claude's settings.
- **401:** wrong username or password in `config.json`. Repeated failures get the address banned by Home Assistant, so don't retry; ask the user to check.
- **409 with `duplicate_id`:** those items are already stored, usually because this meal file was sent before. Nothing new was stored; tell the user it's already logged.
- **409 with `unknown_person`:** the person hasn't been added in the integration's Configure dialog.
- **400:** the details say which item and field; fix it and send again (nothing was stored).
- **"could not connect":** nothing was stored; check the address and that Home Assistant is up.
- **"did not reply in time":** the meal may have been stored. Check with `get <id>`, using an id the script printed, before doing anything else. Sending the same meal file again is also safe: the script saved an id for each item in it, and Home Assistant refuses ids it already has (409 `duplicate_id`, meaning it was stored the first time). Never write a new meal file for a resend, because new ids would store it twice.
- **config.json placeholders:** ask the user for their Home Assistant address, the integration's username and password, and their name as added in the integration.

Still show the user the analysis even if sending fails, so the work isn't lost.

## Step 5: Reading, correcting and deleting stored items

The endpoint is a REST endpoint, so items already stored can be read, replaced and deleted. The same script does it:

```bash
python scripts/send_to_ha.py list                             # the user, today
python scripts/send_to_ha.py list --person David --date 2026-09-24
python scripts/send_to_ha.py list --month 2026-09
python scripts/send_to_ha.py get <id>
python scripts/send_to_ha.py update <id> fixed.json
python scripts/send_to_ha.py delete <id>
```

- `list` and `get` answer questions about what was eaten ("what have I had today", "how many calories so far", "what did I log yesterday"). `list` prints one line per item ending in its id, and a total. It lists one person at a time: without `--person` it lists the user, and another person's items need `--person NAME`.
- `update` takes a meal file holding **exactly one item**, in the same shape as a meal file for sending, and replaces every field of the stored item. The item keeps its id and its person, so don't put them in the file. Changing `created_at` moves the item to another day or month.
- To correct one item of a meal already sent, get its id from `list`, write a one-item meal file with the corrected numbers, and `update`. Don't send the meal again: that stores it twice.
- `delete` removes one item. Ask the user before deleting anything, unless they named the item to delete.

## Step 6: Show the user what was logged

After a successful send, reply in exactly this format. Keep it short, since the user is usually on a phone:

```
Logged dinner: 2 items, 750 kcal
- Tesco vegetable quarter pounder, 2 burgers: 460 kcal
- Jacket potato with margarine, 1 medium-large: 290 kcal
Protein 14 g · Carbohydrate 105 g · Fat 29 g
```

- First line: the meal, the number of items stored and the total kcal.
- One line per item: the name as logged (the food's name from the table, sheet or site it came from), portion (left out if empty, with the mass in grams instead), kcal.
- Then the total protein, carbohydrate and fat in grams.
- Only when the whole meal's kcal could be more than 20% above or below the total: add the likely range to the first line (`750 kcal (likely 550–950)`) and end with a line naming the items that make it uncertain and why, in a few words (`Uncertain: amount of margarine on the potato`). Otherwise leave both out.
- If the meal was logged for another person or another time, add it to the first line (e.g. "Logged lunch for Sam, yesterday 13:00: …").

If the user then corrects something (brand, vegan swaps, how it was cooked), update the stored item as in step 5 and show the new total. Don't send the meal again.
