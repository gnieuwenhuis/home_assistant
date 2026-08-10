"""Level 3 tests: eva_lamp_auto_off loaded from automations.yaml.

Unlike the other Level 3 suites, these leave the automation ENABLED and drive
real state changes carrying an explicit Context. The rule under test — whether a
turn-on was commanded by an automation — reads trigger.to_state.context, which
`automation.trigger` never populates, so the automation.trigger pattern used by
test_hvac_coordinator.py and test_humidity_controller.py cannot reach it. Firing
the triggers for real is also the only coverage in this repo of a trigger block.

Context shapes, and what each one means:
    Context()                     physical button on the plug   -> arms
    Context(user_id="...")        HA dashboard / UI toggle      -> arms
    Context(parent_id="...")      an automation commanded it    -> does not arm
"""
from datetime import timedelta

import pytest
import yaml
from homeassistant.core import Context
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_mock_service

from tests.conftest import REPO_ROOT

LAMP = "switch.eva_lamp_socket_1"
TIMER = "timer.eva_lamp_auto_off"


@pytest.fixture
async def lamp(hass_helpers):
    hass = hass_helpers
    autos = yaml.safe_load((REPO_ROOT / "automations.yaml").read_text())
    chosen = [a for a in autos if a.get("id") == "eva_lamp_auto_off"]
    assert len(chosen) == 1, "eva_lamp_auto_off missing from automations.yaml"
    assert await async_setup_component(hass, "automation", {"automation": chosen})
    hass.states.async_set(LAMP, "off")
    await hass.async_block_till_done()
    calls = {"off": async_mock_service(hass, "switch", "turn_off")}
    yield hass, calls
    await hass.services.async_call(
        "automation", "turn_off", {"entity_id": "all"}, blocking=True
    )
    await hass.services.async_call(
        "timer", "cancel", {"entity_id": TIMER}, blocking=True
    )
    await hass.async_block_till_done()


async def press(hass, state, context):
    """Drive a real state change so the automation's triggers fire."""
    hass.states.async_set(LAMP, state, context=context)
    await hass.async_block_till_done()


def _entities(call):
    e = call.data.get("entity_id")
    return e if isinstance(e, list) else [e]


# --- the discriminator ---------------------------------------------------

async def test_physical_press_arms_the_timer(lamp):
    hass, _ = lamp
    await press(hass, "on", Context())
    assert hass.states.get(TIMER).state == "active"


async def test_ui_toggle_arms_the_timer(lamp):
    hass, _ = lamp
    await press(hass, "on", Context(user_id="a1b2c3"))
    assert hass.states.get(TIMER).state == "active"


async def test_automation_commanded_on_does_not_arm_the_timer(lamp):
    hass, _ = lamp
    await press(hass, "on", Context(parent_id="01JABCDEF0123456789ABCDEFG"))
    assert hass.states.get(TIMER).state == "idle"


async def test_reconnect_already_on_arms_the_timer(lamp):
    # The plug rests `unavailable`; coming back already on is device-originated,
    # so it earns a cutoff rather than staying on indefinitely.
    hass, _ = lamp
    await press(hass, "unavailable", Context())
    await press(hass, "on", Context())
    assert hass.states.get(TIMER).state == "active"


# --- cancellation --------------------------------------------------------

async def test_turning_the_lamp_off_cancels_the_timer(lamp):
    hass, _ = lamp
    await press(hass, "on", Context())
    assert hass.states.get(TIMER).state == "active"
    await press(hass, "off", Context())
    assert hass.states.get(TIMER).state == "idle"


# --- the cutoff ----------------------------------------------------------

async def test_timer_finished_switches_the_lamp_off(lamp):
    hass, calls = lamp
    await press(hass, "on", Context())
    hass.bus.async_fire("timer.finished", {"entity_id": TIMER})
    await hass.async_block_till_done()
    assert len(calls["off"]) == 1
    assert LAMP in _entities(calls["off"][0])


async def test_timer_finished_is_a_no_op_when_already_off(lamp):
    # Guards against a redundant call at the Tuya cloud: HA does not dedupe
    # service calls, so the branch checks the lamp is still on.
    hass, calls = lamp
    hass.bus.async_fire("timer.finished", {"entity_id": TIMER})
    await hass.async_block_till_done()
    assert calls["off"] == []


async def test_second_press_gives_a_fresh_full_window(lamp, freezer):
    hass, _ = lamp
    await press(hass, "on", Context())
    freezer.tick(timedelta(minutes=10))
    await press(hass, "off", Context())
    await press(hass, "on", Context())
    finishes = dt_util.parse_datetime(
        hass.states.get(TIMER).attributes["finishes_at"]
    )
    remaining = finishes - dt_util.utcnow()
    assert timedelta(minutes=29) < remaining <= timedelta(minutes=30)
