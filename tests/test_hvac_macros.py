"""Level 2 tests: hvac.jinja decision macros (pure functions)."""
from tests.util import render

IMPORTS = "{% from 'hvac.jinja' import room_demand, resolve_mode, head_target %}"


def call(hass, expr):
    return render(hass, IMPORTS + expr)


# --- room_demand: which direction a single room wants -----------------------

async def test_room_wants_heat_below_heat_bound(hass_repo):
    assert call(hass_repo, "{{ room_demand(18, 20, 24, 0.5, 'none') }}") == "heat"


async def test_room_wants_cool_above_cool_bound(hass_repo):
    assert call(hass_repo, "{{ room_demand(25, 20, 24, 0.5, 'none') }}") == "cool"


async def test_room_in_band_wants_nothing(hass_repo):
    assert call(hass_repo, "{{ room_demand(22, 20, 24, 0.5, 'none') }}") == "none"


async def test_heat_hysteresis_keeps_heating_past_bound(hass_repo):
    # Already heating, 0.3 above the bound, differential 0.5 → keep heating.
    assert call(hass_repo, "{{ room_demand(20.3, 20, 24, 0.5, 'heat') }}") == "heat"


async def test_heat_hysteresis_does_not_start_inside_differential(hass_repo):
    # Not currently heating at the same temp → no demand (won't short-cycle on).
    assert call(hass_repo, "{{ room_demand(20.3, 20, 24, 0.5, 'none') }}") == "none"


async def test_cool_hysteresis_keeps_cooling_past_bound(hass_repo):
    assert call(hass_repo, "{{ room_demand(23.7, 20, 24, 0.5, 'cool') }}") == "cool"


async def test_cool_hysteresis_does_not_start_inside_differential(hass_repo):
    # Not currently cooling, 0.3 below the cool bound → no demand.
    assert call(hass_repo, "{{ room_demand(23.7, 20, 24, 0.5, 'none') }}") == "none"


# --- resolve_mode: heating wins ---------------------------------------------

async def test_resolve_heating_wins_when_office_cools_studio_heats(hass_repo):
    assert call(hass_repo, "{{ resolve_mode('cool', 'heat') }}") == "heat"


async def test_resolve_heating_wins_when_office_heats_studio_cools(hass_repo):
    assert call(hass_repo, "{{ resolve_mode('heat', 'cool') }}") == "heat"


async def test_resolve_cool_when_only_cool(hass_repo):
    assert call(hass_repo, "{{ resolve_mode('none', 'cool') }}") == "cool"


async def test_resolve_idle_when_no_demand(hass_repo):
    assert call(hass_repo, "{{ resolve_mode('none', 'none') }}") == "idle"


# --- head_target: bound + lead, clamped to [17, 30] -------------------------

async def test_head_target_heat_is_bound_plus_lead(hass_repo):
    assert call(hass_repo, "{{ head_target('heat', 20, 24, 2) }}") == 22


async def test_head_target_cool_is_bound_minus_lead(hass_repo):
    assert call(hass_repo, "{{ head_target('cool', 20, 24, 2) }}") == 22


async def test_head_target_clamps_high(hass_repo):
    assert call(hass_repo, "{{ head_target('heat', 29, 33, 2) }}") == 30


async def test_head_target_clamps_low(hass_repo):
    assert call(hass_repo, "{{ head_target('cool', 16, 17, 2) }}") == 17


async def test_head_target_empty_for_idle(hass_repo):
    # resolve_mode yields 'idle'; head_target has no active bound then.
    assert call(hass_repo, "{{ head_target('idle', 20, 24, 2) }}") == ""
