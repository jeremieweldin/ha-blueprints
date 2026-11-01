# Reinstalling the voice setup

How to rebuild this Home Assistant's local voice assistant from scratch on a
fresh install (or after restoring an old backup). Written against
Home Assistant 2026.10. Everything here runs locally: no LLM, and no cloud
except one optional fallback pipeline.

Work through the steps in order. Values in `<angle brackets>` are your own
(host addresses, entity names).

---

## 1. Speech services (Wyoming)

| Service | Where it runs | Address |
|---|---|---|
| Speech-to-text, main | **faster-whisper on a separate GPU machine** | `<gpu-host>:10300` |
| Speech-to-text, phrase-only | **Speech-to-Phrase** app on the HA box | `core-speech-to-phrase:10300` |
| Text-to-speech | **Piper** app on the HA box | `core-piper:10200` |
| Wake word (server side) | **openWakeWord** app on the HA box | `core-openwakeword:10400` |

1. **Settings → Apps → App store**: install **Piper**, **Speech-to-Phrase**
   and **openWakeWord**. Turn on **Start on boot** and **Watchdog** for each.
2. **Don't install the local Whisper app.** It's CPU-only and used ~800 MB of
   the VM's 4 GB. The remote GPU faster-whisper replaces it.
3. **Settings → Devices & services → Add integration → Wyoming Protocol**,
   host `<gpu-host>`, port `10300`. Repeat for any app that wasn't
   auto-discovered.

## 2. Assist pipelines

**Settings → Voice assistants → Add assistant.** All use the built-in
**Home Assistant** conversation agent, language English, and leave
**Prefer handling commands locally** off.

| Name | Speech-to-text | Text-to-speech voice |
|---|---|---|
| Focused local (STP) — **preferred** | Speech-to-Phrase | Piper `en_US-hfc_female-medium` |
| Focused local (FW-GPU) | faster-whisper (GPU box) | Piper `en_US-amy-medium` |
| Home Assistant Cloud (fallback) | Home Assistant Cloud | Cloud `AmberNeural` |

Per-person copies of a pipeline (same engines, a different voice) work fine
for giving each speaker its own voice. Then assign a pipeline to each voice satellite (Home Assistant Voice PE /
ESPHome speakers) on its device page.

## 3. HACS integrations

Install [HACS](https://hacs.xyz/docs/use/download/download/), then add
[`jeremieweldin/ha-voice-timers`](https://github.com/jeremieweldin/ha-voice-timers)
under **HACS → ⋮ → Custom repositories** (type: Integration) and download
it. Reinstall your device integrations from HACS at the same time.

Restart, then **Settings → Devices & services → Add integration → Voice Timers**.
It writes `config/custom_sentences/en/voice_timers.yaml` itself — don't
copy that file over by hand. With its built-in timer override on (the
default), it handles every timer sentence; satellite-side timers are never used.

## 4. Blueprints and voice automations

Import each blueprint (**Settings → Automations & Scenes → Blueprints →
Import Blueprint**, or use the badges in [README.md](README.md)), then
create one automation from it.

| Automation | Blueprint | Inputs to set |
|---|---|---|
| Voice Math | [`voice-math.yaml`](automation/voice-math.yaml) | defaults |
| Voice Unit Conversion | [`voice-unit-conversion.yaml`](automation/voice-unit-conversion.yaml) | defaults |
| Voice Weather - Extras | [`voice-weather-extras.yaml`](automation/voice-weather-extras.yaml) | `<weather entity>`, units `us` |
| Voice Weather - Local Forecast | TheFes [`1_voice_weather_forecast_local.yaml`](https://github.com/TheFes/ha-blueprints/blob/main/weather/1_voice_weather_forecast_local.yaml) | see below |

The weather entity comes from the **Met.no** integration (added
automatically for your home location).

**Voice Weather - Local Forecast** has local customizations. After creating
it, open it in YAML mode and set:

- `weather_entity: <weather entity>`
- `trigger` — add `what('s| is) the weather [forecast] on {phrase}` at the
  top of the list, so "on Tuesday" works.
- `response_current` — the pressure sentence uses the entity's raw
  `pressure` attribute converted to inches of mercury (the blueprint's own
  value rounds to "30.0"). Copy the full template from the backup of
  `automations.yaml` (see **Backups** below).

> **Keep number ranges small.** Any inline range in a sentence trigger, such
> as `{0..10000:num}`, makes Assist build a spoken-word table for every number
> in it the first time a sentence reaches that range. `0..1000000` used ~3 GB
> and got Home Assistant core killed for running out of memory, again and
> again. `0..10000` costs ~45 MB, once per start. Don't raise these.

### Voice Date & Time

Use **either** the [`voice-date-time.yaml`](automation/voice-date-time.yaml)
blueprint **or** the `packages/voice_date_holiday.yaml` package — not both,
or "what's the date" matches twice. The original box ran the package (the
blueprint was imported but had no automation).

### Automations kept in `automations.yaml`

**Voice Time - Speak the time naturally** isn't a blueprint. Copy it from
the backup `automations.yaml`. It answers "what time is it" with
"It's 7 oh 5 in the morning" style phrasing.

## 5. `configuration.yaml`

Add these alongside `default_config:`:

```yaml
homeassistant:
  packages: !include_dir_named packages

command_line:
  - sensor:
      name: "Voice Commands"
      unique_id: voice_commands_scanner
      command: "python3 /config/scripts/scan_voice_commands.py /config/packages /config/automations.yaml /config/blueprints/automation"
      command_timeout: 15
      scan_interval: 300
      value_template: "{{ value_json.sections | length }}"
      json_attributes:
        - sections
        - generated_at
```

`sensor.voice_commands` lists every sentence trigger, for the "what can I
say" dashboard card. It needs `scan_voice_commands.py` at
`/config/scripts/`.

Files to copy into `/config` from a backup (not in this repo yet):

| File | What it is |
|---|---|
| `scripts/scan_voice_commands.py` | Scanner behind `sensor.voice_commands` |
| `packages/voice_date_holiday.yaml` | "what's the date" with holidays (see above) |
| `packages/*.yaml` | Any other voice packages of your own |

Restart Home Assistant after editing `configuration.yaml`.

## 6. Check it

In **Assist** (top-right of any dashboard), type these one at a time. Each
should answer in under a second:

- what's the weather / what's the weather tomorrow / what's the weather on Tuesday
- what's the pressure / what's the humidity / what's the dew point
- what time is sunrise / when does the sun set
- what time is it / what's the date
- what is 5 plus 3 divided by 2 times 6 → 14
- convert 3 pounds to grams
- set a pizza timer for 10 minutes / how much time is left / cancel the pizza timer
  *(timers make the speakers announce; test during the day)*

If Home Assistant hangs or restarts on a sentence, check the host log for
`Out of memory: Killed process` and look for a large `{a..b}` range (see
above).

## Backups

Before changing anything, copy `automations.yaml`, `configuration.yaml`,
`packages/` and `scripts/` off the box. Steps 4 and 5 restore from those
copies. When replacing a voice file, move the old one into
`/config/replaced_voice_files/` rather than deleting it.
