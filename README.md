# Home Assistant Voice Assist Blueprints

A small collection of local, no-cloud, no-LLM Assist blueprints — pattern-matched
sentence triggers that compute a real answer and speak it back, entirely on your
own Home Assistant instance.

---

## Blueprints

### 🧮 Basic Arithmetic
Addition, subtraction, multiplication, and division, spoken and answered
locally — "what is 6 times 7", "20 divided by 4". Handles chained
expressions with correct order of operations too — "what is 5 plus 3
divided by 2 times 6" answers 14.

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fjeremieweldin%2Fha-blueprints%2Fmain%2Fautomation%2Fvoice-math.yaml)

Whole numbers 0–1,000,000, spoken as words ("five") or digits ("5").
Multiplication and division bind before addition and subtraction, then
left to right; division results are rounded to two decimals. No
parentheses. Each question must start with a number and an operator, so
unrelated queries like "what is the weather" are left untouched.

### 🔁 Unit Conversion
Convert across volume, weight/mass, length/distance, temperature, area,
speed, digital storage, and time — "how many ounces are in 2 cups",
"convert 3 pounds to grams", "what is 100 celsius in fahrenheit".

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fjeremieweldin%2Fha-blueprints%2Fmain%2Fautomation%2Fvoice-unit-conversion.yaml)

Each unit is defined with a dimension, a factor, and an optional offset;
values convert through a shared base unit per dimension, with the offset
handling temperature's affine scale. Conversions between mismatched
dimensions (like cups to pounds) are politely refused. Both the synonym
map and the unit definitions are editable inputs, so you can add units,
translate the synonyms, or add entirely new dimensions.

### 📅 Date & Time
Natural spoken date and time, with US holiday detection — "what's the
date", "what time is it", "what's the date and time".

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fjeremieweldin%2Fha-blueprints%2Fmain%2Fautomation%2Fvoice-date-time.yaml)

Floating holidays (MLK Day, Presidents Day, Memorial Day, Labor Day,
Columbus Day, Thanksgiving) and Easter are computed live via the
Meeus/Jones/Butcher algorithm, so this stays correct every year with no
manual date updates. Holiday announcements can be toggled off entirely
via an input if you're outside the US or don't want them.

### 🌦️ Weather Extras
The one piece of weather info you wanted, without the full forecast
speech — "what's the pressure", "how humid is it", "what's the dew point",
"when does the sun set", "will it rain tomorrow", "what's the forecast
this week".

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fraw.githubusercontent.com%2Fjeremieweldin%2Fha-blueprints%2Fmain%2Fautomation%2Fvoice-weather-extras.yaml)

Pick your weather entity and US (inches of mercury, inches of rain) or
metric (hectopascals, millimeters) units; whatever units the entity
reports are converted. For providers that don't give a chance of rain
(Met.no, for example), "will it rain" falls back to the forecast rain
amount. Every command's sentences are editable inputs.

| Say | Answers |
|---|---|
| "what's the pressure" / "barometric pressure" | "The barometric pressure is 29.92 inches of mercury." |
| "what's the humidity" / "how humid is it" | "The humidity is 45 percent." |
| "what's the dew point" | "The dew point is 50.4 degrees Fahrenheit." |
| "when does the sun rise [tomorrow]" / "what time is sunrise" | "The sun rises tomorrow at 7:20 in the morning." |
| "when does the sun set [tonight\|tomorrow]" / "what time is sunset" | "The sun sets tonight at 6:25 in the evening." |
| "is it going to rain [today\|tomorrow]" / "chance of rain" | "Yes, there's a 70 percent chance of rain today." |
| "what's the forecast this week" / "weekly forecast" | "Here's the next 5 days. Today, rain, high of 61, low of 48…" |

This one needs a weather entity that supports daily forecasts — it's the
only blueprint here that isn't fully self-contained.

---

## Requirements

- Home Assistant with [Assist](https://www.home-assistant.io/voice_control/)
  configured (a conversation agent — this works with the built-in local
  agent, no cloud or LLM subscription needed)
- No additional integrations, helpers, or entities required — each
  blueprint is fully self-contained (except Weather Extras, which needs a
  weather entity)

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

## Tests

The math and unit-conversion blueprints have automated tests under
[`tests/`](tests/). They drive spoken sentences through
[`hassil`](https://github.com/OHF-Voice/hassil) — the exact matcher Home
Assistant's Assist uses — and render each blueprint's real Jinja response
template (pulled straight from the YAML) through Home Assistant's sandboxed
template environment, comparing the spoken answer against an independent
reference implementation across thousands of cases.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r tests/requirements.txt
python -m pytest tests/ -q
```

The Weather Extras blueprint is tested end to end instead: `tests/ha/`
loads it into a real Home Assistant core, creates an automation from it,
and speaks each sentence through Assist's default conversation agent with
a stand-in weather entity and sun (skipped unless the extra requirements
are installed; Linux/WSL, Python 3.13):

```bash
pip install -r tests/requirements-ha.txt
python -m pytest tests/ha -q
```

## License

MIT — see [LICENSE](LICENSE).
