"""Fixtures: a hass wired to this repo's custom_templates and helpers.yaml."""
from pathlib import Path

import pytest
import yaml
from homeassistant.helpers import template as template_helper
from homeassistant.setup import async_setup_component

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
async def hass_repo(hass):
    """hass with this repo as config dir so {% from 'x.jinja' %} imports work."""
    hass.config.config_dir = str(REPO_ROOT)
    await template_helper.async_load_custom_templates(hass)
    return hass


@pytest.fixture
async def hass_helpers(hass_repo):
    """hass_repo plus every helper from helpers.yaml (validates the mirror)."""
    data = yaml.safe_load((REPO_ROOT / "helpers.yaml").read_text())
    for domain in ("input_number", "input_boolean", "input_select", "timer"):
        assert await async_setup_component(
            hass_repo, domain, {domain: data[domain]}
        ), f"helpers.yaml {domain}: block failed to set up"
    return hass_repo
