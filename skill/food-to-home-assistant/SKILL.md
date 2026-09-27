---
name: food-to-home-assistant
description: Analyse a photo of a meal (identify each food, estimate portion, calories, protein, carbohydrate, fat) and send the food list plus the analysis to the Meal Recorder integration in the user's Home Assistant as a food diary entry. Use this skill whenever the user shares a photo of food, a plate, a meal or a snack, or asks "how many calories", "log this meal", "track this", or "send to Home Assistant", even if they don't mention Home Assistant explicitly.
---

# Food photo → Home Assistant

The user takes a photo of what they're eating. You work out what's on the plate and its nutrition, check it with them, then send it to their Home Assistant so it can be logged and totalled there.

## Step 1: Identify the food

Look at the photo and list each distinct item with an estimated portion (grams or a household measure like "1 medium potato"). Use visual cues for size: plate diameter (a standard dinner plate is about 26–27 cm), cutlery, and how much of the plate each item covers.

## Step 2: Estimate nutrition per item

For each item estimate mass (grams), kcal, protein, carbohydrate and fat (grams).

- If the user names a brand or product (e.g. "Tesco vegetable quarter pounders"), search the web for the manufacturer's label values and use them. Label values beat visual guesses, so prefer them whenever a product is named.
- If the user tells you about ingredient swaps (margarine instead of butter, soya milk, nutritional yeast instead of cheese, vegan versions), re-estimate those items. Swaps like these can change a dish's calories a lot, so don't just keep the old number.
- Note cooking fat if relevant (about 100 kcal per tablespoon of oil or spread).
- Round sensibly: kcal to the nearest 5, macros to whole grams. These are estimates and false precision misleads.

## Step 3: Show the user and confirm

Keep it short, since the user is usually on a phone:

- One line with the total kcal and a likely range.
- A short list: item, portion, kcal.
- One line naming the least certain item.

Then ask whether anything needs correcting before it's sent. The user often knows things the photo can't show (brand, vegan swaps, how it was cooked), and a corrected entry is worth more than a fast one. If they correct something, update the numbers and show the new total.

If the user has already said "just send it" or similar, skip the confirmation.

Don't introduce terms or acronyms without defining them.

## Step 4: Send to Home Assistant

The user's Home Assistant runs the Meal Recorder integration (https://github.com/davidmorton0/home-assistant-meal-recorder), which stores each food item as a row in a monthly diary file and shows it on a Meals dashboard.

Once confirmed, write a meal file and run the send script:

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
- Nutrient numbers: `kcal`, and `protein`, `carbohydrate`, `fat` in grams. Numbers only, never text.
- `name` up to 200 characters, `portion` up to 100. Put brand and key swaps in the name (e.g. "Vegan cauliflower cheese (soya milk)"), because there is no notes field.
- `created_at` (optional): an ISO 8601 time with offset, e.g. `2026-09-24T13:00:00+01:00`. Omit it when the user is logging a meal as they eat it, and the script uses the current time. Set it when they say when they ate (e.g. "this was lunch yesterday").
- `person` (optional): only if the user says the meal is someone else's. Omitted means the `person` in `config.json`, the user's own name. Every item is sent with a person; Home Assistant refuses items without one.

```bash
python /path/to/skill/scripts/send_to_ha.py meal.json
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
- **"did not reply in time":** the meal may have been stored. Sending the same meal file again is safe: the script saved an id for each item in it, and Home Assistant refuses ids it already has (409 `duplicate_id`, meaning it was stored the first time). Never write a new meal file for a resend, because new ids would store it twice.
- **config.json placeholders:** ask the user for their Home Assistant address, the integration's username and password, and their name as added in the integration.

Still show the user the analysis even if sending fails, so the work isn't lost.

## Step 5: Confirm

After a successful send, one short line: how many items were stored and the total kcal.
