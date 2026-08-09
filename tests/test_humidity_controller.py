"""Level 3 tests: studio_humidity_controller loaded from automations.yaml.

The controller keeps a tight band around input_number.humidity_set_point
(±input_number.humidity_tolerance) and reconciles the dehumidifier and
humidifier. Short-cycle / fight protection uses two CROSS-DEVICE cooldown
timers:

  timer.dehumidify_cooldown — armed when the dehumidifier turns OFF; blocks the
                              HUMIDIFIER from turning on (so a dehumidify
                              overshoot dipping below the humidifier ON point
                              recovers before the humidifier can react).
  timer.humidify_cooldown   — armed when the humidifier turns OFF; blocks the
                              DEHUMIDIFIER from turning on.

A device's own cooldown never blocks that same device from re-engaging — the
tight dead band governs same-device cycling — so the dehumidifier re-engages at
its high threshold instead of drifting up while a single shared cooldown runs.
"""
import yaml
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

import pytest

from tests.conftest import REPO_ROOT

DEHUM = "switch.studio_dehumidifier_socket_1"
HUMID = "switch.studio_humidifier_socket_1"
HUM_SENSOR = "sensor.tz3000_utwgoauk_snzb_02_humidity"

# set_point 42, tolerance 1.5 → dehum ON ≥43.5 / OFF <42; humid ON ≤40.5 / OFF >42
SET_POINT = 42
TOLERANCE = 1.5


@pytest.fixture
async def controller(hass_helpers):
    hass = hass_helpers
    autos = yaml.safe_load((REPO_ROOT / "automations.yaml").read_text())
    chosen = [a for a in autos if a.get("id") == "studio_humidity_controller"]
    assert len(chosen) == 1, "studio_humidity_controller missing from automations.yaml"
    assert await async_setup_component(hass, "automation", {"automation": chosen})
    await hass.services.async_call(
        "automation", "turn_off",
        {"entity_id": "automation.studio_humidity_controller"}, blocking=True,
    )
    calls = {
        "on": async_mock_service(hass, "switch", "turn_on"),
        "off": async_mock_service(hass, "switch", "turn_off"),
        "bool_on": async_mock_service(hass, "input_boolean", "turn_on"),
        "bool_off": async_mock_service(hass, "input_boolean", "turn_off"),
    }
    yield hass, calls
    await hass.services.async_call(
        "automation", "turn_off", {"entity_id": "all"}, blocking=True
    )
    for t in ("dehumidify_cooldown", "humidify_cooldown",
              "dehumidifier_manual_grace", "humidifier_manual_grace"):
        await hass.services.async_call(
            "timer", "cancel", {"entity_id": f"timer.{t}"}, blocking=True
        )
    await hass.async_block_till_done()


async def arrange(hass, *, humidity, dehum="off", humid="off",
                  dehumidify_cooldown=False, humidify_cooldown=False,
                  dehum_grace=False, humid_grace=False):
    for ent, val in (("humidity_set_point", SET_POINT),
                     ("humidity_tolerance", TOLERANCE)):
        await hass.services.async_call(
            "input_number", "set_value",
            {"entity_id": f"input_number.{ent}", "value": val}, blocking=True,
        )
    hass.states.async_set(HUM_SENSOR, humidity)
    hass.states.async_set(DEHUM, dehum)
    hass.states.async_set(HUMID, humid)
    timers = {
        "dehumidify_cooldown": dehumidify_cooldown,
        "humidify_cooldown": humidify_cooldown,
        "dehumidifier_manual_grace": dehum_grace,
        "humidifier_manual_grace": humid_grace,
    }
    for name, active in timers.items():
        if active:
            await hass.services.async_call(
                "timer", "start",
                {"entity_id": f"timer.{name}", "duration": "00:30:00"},
                blocking=True,
            )
        else:
            await hass.services.async_call(
                "timer", "cancel", {"entity_id": f"timer.{name}"}, blocking=True
            )
    await hass.async_block_till_done()


async def run(hass):
    await hass.services.async_call(
        "automation", "trigger",
        {"entity_id": "automation.studio_humidity_controller",
         "skip_condition": False},
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


# --- basic reconciliation ------------------------------------------------

async def test_dehumidifier_turns_on_above_high_threshold(controller):
    hass, calls = controller
    await arrange(hass, humidity=44)
    await run(hass)
    assert turned_on(calls, DEHUM)
    assert not turned_on(calls, HUMID)


async def test_humidifier_turns_on_below_low_threshold(controller):
    hass, calls = controller
    await arrange(hass, humidity=40)
    await run(hass)
    assert turned_on(calls, HUMID)
    assert not turned_on(calls, DEHUM)


async def test_in_band_holds_both_off(controller):
    hass, calls = controller
    await arrange(hass, humidity=42)
    await run(hass)
    assert not calls["on"]


# --- turn-off arms the matching same-device cooldown ---------------------

async def test_dehumidifier_turn_off_arms_dehumidify_cooldown(controller):
    hass, calls = controller
    await arrange(hass, humidity=41, dehum="on")
    await run(hass)
    assert turned_off(calls, DEHUM)
    assert hass.states.get("timer.dehumidify_cooldown").state == "active"
    assert hass.states.get("timer.humidify_cooldown").state == "idle"


async def test_humidifier_turn_off_arms_humidify_cooldown(controller):
    hass, calls = controller
    await arrange(hass, humidity=43, humid="on")
    await run(hass)
    assert turned_off(calls, HUMID)
    assert hass.states.get("timer.humidify_cooldown").state == "active"
    assert hass.states.get("timer.dehumidify_cooldown").state == "idle"


# --- the fight fix: a device's cooldown blocks the OPPOSITE device --------

async def test_overshoot_does_not_trigger_humidifier_during_dehumidify_cooldown(controller):
    hass, calls = controller
    # Dehumidifier just shut off and the room is coasting down past the
    # humidifier ON point. The humidifier must stay off until the overshoot
    # recovers (this is the recently-observed fight under high outdoor humidity).
    await arrange(hass, humidity=39, dehumidify_cooldown=True)
    await run(hass)
    assert not turned_on(calls, HUMID)


async def test_dehumidify_cooldown_does_not_block_dehumidifier(controller):
    hass, calls = controller
    # The dehumidifier's OWN cooldown must not stop it re-engaging at its high
    # threshold — that drift (humidity climbing while a shared cooldown ran) is
    # what kept the room from holding a tight set point.
    await arrange(hass, humidity=44, dehumidify_cooldown=True)
    await run(hass)
    assert turned_on(calls, DEHUM)


async def test_humidify_cooldown_blocks_dehumidifier(controller):
    hass, calls = controller
    # Reverse direction: after the humidifier turns off, a humidify overshoot
    # rising past the dehumidifier ON point must not trip the dehumidifier.
    await arrange(hass, humidity=44, humidify_cooldown=True)
    await run(hass)
    assert not turned_on(calls, DEHUM)


async def test_humidify_cooldown_does_not_block_humidifier(controller):
    hass, calls = controller
    await arrange(hass, humidity=40, humidify_cooldown=True)
    await run(hass)
    assert turned_on(calls, HUMID)


# --- invariants preserved ------------------------------------------------

async def test_both_on_safety_turns_off_humidifier_when_humid(controller):
    hass, calls = controller
    await arrange(hass, humidity=44, dehum="on", humid="on")
    await run(hass)
    assert turned_off(calls, HUMID)
    assert not turned_off(calls, DEHUM)


async def test_manual_grace_blocks_controller_turn_off(controller):
    hass, calls = controller
    await arrange(hass, humidity=41, dehum="on", dehum_grace=True)
    await run(hass)
    assert not turned_off(calls, DEHUM)
