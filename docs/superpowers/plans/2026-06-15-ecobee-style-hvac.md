# Ecobee-style auto heat/cool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the manual-mode steering control loop and the changeover advisor with a two-setpoint (heat-bound / cool-bound) automatic heat/cool coordinator for the multi-split, plus an ecobee-style thermostat tile.

**Architecture:** A single `hvac_coordinator` automation resolves one system-wide mode (heat / cool / idle) from both rooms' two-setpoint demand — heating wins conflicts — then drives each head on/off toward its bounds. Short-cycle protection: per-bound differential, per-head lockout timers, a heat↔cool dwell, and inverter modulation. Decision logic lives in pure, unit-tested macros (`custom_templates/hvac.jinja`). The changeover advisor is deleted. A HACS template-climate facade exposes the ecobee dial.

**Tech Stack:** Home Assistant YAML (templates, automations, helpers), Jinja macros, pytest + `pytest-homeassistant-custom-component`. Reference spec: `docs/superpowers/specs/2026-06-15-ecobee-style-hvac-design.md`.

**Branch:** `ecobee-hvac` (already created; the design commit is on it).

---

## File structure

| File | Responsibility | Action |
|------|----------------|--------|
| `custom_templates/hvac.jinja` | Pure decision macros: `room_demand`, `resolve_mode`, `head_target` | Create |
| `custom_templates/setpoint.jinja` | Old steering macro | Delete |
| `custom_templates/changeover.jinja` | Old advisor macros | Delete |
| `automations.yaml` | `hvac_coordinator` (new); remove 2 old controllers + 3 advisor automations; retarget 2 backup-heat automations | Modify |
| `configuration.yaml` | Remove setpoint/changeover/duty/mean sensors; add 2 template climate entities | Modify |
| `helpers.yaml` | Add bounds/differentials/enable/system-mode/timers; remove swing/preferred/changeover helpers | Modify |
| `tests/test_hvac_macros.py` | Level 2 macro tests | Create |
| `tests/test_hvac_coordinator.py` | Level 3 coordinator tests | Create |
| `tests/test_helpers_yaml.py` | Helper-mirror assertions | Rewrite |
| `tests/test_harness.py` | Sanity import (setpoint → hvac) | Modify |
| `tests/test_advisor_automations.py`, `tests/test_changeover_balance_sensor.py`, `tests/test_changeover_macros.py` | Old advisor tests | Delete |
| `CLAUDE.md` | Architecture/helpers/HACS docs | Modify |

**Test command throughout:** `.venv/bin/pytest` (run the named file for focused steps).

---

## Task 1: Decision macros `hvac.jinja` (Level 2, TDD)

**Files:**
- Create: `custom_templates/hvac.jinja`
- Test: `tests/test_hvac_macros.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_hvac_macros.py`:

```python
"""Level 2 tests: hvac.jinja decision macros (pure functions)."""
from tests.util import render

IMPORTS = "{% from 'hvac.jinja' import room_demand, resolve_mode, head_target %}"


def call(hass, expr):
    return render(hass, IMPORTS + expr)


# --- room_demand: which direction a single room wants -----------------------

async def test_room_wants_heat_below_heat_bound(hass_repo):
    assert call(hass_repo, "{{ room_demand(18, 20, 24, 0.5, 'none') }}") == "heat"


async def test_room_wants_cool_above_cool_bound(hass_repo):
    assert call(hass_repo, "{{ room_demand(25, 20, 24, 0.5, 'none') }}") == "cool"


async def test_room_in_band_wants_nothing(hass_repo):
    assert call(hass_repo, "{{ room_demand(22, 20, 24, 0.5, 'none') }}") == "none"


async def test_heat_hysteresis_keeps_heating_past_bound(hass_repo):
    # Already heating, 0.3 above the bound, differential 0.5 → keep heating.
    assert call(hass_repo, "{{ room_demand(20.3, 20, 24, 0.5, 'heat') }}") == "heat"


async def test_heat_hysteresis_does_not_start_inside_differential(hass_repo):
    # Not currently heating at the same temp → no demand (won't short-cycle on).
    assert call(hass_repo, "{{ room_demand(20.3, 20, 24, 0.5, 'none') }}") == "none"


async def test_cool_hysteresis_keeps_cooling_past_bound(hass_repo):
    assert call(hass_repo, "{{ room_demand(23.7, 20, 24, 0.5, 'cool') }}") == "cool"


# --- resolve_mode: heating wins ---------------------------------------------

async def test_resolve_heating_wins_conflict(hass_repo):
    assert call(hass_repo, "{{ resolve_mode('cool', 'heat') }}") == "heat"
    assert call(hass_repo, "{{ resolve_mode('heat', 'cool') }}") == "heat"


async def test_resolve_cool_when_only_cool(hass_repo):
    assert call(hass_repo, "{{ resolve_mode('none', 'cool') }}") == "cool"


async def test_resolve_idle_when_no_demand(hass_repo):
    assert call(hass_repo, "{{ resolve_mode('none', 'none') }}") == "idle"


# --- head_target: bound + lead, clamped to [17, 30] -------------------------

async def test_head_target_heat_is_bound_plus_lead(hass_repo):
    assert call(hass_repo, "{{ head_target('heat', 20, 24, 2) }}") == 22


async def test_head_target_cool_is_bound_minus_lead(hass_repo):
    assert call(hass_repo, "{{ head_target('cool', 20, 24, 2) }}") == 22


async def test_head_target_clamps_high(hass_repo):
    assert call(hass_repo, "{{ head_target('heat', 29, 33, 2) }}") == 30


async def test_head_target_clamps_low(hass_repo):
    assert call(hass_repo, "{{ head_target('cool', 16, 17, 2) }}") == 17
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_hvac_macros.py -q`
Expected: FAIL — `TemplateError` / cannot import `room_demand` (file does not exist).

- [ ] **Step 3: Write the macros**

Create `custom_templates/hvac.jinja`:

```jinja
{# Decision macros for the two-setpoint auto heat/cool coordinator.
   Pure functions — rendered by tests and by the hvac_coordinator automation.

   room_demand: what one room wants given its reliable temperature, its two
   bounds, a hysteresis differential, and the direction it is *currently*
   running ('heat' | 'cool' | 'none'). A running head keeps going `differential`
   degrees past its bound before it stops, so it cannot short-cycle at the bound.
   Returns 'heat' | 'cool' | 'none'. #}
{% macro room_demand(temp, heat_bound, cool_bound, differential, current) -%}
  {%- set t = temp | float -%}
  {%- set hb = heat_bound | float -%}
  {%- set cb = cool_bound | float -%}
  {%- set d = differential | float -%}
  {%- if t <= hb or (current == 'heat' and t < hb + d) -%}heat
  {%- elif t >= cb or (current == 'cool' and t > cb - d) -%}cool
  {%- else -%}none
  {%- endif -%}
{%- endmacro %}

{# resolve_mode: one system-wide mode for the shared compressor. Heating wins
   any conflict. Returns 'heat' | 'cool' | 'idle'. #}
{% macro resolve_mode(office_demand, studio_demand) -%}
  {%- if office_demand == 'heat' or studio_demand == 'heat' -%}heat
  {%- elif office_demand == 'cool' or studio_demand == 'cool' -%}cool
  {%- else -%}idle
  {%- endif -%}
{%- endmacro %}

{# head_target: the temperature to command a head, a small `lead` past the
   active bound so the inverter stays committed (the coordinator does the real
   cutoff against the reliable room sensor). Clamped to [17, 30]. Empty for a
   non-active mode. #}
{% macro head_target(mode, heat_bound, cool_bound, lead) -%}
  {%- set l = lead | float -%}
  {%- if mode == 'heat' -%}
    {{ [17, [30, (heat_bound | float + l)] | min] | max }}
  {%- elif mode == 'cool' -%}
    {{ [17, [30, (cool_bound | float - l)] | min] | max }}
  {%- endif -%}
{%- endmacro %}
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_hvac_macros.py -q`
Expected: PASS (13 passed).

- [ ] **Step 5: Commit**

```bash
git add custom_templates/hvac.jinja tests/test_hvac_macros.py
git commit -m "Add hvac.jinja two-setpoint decision macros with Level 2 tests"
```

---

## Task 2: Remove the changeover advisor

Deletes the advisor (the requested revert): 3 automations, the balance sensor + its weather block, the duty/mean evidence sensors, `changeover.jinja`, and the 3 changeover test files. The changeover helpers stay in `helpers.yaml` until Task 7 (nothing references them after this, and `test_helpers_yaml.py` still asserts them until its rewrite in Task 7).

**Files:**
- Modify: `automations.yaml`, `configuration.yaml`
- Delete: `custom_templates/changeover.jinja`, `tests/test_advisor_automations.py`, `tests/test_changeover_balance_sensor.py`, `tests/test_changeover_macros.py`

- [ ] **Step 1: Delete the advisor automations**

In `automations.yaml`, delete the entire trailing block starting at the `# Changeover advisor` banner comment (the line beginning `# ---...` above `- id: heat_pump_mode_advisor`) through the end of file — i.e. the three automations `heat_pump_mode_advisor`, `heat_pump_mode_advisor_response`, `heat_pump_mode_changed` and their banner. The file now ends with the humidity section (`studio_humidity_manual_detector`, `mode: queued`).

- [ ] **Step 2: Delete the changeover + evidence sensors**

In `configuration.yaml`:
- Delete the `# Changeover advisor:` comment block and the entire trigger-based template entry that defines `sensor.changeover_balance` (the list item starting `- triggers:` with the two `weather.get_forecasts` actions, through the `daily_forecast_days:` attribute). This is the last item under the top-level `template:` list.
- Delete the entire trailing top-level `sensor:` block (the `# Changeover advisor evidence sensors` comment through both `history_stats` entries) — `office_temperature_2h_mean`, `studio_temperature_1h_mean`, `office_heat_pump_duty_24h`, `studio_heat_pump_duty_24h`.

Leave the `template: - sensor:` entries (energy, baseboard temps, setpoint, humidity thresholds) and the `notify:` group intact for now.

- [ ] **Step 3: Delete the changeover files**

```bash
git rm custom_templates/changeover.jinja \
       tests/test_advisor_automations.py \
       tests/test_changeover_balance_sensor.py \
       tests/test_changeover_macros.py
```

- [ ] **Step 4: Run the suite**

Run: `.venv/bin/pytest -q`
Expected: PASS. The changeover tests are gone; `test_hvac_macros.py`, `test_harness.py`, and `test_helpers_yaml.py` still pass (`test_helpers_yaml.py` still asserts the changeover helpers, which remain in `helpers.yaml`).

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "Remove changeover advisor (automations, sensors, macros, tests)"
```

---

## Task 3: Remove the old steering control loop

Deletes the two per-room controllers, `setpoint.jinja`, and the two setpoint sensors. Repoints `test_harness.py` at `hvac.jinja`.

**Files:**
- Modify: `automations.yaml`, `configuration.yaml`, `tests/test_harness.py`
- Delete: `custom_templates/setpoint.jinja`

- [ ] **Step 1: Delete the controller automations**

In `automations.yaml`, delete the two automations `office_hvac_controller` (`- id: office_hvac_controller` … `mode: single`) and `studio_hvac_controller` (… `mode: single`), but **keep** the `# HVAC controllers` banner comment block at the top — its body comment is rewritten in Task 5. After this the file's first automation is the backup-heat `Disable Heat Pump in Cold Weather`.

- [ ] **Step 2: Delete the setpoint sensors**

In `configuration.yaml`, under `template: - sensor:`, delete the two entries named `"Office Heat Pump Setpoint Temperature"` (`unique_id: sensor.office_heat_pump_setpoint_temperature`) and `"Studio Heat Pump Setpoint Temperature"` (`unique_id: sensor.studio_heat_pump_setpoint_temperature`), including their `{% from 'setpoint.jinja' ... %}` state templates.

- [ ] **Step 3: Delete the setpoint macro**

```bash
git rm custom_templates/setpoint.jinja
```

- [ ] **Step 4: Repoint the harness sanity test**

In `tests/test_harness.py`, replace the `setpoint.jinja` import check so it does not reference the deleted file:

```python
async def test_repo_custom_templates_importable(hass_repo):
    out = render(hass_repo, "{% from 'hvac.jinja' import room_demand %}ok")
    assert out == "ok"
```

- [ ] **Step 5: Run the suite**

Run: `.venv/bin/pytest -q`
Expected: PASS. (`test_helpers_yaml.py` and the other harness assertions still pass; old steering is gone.)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Remove old steering control loop (setpoint macro, sensors, controllers)"
```

---

## Task 4: Add the new helpers

Additive only — new helpers join `helpers.yaml`; obsolete ones are removed later (Task 7) so the still-present backup-heat automations keep working until retargeted (Task 6).

**Files:**
- Modify: `helpers.yaml`, `tests/test_helpers_yaml.py`

- [ ] **Step 1: Write the failing helper test**

Add to `tests/test_helpers_yaml.py` (append; the file is rewritten in Task 7):

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_helpers_yaml.py -q`
Expected: FAIL — the new helpers do not exist yet.

- [ ] **Step 3: Add the helpers**

In `helpers.yaml`, under `input_number:` add:

```yaml
  office_heat_bound:
    name: Office Heat Bound
    min: 15
    max: 30
    step: 0.5
    mode: slider
    unit_of_measurement: "°C"
    icon: mdi:thermometer-chevron-down
  office_cool_bound:
    name: Office Cool Bound
    min: 15
    max: 30
    step: 0.5
    mode: slider
    unit_of_measurement: "°C"
    icon: mdi:thermometer-chevron-up
  studio_heat_bound:
    name: Studio Heat Bound
    min: 15
    max: 30
    step: 0.5
    mode: slider
    unit_of_measurement: "°C"
    icon: mdi:thermometer-chevron-down
  studio_cool_bound:
    name: Studio Cool Bound
    min: 15
    max: 30
    step: 0.5
    mode: slider
    unit_of_measurement: "°C"
    icon: mdi:thermometer-chevron-up
  office_temp_differential:
    name: Office Temp Differential
    min: 0
    max: 3
    step: 0.1
    mode: box
    unit_of_measurement: "°C"
    icon: mdi:arrow-expand-vertical
  studio_temp_differential:
    name: Studio Temp Differential
    min: 0
    max: 3
    step: 0.1
    mode: box
    unit_of_measurement: "°C"
    icon: mdi:arrow-expand-vertical
```

Under `input_boolean:` add:

```yaml
  hvac_enable:
    name: HVAC Enable
    icon: mdi:hvac
```

Under `input_select:` add (alongside the existing `heat_pump_mode`, which is removed in Task 7):

```yaml
  system_hvac_mode:
    name: System HVAC Mode
    icon: mdi:heat-pump
    options:
      - idle
      - heat
      - cool
      - "off"
```

Under `timer:` add:

```yaml
  mode_min_dwell:
    name: Mode Min Dwell
    duration: "00:15:00"
    restore: true
  office_head_lockout:
    name: Office Head Lockout
    duration: "00:08:00"
    restore: true
  studio_head_lockout:
    name: Studio Head Lockout
    duration: "00:06:00"
    restore: true
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_helpers_yaml.py -q`
Expected: PASS (new + old helper assertions both pass).

- [ ] **Step 5: Commit**

```bash
git add helpers.yaml tests/test_helpers_yaml.py
git commit -m "Add ecobee-model helpers (bounds, differentials, enable, system mode, timers)"
```

---

## Task 5: The HVAC coordinator automation (Level 3, TDD)

**Files:**
- Modify: `automations.yaml`
- Test: `tests/test_hvac_coordinator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_hvac_coordinator.py`:

```python
"""Level 3 tests: hvac_coordinator loaded from automations.yaml."""
import pytest
import yaml
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

from tests.conftest import REPO_ROOT

DEFAULTS = {
    "input_number.office_heat_bound": 20,
    "input_number.office_cool_bound": 24,
    "input_number.studio_heat_bound": 20,
    "input_number.studio_cool_bound": 23,
    "input_number.office_temp_differential": 1.0,
    "input_number.studio_temp_differential": 0.5,
}


@pytest.fixture
async def coordinator(hass_helpers):
    hass = hass_helpers
    autos = yaml.safe_load((REPO_ROOT / "automations.yaml").read_text())
    chosen = [a for a in autos if a.get("id") == "hvac_coordinator"]
    assert len(chosen) == 1, "hvac_coordinator missing from automations.yaml"
    assert await async_setup_component(hass, "automation", {"automation": chosen})
    calls = {
        "on": async_mock_service(hass, "switch", "turn_on"),
        "off": async_mock_service(hass, "switch", "turn_off"),
        "temp": async_mock_service(hass, "climate", "set_temperature"),
    }
    yield hass, calls
    await hass.services.async_call(
        "automation", "turn_off", {"entity_id": "all"}, blocking=True
    )
    for t in ("mode_min_dwell", "office_head_lockout", "studio_head_lockout"):
        await hass.services.async_call(
            "timer", "cancel", {"entity_id": f"timer.{t}"}, blocking=True
        )
    await hass.async_block_till_done()


async def arrange(hass, *, office_temp, studio_temp, stored="idle",
                  enabled=True, backup=False,
                  office_switch="off", studio_switch="off",
                  office_climate="off", studio_climate="off",
                  office_lockout=False, studio_lockout=False):
    for ent, val in DEFAULTS.items():
        await hass.services.async_call(
            "input_number", "set_value", {"entity_id": ent, "value": val},
            blocking=True,
        )
    await hass.services.async_call(
        "input_select", "select_option",
        {"entity_id": "input_select.system_hvac_mode", "option": stored},
        blocking=True,
    )
    await hass.services.async_call(
        "input_boolean", "turn_on" if enabled else "turn_off",
        {"entity_id": "input_boolean.hvac_enable"}, blocking=True,
    )
    await hass.services.async_call(
        "input_boolean", "turn_on" if backup else "turn_off",
        {"entity_id": "input_boolean.backup_heat"}, blocking=True,
    )
    hass.states.async_set("sensor.office_baseboard_current_temperature", office_temp)
    hass.states.async_set("sensor.studio_baseboard_current_temperature", studio_temp)
    hass.states.async_set("switch.office_power", office_switch)
    hass.states.async_set("switch.studio_power", studio_switch)
    hass.states.async_set("climate.office", office_climate, {"temperature": 22})
    hass.states.async_set("climate.studio", studio_climate, {"temperature": 22})
    for room, lock in (("office", office_lockout), ("studio", studio_lockout)):
        if lock:
            await hass.services.async_call(
                "timer", "start",
                {"entity_id": f"timer.{room}_head_lockout", "duration": "00:08:00"},
                blocking=True,
            )
        else:
            await hass.services.async_call(
                "timer", "cancel",
                {"entity_id": f"timer.{room}_head_lockout"}, blocking=True,
            )
    await hass.async_block_till_done()


async def run(hass):
    await hass.services.async_call(
        "automation", "trigger",
        {"entity_id": "automation.hvac_coordinator", "skip_condition": False},
        blocking=True,
    )
    await hass.async_block_till_done()


def _entities(call):
    e = call.data.get("entity_id")
    return e if isinstance(e, list) else [e]


def turned_on(calls, entity):
    return any(entity in _entities(c) for c in calls["on"])


def turned_off(calls, entity):
    return any(entity in _entities(c) for c in calls["off"])


async def test_cold_studio_heats_studio_only(coordinator):
    hass, calls = coordinator
    # Studio below its heat bound (wants heat); office mid-band (no demand).
    await arrange(hass, office_temp=22, studio_temp=18)
    await run(hass)
    assert turned_on(calls, "switch.studio_power")
    assert not turned_on(calls, "switch.office_power")
    assert hass.states.get("input_select.system_hvac_mode").state == "heat"
    heat_calls = [c for c in calls["temp"] if c.data.get("hvac_mode") == "heat"]
    assert heat_calls and heat_calls[0].data["temperature"] == 22  # 20 + lead 2


async def test_conflict_heating_wins_office_head_idle(coordinator):
    hass, calls = coordinator
    # Office hot (wants cool) AND studio cold (wants heat) → heating wins.
    await arrange(hass, office_temp=26, studio_temp=18)
    await run(hass)
    assert hass.states.get("input_select.system_hvac_mode").state == "heat"
    assert turned_on(calls, "switch.studio_power")
    assert not turned_on(calls, "switch.office_power")  # office cannot cool


async def test_lockout_blocks_turn_on(coordinator):
    hass, calls = coordinator
    await arrange(hass, office_temp=22, studio_temp=18, studio_lockout=True)
    await run(hass)
    assert not turned_on(calls, "switch.studio_power")


async def test_master_off_forces_heads_off(coordinator):
    hass, calls = coordinator
    await arrange(hass, office_temp=18, studio_temp=18, enabled=False,
                  office_switch="on", studio_switch="on")
    await run(hass)
    assert turned_off(calls, "switch.office_power")
    assert turned_off(calls, "switch.studio_power")
    assert hass.states.get("input_select.system_hvac_mode").state == "off"


async def test_backup_heat_forces_heads_off(coordinator):
    hass, calls = coordinator
    await arrange(hass, office_temp=18, studio_temp=18, backup=True,
                  office_switch="on", studio_switch="off")
    await run(hass)
    assert turned_off(calls, "switch.office_power")
    assert hass.states.get("input_select.system_hvac_mode").state == "idle"


async def test_in_band_idles(coordinator):
    hass, calls = coordinator
    await arrange(hass, office_temp=22, studio_temp=21)
    await run(hass)
    assert not calls["on"]
    assert not calls["temp"]
    assert hass.states.get("input_select.system_hvac_mode").state == "idle"


async def test_dwell_pins_mode_blocks_reverse(coordinator):
    hass, calls = coordinator
    # Stored heat, dwell running; office now wants cool, no heat demand.
    await arrange(hass, office_temp=26, studio_temp=21, stored="heat")
    await hass.services.async_call(
        "timer", "start",
        {"entity_id": "timer.mode_min_dwell", "duration": "00:15:00"},
        blocking=True,
    )
    await run(hass)
    # Pinned to heat: no flip to cool, office head not cooled on.
    assert hass.states.get("input_select.system_hvac_mode").state == "heat"
    assert not turned_on(calls, "switch.office_power")
    await hass.services.async_call(
        "timer", "cancel", {"entity_id": "timer.mode_min_dwell"}, blocking=True
    )


async def test_drift_resends_target_without_toggle(coordinator):
    hass, calls = coordinator
    # Studio already heating but climate target drifted from desired (22).
    await arrange(hass, office_temp=22, studio_temp=18, stored="heat",
                  studio_switch="on", studio_climate="heat")
    hass.states.async_set("climate.studio", "heat", {"temperature": 19})
    await hass.async_block_till_done()
    await run(hass)
    assert not turned_on(calls, "switch.studio_power")  # no toggle
    assert any(c.data.get("temperature") == 22 for c in calls["temp"])
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_hvac_coordinator.py -q`
Expected: FAIL — `hvac_coordinator missing from automations.yaml`.

- [ ] **Step 3: Add the coordinator automation**

In `automations.yaml`, first replace the body comment under the `# HVAC controllers` banner to describe the new model (keep the banner). Then add this automation immediately after the banner, before the backup-heat section:

```yaml
- id: hvac_coordinator
  alias: HVAC Coordinator
  description: >-
    One coordinator for the multi-split. Resolves a single system-wide mode from
    both rooms' two-setpoint demand (heating wins conflicts), then drives each
    head on/off toward its bounds. Short-cycle protected by per-head lockout
    timers and a heat<->cool dwell. Master-off / backup-heat force both heads
    off. Every Cielo call gated on a real desired-vs-current delta.
  triggers:
  - trigger: state
    entity_id:
    - sensor.office_baseboard_current_temperature
    - sensor.studio_baseboard_current_temperature
    - input_number.office_heat_bound
    - input_number.office_cool_bound
    - input_number.studio_heat_bound
    - input_number.studio_cool_bound
    - input_number.office_temp_differential
    - input_number.studio_temp_differential
    - input_boolean.hvac_enable
    - input_boolean.backup_heat
  - trigger: event
    event_type: timer.finished
    event_data:
      entity_id: timer.mode_min_dwell
  - trigger: event
    event_type: timer.finished
    event_data:
      entity_id: timer.office_head_lockout
  - trigger: event
    event_type: timer.finished
    event_data:
      entity_id: timer.studio_head_lockout
  - trigger: homeassistant
    event: start
  - trigger: time_pattern
    minutes: /5
  variables:
    lead: 2
    enabled: "{{ is_state('input_boolean.hvac_enable', 'on') }}"
    backup: "{{ is_state('input_boolean.backup_heat', 'on') }}"
    stored: "{{ states('input_select.system_hvac_mode') }}"
    dwell_active: "{{ is_state('timer.mode_min_dwell', 'active') }}"
    office_temp: "{{ states('sensor.office_baseboard_current_temperature') | float(0) }}"
    studio_temp: "{{ states('sensor.studio_baseboard_current_temperature') | float(0) }}"
    office_hb: "{{ states('input_number.office_heat_bound') | float(0) }}"
    office_cb: "{{ states('input_number.office_cool_bound') | float(0) }}"
    studio_hb: "{{ states('input_number.studio_heat_bound') | float(0) }}"
    studio_cb: "{{ states('input_number.studio_cool_bound') | float(0) }}"
    office_diff: "{{ states('input_number.office_temp_differential') | float(0) }}"
    studio_diff: "{{ states('input_number.studio_temp_differential') | float(0) }}"
    office_switch_on: "{{ is_state('switch.office_power', 'on') }}"
    studio_switch_on: "{{ is_state('switch.studio_power', 'on') }}"
    office_dir: "{{ stored if office_switch_on and stored in ['heat', 'cool'] else 'none' }}"
    studio_dir: "{{ stored if studio_switch_on and stored in ['heat', 'cool'] else 'none' }}"
    office_demand: >-
      {% from 'hvac.jinja' import room_demand %}
      {{- room_demand(office_temp, office_hb, office_cb, office_diff, office_dir) -}}
    studio_demand: >-
      {% from 'hvac.jinja' import room_demand %}
      {{- room_demand(studio_temp, studio_hb, studio_cb, studio_diff, studio_dir) -}}
    resolved: >-
      {% from 'hvac.jinja' import resolve_mode %}
      {{- resolve_mode(office_demand, studio_demand) -}}
    effective: "{{ stored if (dwell_active and stored in ['heat', 'cool']) else resolved }}"
    office_want_on: >-
      {{ (effective == 'heat' and office_demand == 'heat')
         or (effective == 'cool' and office_demand == 'cool') }}
    studio_want_on: >-
      {{ (effective == 'heat' and studio_demand == 'heat')
         or (effective == 'cool' and studio_demand == 'cool') }}
    desired_hvac: "{{ 'heat' if effective == 'heat' else 'cool' }}"
    office_target_raw: >-
      {% from 'hvac.jinja' import head_target %}
      {{- head_target(effective, office_hb, office_cb, lead) -}}
    studio_target_raw: >-
      {% from 'hvac.jinja' import head_target %}
      {{- head_target(effective, studio_hb, studio_cb, lead) -}}
    office_target: "{{ office_target_raw | float(0) }}"
    studio_target: "{{ studio_target_raw | float(0) }}"
    office_lockout: "{{ is_state('timer.office_head_lockout', 'active') }}"
    studio_lockout: "{{ is_state('timer.studio_head_lockout', 'active') }}"
    current_office_hvac: "{{ states('climate.office') }}"
    current_studio_hvac: "{{ states('climate.studio') }}"
    current_office_target: "{{ state_attr('climate.office', 'temperature') | float(0) }}"
    current_studio_target: "{{ state_attr('climate.studio', 'temperature') | float(0) }}"
    safe_mode: "{{ 'off' if not enabled else 'idle' }}"
  conditions:
  - "{{ states('sensor.office_baseboard_current_temperature') not in ['unavailable', 'unknown'] }}"
  - "{{ states('sensor.studio_baseboard_current_temperature') not in ['unavailable', 'unknown'] }}"
  - "{{ states('switch.office_power') not in ['unavailable', 'unknown'] }}"
  - "{{ states('switch.studio_power') not in ['unavailable', 'unknown'] }}"
  - "{{ states('climate.office') not in ['unavailable', 'unknown'] }}"
  - "{{ states('climate.studio') not in ['unavailable', 'unknown'] }}"
  actions:
  # SAFETY: master disabled or backup heat → force both heads off, then stop.
  - if: "{{ not enabled or backup }}"
    then:
    - if: "{{ office_switch_on }}"
      then:
      - action: switch.turn_off
        target:
          entity_id: switch.office_power
    - if: "{{ studio_switch_on }}"
      then:
      - action: switch.turn_off
        target:
          entity_id: switch.studio_power
    - if: "{{ stored != safe_mode }}"
      then:
      - action: input_select.select_option
        target:
          entity_id: input_select.system_hvac_mode
        data:
          option: "{{ safe_mode }}"
    - stop: master disabled or backup heat
  # Record the resolved/pinned mode; start the dwell on an active-mode change.
  - if: "{{ effective != stored }}"
    then:
    - action: input_select.select_option
      target:
        entity_id: input_select.system_hvac_mode
      data:
        option: "{{ effective }}"
    - if: "{{ effective in ['heat', 'cool'] }}"
      then:
      - action: timer.start
        target:
          entity_id: timer.mode_min_dwell
  # OFFICE head reconcile.
  - choose:
    - conditions: "{{ office_want_on and not office_switch_on and not office_lockout }}"
      sequence:
      - action: switch.turn_on
        target:
          entity_id: switch.office_power
      - action: climate.set_temperature
        target:
          entity_id: climate.office
        data:
          temperature: "{{ office_target }}"
          hvac_mode: "{{ desired_hvac }}"
      - action: timer.start
        target:
          entity_id: timer.office_head_lockout
    - conditions: >-
        {{ office_want_on and office_switch_on
           and (current_office_hvac != desired_hvac
                or current_office_target != office_target) }}
      sequence:
      - action: climate.set_temperature
        target:
          entity_id: climate.office
        data:
          temperature: "{{ office_target }}"
          hvac_mode: "{{ desired_hvac }}"
    - conditions: "{{ not office_want_on and office_switch_on and not office_lockout }}"
      sequence:
      - action: switch.turn_off
        target:
          entity_id: switch.office_power
      - action: timer.start
        target:
          entity_id: timer.office_head_lockout
  # STUDIO head reconcile.
  - choose:
    - conditions: "{{ studio_want_on and not studio_switch_on and not studio_lockout }}"
      sequence:
      - action: switch.turn_on
        target:
          entity_id: switch.studio_power
      - action: climate.set_temperature
        target:
          entity_id: climate.studio
        data:
          temperature: "{{ studio_target }}"
          hvac_mode: "{{ desired_hvac }}"
      - action: timer.start
        target:
          entity_id: timer.studio_head_lockout
    - conditions: >-
        {{ studio_want_on and studio_switch_on
           and (current_studio_hvac != desired_hvac
                or current_studio_target != studio_target) }}
      sequence:
      - action: climate.set_temperature
        target:
          entity_id: climate.studio
        data:
          temperature: "{{ studio_target }}"
          hvac_mode: "{{ desired_hvac }}"
    - conditions: "{{ not studio_want_on and studio_switch_on and not studio_lockout }}"
      sequence:
      - action: switch.turn_off
        target:
          entity_id: switch.studio_power
      - action: timer.start
        target:
          entity_id: timer.studio_head_lockout
  mode: single
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/pytest tests/test_hvac_coordinator.py -q`
Expected: PASS (8 passed). If a test fails on a string/number comparison, confirm the `| float(0)` wrappers on `office_target` / `current_office_target` are present.

- [ ] **Step 5: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add automations.yaml tests/test_hvac_coordinator.py
git commit -m "Add hvac_coordinator automation with Level 3 tests"
```

---

## Task 6: Retarget backup-heat off the removed `preferred`

The two backup-heat automations still reference `input_number.<room>_preferred_temperature`, which Task 7 removes. Repoint them at the derived comfort midpoint (backup on) and `heat_bound − 2.5` (warmup), and drop the `mode: single` heat-pump driving to the coordinator (which already forces heads off when `backup_heat` is on).

**Files:**
- Modify: `automations.yaml`

- [ ] **Step 1: Retarget "Disable Heat Pump in Cold Weather"**

In automation `'1756873917108'`, replace the two baseboard `climate.set_temperature` data templates so each targets the room's comfort midpoint:

```yaml
  - action: climate.set_temperature
    target:
      entity_id: climate.neviweb130_climate_th1123wf
    data:
      temperature: >-
        {{ ((states('input_number.office_heat_bound') | float
             + states('input_number.office_cool_bound') | float) / 2) | round(0) }}
  - action: climate.set_temperature
    target:
      entity_id: climate.neviweb130_climate_th1124wf
    data:
      temperature: >-
        {{ ((states('input_number.studio_heat_bound') | float
             + states('input_number.studio_cool_bound') | float) / 2) | round(0) }}
```

- [ ] **Step 2: Retarget "Enable Heat pump in warm weather"**

In automation `'1756874009383'`, replace the two baseboard targets with `heat_bound − 2.5` (baseboards sit below the pump's heating range so the pump leads):

```yaml
  - action: climate.set_temperature
    target:
      entity_id: climate.neviweb130_climate_th1123wf
    data:
      temperature: "{{ states('input_number.office_heat_bound') | float - 2.5 }}"
  - action: climate.set_temperature
    target:
      entity_id: climate.neviweb130_climate_th1124wf
    data:
      temperature: "{{ states('input_number.studio_heat_bound') | float - 2.5 }}"
```

- [ ] **Step 3: Confirm no remaining `preferred` references**

Run: `grep -n "preferred_temperature" automations.yaml configuration.yaml`
Expected: no output (zero matches).

- [ ] **Step 4: Run the suite**

Run: `.venv/bin/pytest -q`
Expected: PASS (no test covers the backup-heat automations directly; this confirms nothing else broke).

- [ ] **Step 5: Commit**

```bash
git add automations.yaml
git commit -m "Retarget backup-heat baseboards off removed preferred (midpoint / heat_bound-2.5)"
```

---

## Task 7: Remove the obsolete helpers

Now that nothing references them, delete the old helpers and rewrite the helper-mirror test to assert the new set and the removals.

**Files:**
- Modify: `helpers.yaml`, `tests/test_helpers_yaml.py`, `tests/test_harness.py`

- [ ] **Step 1: Remove obsolete helpers from `helpers.yaml`**

Delete these blocks:
- `input_number`: `office_preferred_temperature`, `studio_preferred_temperature`, `office_temp_range`, `studio_temp_range`, `changeover_balance_point`, `changeover_deadband`, `changeover_daily_deadband` (and the changeover comment lines above them)
- `input_select`: `heat_pump_mode`
- `timer`: `changeover_hold` (and its comment)

- [ ] **Step 2: Rewrite `tests/test_helpers_yaml.py`**

Replace the whole file with assertions for the new set + explicit removal checks:

```python
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
```

- [ ] **Step 3: Repoint the harness helper sanity test**

In `tests/test_harness.py`, update `test_helpers_yaml_loads` so it no longer references the removed `heat_pump_mode`:

```python
async def test_helpers_yaml_loads(hass_helpers):
    assert hass_helpers.states.get("input_select.system_hvac_mode") is not None
    assert hass_helpers.states.get("timer.humidity_cooldown") is not None
```

- [ ] **Step 4: Run the suite**

Run: `.venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add helpers.yaml tests/test_helpers_yaml.py tests/test_harness.py
git commit -m "Remove obsolete helpers (preferred, swing, changeover) and update mirror tests"
```

---

## Task 8: Ecobee thermostat tile (template climate facade)

Adds two template climate entities so the standard HA thermostat card shows the dual heat/cool dial. This needs a HACS **Climate Template** custom integration and is **verified manually on device** — the custom component is not installed in the pytest harness, so there is no automated test.

**Files:**
- Modify: `configuration.yaml`

- [ ] **Step 1: Add the template climate entities**

In `configuration.yaml`, add a top-level `climate:` block. **Confirm the field names against the installed integration's README** (forks vary; this matches the common `climate_template` platform):

```yaml
climate:
  - platform: climate_template
    name: Office Thermostat
    unique_id: office_thermostat
    modes:
      - "off"
      - "heat_cool"
    min_temp: 15
    max_temp: 30
    temp_step: 0.5
    current_temperature_template: "{{ states('sensor.office_baseboard_current_temperature') }}"
    target_temperature_low_template: "{{ states('input_number.office_heat_bound') }}"
    target_temperature_high_template: "{{ states('input_number.office_cool_bound') }}"
    hvac_mode_template: "{{ 'heat_cool' if is_state('input_boolean.hvac_enable', 'on') else 'off' }}"
    hvac_action_template: >-
      {% if not is_state('input_boolean.hvac_enable', 'on') %}off
      {%- elif is_state('switch.office_power', 'on') and is_state('input_select.system_hvac_mode', 'heat') %}heating
      {%- elif is_state('switch.office_power', 'on') and is_state('input_select.system_hvac_mode', 'cool') %}cooling
      {%- else %}idle{% endif %}
    set_temperature:
      - action: input_number.set_value
        target:
          entity_id: input_number.office_heat_bound
        data:
          value: "{{ target_temp_low }}"
      - action: input_number.set_value
        target:
          entity_id: input_number.office_cool_bound
        data:
          value: "{{ target_temp_high }}"
    set_hvac_mode:
      - action: "input_boolean.turn_{{ 'on' if hvac_mode == 'heat_cool' else 'off' }}"
        target:
          entity_id: input_boolean.hvac_enable
  - platform: climate_template
    name: Studio Thermostat
    unique_id: studio_thermostat
    modes:
      - "off"
      - "heat_cool"
    min_temp: 15
    max_temp: 30
    temp_step: 0.5
    current_temperature_template: "{{ states('sensor.studio_baseboard_current_temperature') }}"
    target_temperature_low_template: "{{ states('input_number.studio_heat_bound') }}"
    target_temperature_high_template: "{{ states('input_number.studio_cool_bound') }}"
    hvac_mode_template: "{{ 'heat_cool' if is_state('input_boolean.hvac_enable', 'on') else 'off' }}"
    hvac_action_template: >-
      {% if not is_state('input_boolean.hvac_enable', 'on') %}off
      {%- elif is_state('switch.studio_power', 'on') and is_state('input_select.system_hvac_mode', 'heat') %}heating
      {%- elif is_state('switch.studio_power', 'on') and is_state('input_select.system_hvac_mode', 'cool') %}cooling
      {%- else %}idle{% endif %}
    set_temperature:
      - action: input_number.set_value
        target:
          entity_id: input_number.studio_heat_bound
        data:
          value: "{{ target_temp_low }}"
      - action: input_number.set_value
        target:
          entity_id: input_number.studio_cool_bound
        data:
          value: "{{ target_temp_high }}"
    set_hvac_mode:
      - action: "input_boolean.turn_{{ 'on' if hvac_mode == 'heat_cool' else 'off' }}"
        target:
          entity_id: input_boolean.hvac_enable
```

- [ ] **Step 2: Verify the suite still loads**

Run: `.venv/bin/pytest -q`
Expected: PASS (the new `climate:` block is not exercised by tests; this just confirms nothing else regressed).

- [ ] **Step 3: Commit**

```bash
git add configuration.yaml
git commit -m "Add ecobee-style template climate tiles (office/studio thermostat facade)"
```

- [ ] **Step 4: On-device verification (manual, at deploy time — not part of the merge)**

Install the HACS Climate Template integration, sync files, reload, then add a Thermostat card for `climate.office_thermostat`: confirm it shows current temp, a heat handle (heat bound) and cool handle (cool bound), the action label, and that dragging a handle updates the matching `input_number`.

---

## Task 9: Documentation & memory

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Rewrite the control-loop architecture**

In `CLAUDE.md`, replace the "The two-stage heat-pump control loop" section with a description of the single coordinator + two-setpoint model: each room has `<room>_heat_bound` / `<room>_cool_bound` (no `preferred`); the `hvac_coordinator` resolves one system-wide mode (heat / cool / idle) from both rooms' demand with **heating wins** conflicts (the multi-split shares one compressor); short-cycle protection = per-bound differential + per-head lockout timers (`timer.<room>_head_lockout`) + heat↔cool dwell (`timer.mode_min_dwell`) + inverter modulation; `input_boolean.hvac_enable` is the master off; the head target is `bound ± lead` with the real cutoff against `sensor.<room>_baseboard_current_temperature`.

- [ ] **Step 2: Update the backup-heat section**

State that backup heat now forces both heads **off** (the coordinator yields to `backup_heat`); baseboards target the comfort midpoint `(heat_bound + cool_bound)/2`, and on warmup drop to `heat_bound − 2.5 °C` so the heat pump leads.

- [ ] **Step 3: Delete the changeover-advisor section**

Remove the entire "Changeover advisor (suggest + confirm)" subsection and any other mentions of the advisor, `sensor.changeover_balance`, duty/mean sensors, and `changeover.jinja`.

- [ ] **Step 4: Update tracked-files, conventions, and HACS lists**

- In the "Tracked" list, replace `custom_templates/setpoint.jinja` and `custom_templates/changeover.jinja` with `custom_templates/hvac.jinja`.
- In the per-room entity-name conventions, replace `<room>_preferred_temperature` / `<room>_temp_range` with `<room>_heat_bound` / `<room>_cool_bound` / `<room>_temp_differential`.
- In the helpers-migration note, update the helper list to the new set (bounds, differentials, `hvac_enable`, `system_hvac_mode`, `mode_min_dwell`, `<room>_head_lockout`).
- Add to the HACS list: **Climate Template** custom integration (template climate platform `climate_template`) → provides `climate.office_thermostat` / `climate.studio_thermostat` for the ecobee-style thermostat card.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "Update CLAUDE.md for ecobee-style coordinator; drop changeover advisor docs"
```

- [ ] **Step 6: Update memory (housekeeping)**

- Delete `memory/project_setpoint_macro_intent.md` (the setpoint macro no longer exists) and its `MEMORY.md` line.
- Update `memory/project_changeover_advisor_status.md` (and its `MEMORY.md` line) to record that the advisor was removed and replaced by the two-setpoint coordinator on this branch.

---

## Deployment checklist (after merge, on the HA host)

1. Install the HACS **Climate Template** integration.
2. In the HA UI, **add** the new helpers (bounds, differentials, `hvac_enable`, `system_hvac_mode`, the three timers) and **delete** the obsolete ones (`<room>_preferred_temperature`, `<room>_temp_range`, the three `changeover_*`, `heat_pump_mode`, `timer.changeover_hold`) — or perform the `helpers.yaml` `!include` migration described at the top of `helpers.yaml`.
3. Sync the repo files to the host.
4. Reload Template, Input Number/Boolean/Select, Timer, and Automations (or restart HA).
5. Seed bound defaults (office 20/24, studio 20/23; office differential 1.0, studio 0.5; `hvac_enable` on) and tune live.
6. Add the two Thermostat cards and verify the dial behavior.

---

## Self-review notes

- **Spec coverage:** two-setpoint model (Task 1, 5), heating-wins conflict (Task 1 `resolve_mode`, Task 5 test), short-cycle protection — differential (Task 1), lockout (Task 4 timers, Task 5 logic + test), dwell (Task 4, Task 5 logic + test), inverter lead (Task 1 `head_target`); master enable (Task 4, 5); backup heat heads-off + retarget (Task 5 safety branch, Task 6); ecobee tile (Task 8); advisor removal (Task 2); old steering removal (Task 3); helper churn (Task 4, 7); docs/memory (Task 9). All spec sections map to a task.
- **Anti-flap correctness:** `effective = stored` while the dwell runs and `stored` is an active mode — the mode is never relabeled to `idle` mid-dwell, closing the idle-hop bypass (Task 5 var `effective`; `test_dwell_pins_mode_blocks_reverse`).
- **Type consistency:** macros return strings (`heat`/`cool`/`none`/`idle`); the coordinator compares them as strings and wraps `head_target` output with `| float(0)` before numeric comparison against `current_*_target` (also `| float(0)`). Booleans (`office_want_on`, etc.) are HA-native bools in `variables:`, matching the old controllers' pattern.
