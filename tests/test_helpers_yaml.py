"""helpers.yaml mirror: changeover additions."""


async def test_heat_pump_mode_has_off_option(hass_helpers):
    state = hass_helpers.states.get("input_select.heat_pump_mode")
    assert state.attributes["options"] == ["heating", "cooling", "off"]


async def test_changeover_tunables_exist(hass_helpers):
    bp = hass_helpers.states.get("input_number.changeover_balance_point")
    assert bp is not None
    assert bp.attributes["min"] == 10
    assert bp.attributes["max"] == 22
    db = hass_helpers.states.get("input_number.changeover_deadband")
    assert db is not None
    assert db.attributes["max"] == 200


async def test_changeover_hold_timer_exists(hass_helpers):
    assert hass_helpers.states.get("timer.changeover_hold") is not None


async def test_changeover_daily_deadband_exists(hass_helpers):
    db = hass_helpers.states.get("input_number.changeover_daily_deadband")
    assert db is not None
    assert db.attributes["max"] == 10
    assert db.attributes["unit_of_measurement"] == "°C·day"


async def test_hvac_enable_exists(hass_helpers):
    assert hass_helpers.states.get("input_boolean.hvac_enable") is not None


async def test_room_bounds_exist(hass_helpers):
    for ent in (
        "input_number.office_heat_bound", "input_number.office_cool_bound",
        "input_number.studio_heat_bound", "input_number.studio_cool_bound",
    ):
        s = hass_helpers.states.get(ent)
        assert s is not None, ent
        assert s.attributes["min"] == 15
        assert s.attributes["max"] == 30


async def test_differentials_exist(hass_helpers):
    assert hass_helpers.states.get("input_number.office_temp_differential") is not None
    assert hass_helpers.states.get("input_number.studio_temp_differential") is not None


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
