# Changeover Advisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the suggest-and-confirm heat-pump changeover advisor from `docs/superpowers/specs/2026-06-07-changeover-advisor-design.md`: forecast degree-hours nominate heating/cooling/off, duty-cycle-backed indoor evidence confirms, an actionable notification asks the human, a single hold timer prevents nagging.

**Architecture:** Pure decision macros in `custom_templates/changeover.jinja` (unit-tested), wired into a trigger-based template sensor (`sensor.changeover_balance`) in `configuration.yaml` and three automations in `automations.yaml`. New pytest harness (`pytest-homeassistant-custom-component`) tests macros (Level 2) and the real YAML wiring (Level 3).

**Tech Stack:** Home Assistant YAML + Jinja2, pytest, pytest-homeassistant-custom-component.

**Repo facts the executor needs:**
- This repo IS the HA config dir mirror. `custom_templates/` already holds `setpoint.jinja` (the pattern to follow).
- Automations use modern syntax (`triggers:` / `actions:` / `- trigger:` / `- action:`).
- `helpers.yaml` mirrors UI-defined helpers and is NOT yet included from `configuration.yaml` — additions there are mirrors; live HA needs the same helpers created in the UI (Task 8).
- `history_stats` ratio sensors report **percent (0–100)**; the macro `duty_floor` default is `2` (= 2 %).
- Commit message style: plain imperative, no `feat:` prefixes (match `git log`).
- The EC weather entity is assumed to be `weather.lethbridge` — verified against the live instance in Task 8; tests bake the same name.

---

### Task 1: Test harness bootstrap

**Files:**
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/util.py`
- Create: `tests/conftest.py`
- Create: `tests/test_harness.py`
- Modify: `.gitignore` (append)

- [ ] **Step 1: Determine the live HA version for pinning**

Ask the user for the live HA version (HA UI: Settings → System → About; or `cat .HA_VERSION` on the host — it is not in this repo). Then pin `pytest-homeassistant-custom-component` to the matching release from the version table at https://github.com/MatthewFlamm/pytest-homeassistant-custom-component. If the user can't check right now, leave it unpinned (latest) and add a `# TODO(pin)` comment is NOT acceptable — instead record the chosen version with a comment saying which HA version it maps to.

- [ ] **Step 2: Create `requirements-dev.txt`**

```text
# Test harness for template macros and automation wiring.
#
# Keep pytest-homeassistant-custom-component pinned to the release matching
# the live HA version (Settings → System → About on the HA instance, or
# .HA_VERSION on the host — not tracked in this repo). Version table:
#   https://github.com/MatthewFlamm/pytest-homeassistant-custom-component
pytest-homeassistant-custom-component
pyyaml
```

(Replace the bare package name with `pytest-homeassistant-custom-component==<version from Step 1>`.)

- [ ] **Step 3: Create `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 4: Append to `.gitignore`**

```text

# Python test harness
.venv/
__pycache__/
.pytest_cache/
```

- [ ] **Step 5: Create `tests/__init__.py`** (empty file)

- [ ] **Step 6: Create `tests/util.py`**

```python
"""Shared helpers for rendering templates in tests."""
from homeassistant.helpers.template import Template


def render(hass, source):
    """Render template source against the test hass; returns native types."""
    return Template(source, hass).async_render()


def jlist(values):
    """Format a Python list of numbers as a Jinja list literal."""
    return "[" + ", ".join(str(v) for v in values) + "]"
```

- [ ] **Step 7: Create `tests/conftest.py`**

```python
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
```

- [ ] **Step 8: Create `tests/test_harness.py`**

```python
"""Sanity: the harness renders templates and loads repo custom_templates."""
from tests.util import render


async def test_template_engine_renders(hass_repo):
    assert render(hass_repo, "{{ 1 + 1 }}") == 2


async def test_repo_custom_templates_importable(hass_repo):
    out = render(hass_repo, "{% from 'setpoint.jinja' import heat_pump_setpoint %}ok")
    assert out == "ok"


async def test_helpers_yaml_loads(hass_helpers):
    assert hass_helpers.states.get("input_select.heat_pump_mode") is not None
    assert hass_helpers.states.get("timer.humidity_cooldown") is not None
```

- [ ] **Step 9: Create the venv, install, run**

Run: `python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`
Then: `.venv/bin/pytest -v`
Expected: 3 PASSED. If `async_load_custom_templates` raises AttributeError (very old HA pin), the pinned version is wrong for this plan — stop and re-check Step 1 rather than working around it.

- [ ] **Step 10: Commit**

```bash
git add requirements-dev.txt pytest.ini .gitignore tests/
git commit -m "Add pytest harness for HA config (pytest-homeassistant-custom-component)"
```

---

### Task 2: Degree-hour and candidate macros (TDD)

**Files:**
- Create: `custom_templates/changeover.jinja`
- Create: `tests/test_changeover_macros.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_changeover_macros.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_changeover_macros.py -v`
Expected: all FAIL with `TemplateNotFound: changeover.jinja` (or import error).

- [ ] **Step 3: Create `custom_templates/changeover.jinja` (degree-hour + candidate macros only)**

```jinja
{# Changeover advisor decision macros.

   Pure functions — every input is an argument, no states() lookups — so they
   are unit-testable (tests/test_changeover_macros.py) and shared by the
   changeover balance sensor (configuration.yaml) and the advisor automation
   (automations.yaml). Design: docs/superpowers/specs/
   2026-06-07-changeover-advisor-design.md

   Degree-hours follow the standard seasonal-changeover convention: each
   forecast hour contributes max(0, distance past the balance point) in the
   heating or cooling direction. A mixed day (cold morning, hot afternoon)
   contributes to BOTH, which is why this beats threshold-on-mean methods. #}

{% macro heating_degree_hours(temps, balance) -%}
  {%- set ns = namespace(total=0.0) -%}
  {%- for t in temps -%}
    {%- set ns.total = ns.total + [(balance | float) - (t | float), 0] | max -%}
  {%- endfor -%}
  {{ ns.total | round(1) }}
{%- endmacro %}

{% macro cooling_degree_hours(temps, balance) -%}
  {%- set ns = namespace(total=0.0) -%}
  {%- for t in temps -%}
    {%- set ns.total = ns.total + [(t | float) - (balance | float), 0] | max -%}
  {%- endfor -%}
  {{ ns.total | round(1) }}
{%- endmacro %}

{# Candidate regime from the degree-hour balance. The ±deadband dead zone is
   the flap-killer: inside it the answer is 'off' (open windows). The outdoor
   gates fall out of the math — a cold forecast cannot nominate cooling. #}
{% macro candidate_mode(cdh, hdh, deadband) -%}
  {%- set balance = (cdh | float) - (hdh | float) -%}
  {%- if balance > (deadband | float) -%}
    cooling
  {%- elif balance < -(deadband | float) -%}
    heating
  {%- else -%}
    off
  {%- endif -%}
{%- endmacro %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_changeover_macros.py -v`
Expected: 8 PASSED.

- [ ] **Step 5: Commit**

```bash
git add custom_templates/changeover.jinja tests/test_changeover_macros.py
git commit -m "Add changeover degree-hour and candidate-mode macros"
```

---

### Task 3: Confirmation macro with duty-cycle alibi (TDD)

**Files:**
- Modify: `custom_templates/changeover.jinja` (append)
- Modify: `tests/test_changeover_macros.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_changeover_macros.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_changeover_macros.py -v`
Expected: the 8 new tests FAIL (`no name 'confirmation'`); the earlier 8 still PASS.

- [ ] **Step 3: Append the confirmation macro to `custom_templates/changeover.jinja`**

```jinja

{# Demand-based confirmation with a duty-cycle alibi: a room's smoothed
   temperature only counts as evidence when its heat pump has been idle
   (duty below duty_floor, in PERCENT — duties come from history_stats ratio
   sensors, 0–100). Otherwise the pump itself may be the cause — the office
   head especially, being oversized for its small room, overshoots hard.
   Unparseable duty defaults to 100 (busy) so missing data fails safe. #}
{% macro confirmation(candidate, office_mean, studio_mean, office_duty, studio_duty,
                      office_preferred, office_swing, studio_preferred, studio_swing,
                      duty_floor=2) -%}
  {%- set office_idle = (office_duty | float(100)) < (duty_floor | float) -%}
  {%- set studio_idle = (studio_duty | float(100)) < (duty_floor | float) -%}
  {%- set office_high = (office_mean | float) > (office_preferred | float) + (office_swing | float) -%}
  {%- set office_low  = (office_mean | float) < (office_preferred | float) - (office_swing | float) -%}
  {%- set studio_high = (studio_mean | float) > (studio_preferred | float) + (studio_swing | float) -%}
  {%- set studio_low  = (studio_mean | float) < (studio_preferred | float) - (studio_swing | float) -%}
  {%- if candidate == 'cooling' -%}
    {{ (office_idle and office_high) or (studio_idle and studio_high) }}
  {%- elif candidate == 'heating' -%}
    {{ (office_idle and office_low) or (studio_idle and studio_low) }}
  {%- elif candidate == 'off' -%}
    {{ office_idle and studio_idle }}
  {%- else -%}
    False
  {%- endif -%}
{%- endmacro %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_changeover_macros.py -v`
Expected: 16 PASSED.

- [ ] **Step 5: Commit**

```bash
git add custom_templates/changeover.jinja tests/test_changeover_macros.py
git commit -m "Add changeover confirmation macro with duty-cycle alibi"
```

---

### Task 4: Helpers mirror — off mode, tunables, hold timer (TDD)

**Files:**
- Modify: `helpers.yaml`
- Create: `tests/test_helpers_yaml.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_helpers_yaml.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_helpers_yaml.py -v`
Expected: 3 FAIL (missing option / None entities).

- [ ] **Step 3: Edit `helpers.yaml`**

3a. In the `input_select:` block, add the quoted `off` option (unquoted `off` is YAML `False`):

```yaml
input_select:
  heat_pump_mode:
    name: Heat Pump Mode
    icon: mdi:heat-pump
    options:
      - heating
      - cooling
      - "off"
```

3b. Append to the `input_number:` block (after `humidity_tolerance`):

```yaml
  # Changeover advisor tunables (no `initial:` — values restore across
  # restarts; defaults 16 °C / 24 °C·h are set when created in the UI).
  changeover_balance_point:
    name: Changeover Balance Point
    min: 10
    max: 22
    step: 0.5
    mode: box
    unit_of_measurement: "°C"
    icon: mdi:swap-vertical-circle-outline

  changeover_deadband:
    name: Changeover Deadband
    min: 0
    max: 200
    step: 1
    mode: box
    unit_of_measurement: "°C·h"
    icon: mdi:arrow-expand-vertical
```

3c. Append to the `timer:` block:

```yaml
  # Changeover advisor hold: started 12 h on every suggestion (nag floor),
  # 24 h on every mode change (min time-in-mode). restore: true so an HA
  # restart cannot erase a hold and re-open the nag window.
  changeover_hold:
    name: Changeover Hold
    restore: true
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_helpers_yaml.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add helpers.yaml tests/test_helpers_yaml.py
git commit -m "Add changeover helpers (off mode, tunables, hold timer)"
```

---

### Task 5: Sensors in configuration.yaml — balance, duties, means (TDD on the balance sensor)

**Files:**
- Modify: `configuration.yaml`
- Create: `tests/test_changeover_balance_sensor.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_changeover_balance_sensor.py`:

```python
"""Level 3 test: sensor.changeover_balance wired from the real configuration.yaml."""
from datetime import timedelta

import pytest
import yaml
import homeassistant.util.dt as dt_util
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from tests.conftest import REPO_ROOT


class _StubTagLoader(yaml.SafeLoader):
    """Parse configuration.yaml while ignoring HA-specific tags."""


for _tag in ("!secret", "!include", "!include_dir_merge_named",
             "!include_dir_list", "!include_dir_named", "!env_var"):
    _StubTagLoader.add_constructor(_tag, lambda loader, node: None)


@pytest.fixture
async def balance(hass_helpers):
    hass = hass_helpers
    config = yaml.load((REPO_ROOT / "configuration.yaml").read_text(), _StubTagLoader)
    mode = {"fail": False, "temps": [-10.0] * 48}

    async def fake_forecast(call):
        if mode["fail"]:
            raise HomeAssistantError("EC unreachable")
        return {
            "weather.lethbridge": {
                "forecast": [{"temperature": t} for t in mode["temps"]]
            }
        }

    hass.services.async_register(
        "weather", "get_forecasts", fake_forecast,
        supports_response=SupportsResponse.ONLY,
    )
    await hass.services.async_call(
        "input_number", "set_value",
        {"entity_id": "input_number.changeover_balance_point", "value": 16},
        blocking=True,
    )
    assert await async_setup_component(hass, "template", {"template": config["template"]})
    await hass.async_block_till_done()
    return hass, mode


async def fire_hourly(hass):
    target = (dt_util.utcnow() + timedelta(hours=1)).replace(
        minute=0, second=0, microsecond=0
    )
    async_fire_time_changed(hass, target)
    await hass.async_block_till_done()


async def test_balance_from_cold_forecast(balance):
    hass, _ = balance
    await fire_hourly(hass)
    state = hass.states.get("sensor.changeover_balance")
    assert state is not None
    assert float(state.state) == -1248.0          # CDH 0 − HDH 26x48
    assert state.attributes["hdh"] == 1248.0
    assert state.attributes["cdh"] == 0.0
    assert state.attributes["forecast_hours"] == 48


async def test_long_forecast_clipped_to_48h(balance):
    hass, mode = balance
    mode["temps"] = [-10.0] * 72
    await fire_hourly(hass)
    assert hass.states.get("sensor.changeover_balance").attributes["forecast_hours"] == 48


async def test_balance_unavailable_when_forecast_fails(balance):
    hass, mode = balance
    mode["fail"] = True
    await fire_hourly(hass)
    assert hass.states.get("sensor.changeover_balance").state == "unavailable"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_changeover_balance_sensor.py -v`
Expected: FAIL — `sensor.changeover_balance` is None (block not in configuration.yaml yet).

- [ ] **Step 3: Append the balance sensor to the `template:` list in `configuration.yaml`**

Append as a new list item after the existing `- sensor:` item (i.e., after the
`Humidity Low Threshold` sensor, currently the end of the `template:` block),
at the same `  - ` indent level:

```yaml
  # Changeover advisor: degree-hour balance over the next 48 h of EC hourly
  # forecast. Refreshes hourly and on HA start; goes unavailable when the
  # forecast call fails (continue_on_error leaves changeover_forecast
  # undefined → availability false), which short-circuits the advisor.
  # Design: docs/superpowers/specs/2026-06-07-changeover-advisor-design.md
  - triggers:
      - trigger: time_pattern
        minutes: "0"
      - trigger: homeassistant
        event: start
    actions:
      - action: weather.get_forecasts
        data:
          type: hourly
        target:
          entity_id: weather.lethbridge
        response_variable: changeover_forecast
        continue_on_error: true
    sensor:
      - name: "Changeover Balance"
        unique_id: sensor.changeover_balance
        unit_of_measurement: "°C·h"
        state_class: measurement
        availability: >-
          {{ changeover_forecast is defined
             and (changeover_forecast['weather.lethbridge']['forecast'] | count) > 0 }}
        state: >-
          {% from 'changeover.jinja' import heating_degree_hours, cooling_degree_hours %}
          {% set temps = changeover_forecast['weather.lethbridge']['forecast'][:48]
                         | map(attribute='temperature') | list %}
          {% set bp = states('input_number.changeover_balance_point') | float(16) %}
          {{ (cooling_degree_hours(temps, bp) | float)
             - (heating_degree_hours(temps, bp) | float) }}
        attributes:
          cdh: >-
            {% from 'changeover.jinja' import cooling_degree_hours %}
            {% set temps = changeover_forecast['weather.lethbridge']['forecast'][:48]
                           | map(attribute='temperature') | list %}
            {{ cooling_degree_hours(temps,
                 states('input_number.changeover_balance_point') | float(16)) | float }}
          hdh: >-
            {% from 'changeover.jinja' import heating_degree_hours %}
            {% set temps = changeover_forecast['weather.lethbridge']['forecast'][:48]
                           | map(attribute='temperature') | list %}
            {{ heating_degree_hours(temps,
                 states('input_number.changeover_balance_point') | float(16)) | float }}
          forecast_hours: >-
            {{ changeover_forecast['weather.lethbridge']['forecast'][:48] | count }}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_changeover_balance_sensor.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Add the duty and smoothed-mean platform sensors**

Append a new top-level `sensor:` key at the end of `configuration.yaml` (after the `notify:` block). These aren't covered by unit tests — `history_stats` needs the recorder — and are validated in the shadow phase (Task 8):

```yaml
# Changeover advisor evidence sensors. Duty cycles are the load witness
# (history_stats ratio, PERCENT 0-100); the smoothed means ride out sensor
# noise and head overshoot — the office gets the longer window because its
# oversized head overshoots harder.
sensor:
  - platform: statistics
    name: "Office Temperature 2h Mean"
    unique_id: office_temperature_2h_mean
    entity_id: sensor.office_baseboard_current_temperature
    state_characteristic: mean
    sampling_size: 500
    max_age:
      hours: 2
  - platform: statistics
    name: "Studio Temperature 1h Mean"
    unique_id: studio_temperature_1h_mean
    entity_id: sensor.studio_baseboard_current_temperature
    state_characteristic: mean
    sampling_size: 500
    max_age:
      hours: 1
  - platform: history_stats
    name: "Office Heat Pump Duty 24h"
    unique_id: office_heat_pump_duty_24h
    entity_id: switch.office_power
    state: "on"
    type: ratio
    end: "{{ now() }}"
    duration:
      hours: 24
  - platform: history_stats
    name: "Studio Heat Pump Duty 24h"
    unique_id: studio_heat_pump_duty_24h
    entity_id: switch.studio_power
    state: "on"
    type: ratio
    end: "{{ now() }}"
    duration:
      hours: 24
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: all PASSED (the new `sensor:` key must not break the config parse in the balance test's stub loader).

- [ ] **Step 7: Commit**

```bash
git add configuration.yaml tests/test_changeover_balance_sensor.py
git commit -m "Add changeover balance, duty-cycle, and smoothed-mean sensors"
```

---

### Task 6: Advisor automations (TDD, Level 3 against the real automations.yaml)

**Files:**
- Modify: `automations.yaml` (append a new banner section at end of file)
- Create: `tests/test_advisor_automations.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_advisor_automations.py`:

```python
"""Level 3 tests: changeover advisor automations loaded from automations.yaml."""
import pytest
import yaml
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

from tests.conftest import REPO_ROOT

ADVISOR_IDS = {
    "heat_pump_mode_advisor",
    "heat_pump_mode_advisor_response",
    "heat_pump_mode_changed",
}
BALANCE_ATTRS = {"cdh": 50.0, "hdh": 6.0, "forecast_hours": 48}


@pytest.fixture
async def advisor(hass_helpers):
    hass = hass_helpers
    autos = yaml.safe_load((REPO_ROOT / "automations.yaml").read_text())
    chosen = [a for a in autos if a.get("id") in ADVISOR_IDS]
    assert len(chosen) == 3, "changeover automations missing from automations.yaml"
    assert await async_setup_component(hass, "automation", {"automation": chosen})
    notify_calls = async_mock_service(hass, "notify", "mobile_app_pixel_8")
    switch_calls = async_mock_service(hass, "switch", "turn_off")
    return hass, notify_calls, switch_calls


async def arrange(hass, *, mode="heating", balance_state="44",
                  office_mean="22.0", studio_mean="25.5",
                  office_duty="0.0", studio_duty="0.0"):
    """Default scene: cooling candidate confirmed by an idle, hot studio."""
    for ent, val in [
        ("input_number.office_preferred_temperature", 21),
        ("input_number.studio_preferred_temperature", 21),
        ("input_number.office_temp_range", 2),
        ("input_number.studio_temp_range", 2),
        ("input_number.changeover_balance_point", 16),
        ("input_number.changeover_deadband", 24),
    ]:
        await hass.services.async_call(
            "input_number", "set_value",
            {"entity_id": ent, "value": val}, blocking=True,
        )
    await hass.services.async_call(
        "input_select", "select_option",
        {"entity_id": "input_select.heat_pump_mode", "option": mode}, blocking=True,
    )
    hass.states.async_set("sensor.changeover_balance", balance_state, BALANCE_ATTRS)
    hass.states.async_set("sensor.office_temperature_2h_mean", office_mean)
    hass.states.async_set("sensor.studio_temperature_1h_mean", studio_mean)
    hass.states.async_set("sensor.office_heat_pump_duty_24h", office_duty)
    hass.states.async_set("sensor.studio_heat_pump_duty_24h", studio_duty)
    await hass.async_block_till_done()
    # Selecting a mode starts the 24 h hold via heat_pump_mode_changed
    # (itself a behavior under test) — clear it so each test controls the hold.
    await hass.services.async_call(
        "timer", "cancel", {"entity_id": "timer.changeover_hold"}, blocking=True,
    )
    await hass.async_block_till_done()


async def run_advisor(hass):
    await hass.services.async_call(
        "automation", "trigger",
        {"entity_id": "automation.heat_pump_mode_advisor", "skip_condition": False},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_advisor_suggests_cooling(advisor):
    hass, notify_calls, _ = advisor
    await arrange(hass)
    await run_advisor(hass)
    assert len(notify_calls) == 1
    payload = notify_calls[0].data
    assert "cooling" in payload["message"]
    assert payload["data"]["actions"][0]["action"] == "CHANGEOVER_ACCEPT_cooling"
    hold = hass.states.get("timer.changeover_hold")
    assert hold.state == "active"
    assert hold.attributes["duration"] == "12:00:00"


async def test_no_suggestion_when_candidate_matches_mode(advisor):
    hass, notify_calls, _ = advisor
    await arrange(hass, mode="cooling")
    await run_advisor(hass)
    assert notify_calls == []


async def test_no_suggestion_during_hold(advisor):
    hass, notify_calls, _ = advisor
    await arrange(hass)
    await hass.services.async_call(
        "timer", "start",
        {"entity_id": "timer.changeover_hold", "duration": "01:00:00"},
        blocking=True,
    )
    await run_advisor(hass)
    assert notify_calls == []


async def test_duty_alibi_blocks_suggestion(advisor):
    hass, notify_calls, _ = advisor
    # Studio hot but busy (its own pump may have caused it); office in band.
    await arrange(hass, studio_duty="15.0")
    await run_advisor(hass)
    assert notify_calls == []


async def test_backup_heat_blocks_suggestion(advisor):
    hass, notify_calls, _ = advisor
    await arrange(hass)
    await hass.services.async_call(
        "input_boolean", "turn_on",
        {"entity_id": "input_boolean.backup_heat"}, blocking=True,
    )
    await run_advisor(hass)
    assert notify_calls == []


async def test_unavailable_balance_blocks_suggestion(advisor):
    hass, notify_calls, _ = advisor
    await arrange(hass)
    hass.states.async_set("sensor.changeover_balance", "unavailable", BALANCE_ATTRS)
    await run_advisor(hass)
    assert notify_calls == []


async def test_accept_sets_mode_and_24h_hold(advisor):
    hass, _, _ = advisor
    await arrange(hass)
    hass.bus.async_fire(
        "mobile_app_notification_action", {"action": "CHANGEOVER_ACCEPT_cooling"}
    )
    await hass.async_block_till_done()
    assert hass.states.get("input_select.heat_pump_mode").state == "cooling"
    hold = hass.states.get("timer.changeover_hold")
    assert hold.state == "active"
    assert hold.attributes["duration"] == "24:00:00"


async def test_entering_off_powers_down_only_running_heads(advisor):
    hass, _, switch_calls = advisor
    await arrange(hass, mode="cooling")
    hass.states.async_set("switch.office_power", "on")
    hass.states.async_set("switch.studio_power", "off")
    await hass.services.async_call(
        "input_select", "select_option",
        {"entity_id": "input_select.heat_pump_mode", "option": "off"}, blocking=True,
    )
    await hass.async_block_till_done()
    assert len(switch_calls) == 1
    ent = switch_calls[0].data["entity_id"]
    assert ent in ("switch.office_power", ["switch.office_power"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_advisor_automations.py -v`
Expected: all FAIL at the fixture assertion `changeover automations missing`.

- [ ] **Step 3: Append the changeover advisor section to `automations.yaml`**

Append at end of file (after the Humidity section), keeping the repo's banner style:

```yaml

# ---------------------------------------------------------------------------
# Changeover advisor
#
# Suggest-and-confirm seasonal changeover — see docs/superpowers/specs/
# 2026-06-07-changeover-advisor-design.md. sensor.changeover_balance
# (configuration.yaml) nominates heating / cooling / off from 48 h of EC
# hourly forecast degree-hours; the advisor only notifies when a room whose
# heat pump has been idle (duty-cycle alibi) confirms the demand, no hold is
# running, and backup heat is off. A human gates every changeover via the
# actionable notification. timer.changeover_hold: 12 h after any suggestion
# (nag floor), 24 h after any mode change (minimum time-in-mode).

- id: heat_pump_mode_advisor
  alias: Heat Pump Mode Advisor
  description: >-
    Hourly (at :05, after sensor.changeover_balance refreshes at :00) and when
    the hold expires: compute the candidate regime, require duty-cycle-backed
    indoor confirmation, then send an actionable changeover suggestion and
    start the 12 h nag-floor hold.
  triggers:
  - trigger: time_pattern
    minutes: "5"
  - trigger: event
    event_type: timer.finished
    event_data:
      entity_id: timer.changeover_hold
  variables:
    cdh: "{{ state_attr('sensor.changeover_balance', 'cdh') | float(0) }}"
    hdh: "{{ state_attr('sensor.changeover_balance', 'hdh') | float(0) }}"
    deadband: "{{ states('input_number.changeover_deadband') | float(24) }}"
    candidate: >-
      {% from 'changeover.jinja' import candidate_mode %}
      {{- candidate_mode(cdh, hdh, deadband) -}}
    current_mode: "{{ states('input_select.heat_pump_mode') }}"
    confirmed: >-
      {% from 'changeover.jinja' import confirmation %}
      {{- confirmation(candidate,
                       states('sensor.office_temperature_2h_mean'),
                       states('sensor.studio_temperature_1h_mean'),
                       states('sensor.office_heat_pump_duty_24h'),
                       states('sensor.studio_heat_pump_duty_24h'),
                       states('input_number.office_preferred_temperature'),
                       states('input_number.office_temp_range'),
                       states('input_number.studio_preferred_temperature'),
                       states('input_number.studio_temp_range')) -}}
  conditions:
  - "{{ states('sensor.changeover_balance') not in ['unavailable', 'unknown'] }}"
  - "{{ states('sensor.office_temperature_2h_mean') not in ['unavailable', 'unknown'] }}"
  - "{{ states('sensor.studio_temperature_1h_mean') not in ['unavailable', 'unknown'] }}"
  - "{{ states('sensor.office_heat_pump_duty_24h') not in ['unavailable', 'unknown'] }}"
  - "{{ states('sensor.studio_heat_pump_duty_24h') not in ['unavailable', 'unknown'] }}"
  - "{{ is_state('input_boolean.backup_heat', 'off') }}"
  - "{{ is_state('timer.changeover_hold', 'idle') }}"
  - "{{ candidate != current_mode }}"
  - "{{ confirmed | string == 'True' }}"
  actions:
  - action: notify.mobile_app_pixel_8
    data:
      title: Heat pump changeover
      message: >-
        Next 48 h: {{ cdh | round(0) }} cooling vs {{ hdh | round(0) }} heating
        degree-hours. Office 2 h mean
        {{ states('sensor.office_temperature_2h_mean') }} °C, studio 1 h mean
        {{ states('sensor.studio_temperature_1h_mean') }} °C. Switch to
        {{ candidate }}?
      data:
        tag: changeover
        actions:
        - action: "CHANGEOVER_ACCEPT_{{ candidate }}"
          title: "Switch to {{ candidate }}"
        - action: CHANGEOVER_DISMISS
          title: Not now
  - action: timer.start
    target:
      entity_id: timer.changeover_hold
    data:
      duration: "12:00:00"
  mode: single

- id: heat_pump_mode_advisor_response
  alias: Heat Pump Mode Advisor Response
  description: >-
    Apply an accepted changeover suggestion. The action id carries the
    candidate that was offered, so even a stale tap applies exactly what was
    offered. "Not now" needs no handler — the 12 h hold already started when
    the suggestion was sent.
  triggers:
  - trigger: event
    event_type: mobile_app_notification_action
    event_data:
      action: CHANGEOVER_ACCEPT_heating
  - trigger: event
    event_type: mobile_app_notification_action
    event_data:
      action: CHANGEOVER_ACCEPT_cooling
  - trigger: event
    event_type: mobile_app_notification_action
    event_data:
      action: CHANGEOVER_ACCEPT_off
  actions:
  - action: input_select.select_option
    target:
      entity_id: input_select.heat_pump_mode
    data:
      option: "{{ trigger.event.data.action | replace('CHANGEOVER_ACCEPT_', '') }}"
  mode: queued

- id: heat_pump_mode_changed
  alias: Heat Pump Mode Changed
  description: >-
    Every real mode change — advisor-accepted or manual — starts the 24 h
    minimum-time-in-mode hold so the advisor cannot second-guess a fresh mode.
    Entering off also powers down both heads, each call gated on the switch
    actually being on (Cielo API dedupe).
  triggers:
  - trigger: state
    entity_id: input_select.heat_pump_mode
  conditions:
  - "{{ trigger.from_state is not none and trigger.to_state is not none and
        trigger.from_state.state != trigger.to_state.state }}"
  actions:
  - action: timer.start
    target:
      entity_id: timer.changeover_hold
    data:
      duration: "24:00:00"
  - if:
    - "{{ trigger.to_state.state == 'off' }}"
    then:
    - if:
      - "{{ is_state('switch.office_power', 'on') }}"
      then:
      - action: switch.turn_off
        target:
          entity_id: switch.office_power
    - if:
      - "{{ is_state('switch.studio_power', 'on') }}"
      then:
      - action: switch.turn_off
        target:
          entity_id: switch.studio_power
  mode: queued
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_advisor_automations.py -v`
Expected: 8 PASSED. If `test_advisor_suggests_cooling` fails on the `confirmed` condition, debug by rendering the `confirmation(...)` call in Developer-Tools style via `tests/util.py render()` with the same states — do not weaken the condition to make it pass.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest -v`
Expected: all PASSED (30 tests).

- [ ] **Step 6: Commit**

```bash
git add automations.yaml tests/test_advisor_automations.py
git commit -m "Add changeover advisor automations (suggest + confirm + hold)"
```

---

### Task 7: Documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Replace the no-pipeline sentence**

Replace this paragraph in CLAUDE.md:

> There is no build / test / lint pipeline. Changes are deployed by syncing these files to the HA instance and reloading the relevant domain (automations, template entities) from the HA UI or via `homeassistant.reload_*` services.

with:

```markdown
## Tests

`pytest` covers the changeover logic: Level 2 tests render the
`custom_templates/*.jinja` macros against a real HA template engine
(`pytest-homeassistant-custom-component`); Level 3 tests load the changeover
automations and the changeover-balance template sensor **from the real YAML
files** and exercise triggers/conditions/actions with mocked services.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # keep pinned to the live HA version
.venv/bin/pytest
```

There is no other build / lint pipeline. Changes are deployed by syncing these
files to the HA instance and reloading the relevant domain (automations,
template entities) from the HA UI or via `homeassistant.reload_*` services.
```

- [ ] **Step 2: Add the architecture subsection**

Insert after the "### Backup heat mode" section, before "### Humidity (independent of HVAC)":

```markdown
### Changeover advisor (suggest + confirm)

`heat_pump_mode` is never switched autonomously. `sensor.changeover_balance`
(hourly) integrates the next 48 h of Environment Canada hourly forecast into
heating/cooling degree-hours around `input_number.changeover_balance_point`
(~16 °C); outside `±input_number.changeover_deadband` it nominates
heating/cooling, inside it nominates off (open windows) — so the outdoor
gates (no AC when cold out, no heat when warm out) fall out of the math.

A nomination only becomes a Pixel 8 actionable notification
(`heat_pump_mode_advisor`) when a room confirms the demand **with a
duty-cycle alibi**: indoor temperature is a regulated variable, so a room's
smoothed mean (`sensor.<room>_temperature_<1h|2h>_mean`) only counts as
evidence when that room's pump was idle (`sensor.<room>_heat_pump_duty_24h`
< 2 %) — otherwise the pump itself may be the cause (the office head is
oversized for its small room and overshoots, hence its longer 2 h window).

`timer.changeover_hold` blocks suggestions while active: started for 12 h on
every suggestion (nag floor) and 24 h on every mode change
(`heat_pump_mode_changed`, which also powers down both heads when entering
`off`). Decision logic lives in `custom_templates/changeover.jinja` as pure
macros — tested in `tests/`, shared by the sensor and the advisor.
```

- [ ] **Step 3: Update the tracked-files list and external entities**

In the "Tracked:" list, add after the `custom_templates/setpoint.jinja` line:

```markdown
- `custom_templates/changeover.jinja` — changeover advisor decision macros
- `tests/`, `pytest.ini`, `requirements-dev.txt` — pytest harness (see "Tests")
```

In the external-entities sentence, add `weather.lethbridge` (EC weather entity used by `sensor.changeover_balance`) to the list alongside `sensor.lethbridge_temperature`.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "Document changeover advisor and test harness in CLAUDE.md"
```

---

### Task 8: Live deployment checklist (manual — requires the user / HA host)

No repo files change in this task (except a possible entity-id correction). These steps run against the live HA instance and are the spec's staged deployment.

- [ ] **Step 1: Verify the weather entity.** In HA: Developer Tools → Actions → `weather.get_forecasts`, target `weather.lethbridge`, type `hourly`. Confirm it returns ≥ 48 hourly entries with `temperature`. If the entity id differs, update it in `configuration.yaml` (balance sensor) and `tests/test_changeover_balance_sensor.py` (fixture + assertions), re-run pytest, and commit the correction.

- [ ] **Step 2: Create the UI helpers** (Settings → Devices & services → Helpers), mirroring Task 4 exactly:
  - Edit `input_select.heat_pump_mode`: add option `off`
  - `input_number.changeover_balance_point` — min 10, max 22, step 0.5, box, °C; set value **16**
  - `input_number.changeover_deadband` — min 0, max 200, step 1, box, °C·h; set value **24**
  - `timer.changeover_hold` — no default duration, restore enabled

- [ ] **Step 3: Sync repo files to the HA host** (the usual sync method): `configuration.yaml`, `automations.yaml`, `custom_templates/changeover.jinja`.

- [ ] **Step 4: Restart HA** (the new `sensor:` platform key — statistics/history_stats — is not covered by domain reloads).

- [ ] **Step 5: Disable the advisor for the shadow phase.** Settings → Automations → "Heat Pump Mode Advisor" → disable. Leave "Heat Pump Mode Advisor Response" and "Heat Pump Mode Changed" enabled (they only act on human-initiated events).

- [ ] **Step 6: Shadow phase (a few days).** Watch on a dashboard/history: `sensor.changeover_balance` (and its `cdh`/`hdh` attributes) against EC's published forecast; `sensor.<room>_heat_pump_duty_24h` against the power-switch history; the smoothed means against the raw baseboard temps. Sanity targets: balance strongly negative in heating season; duties nonzero on days the pumps ran.

- [ ] **Step 7: Notification round-trip test.** Run the (still-disabled) advisor manually: Developer Tools → Actions → `automation.trigger` on `automation.heat_pump_mode_advisor` (manual trigger skips conditions, so a notification arrives regardless of season). Verify on the Pixel 8: tapping **Switch to …** changes `input_select.heat_pump_mode` and starts a 24 h `timer.changeover_hold`; **Not now** does nothing. Then set the mode back and cancel the timer.

- [ ] **Step 8: Enable the advisor.** Suggestion volume is self-limiting (≥ 12 h apart); live observation for a couple of weeks is the soak test.

---

## Self-review notes

- **Spec coverage:** forecast nomination (T5), tunables + off option + hold timer (T4), duty/mean evidence sensors (T5), advisor/response/mode-changed with all five condition classes (T6), macro extraction + Level 2 (T2–T3), Level 3 on real YAML (T5–T6), CLAUDE.md (T7), staged deployment + EC entity verification (T8). Hold semantics (12 h vs 24 h) asserted in `test_advisor_suggests_cooling` and `test_accept_sets_mode_and_24h_hold`.
- **Known intentional gaps:** statistics/history_stats sensors have no unit tests (recorder dependency) — covered by the shadow phase; `CHANGEOVER_DISMISS` has no handler by design.
- **Type consistency:** duties are percent everywhere (history_stats ratio, `duty_floor=2`, tests use `"15.0"`/`"1.9"`); macro arg order `(candidate, office_mean, studio_mean, office_duty, studio_duty, office_preferred, office_swing, studio_preferred, studio_swing, duty_floor)` matches between `changeover.jinja`, the advisor variables, and `tests/test_changeover_macros.py`.
