"""Level 3 tests: hvac_coordinator loaded from automations.yaml."""
import pytest
import yaml
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

from tests.conftest import REPO_ROOT

DEFAULTS = {
    "input_number.office_heat_bound": 20,
    "input_number.office_cool_bound": 24,
    "input_number.studio_heat_bound": 20,
    "input_number.studio_cool_bound": 23,
    "input_number.office_temp_differential": 1.0,
    "input_number.studio_temp_differential": 0.5,
}


@pytest.fixture
async def coordinator(hass_helpers):
    hass = hass_helpers
    autos = yaml.safe_load((REPO_ROOT / "automations.yaml").read_text())
    chosen = [a for a in autos if a.get("id") == "hvac_coordinator"]
    assert len(chosen) == 1, "hvac_coordinator missing from automations.yaml"
    assert await async_setup_component(hass, "automation", {"automation": chosen})
    # Disable live triggers so state changes in arrange() don't fire the
    # coordinator mid-setup; each test drives exactly one run via run()
    # (automation.trigger executes the actions even while disabled).
    await hass.services.async_call(
        "automation", "turn_off",
        {"entity_id": "automation.hvac_coordinator"}, blocking=True,
    )
    calls = {
        "on": async_mock_service(hass, "switch", "turn_on"),
        "off": async_mock_service(hass, "switch", "turn_off"),
        "temp": async_mock_service(hass, "climate", "set_temperature"),
    }
    yield hass, calls
    await hass.services.async_call(
        "automation", "turn_off", {"entity_id": "all"}, blocking=True
    )
    for t in ("mode_min_dwell", "office_head_lockout", "studio_head_lockout"):
        await hass.services.async_call(
            "timer", "cancel", {"entity_id": f"timer.{t}"}, blocking=True
        )
    await hass.async_block_till_done()


async def arrange(hass, *, office_temp, studio_temp, stored="idle",
                  enabled=True, backup=False,
                  office_switch="off", studio_switch="off",
                  office_climate="off", studio_climate="off",
                  office_lockout=False, studio_lockout=False):
    for ent, val in DEFAULTS.items():
        await hass.services.async_call(
            "input_number", "set_value", {"entity_id": ent, "value": val},
            blocking=True,
        )
    await hass.services.async_call(
        "input_select", "select_option",
        {"entity_id": "input_select.system_hvac_mode", "option": stored},
        blocking=True,
    )
    await hass.services.async_call(
        "input_boolean", "turn_on" if enabled else "turn_off",
        {"entity_id": "input_boolean.hvac_enable"}, blocking=True,
    )
    await hass.services.async_call(
        "input_boolean", "turn_on" if backup else "turn_off",
        {"entity_id": "input_boolean.backup_heat"}, blocking=True,
    )
    hass.states.async_set("sensor.office_baseboard_current_temperature", office_temp)
    hass.states.async_set("sensor.studio_control_temperature", studio_temp)
    hass.states.async_set("switch.office_power", office_switch)
    hass.states.async_set("switch.studio_power", studio_switch)
    hass.states.async_set("climate.office", office_climate, {"temperature": 22})
    hass.states.async_set("climate.studio", studio_climate, {"temperature": 22})
    for room, lock in (("office", office_lockout), ("studio", studio_lockout)):
        if lock:
            await hass.services.async_call(
                "timer", "start",
                {"entity_id": f"timer.{room}_head_lockout", "duration": "00:08:00"},
                blocking=True,
            )
        else:
            await hass.services.async_call(
                "timer", "cancel",
                {"entity_id": f"timer.{room}_head_lockout"}, blocking=True,
            )
    await hass.async_block_till_done()


async def run(hass):
    await hass.services.async_call(
        "automation", "trigger",
        {"entity_id": "automation.hvac_coordinator", "skip_condition": False},
        blocking=True,
    )
    await hass.async_block_till_done()


def _entities(call):
    e = call.data.get("entity_id")
    return e if isinstance(e, list) else [e]


def turned_on(calls, entity):
    return any(entity in _entities(c) for c in calls["on"])


def turned_off(calls, entity):
    return any(entity in _entities(c) for c in calls["off"])


async def test_cold_studio_heats_studio_only(coordinator):
    hass, calls = coordinator
    await arrange(hass, office_temp=22, studio_temp=18)
    await run(hass)
    assert turned_on(calls, "switch.studio_power")
    assert not turned_on(calls, "switch.office_power")
    assert hass.states.get("input_select.system_hvac_mode").state == "heat"
    heat_calls = [c for c in calls["temp"] if c.data.get("hvac_mode") == "heat"]
    assert heat_calls and heat_calls[0].data["temperature"] == 21.7  # studio 20 + lead 1.5 = 21.5 -> 71 F = 21.7


async def test_conflict_heating_wins_office_head_idle(coordinator):
    hass, calls = coordinator
    await arrange(hass, office_temp=26, studio_temp=18)
    await run(hass)
    assert hass.states.get("input_select.system_hvac_mode").state == "heat"
    assert turned_on(calls, "switch.studio_power")
    assert not turned_on(calls, "switch.office_power")


async def test_lockout_blocks_turn_on(coordinator):
    hass, calls = coordinator
    await arrange(hass, office_temp=22, studio_temp=18, studio_lockout=True)
    await run(hass)
    assert not turned_on(calls, "switch.studio_power")


async def test_master_off_forces_heads_off(coordinator):
    hass, calls = coordinator
    await arrange(hass, office_temp=18, studio_temp=18, enabled=False,
                  office_switch="on", studio_switch="on")
    await run(hass)
    assert turned_off(calls, "switch.office_power")
    assert turned_off(calls, "switch.studio_power")
    assert hass.states.get("input_select.system_hvac_mode").state == "off"


async def test_backup_heat_forces_heads_off(coordinator):
    hass, calls = coordinator
    await arrange(hass, office_temp=18, studio_temp=18, backup=True,
                  office_switch="on", studio_switch="off")
    await run(hass)
    assert turned_off(calls, "switch.office_power")
    assert hass.states.get("input_select.system_hvac_mode").state == "idle"


async def test_in_band_idles(coordinator):
    hass, calls = coordinator
    await arrange(hass, office_temp=22, studio_temp=21)
    await run(hass)
    assert not calls["on"]
    assert not calls["temp"]
    assert hass.states.get("input_select.system_hvac_mode").state == "idle"


async def test_dwell_pins_mode_blocks_reverse(coordinator):
    hass, calls = coordinator
    await arrange(hass, office_temp=26, studio_temp=21, stored="heat")
    await hass.services.async_call(
        "timer", "start",
        {"entity_id": "timer.mode_min_dwell", "duration": "00:15:00"},
        blocking=True,
    )
    await run(hass)
    assert hass.states.get("input_select.system_hvac_mode").state == "heat"
    assert not turned_on(calls, "switch.office_power")
    await hass.services.async_call(
        "timer", "cancel", {"entity_id": "timer.mode_min_dwell"}, blocking=True
    )


async def test_drift_resends_target_without_toggle(coordinator):
    hass, calls = coordinator
    await arrange(hass, office_temp=22, studio_temp=18, stored="heat",
                  studio_switch="on", studio_climate="heat")
    hass.states.async_set("climate.studio", "heat", {"temperature": 19})
    await hass.async_block_till_done()
    await run(hass)
    assert not turned_on(calls, "switch.studio_power")
    assert any(c.data.get("temperature") == 21.7 for c in calls["temp"])  # studio 20 + lead 1.5 = 21.5 -> 71 F = 21.7


async def test_hot_rooms_cool_with_cool_target(coordinator):
    hass, calls = coordinator
    # Both rooms above their cool bound, neither wants heat → resolved cool.
    await arrange(hass, office_temp=26, studio_temp=25)
    await run(hass)
    assert hass.states.get("input_select.system_hvac_mode").state == "cool"
    assert turned_on(calls, "switch.office_power")
    assert turned_on(calls, "switch.studio_power")
    office_cool = [c for c in calls["temp"]
                   if "climate.office" in _entities(c) and c.data.get("hvac_mode") == "cool"]
    studio_cool = [c for c in calls["temp"]
                   if "climate.studio" in _entities(c) and c.data.get("hvac_mode") == "cool"]
    assert office_cool and office_cool[0].data["temperature"] == 23.9  # cool_bound 24 -> 75 F = 23.9, no lead
    assert studio_cool and studio_cool[0].data["temperature"] == 22.8  # cool_bound 23 -> 73 F = 22.8, no lead


async def test_heat_lead_is_asymmetric_office_zero_studio_positive(coordinator):
    hass, calls = coordinator
    # Both rooms cold → system heats, both heads on. Office (fast) is commanded
    # its bound; studio (slow) is commanded its bound + 1.5 so the inverter commits.
    await arrange(hass, office_temp=18, studio_temp=18)
    await run(hass)
    assert hass.states.get("input_select.system_hvac_mode").state == "heat"
    office_heat = [c for c in calls["temp"]
                   if "climate.office" in _entities(c) and c.data.get("hvac_mode") == "heat"]
    studio_heat = [c for c in calls["temp"]
                   if "climate.studio" in _entities(c) and c.data.get("hvac_mode") == "heat"]
    assert office_heat and office_heat[0].data["temperature"] == 20    # office bound 20, lead 0
    assert studio_heat and studio_heat[0].data["temperature"] == 21.7  # studio 20 + lead 1.5 = 21.5 -> 71 F = 21.7


async def test_demand_drop_turns_head_off(coordinator):
    hass, calls = coordinator
    # Studio was heating; now back in band → head turns off and the system idles.
    await arrange(hass, office_temp=22, studio_temp=22, stored="heat",
                  studio_switch="on", studio_climate="heat")
    await run(hass)
    assert turned_off(calls, "switch.studio_power")
    assert hass.states.get("input_select.system_hvac_mode").state == "idle"


async def test_safety_off_overrides_lockout(coordinator):
    hass, calls = coordinator
    # Master disabled forces heads off even while their lockouts are active.
    await arrange(hass, office_temp=18, studio_temp=18, enabled=False,
                  office_switch="on", studio_switch="on",
                  office_lockout=True, studio_lockout=True)
    await run(hass)
    assert turned_off(calls, "switch.office_power")
    assert turned_off(calls, "switch.studio_power")


async def test_safety_off_arms_lockout(coordinator):
    hass, calls = coordinator
    # A forced-off head arms its lockout so a quick re-enable / backup-heat
    # flap cannot restart the compressor immediately.
    await arrange(hass, office_temp=18, studio_temp=18, enabled=False,
                  office_switch="on", studio_switch="on")
    await run(hass)
    assert hass.states.get("timer.office_head_lockout").state == "active"
    assert hass.states.get("timer.studio_head_lockout").state == "active"


async def test_overcool_turns_off_during_lockout(coordinator):
    hass, calls = coordinator
    # Root-cause regression for the over-cool yo-yo: a head that has cooled past
    # its cutoff must turn OFF *now*, even while its lockout is still running.
    # The lockout is a minimum OFF-time (anti-restart), not a minimum ON-time —
    # forcing the head to keep cooling is what drove the room far below the bound.
    await arrange(hass, office_temp=22, studio_temp=21, stored="cool",
                  studio_switch="on", studio_climate="cool",
                  studio_lockout=True)
    await run(hass)
    assert turned_off(calls, "switch.studio_power")


async def test_no_resend_when_head_already_on_target_step(coordinator):
    hass, calls = coordinator
    # Studio wants heat and the head already sits on the commanded step:
    # 20 + 1.5 = 21.5 C snaps to 71 F, which HA reports back as 21.7.
    await arrange(hass, office_temp=22, studio_temp=18, stored="heat",
                  studio_switch="on", studio_climate="heat")
    hass.states.async_set("climate.studio", "heat", {"temperature": 21.7})
    await hass.async_block_till_done()
    await run(hass)
    studio_temp_calls = [c for c in calls["temp"] if "climate.studio" in _entities(c)]
    assert not studio_temp_calls, (
        f"head already on 71 F, expected no re-command, got {studio_temp_calls}"
    )


async def test_no_resend_when_reported_spelling_differs_from_commanded(coordinator):
    hass, calls = coordinator
    # heat_bound 17 + lead 1.5 = 18.5 C, which snaps to 65 F. The commanded
    # spelling is 18.4 and HA displays 18.3 — the same step, so no re-command.
    await arrange(hass, office_temp=22, studio_temp=15, stored="heat",
                  studio_switch="on", studio_climate="heat")
    await hass.services.async_call(
        "input_number", "set_value",
        {"entity_id": "input_number.studio_heat_bound", "value": 17},
        blocking=True,
    )
    hass.states.async_set("climate.studio", "heat", {"temperature": 18.3})
    await hass.async_block_till_done()
    await run(hass)
    studio_temp_calls = [c for c in calls["temp"] if "climate.studio" in _entities(c)]
    assert not studio_temp_calls, (
        f"18.4 commanded and 18.3 reported are both 65 F, got {studio_temp_calls}"
    )
