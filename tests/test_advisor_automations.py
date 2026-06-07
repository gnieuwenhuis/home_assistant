"""Level 3 tests: changeover advisor automations loaded from automations.yaml."""
import pytest
import yaml
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

from tests.conftest import REPO_ROOT

ADVISOR_IDS = {
    "heat_pump_mode_advisor",
    "heat_pump_mode_advisor_response",
    "heat_pump_mode_changed",
}
BALANCE_ATTRS = {
    "cdh": 50.0, "hdh": 6.0, "forecast_hours": 48,
    "daily_cdh": 4.0, "daily_hdh": 0.0, "daily_forecast_days": 2,
}


@pytest.fixture
async def advisor(hass_helpers):
    hass = hass_helpers
    autos = yaml.safe_load((REPO_ROOT / "automations.yaml").read_text())
    chosen = [a for a in autos if a.get("id") in ADVISOR_IDS]
    assert len(chosen) == 3, "changeover automations missing from automations.yaml"
    assert await async_setup_component(hass, "automation", {"automation": chosen})
    notify_calls = async_mock_service(hass, "notify", "mobile_app_pixel_8")
    switch_calls = async_mock_service(hass, "switch", "turn_off")
    yield hass, notify_calls, switch_calls
    # heat_pump_mode_advisor's time_pattern trigger registers a recurring time
    # listener; turning the automations off detaches their triggers so HA's
    # verify_cleanup autouse fixture doesn't flag a lingering timer at teardown.
    await hass.services.async_call(
        "automation", "turn_off",
        {"entity_id": "all"}, blocking=True,
    )
    # A running hold schedules its own finish callback; cancel it so it isn't
    # flagged as a lingering timer either.
    await hass.services.async_call(
        "timer", "cancel",
        {"entity_id": "timer.changeover_hold"}, blocking=True,
    )
    await hass.async_block_till_done()


async def arrange(hass, *, mode="heating", balance_state="44",
                  office_mean="22.0", studio_mean="25.5",
                  office_duty="0.0", studio_duty="0.0"):
    """Default scene: cooling candidate confirmed by an idle, hot studio."""
    for ent, val in [
        ("input_number.office_preferred_temperature", 21),
        ("input_number.studio_preferred_temperature", 21),
        ("input_number.office_temp_range", 2),
        ("input_number.studio_temp_range", 2),
        ("input_number.changeover_balance_point", 16),
        ("input_number.changeover_deadband", 24),
        ("input_number.changeover_daily_deadband", 1.0),
    ]:
        await hass.services.async_call(
            "input_number", "set_value",
            {"entity_id": ent, "value": val}, blocking=True,
        )
    await hass.services.async_call(
        "input_select", "select_option",
        {"entity_id": "input_select.heat_pump_mode", "option": mode}, blocking=True,
    )
    hass.states.async_set("sensor.changeover_balance", balance_state, BALANCE_ATTRS)
    hass.states.async_set("sensor.office_temperature_2h_mean", office_mean)
    hass.states.async_set("sensor.studio_temperature_1h_mean", studio_mean)
    hass.states.async_set("sensor.office_heat_pump_duty_24h", office_duty)
    hass.states.async_set("sensor.studio_heat_pump_duty_24h", studio_duty)
    await hass.async_block_till_done()
    # Selecting a mode starts the 24 h hold via heat_pump_mode_changed
    # (itself a behavior under test) — clear it so each test controls the hold.
    await hass.services.async_call(
        "timer", "cancel", {"entity_id": "timer.changeover_hold"}, blocking=True,
    )
    await hass.async_block_till_done()


async def run_advisor(hass):
    await hass.services.async_call(
        "automation", "trigger",
        {"entity_id": "automation.heat_pump_mode_advisor", "skip_condition": False},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_advisor_suggests_cooling(advisor):
    hass, notify_calls, _ = advisor
    await arrange(hass)
    await run_advisor(hass)
    assert len(notify_calls) == 1
    payload = notify_calls[0].data
    assert "cooling" in payload["message"]
    assert payload["data"]["actions"][0]["action"] == "CHANGEOVER_ACCEPT_cooling"
    hold = hass.states.get("timer.changeover_hold")
    assert hold.state == "active"
    assert hold.attributes["duration"] == "12:00:00"


async def test_no_suggestion_when_candidate_matches_mode(advisor):
    hass, notify_calls, _ = advisor
    await arrange(hass, mode="cooling")
    await run_advisor(hass)
    assert notify_calls == []


async def test_no_suggestion_during_hold(advisor):
    hass, notify_calls, _ = advisor
    await arrange(hass)
    await hass.services.async_call(
        "timer", "start",
        {"entity_id": "timer.changeover_hold", "duration": "01:00:00"},
        blocking=True,
    )
    await run_advisor(hass)
    assert notify_calls == []


async def test_duty_alibi_blocks_suggestion(advisor):
    hass, notify_calls, _ = advisor
    # Studio hot but busy (its own pump may have caused it); office in band.
    await arrange(hass, studio_duty="15.0")
    await run_advisor(hass)
    assert notify_calls == []


async def test_backup_heat_blocks_suggestion(advisor):
    hass, notify_calls, _ = advisor
    await arrange(hass)
    await hass.services.async_call(
        "input_boolean", "turn_on",
        {"entity_id": "input_boolean.backup_heat"}, blocking=True,
    )
    await run_advisor(hass)
    assert notify_calls == []


async def test_unavailable_balance_blocks_suggestion(advisor):
    hass, notify_calls, _ = advisor
    await arrange(hass)
    hass.states.async_set("sensor.changeover_balance", "unavailable", BALANCE_ATTRS)
    await run_advisor(hass)
    assert notify_calls == []


async def test_accept_sets_mode_and_24h_hold(advisor):
    hass, _, _ = advisor
    await arrange(hass)
    hass.bus.async_fire(
        "mobile_app_notification_action", {"action": "CHANGEOVER_ACCEPT_cooling"}
    )
    await hass.async_block_till_done()
    # Accept is a two-hop chain: the response automation sets the mode, and that
    # state change in turn triggers heat_pump_mode_changed to start the 24 h
    # hold. A single block drains the first hop; drain again for the second.
    await hass.async_block_till_done()
    assert hass.states.get("input_select.heat_pump_mode").state == "cooling"
    hold = hass.states.get("timer.changeover_hold")
    assert hold.state == "active"
    assert hold.attributes["duration"] == "24:00:00"


async def test_entering_off_powers_down_only_running_heads(advisor):
    hass, _, switch_calls = advisor
    await arrange(hass, mode="cooling")
    hass.states.async_set("switch.office_power", "on")
    hass.states.async_set("switch.studio_power", "off")
    await hass.services.async_call(
        "input_select", "select_option",
        {"entity_id": "input_select.heat_pump_mode", "option": "off"}, blocking=True,
    )
    await hass.async_block_till_done()
    assert len(switch_calls) == 1
    ent = switch_calls[0].data["entity_id"]
    assert ent in ("switch.office_power", ["switch.office_power"])


async def test_no_suggestion_when_daily_disagrees(advisor):
    hass, notify_calls, _ = advisor
    # Hourly says cooling (cdh 50/hdh 6) but the 2-day daily trend is cold
    # (daily_hdh dominant) → regimes disagree → no suggestion.
    await arrange(hass)
    hass.states.async_set(
        "sensor.changeover_balance", "44",
        {**BALANCE_ATTRS, "daily_cdh": 0.0, "daily_hdh": 8.0},
    )
    await run_advisor(hass)
    assert notify_calls == []


async def test_suggests_when_both_regimes_agree(advisor):
    hass, notify_calls, _ = advisor
    # Explicit agreement scene (mirrors the default arrange, kept for clarity).
    await arrange(hass)
    await run_advisor(hass)
    assert len(notify_calls) == 1
    assert notify_calls[0].data["data"]["actions"][0]["action"] == "CHANGEOVER_ACCEPT_cooling"
