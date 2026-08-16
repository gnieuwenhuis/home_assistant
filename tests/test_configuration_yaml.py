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
from homeassistant.core_config import CORE_CONFIG_SCHEMA
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import loader

from tests.conftest import REPO_ROOT

# The head_target macro in custom_templates/hvac.jinja clamps commanded
# setpoints to this floor. A bound below it can never be commanded, so demand
# in that direction would never clear.
HEAD_TARGET_CLAMP_FLOOR = 17

# One climate_template thermostat tile per room. Asserted before each loop over
# climate:, so a block that lost its entries fails instead of passing vacuously.
THERMOSTAT_TILES = 2

# Home Assistant derives a `sum` statistic only for these two state classes.
# `measurement` yields a mean instead, which the energy dashboard cannot consume.
SUM_STATE_CLASSES = {"total", "total_increasing"}


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


def test_core_config_block_validates(config):
    """The homeassistant: block is the one whose breakage costs everything.

    An invalid core config puts HA into recovery mode, where no automations
    load at all — the coordinator included.
    """
    CORE_CONFIG_SCHEMA(config["homeassistant"])


def test_included_files_exist():
    for name in ("automations.yaml", "scripts.yaml", "scenes.yaml",
                 "helpers.yaml"):
        assert (REPO_ROOT / name).exists(), f"{name} is included but missing"


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_template_entities_are_created(hass_repo, config):
    """Every sensor declared in the template: block exists after setup.

    The studio control sensor's 5-minute time_pattern trigger leaves a timer
    scheduled past the end of the test, and the template integration exposes no
    service that detaches a trigger block's listeners, so the lingering-timer
    check is parametrized off here (it cancels the handle either way).

    `async_setup_component` returns True even when the block is rejected: HA
    logs `Invalid config for 'template'`, drops the whole block, and reports
    success. Counting entities is what makes a schema error visible. The
    entities the sensors read do not exist here, so their states are unknown —
    existence is the assertion, not value.

    A dropped block creates zero sensors, which costs
    `sensor.<room>_baseboard_current_temperature`; hvac_coordinator guards on
    both and short-circuits every run without them.
    """
    await async_setup_component(
        hass_repo, "template", {"template": config["template"]}
    )
    await hass_repo.async_block_till_done()
    expected = sum(len(b["sensor"]) for b in config["template"] if "sensor" in b)
    created = hass_repo.states.async_entity_ids("sensor")
    assert len(created) == expected, (expected, sorted(created))


def test_energy_sensors_produce_sum_statistics(config):
    """Every energy sensor records a sum rather than a mean.

    An energy sensor left at `state_class: measurement` still shows a plausible
    value on a card, so nothing looks wrong until the energy dashboard reports
    that source contributing zero. The live symptom is `has_sum: false` from
    `recorder/list_statistic_ids`, which is the only place it surfaces.
    """
    energy = [
        sensor
        for block in config["template"] if "sensor" in block
        for sensor in block["sensor"]
        if sensor.get("device_class") == "energy"
    ]
    assert energy, "no energy template sensors found in configuration.yaml"
    wrong = {
        sensor["name"]: sensor.get("state_class")
        for sensor in energy
        if sensor.get("state_class") not in SUM_STATE_CLASSES
    }
    assert not wrong, (
        f"energy sensors recording a mean instead of a sum: {wrong}. The energy "
        f"dashboard consumes sums, so these contribute nothing to it."
    )


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
    assert len(config["climate"]) == THERMOSTAT_TILES
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
    assert len(config["climate"]) == THERMOSTAT_TILES
    for entry in config["climate"]:
        missing = required - set(entry)
        assert not missing, f"{entry.get('name')} is missing {sorted(missing)}"


def test_neviweb130_block_has_required_keys(config):
    required = {"username", "password", "network", "scan_interval",
                "homekit_mode", "stat_interval", "notify"}
    missing = required - set(config["neviweb130"])
    assert not missing, f"neviweb130: is missing {sorted(missing)}"
