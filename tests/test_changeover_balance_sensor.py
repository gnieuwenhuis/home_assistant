"""Level 3 test: sensor.changeover_balance wired from the real configuration.yaml."""
from datetime import timedelta

import pytest
import yaml
import homeassistant.util.dt as dt_util
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.conftest import REPO_ROOT


class _StubTagLoader(yaml.SafeLoader):
    """Parse configuration.yaml while ignoring HA-specific tags."""


for _tag in ("!secret", "!include", "!include_dir_merge_named",
             "!include_dir_list", "!include_dir_named", "!env_var"):
    _StubTagLoader.add_constructor(_tag, lambda loader, node: None)


@pytest.fixture
async def balance(hass_helpers):
    hass = hass_helpers
    config = yaml.load((REPO_ROOT / "configuration.yaml").read_text(), _StubTagLoader)
    mode = {
        "fail": False,
        "temps": [-10.0] * 48,
        "daily": [{"temperature": 2.0, "templow": -8.0}] * 6,  # mean -3 → heating
    }

    async def fake_forecast(call):
        if mode["fail"]:
            raise HomeAssistantError("EC unreachable")
        forecast_type = call.data.get("type")
        if forecast_type == "daily":
            return {"weather.lethbridge_forecast": {"forecast": mode["daily"]}}
        return {
            "weather.lethbridge_forecast": {
                "forecast": [{"temperature": t} for t in mode["temps"]]
            }
        }

    hass.services.async_register(
        "weather", "get_forecasts", fake_forecast,
        supports_response=SupportsResponse.ONLY,
    )
    await hass.services.async_call(
        "input_number", "set_value",
        {"entity_id": "input_number.changeover_balance_point", "value": 16},
        blocking=True,
    )
    # Load only the trigger-based changeover balance sensor (the one template
    # item with a `triggers:` key). The repo's other (state-based) template
    # sensors reference live HVAC entities that aren't stubbed here and emit
    # teardown TemplateErrors; they belong to other tasks, not this one.
    template_config = [
        item for item in config["template"] if "triggers" in item
    ]
    assert template_config, "changeover balance sensor not found in configuration.yaml"
    assert await async_setup_component(hass, "template", {"template": template_config})
    await hass.async_block_till_done()
    yield hass, mode
    # The time_pattern trigger registers a recurring time listener via the
    # template integration's TriggerUpdateCoordinator. For YAML config this is
    # only cancelled on config-entry unload / reload, not on HA stop, so shut
    # the coordinators down explicitly to avoid a lingering-timer teardown error.
    from homeassistant.components.template import DATA_COORDINATORS

    for coordinator in hass.data.get(DATA_COORDINATORS, []):
        await coordinator.async_shutdown()


async def fire_hourly(hass):
    target = (dt_util.utcnow() + timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )
    async_fire_time_changed(hass, target)
    await hass.async_block_till_done()


async def test_balance_from_cold_forecast(balance):
    hass, _ = balance
    await fire_hourly(hass)
    state = hass.states.get("sensor.changeover_balance")
    assert state is not None
    assert float(state.state) == -1248.0          # CDH 0 − HDH 26x48
    assert state.attributes["hdh"] == 1248.0
    assert state.attributes["cdh"] == 0.0
    assert state.attributes["forecast_hours"] == 48


async def test_long_forecast_clipped_to_48h(balance):
    hass, mode = balance
    mode["temps"] = [-10.0] * 72
    await fire_hourly(hass)
    assert hass.states.get("sensor.changeover_balance").attributes["forecast_hours"] == 48


async def test_balance_unavailable_when_forecast_fails(balance):
    hass, mode = balance
    mode["fail"] = True
    await fire_hourly(hass)
    assert hass.states.get("sensor.changeover_balance").state == "unavailable"


async def test_daily_attributes_present(balance):
    hass, _ = balance
    await fire_hourly(hass)
    state = hass.states.get("sensor.changeover_balance")
    assert state.attributes["daily_forecast_days"] == 2          # clipped to 2
    # 2 daily means of -3.0, balance 16 → hdh (16 - -3) * 2 = 38, cdh 0
    assert state.attributes["daily_hdh"] == 38.0
    assert state.attributes["daily_cdh"] == 0.0


async def test_unavailable_when_daily_forecast_empty(balance):
    hass, mode = balance
    mode["daily"] = []
    await fire_hourly(hass)
    assert hass.states.get("sensor.changeover_balance").state == "unavailable"
