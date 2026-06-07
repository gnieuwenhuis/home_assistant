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


CONFIRM_IMPORT = "{% from 'changeover.jinja' import confirmation %}"


def confirm(hass, candidate, office_mean, studio_mean, office_duty, studio_duty):
    """Both rooms: preferred 21, swing 2 → band [19, 23]. Duties in percent."""
    expr = (
        CONFIRM_IMPORT
        + "{{ confirmation('" + candidate + "', "
        + f"{office_mean}, {studio_mean}, {office_duty}, {studio_duty}, "
        + "21, 2, 21, 2) }}"
    )
    return render(hass, expr)


async def test_cooling_confirmed_by_idle_hot_studio(hass_repo):
    assert confirm(hass_repo, "cooling", 21, 25.5, 0, 0) is True


async def test_overshoot_alibi_blocks_busy_studio(hass_repo):
    # Studio hot but its pump ran (15 % duty) → the pump may be the culprit.
    assert confirm(hass_repo, "cooling", 21, 25.5, 0, 15) is False


async def test_office_overshoot_alibi(hass_repo):
    # Named regression from the spec: oversized office head overshoots; a hot
    # office with nonzero duty cannot confirm cooling.
    assert confirm(hass_repo, "cooling", 24.5, 21, 10, 0) is False


async def test_heating_confirmed_by_idle_cold_office(hass_repo):
    assert confirm(hass_repo, "heating", 17.0, 21, 0, 0) is True


async def test_off_requires_both_idle(hass_repo):
    assert confirm(hass_repo, "off", 21, 21, 0.5, 1.9) is True
    assert confirm(hass_repo, "off", 21, 21, 0, 5) is False


async def test_duty_floor_tolerates_heartbeat_blips(hass_repo):
    # 1.9 % < the 2 % floor → still counts as idle.
    assert confirm(hass_repo, "cooling", 21, 25.5, 0, 1.9) is True


async def test_unparseable_duty_fails_safe(hass_repo):
    expr = (
        CONFIRM_IMPORT
        + "{{ confirmation('cooling', 21, 25.5, 0, 'unknown', 21, 2, 21, 2) }}"
    )
    assert render(hass_repo, expr) is False


async def test_unknown_candidate_is_false(hass_repo):
    assert confirm(hass_repo, "nonsense", 17, 25.5, 0, 0) is False


async def test_unparseable_mean_is_neutral(hass_repo):
    # A flaky mean sensor renders as the string 'unknown'; it must not error
    # the macro (HA renders automation variables before conditions can guard)
    # and must not fabricate evidence — it defaults to preferred (neutral).
    def expr(candidate, studio_mean):
        return (
            CONFIRM_IMPORT
            + "{{ confirmation('"
            + candidate
            + "', 'unknown', "
            + studio_mean
            + ", 0, 0, 21, 2, 21, 2) }}"
        )

    assert render(hass_repo, expr("cooling", "'unknown'")) is False
    assert render(hass_repo, expr("heating", "'unknown'")) is False
    assert render(hass_repo, expr("off", "'unknown'")) is True
    # the healthy room's evidence still works alongside a flaky one
    assert render(hass_repo, expr("cooling", "25.5")) is True


MEANS_IMPORT = "{% from 'changeover.jinja' import daily_means %}"


def means(hass, entries_literal):
    return render(hass, MEANS_IMPORT + "{{ daily_means(" + entries_literal + ") }}")


async def test_daily_means_basic(hass_repo):
    # (high + low) / 2 per entry
    entries = "[{'temperature': 20, 'templow': 10}, {'temperature': 4, 'templow': -2}]"
    assert means(hass_repo, entries) == [15.0, 1.0]


async def test_daily_means_null_field_is_neutral_skipped(hass_repo):
    # A flaky daily entry with a null field must not error the sensor. The
    # entry collapses to a neutral mean equal to whichever field is present;
    # if both are null it is dropped so it cannot fabricate a degree-day.
    entries = ("[{'temperature': 20, 'templow': 10}, "
               "{'temperature': none, 'templow': none}]")
    assert means(hass_repo, entries) == [15.0]


async def test_daily_means_one_null_field_uses_present(hass_repo):
    # Only templow missing → fall back to the present field (temperature),
    # so the day still contributes its real, known temperature.
    entries = "[{'temperature': 22, 'templow': none}]"
    assert means(hass_repo, entries) == [22.0]


async def test_daily_means_absent_key_falls_back(hass_repo):
    # An entry missing the templow KEY entirely (not just null) must behave
    # like a null field — fall back to the present field — not raise.
    entries = "[{'temperature': 20, 'templow': 10}, {'temperature': 18}]"
    assert means(hass_repo, entries) == [15.0, 18.0]


async def test_daily_means_entry_missing_both_keys_dropped(hass_repo):
    # An entry with neither key is dropped, like the both-null case.
    entries = "[{'temperature': 20, 'templow': 10}, {}]"
    assert means(hass_repo, entries) == [15.0]


async def test_daily_means_composes_with_degree_hours(hass_repo):
    # The macro exists to feed the degree-hour macros. Consumers must
    # deserialize with | from_json so the result is a real list, not a
    # string iterated character-by-character. Two daily means of -3.0 at
    # balance 16 → hdh (16 - -3) * 2 = 38, cdh 0.
    src = (
        "{% from 'changeover.jinja' import daily_means, "
        "heating_degree_hours, cooling_degree_hours %}"
        "{% set entries = [{'temperature': 2.0, 'templow': -8.0}, "
        "{'temperature': 2.0, 'templow': -8.0}] %}"
        "{% set means = daily_means(entries) | from_json %}"
    )
    assert render(hass_repo, src + "{{ heating_degree_hours(means, 16) }}") == 38.0
    assert render(hass_repo, src + "{{ cooling_degree_hours(means, 16) }}") == 0.0
