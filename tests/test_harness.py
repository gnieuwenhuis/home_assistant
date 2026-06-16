"""Sanity: the harness renders templates and loads repo custom_templates."""
from tests.util import render


async def test_template_engine_renders(hass_repo):
    assert render(hass_repo, "{{ 1 + 1 }}") == 2


async def test_repo_custom_templates_importable(hass_repo):
    out = render(hass_repo, "{% from 'hvac.jinja' import room_demand %}ok")
    assert out == "ok"


async def test_helpers_yaml_loads(hass_helpers):
    assert hass_helpers.states.get("input_select.heat_pump_mode") is not None
    assert hass_helpers.states.get("timer.humidity_cooldown") is not None
