"""helpers.yaml mirror: ecobee-model helper set."""


async def test_hvac_enable_exists(hass_helpers):
    assert hass_helpers.states.get("input_boolean.hvac_enable") is not None


async def test_room_bounds_exist(hass_helpers):
    for ent in (
        "input_number.office_heat_bound", "input_number.office_cool_bound",
        "input_number.studio_heat_bound", "input_number.studio_cool_bound",
    ):
        s = hass_helpers.states.get(ent)
        assert s is not None, ent
        assert s.attributes["min"] == 17
        assert s.attributes["max"] == 30


async def test_differentials_exist(hass_helpers):
    assert hass_helpers.states.get("input_number.office_temp_differential") is not None
    assert hass_helpers.states.get("input_number.studio_temp_differential") is not None


async def test_unwritten_helpers_have_initial(hass_helpers):
    # Nothing writes these at runtime, so `initial:` is the only thing standing
    # between a rebuild-from-repo and every one of them landing at `min`.
    for ent, initial in (
        ("input_number.office_temp_differential", 1.0),
        ("input_number.studio_temp_differential", 0.5),
        ("input_number.humidity_set_point", 42),
        ("input_number.humidity_tolerance", 1.5),
    ):
        s = hass_helpers.states.get(ent)
        assert s is not None, ent
        assert float(s.state) == initial, ent


async def test_system_hvac_mode_options(hass_helpers):
    s = hass_helpers.states.get("input_select.system_hvac_mode")
    assert s.attributes["options"] == ["idle", "heat", "cool", "off"]


async def test_new_timers_exist(hass_helpers):
    for ent in (
        "timer.mode_min_dwell",
        "timer.office_head_lockout",
        "timer.studio_head_lockout",
    ):
        assert hass_helpers.states.get(ent) is not None


async def test_obsolete_helpers_removed(hass_helpers):
    for ent in (
        "input_number.office_preferred_temperature",
        "input_number.studio_preferred_temperature",
        "input_number.office_temp_range",
        "input_number.studio_temp_range",
        "input_number.changeover_balance_point",
        "input_number.changeover_deadband",
        "input_number.changeover_daily_deadband",
        "input_select.heat_pump_mode",
        "timer.changeover_hold",
    ):
        assert hass_helpers.states.get(ent) is None, ent


async def test_eva_lamp_auto_off_timer(hass_helpers):
    s = hass_helpers.states.get("timer.eva_lamp_auto_off")
    assert s is not None
    assert s.attributes["duration"] == "0:30:00"
    assert s.attributes["restore"] is True
