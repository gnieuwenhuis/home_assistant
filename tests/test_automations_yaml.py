"""Every automation in automations.yaml must survive Home Assistant's schema.

The Level 3 tests each filter `automations.yaml` down to the one `id` they
exercise, so the other automations are parsed as YAML and never validated. An
automation HA rejects still gets an entity — in state `unavailable` — and the
rest of the file loads around it, so the instance looks healthy while, say,
backup heat silently never arms below −12 °C.
"""
import yaml
from homeassistant.setup import async_setup_component

from tests.conftest import REPO_ROOT


async def test_all_automations_load(hass_helpers):
    hass = hass_helpers
    autos = yaml.safe_load((REPO_ROOT / "automations.yaml").read_text())
    assert await async_setup_component(hass, "automation", {"automation": autos})
    await hass.async_block_till_done()
    # The coordinator's 5-minute time_pattern trigger otherwise leaves a timer
    # running past the end of the test.
    await hass.services.async_call(
        "automation", "turn_off", {"entity_id": "all"}, blocking=True
    )
    loaded = hass.states.async_entity_ids("automation")
    bad = {e: hass.states.get(e).state
           for e in loaded
           if hass.states.get(e).state == "unavailable"}
    assert not bad, bad
    assert len(loaded) == len(autos)
