"""Level 3 tests: studio_dehumidifier_relay_failure loaded from automations.yaml.

The dehumidifier's compressor is an inductive load, and the relay that carries
it is the part that fails. The failure is not silent-but-harmless: a welded
relay keeps the compressor running with the switch commanded open, so the room
dries out past the set point with nothing in the control loop able to stop it.

Measured current with the switch off is the signature. The wattage threshold
lives in `conditions:` as well as in the trigger, because `automation.trigger`
bypasses trigger blocks entirely — a threshold that existed only in the trigger
would be unverifiable here.
"""
import yaml
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

import pytest

from tests.conftest import REPO_ROOT

AUTOMATION_ID = "studio_dehumidifier_relay_failure"
ENTITY = f"automation.{AUTOMATION_ID}"
SWITCH = "switch.studio_dehumidifier"
WATTS = "sensor.studio_dehumidifier_electric_consumption_w"

# Running draw for the compressor. Any value well clear of the threshold works;
# the point is that it is unambiguously a load rather than meter noise.
RUNNING_WATTS = 250


@pytest.fixture
def automation_config():
    autos = yaml.safe_load((REPO_ROOT / "automations.yaml").read_text())
    chosen = [a for a in autos if a.get("id") == AUTOMATION_ID]
    assert len(chosen) == 1, f"{AUTOMATION_ID} missing from automations.yaml"
    return chosen[0]


@pytest.fixture
async def detector(hass_repo, automation_config):
    hass = hass_repo
    assert await async_setup_component(
        hass, "automation", {"automation": [automation_config]}
    )
    await hass.services.async_call(
        "automation", "turn_off", {"entity_id": ENTITY}, blocking=True
    )
    notifications = async_mock_service(hass, "notify", "notification_group")
    yield hass, notifications
    await hass.services.async_call(
        "automation", "turn_off", {"entity_id": "all"}, blocking=True
    )
    await hass.async_block_till_done()


async def arrange(hass, *, switch, watts):
    hass.states.async_set(SWITCH, switch)
    hass.states.async_set(WATTS, watts)
    await hass.async_block_till_done()


async def run(hass):
    await hass.services.async_call(
        "automation", "trigger",
        {"entity_id": ENTITY, "skip_condition": False},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_notifies_when_current_flows_with_switch_off(detector):
    """The failure signature: the relay passes current with the switch open."""
    hass, notifications = detector
    await arrange(hass, switch="off", watts=RUNNING_WATTS)
    await run(hass)
    assert len(notifications) == 1


async def test_silent_while_the_switch_is_on(detector):
    """Current with the switch on is the dehumidifier working normally."""
    hass, notifications = detector
    await arrange(hass, switch="on", watts=RUNNING_WATTS)
    await run(hass)
    assert not notifications


async def test_silent_below_the_threshold(detector):
    """Meter noise with the switch off is not a welded relay."""
    hass, notifications = detector
    await arrange(hass, switch="off", watts=1.2)
    await run(hass)
    assert not notifications


async def test_silent_when_the_meter_is_unavailable(detector):
    """An unavailable meter floats to 0 W, which must not read as healthy.

    It must not read as a fault either — the same short-circuit-on-bad-data
    rule the HVAC coordinator applies.
    """
    hass, notifications = detector
    await arrange(hass, switch="off", watts="unavailable")
    await run(hass)
    assert not notifications


async def test_silent_when_the_switch_is_unavailable(detector):
    """A switch reading `unavailable` is not a switch reading `off`."""
    hass, notifications = detector
    await arrange(hass, switch="unavailable", watts=RUNNING_WATTS)
    await run(hass)
    assert not notifications


def test_trigger_threshold_matches_condition_threshold(automation_config):
    """The trigger debounces; the condition decides. They must agree.

    The trigger's `above:` cannot reference `variables:` — HA renders those
    after the trigger fires — so the number is written twice. If the two drift,
    the automation either alerts below its stated threshold or never fires at
    all, and nothing else in the suite would notice.
    """
    triggers = [
        t for t in automation_config["triggers"]
        if t.get("trigger") == "numeric_state" and t.get("entity_id") == WATTS
    ]
    assert len(triggers) == 1, f"expected one numeric_state trigger on {WATTS}"
    assert triggers[0]["above"] == automation_config["variables"]["leak_watts"]
