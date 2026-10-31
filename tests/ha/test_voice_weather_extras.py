"""End-to-end tests for automation/voice-weather-extras.yaml.

Unlike the hassil + Jinja tests one folder up, these load the blueprint into a
real Home Assistant core (via pytest-homeassistant-custom-component), create
an automation from it, and speak sentences through Assist's default
conversation agent. The weather entity and sun.sun are
stand-ins, so answers are deterministic.

Run (Linux/WSL, Python 3.13):
  pip install -r tests/requirements-ha.txt
  python -m pytest tests/ha -q
"""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.components import conversation  # noqa: E402
from homeassistant.core import Context, HomeAssistant  # noqa: E402
from homeassistant.setup import async_setup_component  # noqa: E402

BLUEPRINT = Path(__file__).parents[2] / "automation" / "voice-weather-extras.yaml"
WEATHER = "weather.home"

# 08:00 EDT on Tuesday 2026-10-20.
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def setup(hass: HomeAssistant, tmp_path: Path, freezer):
    """Return a coroutine that sets up the blueprint with the given inputs."""
    freezer.move_to(NOW)
    await hass.config.async_set_time_zone("America/New_York")
    (tmp_path / "configuration.yaml").write_text("")
    dest = tmp_path / "blueprints" / "automation" / "jeremieweldin"
    dest.mkdir(parents=True)
    shutil.copy(BLUEPRINT, dest / BLUEPRINT.name)
    hass.config.config_dir = str(tmp_path)

    async def _setup(
        units: str = "us",
        attrs: dict | None = None,
    ) -> None:
        hass.states.async_set(
            WEATHER,
            "rainy",
            {
                "temperature": 60,
                "humidity": 45,
                "pressure": 1013.25,
                "dew_point": 50.4,
                "temperature_unit": "°F",
                "pressure_unit": "hPa",
                **(attrs or {}),
            },
        )
        hass.states.async_set(
            "sun.sun",
            "above_horizon",
            {
                # Sunrise already happened today, so next_rising is tomorrow.
                "next_rising": "2026-10-21T11:20:00+00:00",  # 7:20 EDT
                "next_setting": "2026-10-20T22:25:00+00:00",  # 6:25 EDT
            },
        )

        assert await async_setup_component(hass, "homeassistant", {})
        assert await async_setup_component(hass, "conversation", {})
        assert await async_setup_component(
            hass,
            "automation",
            {
                "automation": [
                    {
                        "alias": "Voice Weather Extras",
                        "use_blueprint": {
                            "path": f"jeremieweldin/{BLUEPRINT.name}",
                            "input": {
                                "weather_entity": WEATHER,
                                "units": units,
                            },
                        },
                    }
                ]
            },
        )
        await hass.async_block_till_done()

    return _setup


async def say(hass: HomeAssistant, text: str) -> str:
    result = await conversation.async_converse(hass, text, None, Context(), language="en")
    return " ".join(result.response.speech["plain"]["speech"].split())


async def test_pressure_us_and_variants(hass, setup) -> None:
    await setup()
    for text in ("what's the pressure", "whats the barometric pressure", "pressure"):
        assert await say(hass, text) == (
            "The barometric pressure is 29.92 inches of mercury."
        ), text


async def test_pressure_metric(hass, setup) -> None:
    await setup(units="metric")
    assert await say(hass, "what is the pressure") == (
        "The barometric pressure is 1013 hectopascals."
    )


async def test_pressure_reported_in_inhg(hass, setup) -> None:
    await setup(attrs={"pressure": 30.1, "pressure_unit": "inHg"})
    assert await say(hass, "what's the pressure") == (
        "The barometric pressure is 30.1 inches of mercury."
    )


async def test_humidity_and_dew_point(hass, setup) -> None:
    await setup()
    assert await say(hass, "how humid is it") == "The humidity is 45 percent."
    assert await say(hass, "what's the dew point") == (
        "The dew point is 50.4 degrees Fahrenheit."
    )


async def test_missing_values_say_sorry(hass, setup) -> None:
    await setup(attrs={"pressure": None, "humidity": None, "dew_point": None})
    assert await say(hass, "pressure") == "Sorry, I don't have the pressure right now."
    assert await say(hass, "humidity") == "Sorry, I don't have the humidity right now."
    assert await say(hass, "dew point") == "Sorry, I don't have the dew point right now."


async def test_sunrise_and_sunset(hass, setup) -> None:
    await setup()
    assert await say(hass, "when does the sun rise") == (
        "The sun rises tomorrow at 7:20 in the morning."
    )
    assert await say(hass, "what time is sunset tonight") == (
        "The sun sets tonight at 6:25 in the evening."
    )
    assert await say(hass, "when does the sun set tomorrow") == (
        "The sun sets tomorrow at 6:25 in the evening."
    )


async def test_unrelated_questions_are_not_hijacked(hass, setup) -> None:
    await setup()
    for text in ("what's the weather", "what time is it", "turn on the pressure washer"):
        assert "barometric" not in await say(hass, text), text


async def test_rain_and_forecast_are_left_to_other_automations(hass, setup) -> None:
    """Will-it-rain and weekly-forecast were removed on purpose (2026-10-31):
    on a live install they stalled Home Assistant, and "what's the weather
    tomorrow" from a forecast blueprint covers them."""
    await setup()
    removed = ("Yes, there's", "Maybe", "Unlikely", "No rain expected", "Here's the next")
    for text in ("will it rain tomorrow", "what's the forecast this week"):
        assert not (await say(hass, text)).startswith(removed), text
