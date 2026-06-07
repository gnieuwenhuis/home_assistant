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
