"""Every automation in automations.yaml must survive Home Assistant's schema.

The Level 3 tests each filter `automations.yaml` down to the one `id` they
exercise, so the other automations are parsed as YAML and never validated. An
automation HA rejects still gets an entity — in state `unavailable` — and the
rest of the file loads around it, so the instance looks healthy while, say,
backup heat silently never arms below −12 °C.
"""
import pytest
import yaml
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

from tests.conftest import REPO_ROOT

# Degrees below heat_bound each baseboard idles at while the heat pump leads.
# automations.yaml spells this constant once per baseboard in each of the two
# automations that write a standby setpoint.
STANDBY_OFFSET = 2.5
STANDBY_COPIES = 4
# The comfort midpoint is spelled once per baseboard in the backup-heat entry
# automation and once per baseboard in baseboard_standby_setpoint.
MIDPOINT_COPIES = 4
# Every automation that commands a baseboard setpoint.
BASEBOARD_WRITERS = (
    "1756873917108", "1756874009383", "baseboard_standby_setpoint",
)

OFFICE_BASEBOARD = "climate.neviweb130_climate_th1123wf"
STUDIO_BASEBOARD = "climate.neviweb130_climate_th1124wf"

BOUNDS = {
    "input_number.office_heat_bound": 20,
    "input_number.office_cool_bound": 24,
    "input_number.studio_heat_bound": 19,
    "input_number.studio_cool_bound": 23,
}


def _load_automations():
    return yaml.safe_load((REPO_ROOT / "automations.yaml").read_text())


def _setpoint_expressions(node, found=None):
    """Every climate.set_temperature template, and every variable one can read."""
    found = [] if found is None else found
    if isinstance(node, dict):
        if node.get("action") == "climate.set_temperature":
            # A setpoint written as a bare number is legal YAML and loads as one.
            found.append(str(node["data"]["temperature"]))
        found.extend(str(value) for value in node.get("variables", {}).values())
        for value in node.values():
            _setpoint_expressions(value, found)
    elif isinstance(node, list):
        for value in node:
            _setpoint_expressions(value, found)
    return found


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


async def test_baseboard_setpoint_tracks_all_four_bounds(hass_helpers):
    """Both setpoints derive from bounds, and the midpoint needs the cool ones."""
    autos = _load_automations()
    chosen = [a for a in autos if a.get("id") == "baseboard_standby_setpoint"]
    assert len(chosen) == 1, "baseboard_standby_setpoint missing"
    triggered = set()
    for trig in chosen[0]["triggers"]:
        ent = trig.get("entity_id")
        triggered.update(ent if isinstance(ent, list) else [ent])
    assert set(BOUNDS) <= triggered, set(BOUNDS) - triggered


def _per_room_shape(template):
    """One room's expression, rewritten so the other room's reads the same."""
    collapsed = " ".join(template.split())
    for room in ("office", "studio"):
        collapsed = collapsed.replace(f"{room}_", "<room>_")
    return collapsed


def test_standby_offset_is_identical_in_every_copy():
    """A standby copy that drifts puts a baseboard in competition with the pump."""
    writers = [a for a in _load_automations() if a.get("id") in BASEBOARD_WRITERS]
    standby = [t for t in _setpoint_expressions(writers)
               if "heat_bound" in t and "cool_bound" not in t]
    assert len(standby) == STANDBY_COPIES, standby
    for template in standby:
        assert f"- {STANDBY_OFFSET}" in template, template


def test_comfort_midpoint_is_identical_in_every_copy():
    """Two copies that disagree hold a delta the gate rewrites on every trigger."""
    writers = [a for a in _load_automations() if a.get("id") in BASEBOARD_WRITERS]
    midpoints = [t for t in _setpoint_expressions(writers)
                 if "heat_bound" in t and "cool_bound" in t]
    assert len(midpoints) == MIDPOINT_COPIES, midpoints
    assert len({_per_room_shape(t) for t in midpoints}) == 1, midpoints


@pytest.fixture
async def baseboard_setpoint(hass_helpers):
    hass = hass_helpers
    chosen = [a for a in _load_automations()
              if a.get("id") == "baseboard_standby_setpoint"]
    assert len(chosen) == 1, "baseboard_standby_setpoint missing from automations.yaml"
    assert await async_setup_component(hass, "automation", {"automation": chosen})
    # The alias is what HA slugs into an entity_id on a registry-less test run,
    # so read the entity back rather than spelling the slug here.
    [entity_id] = hass.states.async_entity_ids("automation")
    await hass.services.async_call(
        "automation", "turn_off", {"entity_id": entity_id}, blocking=True,
    )
    calls = async_mock_service(hass, "climate", "set_temperature")
    yield hass, entity_id, calls
    await hass.services.async_call(
        "automation", "turn_off", {"entity_id": "all"}, blocking=True
    )
    await hass.async_block_till_done()


async def _arrange_bounds(hass, *, backup, overrides=None):
    for entity_id, value in {**BOUNDS, **(overrides or {})}.items():
        await hass.services.async_call(
            "input_number", "set_value",
            {"entity_id": entity_id, "value": value}, blocking=True,
        )
    await hass.services.async_call(
        "input_boolean", "turn_on" if backup else "turn_off",
        {"entity_id": "input_boolean.backup_heat"}, blocking=True,
    )
    await hass.async_block_till_done()


async def _run(hass, entity_id):
    await hass.services.async_call(
        "automation", "trigger",
        {"entity_id": entity_id, "skip_condition": False}, blocking=True,
    )
    await hass.async_block_till_done()


async def _hold(hass, office, studio):
    """Give each baseboard a stored target, the value the delta gate reads."""
    hass.states.async_set(OFFICE_BASEBOARD, "heat", {"temperature": office})
    hass.states.async_set(STUDIO_BASEBOARD, "heat", {"temperature": studio})
    await hass.async_block_till_done()


def _commanded(calls, baseboard):
    """Temperatures commanded to one baseboard, in call order."""
    out = []
    for call in calls:
        target = call.data.get("entity_id")
        targets = [target] if isinstance(target, str) else target
        if baseboard in targets:
            out.append(call.data["temperature"])
    return out


async def test_standby_writes_both_baseboards_under_their_heat_bound(
        baseboard_setpoint):
    """Backup heat off: each baseboard sits heat_bound - 2.5 under the pump."""
    hass, entity_id, calls = baseboard_setpoint
    await _arrange_bounds(hass, backup=False)
    await _run(hass, entity_id)
    office = BOUNDS["input_number.office_heat_bound"] - STANDBY_OFFSET
    studio = BOUNDS["input_number.studio_heat_bound"] - STANDBY_OFFSET
    assert _commanded(calls, OFFICE_BASEBOARD) == [office]
    assert _commanded(calls, STUDIO_BASEBOARD) == [studio]


async def test_backup_heat_writes_both_baseboards_the_comfort_midpoint(
        baseboard_setpoint):
    """Backup heat on: the heads are forced off, so the midpoint must track too."""
    hass, entity_id, calls = baseboard_setpoint
    await _arrange_bounds(hass, backup=True)
    await _run(hass, entity_id)
    office = (BOUNDS["input_number.office_heat_bound"]
              + BOUNDS["input_number.office_cool_bound"]) / 2
    studio = (BOUNDS["input_number.studio_heat_bound"]
              + BOUNDS["input_number.studio_cool_bound"]) / 2
    assert _commanded(calls, OFFICE_BASEBOARD) == [office]
    assert _commanded(calls, STUDIO_BASEBOARD) == [studio]


async def test_a_setpoint_the_baseboard_already_holds_is_not_rewritten(
        baseboard_setpoint):
    """A cool bound moves, the standby arm reads only heat_bound: nothing to say."""
    hass, entity_id, calls = baseboard_setpoint
    await _arrange_bounds(hass, backup=False)
    await _hold(hass,
                BOUNDS["input_number.office_heat_bound"] - STANDBY_OFFSET,
                BOUNDS["input_number.studio_heat_bound"] - STANDBY_OFFSET)
    await _run(hass, entity_id)
    assert calls == []


async def test_only_the_baseboard_whose_setpoint_moved_is_written(
        baseboard_setpoint):
    """One card drag writes both bounds; only a real delta reaches the cloud."""
    hass, entity_id, calls = baseboard_setpoint
    await _arrange_bounds(hass, backup=False)
    studio = BOUNDS["input_number.studio_heat_bound"] - STANDBY_OFFSET
    await _hold(hass,
                BOUNDS["input_number.office_heat_bound"] - STANDBY_OFFSET,
                studio + 1)
    await _run(hass, entity_id)
    assert _commanded(calls, OFFICE_BASEBOARD) == []
    assert _commanded(calls, STUDIO_BASEBOARD) == [studio]


async def test_the_comfort_midpoint_is_rounded_to_the_baseboards_half_step(
        baseboard_setpoint):
    """19.0 / 23.5 midpoints at 21.25, a step a baseboard cannot store."""
    hass, entity_id, calls = baseboard_setpoint
    await _arrange_bounds(hass, backup=True, overrides={
        "input_number.studio_heat_bound": 19.0,
        "input_number.studio_cool_bound": 23.5,
    })
    await _run(hass, entity_id)
    assert _commanded(calls, STUDIO_BASEBOARD) == [21.5]
