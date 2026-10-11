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

- If the user names a brand or product (e.g. "Tesco vegetable quarter pounders"), search the web for the manufacturer's label values and use them. Label values beat visual guesses, so prefer them whenever a product is named.
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
Logged dinner: 2 items, 750 kcal (likely 650–900)
- Tesco vegetable quarter pounder, 2 burgers: 460 kcal
- Jacket potato with margarine, 1 medium-large: 290 kcal
Protein 14 g · Carbohydrate 105 g · Fat 29 g
Least certain: margarine on the potato
```

- First line: the meal, the number of items stored and the total kcal, with a likely range in brackets.
- One line per item: name, portion (left out if empty, with the mass in grams instead), kcal.
- Then the total protein, carbohydrate and fat in grams.
- Last line: the least certain item and why, in a few words. Leave out the range and this line when every item came from a common item or a remembered item, since those numbers aren't new estimates.
- If the meal was logged for another person or another time, add it to the first line (e.g. "Logged lunch for Sam, yesterday 13:00: …").

If the user then corrects something (brand, vegan swaps, how it was cooked), update the stored item as in step 5 and show the new total. Don't send the meal again.
