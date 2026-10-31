"""End-to-end tests for automation/voice-weather-extras.yaml.

Unlike the hassil + Jinja tests one folder up, these load the blueprint into a
real Home Assistant core (via pytest-homeassistant-custom-component), create
an automation from it, and speak sentences through Assist's default
conversation agent. The weather entity, its daily forecast and sun.sun are
stand-ins, so answers are deterministic.

Run (Linux/WSL, Python 3.13):
  pip install -r tests/requirements-ha.txt
  python -m pytest tests/ha -q
"""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.components import conversation  # noqa: E402
from homeassistant.core import (  # noqa: E402
    Context,
    HomeAssistant,
    ServiceCall,
    SupportsResponse,
)
from homeassistant.setup import async_setup_component  # noqa: E402

BLUEPRINT = Path(__file__).parents[2] / "automation" / "voice-weather-extras.yaml"
WEATHER = "weather.home"

# 08:00 EDT on Tuesday 2026-10-20.
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


def _day(offset: int, **fields) -> dict:
    return {"datetime": (NOW + timedelta(days=offset, hours=4)).isoformat(), **fields}


DEFAULT_FORECAST = [
    _day(0, condition="rainy", temperature=61.4, templow=48.2, precipitation_probability=70),
    _day(1, condition="sunny", temperature=65, templow=50, precipitation=5.0),
    _day(2, condition="partlycloudy", temperature=63, templow=47),
    _day(3, condition="cloudy", temperature=58, templow=45, precipitation_probability=40),
    _day(4, condition="pouring", temperature=55, templow=44),
    _day(5, condition="sunny", temperature=60, templow=42),
    _day(6, condition="windy", temperature=57, templow=41),
]


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
        forecast_days: int = 5,
        forecast: list[dict] | None = None,
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
                "precipitation_unit": "mm",
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

        async def get_forecasts(call: ServiceCall) -> dict:
            return {WEATHER: {"forecast": DEFAULT_FORECAST if forecast is None else forecast}}

        hass.services.async_register(
            "weather", "get_forecasts", get_forecasts, supports_response=SupportsResponse.ONLY
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
                                "forecast_days": forecast_days,
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


async def test_rain_with_probability_and_amount(hass, setup) -> None:
    await setup()
    assert await say(hass, "is it going to rain") == (
        "Yes, there's a 70 percent chance of rain today."
    )
    # Tomorrow has no probability, only 5 mm of rain.
    assert await say(hass, "will it rain tomorrow") == (
        "Yes, rain is expected tomorrow, about 0.2 inches."
    )


async def test_rain_metric_and_light_shower(hass, setup) -> None:
    forecast = [
        _day(0, condition="rainy", temperature=60, precipitation=1.0),
        _day(1, condition="sunny", temperature=60, precipitation=5.0),
    ]
    await setup(units="metric", forecast=forecast)
    assert await say(hass, "chance of rain") == (
        "Maybe a little - just a light shower today, under 2 and a half millimeters."
    )
    assert await say(hass, "what's the chance of rain tomorrow") == (
        "Yes, rain is expected tomorrow, about 5.0 millimeters."
    )


async def test_rain_without_forecast(hass, setup) -> None:
    await setup(forecast=[])
    assert await say(hass, "will it rain") == "Sorry, I don't have a forecast right now."


async def test_weekly_forecast_respects_day_count(hass, setup) -> None:
    await setup(forecast_days=3)
    assert await say(hass, "what's the forecast this week") == (
        "Here's the next 3 days. "
        "Today, rain, high of 61, low of 48, with a 70 percent chance of rain. "
        "Tomorrow, sunny, high of 65, low of 50. "
        "Thursday, partly cloudy, high of 63, low of 47."
    )


async def test_unrelated_questions_are_not_hijacked(hass, setup) -> None:
    await setup()
    for text in ("what's the weather", "what time is it", "turn on the pressure washer"):
        assert "barometric" not in await say(hass, text), text
