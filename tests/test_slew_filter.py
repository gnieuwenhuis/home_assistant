"""Level 2 tests: the studio slew filter macro (pure function)."""
import json
from datetime import datetime, timedelta

from tests.util import render

IMPORTS = "{% from 'hvac.jinja' import slew_filter %}"

NOW = "2026-08-15T11:04:12+00:00"
REJECT, REENTER, MAX_HOLD = 1.0, 0.5, 20


def at(minutes):
    """The test clock, `minutes` past NOW, as an ISO string."""
    return (datetime.fromisoformat(NOW) + timedelta(minutes=minutes)).isoformat()


def filt(hass, raw, last_good, hold_since, pending="", now=NOW,
         raw_at=None, value_at="", pending_at=""):
    """Render the macro. `raw_at` defaults to a reading that just landed."""
    out = render(hass, IMPORTS + (
        "{{ slew_filter('%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s', %s, %s, %s) }}"
        % (raw, now if raw_at is None else raw_at, last_good, value_at,
           hold_since, pending, pending_at, now, REJECT, REENTER, MAX_HOLD)
    ))
    return json.loads(out) if isinstance(out, str) else out


async def test_a_lone_first_reading_is_not_a_seed(hass_repo):
    # Taken inside a plume it would latch the peak for the whole hold.
    got = filt(hass_repo, 19.4, "unknown", "", raw_at=at(-4))
    assert got["value"] is None
    assert got["pending"] == "19.4"
    assert got["pending_at"] == at(-4)


async def test_seeds_from_a_second_agreeing_reading(hass_repo):
    got = filt(hass_repo, 19.5, "unknown", "",
               pending=19.4, pending_at=at(-4), raw_at=NOW)
    assert got["value"] == "19.5"
    assert got["value_at"] == NOW
    assert got["pending"] == ""
    assert got["pending_at"] == ""


async def test_a_heartbeat_re_render_never_seeds(hass_repo):
    # The sensor's own /5 time_pattern re-renders the reading already held in
    # `pending`, which trivially agrees with itself. Counting renders instead of
    # source updates seeds a plume plateau on its second render.
    got = filt(hass_repo, 22.4, "unknown", "",
               pending=22.4, pending_at=at(-4), raw_at=at(-4), now=at(1))
    assert got["value"] is None
    assert got["pending"] == "22.4"
    assert got["pending_at"] == at(-4)


async def test_a_disagreeing_reading_replaces_the_seed_candidate(hass_repo):
    got = filt(hass_repo, 21.1, "unknown", "",
               pending=22.4, pending_at=at(-4), raw_at=NOW)
    assert got["value"] is None
    assert got["pending"] == "21.1"
    assert got["pending_at"] == NOW


async def test_seeding_rides_out_the_measured_plume(hass_repo):
    """The 05:05 dehumidifier run, replayed from a cold start.

    22.4 is the plume peak and the room is really 19.x. The source reports
    every ~4 minutes and the sensor's own /5 trigger re-renders in between with
    the reading unchanged, so the replay interleaves both.
    """
    # Columns: render at, raw, source last_changed. A row repeating the row
    # above's last_changed is a heartbeat; a row where the two agree is a
    # source update.
    replay = [
        (0.0, 22.4, 0.0),
        (4.2, 21.1, 4.2),
        (5.0, 21.1, 4.2),
        (10.0, 21.1, 4.2),
        (15.0, 21.1, 4.2),
        (20.0, 21.1, 4.2),
        (21.0, 19.1, 21.0),
        (25.0, 19.1, 21.0),
        (25.2, 19.0, 25.2),
    ]
    pending, pending_at, values = "", "", []
    for minutes, raw, changed in replay:
        got = filt(hass_repo, raw, "unknown", "", pending=pending,
                   pending_at=pending_at, raw_at=at(changed), now=at(minutes))
        pending, pending_at = got["pending"], got["pending_at"]
        values.append(got["value"])
    assert values == [None] * 8 + ["19.0"]


async def test_accepts_a_plausible_change(hass_repo):
    # Measured genuine slew in this room peaks near 0.7 C per reporting interval.
    got = filt(hass_repo, 19.6, 19.0, "", value_at=at(-4))
    assert got["value"] == "19.6"
    assert got["value_at"] == NOW
    assert got["hold_since"] == ""


async def test_rejects_the_exhaust_spike_and_starts_a_hold(hass_repo):
    # The measured 11:04 event: 19.4 accepted, then a 21.6 plume reading.
    got = filt(hass_repo, 21.6, 19.4, "", value_at=at(-4))
    assert got["value"] == "19.4"
    assert got["hold_since"] == NOW
    # The acceptance stamp rides along, so staleness measures from acceptance.
    assert got["value_at"] == at(-4)


async def test_rejects_the_decaying_tail_via_the_reenter_band(hass_repo):
    # 20.0 is 0.6 from the held 19.4 — inside the 1.0 reject band but outside
    # the 0.5 re-entry band, so a plain threshold would wrongly accept it.
    got = filt(hass_repo, 20.0, 19.4, "2026-08-15T10:52:00+00:00")
    assert got["value"] == "19.4"


async def test_reaccepts_once_the_reading_returns(hass_repo):
    got = filt(hass_repo, 19.5, 19.4, "2026-08-15T10:52:00+00:00")
    assert got["value"] == "19.5"
    assert got["value_at"] == NOW
    assert got["hold_since"] == ""


async def test_resyncs_after_the_max_hold(hass_repo):
    # A hold this long is a real shift, not a plume.
    got = filt(hass_repo, 22.0, 19.4, "2026-08-15T10:40:00+00:00")
    assert got["value"] == "22.0"
    assert got["value_at"] == NOW
    assert got["hold_since"] == ""


async def test_a_hold_keeps_its_start_time_until_the_cap(hass_repo):
    # Chained, because hold_since carrying forward is what makes max_hold a cap:
    # re-stamping it on every rejection makes a hold permanent.
    value, hold_since, value_at = 19.4, "", at(-4)
    for minutes, raw in [(0, 21.6), (5, 21.0), (10, 20.4)]:
        got = filt(hass_repo, raw, value, hold_since,
                   value_at=value_at, now=at(minutes))
        assert got["value"] == "19.4"
        assert got["hold_since"] == NOW
        assert got["value_at"] == at(-4)
        value, hold_since, value_at = (
            got["value"], got["hold_since"], got["value_at"]
        )
    got = filt(hass_repo, 20.2, value, hold_since, value_at=value_at, now=at(21))
    assert got["value"] == "20.2"
    assert got["value_at"] == at(21)
    assert got["hold_since"] == ""


async def test_a_stale_restored_value_falls_through_to_seeding(hass_repo):
    # HA restores this sensor's state and attributes, so a restart long enough
    # for the room to move restores a value that describes nothing.
    got = filt(hass_repo, 16.0, 21.0, "", value_at=at(-24))
    assert got["value"] is None
    assert got["pending"] == "16.0"


async def test_a_fresh_restored_value_still_filters(hass_repo):
    got = filt(hass_repo, 16.0, 21.0, "", value_at=at(-5))
    assert got["value"] == "21.0"
    assert got["hold_since"] == NOW


async def test_a_value_with_no_acceptance_stamp_is_not_stale(hass_repo):
    # An empty stamp is no evidence of age; only a timestamp past the cap is.
    got = filt(hass_repo, 16.0, 21.0, "", value_at="")
    assert got["value"] == "21.0"
    assert got["hold_since"] == NOW


async def test_the_stale_check_is_skipped_mid_hold(hass_repo):
    # Mid-hold the max_hold cap governs. Applying the stale check here would
    # make that cap dead code and drop the held value before it expires.
    got = filt(hass_repo, 21.6, 19.4, at(-5), value_at=at(-40))
    assert got["value"] == "19.4"
    assert got["hold_since"] == at(-5)
    assert got["value_at"] == at(-40)


async def test_holds_through_a_source_dropout(hass_repo):
    got = filt(hass_repo, "unavailable", 19.4, "", value_at=at(-4))
    assert got["value"] == "19.4"
    assert got["hold_since"] == NOW
    assert got["value_at"] == at(-4)


async def test_goes_unavailable_when_a_dropout_outlasts_the_hold(hass_repo):
    got = filt(hass_repo, "unavailable", 19.4, "2026-08-15T10:40:00+00:00")
    assert got["value"] is None


async def test_unavailable_with_no_history_is_unavailable(hass_repo):
    got = filt(hass_repo, "unavailable", "unknown", "")
    assert got["value"] is None
    assert got["pending"] == ""
    assert got["pending_at"] == ""
