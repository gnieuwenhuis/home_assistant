"""configuration.yaml must stay loadable and structurally sound.

This is the only tracked file whose breakage prevents Home Assistant from
starting, and deploys restart HA. The HACS platforms (`climate_template`,
`neviweb130`, `cielo_home`) are not installed in CI, so they cannot be set up;
what can be checked is that the file parses, that everything it includes
exists, that the blocks which CAN be set up do set up, and that every Jinja
string in the blocks which cannot at least renders.
"""
from pathlib import Path

import pytest
import yaml as pyyaml
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import loader

from tests.conftest import REPO_ROOT

# The head_target macro in custom_templates/hvac.jinja clamps commanded
# setpoints to this floor. A bound below it can never be commanded, so demand
# in that direction would never clear.
HEAD_TARGET_CLAMP_FLOOR = 17


class ExampleSecrets(loader.Secrets):
    """Resolve !secret from secrets.yaml.example so CI needs no real secrets.

    Doubles as an assertion that the example file lists every key the config
    actually uses, which is the example file's entire purpose.
    """

    def __init__(self, config_dir: Path) -> None:
        super().__init__(config_dir)
        self._example = pyyaml.safe_load(
            (config_dir / "secrets.yaml.example").read_text()
        )

    def get(self, requester_path: str, secret: str) -> str:
        if secret not in self._example:
            raise AssertionError(
                f"configuration.yaml uses !secret {secret}, but "
                f"secrets.yaml.example does not list it. Add it there, and "
                f"add the real value to secrets.yaml on the HA host before "
                f"deploying."
            )
        return self._example[secret]


@pytest.fixture
def config():
    """configuration.yaml with !include and !secret resolved."""
    return loader.load_yaml_dict(
        REPO_ROOT / "configuration.yaml", ExampleSecrets(REPO_ROOT)
    )


def test_configuration_parses_and_includes_resolve(config):
    assert "automation" in config, "automations.yaml failed to include"
    assert len(config["automation"]) >= 1
    assert "homeassistant" in config
    assert config["homeassistant"]["packages"]["helpers"], (
        "helpers.yaml package include resolved empty"
    )


def test_included_files_exist():
    for name in ("automations.yaml", "scripts.yaml", "scenes.yaml",
                 "helpers.yaml"):
        assert (REPO_ROOT / name).exists(), f"{name} is included but missing"


async def test_template_block_sets_up(hass_repo, config):
    """The template: sensors schema-validate against a real HA.

    The entities they read do not exist here; templates resolve to unknown and
    setup still succeeds, so a failure here is a schema error.
    """
    assert await async_setup_component(
        hass_repo, "template", {"template": config["template"]}
    ), "the template: block failed to set up"


async def test_climate_templates_render(hass_repo, config):
    """Every *_template string in the climate: block is valid Jinja.

    climate_template is a HACS integration and cannot be set up in CI, but its
    templates are ordinary strings — a syntax error here is a runtime failure
    that this catches statically. Only top-level *_template keys are rendered;
    the set_temperature / set_hvac_mode action blocks reference runtime
    variables that do not exist outside a service call.
    """
    rendered = 0
    for entry in config["climate"]:
        for key, value in entry.items():
            if key.endswith("_template"):
                Template(value, hass_repo).async_render(parse_result=False)
                rendered += 1
    assert rendered >= 10, (
        f"expected at least 10 climate templates across both rooms, "
        f"rendered {rendered}"
    )


def test_climate_min_temp_matches_head_target_clamp(config):
    """A cool_bound below the clamp floor could never be commanded.

    head_target clamps to [17, 30]; if a thermostat tile let the user dial a
    bound under that floor, cooling demand would never clear.
    """
    for entry in config["climate"]:
        assert entry["min_temp"] == HEAD_TARGET_CLAMP_FLOOR, (
            f"{entry['name']} min_temp is {entry['min_temp']} but "
            f"head_target clamps to {HEAD_TARGET_CLAMP_FLOOR}"
        )


def test_climate_entries_have_required_keys(config):
    required = {
        "platform", "name", "unique_id", "modes", "min_temp", "max_temp",
        "current_temperature_template", "target_temperature_low_template",
        "target_temperature_high_template", "hvac_mode_template",
        "hvac_action_template", "set_temperature", "set_hvac_mode",
    }
    for entry in config["climate"]:
        missing = required - set(entry)
        assert not missing, f"{entry.get('name')} is missing {sorted(missing)}"


def test_neviweb130_block_has_required_keys(config):
    required = {"username", "password", "network", "scan_interval",
                "homekit_mode", "stat_interval", "notify"}
    missing = required - set(config["neviweb130"])
    assert not missing, f"neviweb130: is missing {sorted(missing)}"
