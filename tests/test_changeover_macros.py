"""Level 2 tests: changeover.jinja decision macros (pure functions)."""
from tests.util import render, jlist

IMPORTS = (
    "{% from 'changeover.jinja' import heating_degree_hours, "
    "cooling_degree_hours, candidate_mode %}"
)


def call(hass, expr):
    return render(hass, IMPORTS + expr)


async def test_hdh_uniform_cold(hass_repo):
    # 48 h at -10 °C, balance 16 → 26 °C·h x 48
    out = call(hass_repo, "{{ heating_degree_hours(" + jlist([-10] * 48) + ", 16) }}")
    assert out == 1248.0


async def test_cdh_uniform_warm(hass_repo):
    out = call(hass_repo, "{{ cooling_degree_hours(" + jlist([24] * 48) + ", 16) }}")
    assert out == 384.0


async def test_mixed_day_contributes_both_directions(hass_repo):
    # 24 h at 10 °C + 24 h at 22 °C, balance 16: a mean-based method would
    # see ~0; degree-hours see 144 each way.
    temps = jlist([10] * 24 + [22] * 24)
    assert call(hass_repo, "{{ heating_degree_hours(" + temps + ", 16) }}") == 144.0
    assert call(hass_repo, "{{ cooling_degree_hours(" + temps + ", 16) }}") == 144.0


async def test_chinook_afternoon_does_not_flip_the_balance(hass_repo):
    # Named regression from the spec: 44 cold hours vs one 4 h warm chinook.
    temps = jlist([-10] * 44 + [20] * 4)
    hdh = call(hass_repo, "{{ heating_degree_hours(" + temps + ", 16) }}")
    cdh = call(hass_repo, "{{ cooling_degree_hours(" + temps + ", 16) }}")
    assert hdh == 1144.0
    assert cdh == 16.0
    assert call(hass_repo, f"{{{{ candidate_mode({cdh}, {hdh}, 24) }}}}") == "heating"


async def test_candidate_cooling(hass_repo):
    assert call(hass_repo, "{{ candidate_mode(50, 6, 24) }}") == "cooling"


async def test_candidate_heating(hass_repo):
    assert call(hass_repo, "{{ candidate_mode(6, 50, 24) }}") == "heating"


async def test_candidate_off_inside_deadband(hass_repo):
    assert call(hass_repo, "{{ candidate_mode(20, 10, 24) }}") == "off"


async def test_deadband_boundary_is_off(hass_repo):
    # exactly at +K stays off — strict inequality
    assert call(hass_repo, "{{ candidate_mode(30, 6, 24) }}") == "off"


async def test_null_forecast_hours_are_neutral(hass_repo):
    # A flaky EC hour ({'temperature': None}) must not error the sensor:
    # null hours contribute zero degree-hours in both directions.
    # [-10, none, -10, 'unavailable'], balance 16:
    #   -10 → 26 hdh, none/unavailable → 0 each, -10 → 26 hdh = 52 total
    temps = "[-10, none, -10, 'unavailable']"
    assert call(hass_repo, "{{ heating_degree_hours(" + temps + ", 16) }}") == 52.0
    assert call(hass_repo, "{{ cooling_degree_hours(" + temps + ", 16) }}") == 0.0
