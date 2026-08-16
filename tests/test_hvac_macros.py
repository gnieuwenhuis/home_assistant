"""Level 2 tests: hvac.jinja decision macros (pure functions)."""
from tests.util import render

IMPORTS = ("{% from 'hvac.jinja' import room_demand, resolve_mode, head_target, "
           "snap_to_head_grid, command_step, report_step %}")


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
    # 22 C is 71.6 F; nearest step 72 F = 22.3 C commanded.
    assert call(hass_repo, "{{ head_target('heat', 20, 24, 2) }}") == 22.3


async def test_head_target_cool_is_bound_minus_lead(hass_repo):
    assert call(hass_repo, "{{ head_target('cool', 20, 24, 2) }}") == 22.3


async def test_head_target_clamps_high(hass_repo):
    assert call(hass_repo, "{{ head_target('heat', 29, 33, 2) }}") == 30


async def test_head_target_clamps_low(hass_repo):
    # Clamps to 17, then snaps to 63 F = 17.3 C commanded.
    assert call(hass_repo, "{{ head_target('cool', 16, 17, 2) }}") == 17.3


async def test_head_target_empty_for_idle(hass_repo):
    # resolve_mode yields 'idle'; head_target has no active bound then.
    assert call(hass_repo, "{{ head_target('idle', 20, 24, 2) }}") == ""


# --- snap_to_head_grid: the head's grid is whole degrees Fahrenheit ---------

async def test_snap_lands_on_a_whole_fahrenheit_step(hass_repo):
    # 20.5 C is 68.9 F; the nearest step is 69 F = 20.5556 C.
    assert call(hass_repo, "{{ snap_to_head_grid(20.5) }}") == 20.6


async def test_snap_rounds_celsius_up_so_truncation_lands_right(hass_repo):
    # 63 F is 17.2222 C. Sending 17.2 gives 62.96 F, which truncates one step
    # low, so the commanded spelling rounds up.
    assert call(hass_repo, "{{ snap_to_head_grid(17.0) }}") == 17.3


async def test_snap_is_identity_on_an_exact_step(hass_repo):
    assert call(hass_repo, "{{ snap_to_head_grid(20.0) }}") == 20.0


async def test_snap_never_escapes_the_upper_clamp(hass_repo):
    # 30 C is exactly 86 F, so nothing above the clamp can be produced.
    assert call(hass_repo, "{{ snap_to_head_grid(29.8) }}") == 30.0


# --- the three ties: half-degree Fahrenheit values must round up ------------

async def test_snap_breaks_the_low_tie_upward(hass_repo):
    # 17.5 C is exactly 63.5 F; half-up takes 64 F = 17.7778 C.
    assert call(hass_repo, "{{ snap_to_head_grid(17.5) }}") == 17.8


async def test_snap_breaks_the_middle_tie_upward(hass_repo):
    # 22.5 C is exactly 72.5 F; half-up takes 73 F = 22.7778 C. Tie-to-even
    # takes 72 F, which is where a 22.0 C request already lands.
    assert call(hass_repo, "{{ snap_to_head_grid(22.5) }}") == 22.8


async def test_snap_breaks_the_high_tie_upward(hass_repo):
    # 27.5 C is exactly 81.5 F; half-up takes 82 F = 27.7778 C.
    assert call(hass_repo, "{{ snap_to_head_grid(27.5) }}") == 27.8


async def test_a_half_degree_lead_step_moves_the_commanded_value(hass_repo):
    # At the live studio heat bound of 19, lead 3.0 asks for 22.0 C and lead 3.5
    # asks for 22.5 C. A retune reads a lead as saturated when stepping it
    # commands the same value, so the two must differ.
    at_3_0 = call(hass_repo, "{{ head_target('heat', 19, 23, 3.0) }}")
    at_3_5 = call(hass_repo, "{{ head_target('heat', 19, 23, 3.5) }}")
    assert at_3_0 == 22.3
    assert at_3_5 == 22.8
    assert at_3_0 != at_3_5


# --- command_step / report_step: the same physical step from both sides -----

async def test_command_step_truncates_like_the_head(hass_repo):
    # 20.5 C is 68.9 F; the head truncates to 68 F.
    assert call(hass_repo, "{{ command_step(20.5) }}") == 68


async def test_report_step_recovers_the_step_behind_a_reading(hass_repo):
    # HA shows 20.6 for a head sitting on 69 F.
    assert call(hass_repo, "{{ report_step(20.6) }}") == 69


async def test_snapped_command_and_its_reading_agree(hass_repo):
    # The gate settles only if both sides name the same step. 17.3 is sent,
    # 17.2 is displayed, and both are 63 F.
    assert call(hass_repo, "{{ command_step(17.3) }}") == 63
    assert call(hass_repo, "{{ report_step(17.2) }}") == 63


async def test_a_bound_change_across_a_step_still_differs(hass_repo):
    # 21.7 C (71 F) against a head resting on 69 F must not compare equal.
    assert call(hass_repo, "{{ command_step(21.7) }}") == 71
    assert call(hass_repo, "{{ report_step(20.6) }}") == 69
