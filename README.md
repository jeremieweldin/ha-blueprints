# Home Assistant Voice Assist Blueprints

A small collection of local, no-cloud, no-LLM Assist blueprints — pattern-matched
sentence triggers that compute a real answer and speak it back, entirely on your
own Home Assistant instance.

---

## Blueprints

### 🧮 Basic Arithmetic
Addition, subtraction, multiplication, and division, spoken and answered
locally — "what is 6 times 7", "20 divided by 4".

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fjeremieweldin%2Fha-blueprints%2Fmain%2Fautomation%2Fvoice-math.yaml)

Whole numbers, 0–1,000,000, two-number single-operation questions only —
see the blueprint's own description for the full limitations note on why
chained expressions ("5 plus 3 times 2") aren't supported.

### 🥤 Volume Unit Conversion
Convert between teaspoons, tablespoons, ounces, cups, pints, quarts,
gallons, milliliters, and liters — "how many ounces are in 2 cups".

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fjeremieweldin%2Fha-blueprints%2Fmain%2Fautomation%2Fvoice-unit-conversion.yaml)

Unit names and conversion factors are both editable inputs, so you can add
units, translate the synonym list, or swap to a different measurement
system.

### 📅 Date & Time
Natural spoken date and time, with US holiday detection — "what's the
date", "what time is it", "what's the date and time".

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fjeremieweldin%2Fha-blueprints%2Fmain%2Fautomation%2Fvoice-date-time.yaml)

Floating holidays (MLK Day, Presidents Day, Memorial Day, Labor Day,
Columbus Day, Thanksgiving) and Easter are computed live via the
Meeus/Jones/Butcher algorithm, so this stays correct every year with no
manual date updates. Holiday announcements can be toggled off entirely
via an input if you're outside the US or don't want them.

---

## Requirements

- Home Assistant with [Assist](https://www.home-assistant.io/voice_control/)
  configured (a conversation agent — this works with the built-in local
  agent, no cloud or LLM subscription needed)
- No additional integrations, helpers, or entities required — each
  blueprint is fully self-contained

## Installation

**Option 1 — one-click import** (requires the
[Home Assistant Cloud/companion redirect service](https://my.home-assistant.io),
works automatically if your instance is reachable): click any badge above.

**Option 2 — manual import:**
1. In Home Assistant, go to **Settings → Automations & Scenes → Blueprints**
2. Click **Import Blueprint**
3. Paste in the blueprint's raw GitHub URL, e.g.:
   `https://raw.githubusercontent.com/jeremieweldin/ha-blueprints/main/automation/voice-math.yaml`
4. Click **Preview**, then **Import Blueprint**

After importing, create an automation from the blueprint (**Settings →
Automations & Scenes → Create Automation → Use Blueprint**). All inputs
come pre-filled with working defaults — you can save immediately, or
customize the trigger sentences first.

## Notes on sentence triggers

Home Assistant's sentence-trigger matcher (`hassil`) is picky about
punctuation — a single misplaced apostrophe or bracket can silently break
an entire trigger list rather than just the one malformed sentence. If you
customize any trigger sentence input, keep it to plain words, `[optional]`
brackets, `(option one|option two)` alternatives, and `{0..100:name}`
numeric ranges. Avoid embedding punctuation mid-word.

## License

MIT — see [LICENSE](LICENSE).
