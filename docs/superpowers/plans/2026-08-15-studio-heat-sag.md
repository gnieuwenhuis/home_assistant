# Studio Heat Sag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the studio head from being starved by a contaminated temperature sensor and by setpoint quantization, so the configured heating lead reaches the hardware and heat cycles are not cut short by the dehumidifier.

**Architecture:** Three independent defects, three isolated fixes. (1) `head_target` snaps its result onto the head's whole-degree-Fahrenheit grid, so a commanded 20.5 °C lands on 69 °F instead of truncating to 68 °F. (2) The coordinator's re-command gate compares whole-°F integers instead of Celsius, so it settles instead of firing on every run. (3) A new `sensor.studio_control_temperature` — a trigger-based template sensor driven by a pure, unit-tested Schmitt-trigger slew filter — becomes the studio's control input, rejecting the dehumidifier's exhaust plume. `studio_heat_lead` stays at 1.5; retuning happens in Phase 2 against clean data.

**Tech Stack:** Home Assistant 2026.8.2 YAML (`automations.yaml`, `configuration.yaml`) + Jinja macros in `custom_templates/hvac.jinja`; pytest via `pytest-homeassistant-custom-component` (run with `.venv/bin/pytest`).

**Spec:** `docs/superpowers/specs/2026-08-15-studio-heat-sag-design.md`

## Global Constraints

- Python ≥ 3.14; run tests with `.venv/bin/pytest` (env setup per CLAUDE.md "Tests").
- Per-room entity naming `<domain>.<room>_<thing>`. The new sensor is `sensor.studio_control_temperature`.
- `studio_heat_lead` stays **1.5** and `office_heat_lead` stays **0** in this plan. Retuning is Phase 2 (Task 7), after one clean night.
- The office keeps `sensor.office_baseboard_current_temperature` as its control input. Only the studio gets a filter — only the studio has a dehumidifier beside its thermostat.
- Filter constants: **reject 1.0 °C**, **re-enter 0.5 °C**, **max hold 20 minutes**.
- The head's grid is whole degrees **Fahrenheit**, and the head **truncates** toward zero. HA reports the value back rounded to one decimal. Commanded and reported °C spellings may legitimately differ (17.3 sent, 17.2 shown) while naming the same step.
- Comments follow `.claude/rules/code-comments.md` — timeless present, no change narrative ("Mutex serializes access", never "Added mutex to fix race").
- Never deploy from an agent session. `main` is the only path to the box (CLAUDE.md "Deployment"). Merging is the user's call.
- No `climate.*` / `switch.*` / `POST /api/services/*` call without asking the user first, every time.

---

### Task 1: Snap commanded setpoints onto the head's Fahrenheit grid

**Files:**
- Modify: `custom_templates/hvac.jinja` (add `snap_to_head_grid`; wrap `head_target`'s two outputs, lines 29–41)
- Modify: `tests/test_hvac_macros.py` (`IMPORTS` line 4; the `head_target` assertions, lines 64–82; add new tests)
- Modify: `tests/test_hvac_coordinator.py` (assertions at lines ~123, ~194, ~209, ~210, ~225)

**Interfaces:**
- Produces: `snap_to_head_grid(celsius)` → the °C string to command so the head lands on the nearest whole °F step. `head_target(mode, heat_bound, cool_bound, lead)` keeps its signature and clamp but now returns a snapped value.

- [ ] **Step 1: Write the failing macro tests**

Add to `tests/test_hvac_macros.py`. Change line 4 to import the new macro:

```python
IMPORTS = ("{% from 'hvac.jinja' import room_demand, resolve_mode, head_target, "
           "snap_to_head_grid %}")
```

Then append:

```python
# --- snap_to_head_grid: the head's grid is whole degrees Fahrenheit ---------

async def test_snap_lands_on_a_whole_fahrenheit_step(hass_repo):
    # 20.5 C is 68.9 F; the nearest step is 69 F = 20.5556 C.
    assert call(hass_repo, "{{ snap_to_head_grid(20.5) }}") == 20.6


async def test_snap_rounds_celsius_up_so_truncation_lands_right(hass_repo):
    # 63 F is 17.2222 C. Sending 17.2 gives 62.96 F, which truncates one step
    # low, so the commanded spelling rounds up.
    assert call(hass_repo, "{{ snap_to_head_grid(17.0) }}") == 17.3


async def test_snap_is_identity_on_an_exact_step(hass_repo):
    assert call(hass_repo, "{{ snap_to_head_grid(20.0) }}") == 20.0


async def test_snap_never_escapes_the_upper_clamp(hass_repo):
    # 30 C is exactly 86 F, so nothing above the clamp can be produced.
    assert call(hass_repo, "{{ snap_to_head_grid(29.8) }}") == 30.0
```

And replace the four `head_target` assertions at lines 64–77 with their snapped values:

```python
async def test_head_target_heat_is_bound_plus_lead(hass_repo):
    # 22 C is 71.6 F; nearest step 72 F = 22.3 C commanded.
    assert call(hass_repo, "{{ head_target('heat', 20, 24, 2) }}") == 22.3


async def test_head_target_cool_is_bound_minus_lead(hass_repo):
    assert call(hass_repo, "{{ head_target('cool', 20, 24, 2) }}") == 22.3


async def test_head_target_clamps_high(hass_repo):
    assert call(hass_repo, "{{ head_target('heat', 29, 33, 2) }}") == 30


async def test_head_target_clamps_low(hass_repo):
    # Clamps to 17, then snaps to 63 F = 17.3 C commanded.
    assert call(hass_repo, "{{ head_target('cool', 16, 17, 2) }}") == 17.3
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_hvac_macros.py -v`
Expected: FAIL — the four new `snap_to_head_grid` tests error with `'snap_to_head_grid' is undefined`, and the four changed `head_target` tests fail comparing `22 != 22.3`, `17 != 17.3`.

- [ ] **Step 3: Add the macro and wrap head_target**

In `custom_templates/hvac.jinja`, insert before the `head_target` block:

```jinja
{# snap_to_head_grid: the °C value to command so the head lands on the nearest
   whole degree Fahrenheit. The head's grid is whole °F and it truncates, so the
   °C spelling rounds up — 63 °F is 17.2222 °C, and sending 17.2 gives 62.96 °F,
   one step low. #}
{% macro snap_to_head_grid(celsius) -%}
  {%- set f = (celsius | float * 9 / 5 + 32) | round(0) -%}
  {{- ((f - 32) * 5 / 9) | round(1, 'ceil') -}}
{%- endmacro %}
```

Then replace the two output lines inside `head_target` (currently lines 37 and 39):

```jinja
{% macro head_target(mode, heat_bound, cool_bound, lead) -%}
  {%- set l = lead | float -%}
  {%- if mode == 'heat' -%}
    {{- snap_to_head_grid([17, [30, (heat_bound | float + l)] | min] | max) -}}
  {%- elif mode == 'cool' -%}
    {{- snap_to_head_grid([17, [30, (cool_bound | float - l)] | min] | max) -}}
  {%- endif -%}
{%- endmacro %}
```

Update the `head_target` docstring comment (lines 29–33) to:

```jinja
{# head_target: the temperature to command a head, a small `lead` past the
   active bound so the inverter stays committed (the coordinator does the real
   cutoff against the reliable room sensor). Clamped to [17, 30], then snapped
   onto the head's whole-degree-Fahrenheit grid. Empty for a non-active mode. #}
```

- [ ] **Step 4: Run the macro tests to verify they pass**

Run: `.venv/bin/pytest tests/test_hvac_macros.py -v`
Expected: PASS, all tests.

- [ ] **Step 5: Update the coordinator test assertions**

Snapping changes what the coordinator commands. In `tests/test_hvac_coordinator.py` (`DEFAULTS` uses `heat_bound 20`, `office_cool_bound 24`, `studio_cool_bound 23`):

- line ~123: `== 21.5` → `== 21.7` and comment `# studio 20 + lead 1.5 = 21.5 -> 71 F = 21.7`
- line ~194: `== 21.5` → `== 21.7` and the same comment
- line ~209: `== 24` → `== 23.9` and comment `# cool_bound 24 -> 75 F = 23.9, no lead`
- line ~210: `== 23` → `== 22.8` and comment `# cool_bound 23 -> 73 F = 22.8, no lead`
- line ~225: `== 21.5` → `== 21.7` and the same comment as line 123

Line ~224 (`office_heat[0].data["temperature"] == 20`) stays — 20 °C is exactly 68 °F.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest`
Expected: PASS. If `tests/test_configuration_yaml.py` fails, the clamp floor constant is unrelated to snapping — re-read the failure before changing anything.

- [ ] **Step 7: Commit**

```bash
git add custom_templates/hvac.jinja tests/test_hvac_macros.py tests/test_hvac_coordinator.py
git commit -m "Snap commanded head setpoints onto the whole-Fahrenheit grid"
```

---

### Task 2: Compare the re-command gate on the device grid

**Files:**
- Modify: `custom_templates/hvac.jinja` (add `command_step` and `report_step`)
- Modify: `automations.yaml` (four new `variables:` after `current_studio_target`, line ~123; the two already-on `conditions:` at lines ~188–191 and ~225–228)
- Modify: `tests/test_hvac_macros.py` (`IMPORTS`; new tests)
- Modify: `tests/test_hvac_coordinator.py` (new test)

**Interfaces:**
- Consumes: `head_target(...)` from Task 1, now snapped.
- Produces: `command_step(celsius)` → int °F the head will truncate a command to. `report_step(celsius)` → int °F behind a value HA reports back. Coordinator variables `office_target_step`, `studio_target_step`, `office_device_step`, `studio_device_step`.

- [ ] **Step 1: Write the failing macro tests**

Extend `IMPORTS` in `tests/test_hvac_macros.py`:

```python
IMPORTS = ("{% from 'hvac.jinja' import room_demand, resolve_mode, head_target, "
           "snap_to_head_grid, command_step, report_step %}")
```

Append:

```python
# --- command_step / report_step: the same physical step from both sides -----

async def test_command_step_truncates_like_the_head(hass_repo):
    # 20.5 C is 68.9 F; the head truncates to 68 F.
    assert call(hass_repo, "{{ command_step(20.5) }}") == 68


async def test_report_step_recovers_the_step_behind_a_reading(hass_repo):
    # HA shows 20.6 for a head sitting on 69 F.
    assert call(hass_repo, "{{ report_step(20.6) }}") == 69


async def test_snapped_command_and_its_reading_agree(hass_repo):
    # The gate settles only if both sides name the same step. 17.3 is sent,
    # 17.2 is displayed, and both are 63 F.
    assert call(hass_repo, "{{ command_step(17.3) }}") == 63
    assert call(hass_repo, "{{ report_step(17.2) }}") == 63


async def test_a_bound_change_across_a_step_still_differs(hass_repo):
    # 21.7 C (71 F) against a head resting on 69 F must not compare equal.
    assert call(hass_repo, "{{ command_step(21.7) }}") == 71
    assert call(hass_repo, "{{ report_step(20.6) }}") == 69
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_hvac_macros.py -k "step" -v`
Expected: FAIL with `'command_step' is undefined`.

- [ ] **Step 3: Add the two macros**

Append to `custom_templates/hvac.jinja`:

```jinja
{# command_step / report_step: the whole-degree-Fahrenheit step behind a °C
   value, from each side of the head. The head truncates what it is commanded;
   HA rounds what it reports back. A commanded 17.3 and a reported 17.2 are the
   same 63 °F step, so a re-command gate compares steps, never Celsius. #}
{% macro command_step(celsius) -%}
  {{- (celsius | float * 9 / 5 + 32) | round(0, 'floor') | int -}}
{%- endmacro %}

{% macro report_step(celsius) -%}
  {{- (celsius | float * 9 / 5 + 32) | round(0) | int -}}
{%- endmacro %}
```

- [ ] **Step 4: Run the macro tests to verify they pass**

Run: `.venv/bin/pytest tests/test_hvac_macros.py -k "step" -v`
Expected: PASS.

- [ ] **Step 5: Write the failing coordinator test**

Append to `tests/test_hvac_coordinator.py`:

```python
async def test_no_resend_when_head_already_on_target_step(coordinator):
    hass, calls = coordinator
    # Studio wants heat and the head already sits on the commanded step:
    # 20 + 1.5 = 21.5 C snaps to 71 F, which HA reports back as 21.7.
    await arrange(hass, office_temp=22, studio_temp=18, stored="heat",
                  studio_switch="on", studio_climate="heat")
    hass.states.async_set("climate.studio", "heat", {"temperature": 21.7})
    await hass.async_block_till_done()
    await run(hass)
    studio_temp_calls = [c for c in calls["temp"] if "climate.studio" in _entities(c)]
    assert not studio_temp_calls, (
        f"head already on 71 F, expected no re-command, got {studio_temp_calls}"
    )


async def test_no_resend_when_reported_spelling_differs_from_commanded(coordinator):
    hass, calls = coordinator
    # heat_bound 17 + lead 1.5 = 18.5 C, which snaps to 65 F. The commanded
    # spelling is 18.4 and HA displays 18.3 — the same step, so no re-command.
    await arrange(hass, office_temp=22, studio_temp=15, stored="heat",
                  studio_switch="on", studio_climate="heat")
    await hass.services.async_call(
        "input_number", "set_value",
        {"entity_id": "input_number.studio_heat_bound", "value": 17},
        blocking=True,
    )
    hass.states.async_set("climate.studio", "heat", {"temperature": 18.3})
    await hass.async_block_till_done()
    await run(hass)
    studio_temp_calls = [c for c in calls["temp"] if "climate.studio" in _entities(c)]
    assert not studio_temp_calls, (
        f"18.4 commanded and 18.3 reported are both 65 F, got {studio_temp_calls}"
    )
```

The second test is the one that must fail before the fix — `18.3 != 18.4` in
Celsius. The first passes already under Task 1 (exact Celsius equality happens to
hold at 21.7) and stands as a regression guard.

- [ ] **Step 6: Run the coordinator tests to verify they fail**

Run: `.venv/bin/pytest tests/test_hvac_coordinator.py -k "no_resend" -v`
Expected: FAIL — a `climate.set_temperature` call is recorded, because the gate still compares Celsius (`21.7 != 21.7` is false, but `current_studio_target` is read via `| float(0)` and compared against `studio_target`, which for the second test differ as `17.2 != 17.3`).

If the first test passes already, that is expected — exact Celsius equality happens to hold there. The second test is the one that must fail.

- [ ] **Step 7: Add the coordinator variables**

In `automations.yaml`, insert immediately after `current_studio_target` (line ~123) and before `safe_mode`:

```yaml
    # The head truncates a command to a whole degree Fahrenheit and HA rounds
    # what it reports back, so a commanded 17.3 returns as 17.2. Comparing the
    # step each side names is the only comparison that settles.
    office_target_step: >-
      {% from 'hvac.jinja' import command_step %}
      {{- command_step(office_target) -}}
    studio_target_step: >-
      {% from 'hvac.jinja' import command_step %}
      {{- command_step(studio_target) -}}
    office_device_step: >-
      {% from 'hvac.jinja' import report_step %}
      {{- report_step(current_office_target) -}}
    studio_device_step: >-
      {% from 'hvac.jinja' import report_step %}
      {{- report_step(current_studio_target) -}}
```

- [ ] **Step 8: Switch both gates to the step comparison**

Replace the office already-on condition (lines ~188–191):

```yaml
    - conditions: >-
        {{ office_want_on and office_switch_on
           and (current_office_hvac != desired_hvac
                or office_target_step | int(0) != office_device_step | int(0)) }}
```

And the studio's (lines ~225–228):

```yaml
    - conditions: >-
        {{ studio_want_on and studio_switch_on
           and (current_studio_hvac != desired_hvac
                or studio_target_step | int(0) != studio_device_step | int(0)) }}
```

- [ ] **Step 9: Run the full suite**

Run: `.venv/bin/pytest`
Expected: PASS, including `test_drift_resends_target_without_toggle` — that test pins `climate.studio` to 19 (66 °F) against a commanded 21.7 (71 °F), so the gate still fires.

- [ ] **Step 10: Commit**

```bash
git add custom_templates/hvac.jinja automations.yaml tests/test_hvac_macros.py tests/test_hvac_coordinator.py
git commit -m "Compare the head re-command gate on the Fahrenheit step"
```

---

### Task 3: The slew filter macro

**Files:**
- Modify: `custom_templates/hvac.jinja` (add `slew_filter`)
- Create: `tests/test_slew_filter.py`

**Interfaces:**
- Produces: `slew_filter(raw, last_good, hold_since, now_iso, reject, reenter, max_hold)` → a JSON string `{"value": "<°C or 'unavailable'>", "hold_since": "<ISO8601 or ''>"}`. Consumed by Task 4's template sensor via `| from_json`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_slew_filter.py`:

```python
"""Level 2 tests: the studio slew filter macro (pure function)."""
import json

from tests.util import render

IMPORTS = "{% from 'hvac.jinja' import slew_filter %}"

NOW = "2026-08-15T11:04:12+00:00"
REJECT, REENTER, MAX_HOLD = 1.0, 0.5, 20


def filt(hass, raw, last_good, hold_since, now=NOW):
    out = render(hass, IMPORTS + (
        "{{ slew_filter('%s', '%s', '%s', '%s', %s, %s, %s) }}"
        % (raw, last_good, hold_since, now, REJECT, REENTER, MAX_HOLD)
    ))
    return json.loads(out) if isinstance(out, str) else out


async def test_seeds_from_the_first_reading(hass_repo):
    assert filt(hass_repo, 19.4, "unknown", "")["value"] == "19.4"


async def test_accepts_a_plausible_change(hass_repo):
    # Measured genuine slew in this room peaks near 0.7 C per reporting interval.
    got = filt(hass_repo, 19.6, 19.0, "")
    assert got["value"] == "19.6"
    assert got["hold_since"] == ""


async def test_rejects_the_exhaust_spike_and_starts_a_hold(hass_repo):
    # The measured 11:04 event: 19.4 accepted, then a 21.6 plume reading.
    got = filt(hass_repo, 21.6, 19.4, "")
    assert got["value"] == "19.4"
    assert got["hold_since"] == NOW


async def test_rejects_the_decaying_tail_via_the_reenter_band(hass_repo):
    # 20.0 is 0.6 from the held 19.4 — inside the 1.0 reject band but outside
    # the 0.5 re-entry band, so a plain threshold would wrongly accept it.
    got = filt(hass_repo, 20.0, 19.4, "2026-08-15T10:52:00+00:00")
    assert got["value"] == "19.4"


async def test_reaccepts_once_the_reading_returns(hass_repo):
    got = filt(hass_repo, 19.5, 19.4, "2026-08-15T10:52:00+00:00")
    assert got["value"] == "19.5"
    assert got["hold_since"] == ""


async def test_resyncs_after_the_max_hold(hass_repo):
    # A hold this long is a real shift, not a plume.
    got = filt(hass_repo, 22.0, 19.4, "2026-08-15T10:40:00+00:00")
    assert got["value"] == "22.0"
    assert got["hold_since"] == ""


async def test_holds_through_a_source_dropout(hass_repo):
    got = filt(hass_repo, "unavailable", 19.4, "")
    assert got["value"] == "19.4"
    assert got["hold_since"] == NOW


async def test_goes_unavailable_when_a_dropout_outlasts_the_hold(hass_repo):
    got = filt(hass_repo, "unavailable", 19.4, "2026-08-15T10:40:00+00:00")
    assert got["value"] == "unavailable"


async def test_unavailable_with_no_history_is_unavailable(hass_repo):
    assert filt(hass_repo, "unavailable", "unknown", "")["value"] == "unavailable"
```

`test_rejects_the_decaying_tail_via_the_reenter_band` is the load-bearing case:
20.0 is 0.6 from the held 19.4, inside the 1.0 reject band but outside the 0.5
re-entry band, so a plain threshold filter would wrongly accept it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_slew_filter.py -v`
Expected: FAIL with `'slew_filter' is undefined`.

- [ ] **Step 3: Add the macro**

Append to `custom_templates/hvac.jinja`:

```jinja
{# slew_filter: a Schmitt-trigger slew filter for a room sensor sitting in a
   heat source's exhaust path. A reading further than `reject` from the last
   accepted value starts a hold; while holding, a reading must come back within
   the tighter `reenter` band to be accepted, which is what rejects the decaying
   tail of a plume. A hold lasting `max_hold` minutes is a real shift rather
   than a plume, and resyncs. A non-numeric source rides out the same hold.
   Returns JSON: {"value": "<°C or 'unavailable'>", "hold_since": "<ISO or ''>"}.
   #}
{% macro slew_filter(raw, last_good, hold_since, now_iso, reject, reenter, max_hold) -%}
  {%- set hs = (hold_since | default('', true)) | string -%}
  {%- set holding = hs | length > 0 and hs != 'None' -%}
  {%- set held = ((now_iso | as_datetime - hs | as_datetime).total_seconds() / 60)
                 if holding else 0 -%}
  {%- set expired = holding and held >= (max_hold | float) -%}
  {%- set have_history = last_good | is_number -%}
  {%- set have_reading = raw | is_number -%}
  {%- set started = hs if holding else now_iso -%}
  {%- if have_history and have_reading and not expired -%}
    {%- set band = (reenter | float) if holding else (reject | float) -%}
    {%- if ((raw | float) - (last_good | float)) | abs > band -%}
      {"value": "{{ last_good | float }}", "hold_since": "{{ started }}"}
    {%- else -%}
      {"value": "{{ raw | float }}", "hold_since": ""}
    {%- endif -%}
  {%- elif have_history and not have_reading and not expired -%}
    {"value": "{{ last_good | float }}", "hold_since": "{{ started }}"}
  {%- elif have_reading -%}
    {"value": "{{ raw | float }}", "hold_since": ""}
  {%- else -%}
    {"value": "unavailable", "hold_since": ""}
  {%- endif -%}
{%- endmacro %}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_slew_filter.py -v`
Expected: PASS, all nine tests.

If a value assertion fails on formatting (`"19.4"` vs `"19.40"`), the cause is `| float` rendering — read the actual output before adjusting either side.

- [ ] **Step 5: Run the full suite**

Run: `.venv/bin/pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add custom_templates/hvac.jinja tests/test_slew_filter.py
git commit -m "Add a Schmitt-trigger slew filter for exhaust-contaminated room sensors"
```

---

### Task 4: The studio control temperature sensor

**Files:**
- Modify: `configuration.yaml` (new trigger block under `template:`, after the existing `- sensor:` block ending around line 80; the studio facade's `current_temperature_template`, line 145)
- Modify: `automations.yaml` (coordinator trigger `entity_id` list line ~35; `studio_temp` variable line ~78; the studio availability condition line ~127)
- Modify: `tests/test_hvac_coordinator.py` (`arrange()` line 73)

**Interfaces:**
- Consumes: `slew_filter(...)` from Task 3.
- Produces: `sensor.studio_control_temperature`, carrying attribute `hold_since`. Replaces `sensor.studio_baseboard_current_temperature` as the studio's control input. The raw sensor stays — it still feeds this filter.

- [ ] **Step 1: Add the trigger-based template sensor**

In `configuration.yaml`, append a second list item to the `template:` block (a sibling of the existing `- sensor:` at line 31):

```yaml
  # The studio thermostat sits in the dehumidifier's exhaust path, which lifts it
  # up to 3 °C above the room for ~15 minutes and reads as a satisfied room. The
  # filter holds the last plausible value across the plume. The time_pattern
  # trigger is what expires a hold when the source stops changing.
  - trigger:
      - trigger: state
        entity_id: sensor.studio_baseboard_current_temperature
      - trigger: homeassistant
        event: start
      - trigger: time_pattern
        minutes: /5
    sensor:
      - name: "Studio control temperature"
        unique_id: sensor.studio_control_temperature
        unit_of_measurement: "°C"
        device_class: temperature
        state_class: measurement
        state: >-
          {% from 'hvac.jinja' import slew_filter %}
          {{- (slew_filter(
                 states('sensor.studio_baseboard_current_temperature'),
                 this.state,
                 this.attributes.get('hold_since', ''),
                 now().isoformat(), 1.0, 0.5, 20) | from_json).value -}}
        attributes:
          hold_since: >-
            {% from 'hvac.jinja' import slew_filter %}
            {{- (slew_filter(
                   states('sensor.studio_baseboard_current_temperature'),
                   this.state,
                   this.attributes.get('hold_since', ''),
                   now().isoformat(), 1.0, 0.5, 20) | from_json).hold_since -}}
```

Both templates render against the same pre-update `this`, so the two calls agree.

- [ ] **Step 2: Run the config test to verify the block loads**

Run: `.venv/bin/pytest tests/test_configuration_yaml.py -v`
Expected: PASS. `test_template_entities_are_created` counts `sensor` keys across every block including this one, so the count rises by one and the new entity must exist after setup.

If it fails with `Invalid config for 'template'`, the whole block is dropped — read the logged validation error, do not guess at the schema.

- [ ] **Step 3: Point the coordinator at the filtered sensor**

Three edits in `automations.yaml`:

Trigger list (line ~35): `- sensor.studio_baseboard_current_temperature` → `- sensor.studio_control_temperature`

Variable (line ~78):

```yaml
    studio_temp: "{{ states('sensor.studio_control_temperature') | float(0) }}"
```

Availability condition (line ~127):

```yaml
  - "{{ states('sensor.studio_control_temperature') not in ['unavailable', 'unknown'] }}"
```

- [ ] **Step 4: Point the studio thermostat tile at the filtered sensor**

`configuration.yaml` line 145 — the tile shows what the coordinator acts on:

```yaml
    current_temperature_template: "{{ states('sensor.studio_control_temperature') }}"
```

- [ ] **Step 5: Update the coordinator test fixture**

`tests/test_hvac_coordinator.py` line 73:

```python
    hass.states.async_set("sensor.studio_control_temperature", studio_temp)
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/pytest`
Expected: PASS. Every coordinator test drives `studio_temp` through the new entity; the office is untouched.

- [ ] **Step 7: Commit**

```bash
git add configuration.yaml automations.yaml tests/test_hvac_coordinator.py
git commit -m "Drive studio HVAC demand from a slew-filtered control temperature"
```

---

### Task 5: Documentation

**Files:**
- Modify: `CLAUDE.md` (the `head_target` bullet and the coordinator's sensor references in "The ecobee-style HVAC coordinator"; the "Two rooms, two device pairs per room" dehumidifier paragraph)
- Modify: `README.md` (**Troubleshooting** section)

**Interfaces:** none — prose only.

- [ ] **Step 1: Update CLAUDE.md's coordinator section**

Extend the `head_target` bullet to state the grid, and add the filter. Replace the sensor name where the coordinator's input is described: the coordinator reads `sensor.studio_control_temperature` for the studio and `sensor.office_baseboard_current_temperature` for the office. Add, in the same bullet list:

```markdown
- Commanded setpoints are snapped onto the head's grid, which is **whole degrees
  Fahrenheit**, truncated. `head_target` returns a °C spelling that lands on the
  intended step (63 °F is 17.2222 °C, so it commands 17.3 — 17.2 would truncate
  one step low). HA reports the value back rounded, so the commanded and reported
  °C can differ while naming the same step: `command_step` / `report_step` are
  what the re-command gate compares, and comparing Celsius there never settles.
```

And under the short-cycle protection list, add:

```markdown
**Sensor filtering (studio only).** The studio baseboard thermostat sits in the
dehumidifier's exhaust path, which lifts it up to 3 °C above the room for ~15
minutes. `sensor.studio_control_temperature` — a trigger-based template sensor
over the `slew_filter` macro — is the coordinator's studio input, holding the
last plausible reading across a plume (reject 1.0 °C, re-enter 0.5 °C, resync
after 20 minutes). Its `hold_since` attribute is non-empty exactly while it is
holding. The office has no such source and reads its baseboard sensor directly.
```

- [ ] **Step 2: Update the dehumidifier hardware note in CLAUDE.md**

In "Two rooms, two device pairs per room", after the dehumidifier bullet, add:

```markdown
The dehumidifier's exhaust reaches the studio baseboard thermostat, so its runs
show up as 3 °C spikes on `sensor.studio_baseboard_current_temperature` while the
room is unchanged. That sensor is unfiltered and still correct for display;
control reads `sensor.studio_control_temperature`.
```

- [ ] **Step 3: Add the Troubleshooting entries in README.md**

Under **Troubleshooting**, add two entries matching the section's existing format:

```markdown
- **The studio thermostat card and the baseboard sensor disagree by a few
  degrees.** The dehumidifier is running or recently stopped. Its exhaust reaches
  the studio wall thermostat; the card shows the filtered value the coordinator
  acts on, which is the room. Check `hold_since` on
  `sensor.studio_control_temperature` — non-empty means a hold is active.
- **A head reports a target half a degree off what was commanded.** The heads run
  on a whole-degree-Fahrenheit grid. A commanded 17.3 °C is 63 °F and displays as
  17.2 °C. Both name the same step, and the coordinator compares steps, so this
  is not drift and produces no re-command.
```

- [ ] **Step 4: Run yamllint and the suite**

Run: `.venv/bin/pytest && .venv/bin/yamllint -c .yamllint.yml automations.yaml helpers.yaml configuration.yaml`
Expected: PASS both. If `yamllint` is absent from the venv, CI still runs it — install per `requirements-dev.txt`.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "Document the Fahrenheit setpoint grid and the studio sensor filter"
```

---

### Task 6: Keep the baseboard warmup setpoint in step with the bound (independent)

This task is unrelated to the sag and can be dropped without affecting Tasks 1–5.

`'1756874009383'` writes each baseboard to `heat_bound − 2.5` only on the
backup-heat exit edge. `studio_heat_bound` has since moved 20 → 19, so the studio
baseboard sits at 17.5 where the design intends 16.5. Harmless while the bound is
above it; a bound dropped below 17.5 would have the baseboard fighting the heat
pump.

**Files:**
- Modify: `automations.yaml` (new automation under the `# Backup heat` banner)
- Modify: `tests/test_automations_yaml.py` (structural assertion)

- [ ] **Step 1: Write the failing structural test**

Append to `tests/test_automations_yaml.py`. That file has no fixture — it loads
the YAML inline, and `yaml` and `REPO_ROOT` are already imported at its top:

```python
async def test_baseboard_standby_tracks_the_heat_bounds(hass_helpers):
    """The standby setpoint is derived from a bound, so a bound move re-writes it."""
    autos = yaml.safe_load((REPO_ROOT / "automations.yaml").read_text())
    chosen = [a for a in autos if a.get("id") == "baseboard_standby_setpoint"]
    assert len(chosen) == 1, "baseboard_standby_setpoint missing"
    triggered = set()
    for trig in chosen[0]["triggers"]:
        ent = trig.get("entity_id")
        triggered.update(ent if isinstance(ent, list) else [ent])
    assert "input_number.office_heat_bound" in triggered
    assert "input_number.studio_heat_bound" in triggered
```

`test_all_automations_load` in the same file already validates the new
automation against HA's schema, so no separate schema assertion is needed.

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_automations_yaml.py -k standby -v`
Expected: FAIL with `baseboard_standby_setpoint missing`.

- [ ] **Step 3: Add the automation**

Under the `# Backup heat` banner in `automations.yaml`, after `'1756874009383'`:

```yaml
- id: baseboard_standby_setpoint
  alias: Baseboard Standby Setpoint
  description: >-
    The standby baseboard setpoint is heat_bound - 2.5, which keeps the
    baseboard under the heat pump so the pump takes primary duty. It is derived
    from a bound the user can move at any time, so it is re-written whenever a
    bound moves. Backup heat owns the setpoint while it is on.
  triggers:
  - trigger: state
    entity_id:
    - input_number.office_heat_bound
    - input_number.studio_heat_bound
  conditions:
  - condition: state
    entity_id: input_boolean.backup_heat
    state: 'off'
  actions:
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
  mode: single
```

- [ ] **Step 4: Run the suite**

Run: `.venv/bin/pytest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add automations.yaml tests/test_automations_yaml.py
git commit -m "Re-derive the baseboard standby setpoint when a heat bound moves"
```

---

### Task 7: Phase 2 — observe, then retune (no code)

Runs after Tasks 1–5 are merged to `main` and the box has picked them up. Do not
start this in the same session.

- [ ] **Step 1: Confirm the box is running the new config**

```sh
set -a; . ./.env; set +a
curl -s -H "Authorization: Bearer $HOME_ASSISTANT_TOKEN" \
  http://homeassistant.local:8123/api/states/sensor.studio_control_temperature
```

Expected: a numeric state with a `hold_since` attribute. Absent means the Git
pull add-on has not polled yet, or HA rejected the config (CLAUDE.md
"Deployment").

- [ ] **Step 2: After one night, pull the three series**

```sh
set -a; . ./.env; set +a
curl -s -H "Authorization: Bearer $HOME_ASSISTANT_TOKEN" \
  "http://homeassistant.local:8123/api/history/period/<ISO8601>?end_time=<ISO8601>&filter_entity_id=sensor.studio_control_temperature,sensor.studio_baseboard_current_temperature,switch.studio_dehumidifier,switch.studio_power,climate.studio"
```

- [ ] **Step 3: Verify the filter did its job**

Check that each `switch.studio_dehumidifier` run shows a spike on the raw
baseboard sensor and **no** corresponding spike on
`sensor.studio_control_temperature`, and that no `switch.studio_power` turn-off
coincides with a dehumidifier run.

If a turn-off still coincides, the filter is not the whole story — return to
`superpowers:systematic-debugging` rather than raising the lead.

- [ ] **Step 4: Read the setpoint error the inverter actually sees**

For each `switch.studio_power` on-cycle, compare `climate.studio`'s onboard
`current_temperature` against its `temperature` (which, after Task 1, is exactly
what was commanded). The measured baseline is an onboard sensor running 2–4 °C
above the room, with the head delivering nothing until onboard drops below the
commanded target.

- [ ] **Step 5: Retune**

Raise `studio_heat_lead` in `automations.yaml` until the onboard reading sits
below the commanded target for the first half of each on-cycle. The
2026-06-22 design sanctions 2.0–2.5; the measured offset suggests 3.0 or higher.
Keep it a multiple of 0.5. The cutoff is `room_demand` against
`sensor.studio_control_temperature` at `heat_bound + differential` and is
independent of the lead, so the cost of raising it is inverter runtime, not
overshoot.

Update `tests/test_hvac_coordinator.py`'s three `21.7` assertions to the new
snapped value, and the `studio_heat_lead` comment in `automations.yaml`.

- [ ] **Step 6: Consider the deferred offset**

`number.studio_temperature_offset` (0 °F) would correct the head's onboard bias
at source and let the lead return to 0. Whether Cielo applies it to the control
loop or only to the reported value is unverified — probing it commands hardware,
so ask the user before writing it.
