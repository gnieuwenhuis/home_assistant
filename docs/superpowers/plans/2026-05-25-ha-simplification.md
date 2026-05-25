# Home Assistant Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply Package 2 of the simplification spec: collapse the office and studio HVAC controllers into event-driven, single-comparison automations; remove the now-redundant setpoint-sync and studio-only mode-switch automations; split humidity controllers into single-purpose ON/OFF automations; refresh stale docs.

**Architecture:** This is a YAML/markdown refactor of a live Home Assistant config, deployed by syncing files to the HA instance and reloading the relevant domains. There is no test framework; verification is empirical — validate YAML, reload, observe behavior in Developer Tools → States and the Cielo Home activity log. Each task is one self-contained commit so any individual change can be reverted without affecting the rest.

**Tech Stack:** Home Assistant YAML (automations, templates), Jinja2 (the setpoint macro), HACS integrations `cielo_home` (heat pumps) and `neviweb130` (baseboard heaters).

**Reference spec:** `docs/superpowers/specs/2026-05-25-ha-simplification-design.md`

**Deployment note (read before starting):**
- Each task's "Deploy" step assumes you have your own established workflow for syncing the file from this repo to the HA host (rsync, samba mount, git pull on host, etc.). Use whatever you use today.
- After syncing, "Reload" steps walk you through the HA UI action that applies the change.
- "Verify" steps tell you what to look for in HA's Developer Tools → States, Developer Tools → Logs, or the Cielo Home activity feed.
- If a verify step fails, stop and investigate. Each task ends with a commit so a `git revert <hash>` on the previous successful state is a clean rollback.

---

## Task 1: Add humidity threshold template sensors

**Why first:** Task 4's new humidity automations reference `sensor.humidity_high_threshold` and `sensor.humidity_low_threshold`. These must exist before those automations are deployed.

**Files:**
- Modify: `configuration.yaml` (insert into the existing `template: - sensor:` block, after the existing studio setpoint sensor at ~line 86)

- [ ] **Step 1: Edit `configuration.yaml`**

Open `/Users/gregn/Documents/office/configuration.yaml`. Find the last item in the `template: - sensor:` block (the "Studio Heat Pump Setpoint Temperature" entry, currently lines 76–86). Append two new sensors immediately after it, keeping the same indentation (6 spaces before the `-`):

```yaml
      - name: "Humidity High Threshold"
        unique_id: sensor.humidity_high_threshold
        unit_of_measurement: "%"
        device_class: humidity
        state_class: measurement
        state: >-
          {{ states('input_number.humidity_set_point') | float
             + states('input_number.humidity_tolerance') | float }}
      - name: "Humidity Low Threshold"
        unique_id: sensor.humidity_low_threshold
        unit_of_measurement: "%"
        device_class: humidity
        state_class: measurement
        state: >-
          {{ states('input_number.humidity_set_point') | float
             - states('input_number.humidity_tolerance') | float }}
```

- [ ] **Step 2: Validate YAML locally**

Run:
```bash
python3 -c "import yaml; yaml.safe_load(open('/Users/gregn/Documents/office/configuration.yaml'))"
```
Expected: no output (success). If you get a `yaml.YAMLError`, fix the indentation and retry.

- [ ] **Step 3: Deploy `configuration.yaml` to the HA host**

Sync the file with your usual workflow (rsync / samba / git pull on host).

- [ ] **Step 4: Validate the live HA config**

In HA UI: **Developer Tools → YAML → Check Configuration**. Click "Check Configuration".
Expected: "Configuration valid!" If errors mention the new sensors, fix the YAML and re-sync.

- [ ] **Step 5: Reload the template integration**

In HA UI: **Developer Tools → YAML → Template Entities** → click "Reload".

- [ ] **Step 6: Verify both sensors exist with correct values**

In HA UI: **Developer Tools → States**. Filter by `sensor.humidity_`. You should see two new entities:
- `sensor.humidity_high_threshold` — value should equal `input_number.humidity_set_point + input_number.humidity_tolerance`
- `sensor.humidity_low_threshold` — value should equal `input_number.humidity_set_point − input_number.humidity_tolerance`

If either is `unavailable` or `unknown`, check Developer Tools → Logs for template errors.

- [ ] **Step 7: Commit**

```bash
cd /Users/gregn/Documents/office
git add configuration.yaml
git commit -m "Add humidity threshold template sensors

Provides sensor.humidity_high_threshold and sensor.humidity_low_threshold
for upcoming humidity automation rewrite. set_point ± tolerance computed
as template sensors so numeric_state triggers can reference them directly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Replace office HVAC controller

**Why before the studio:** Smaller blast radius. If the new event-driven pattern has a subtle bug, you find it on one room before applying it to both. The studio keeps using the old controller, sync, and the studio-only mode-switch automations until Task 3.

**What this task deletes:**
- `office_hvac_controller` (current lines 19–135) — replaced by the new version below
- `office_temperature_sync` (current lines 410–436) — subsumed by the "already on, drifted" branch of the new controller

**What this task adds:**
- New `office_hvac_controller` (event-driven, ~50 lines)

The two studio-only mode-switch automations (`'1765126659858'`, `'1765126778404'`) stay in place this task. They still drive the *studio* climate; the new office controller handles its own mode changes via its mode trigger.

**Files:**
- Modify: `automations.yaml` (delete lines 19–135 + 410–436; insert new controller in place of the old one)

- [ ] **Step 1: Delete the old office controller (lines 19–135)**

In `automations.yaml`, delete the entire `- id: office_hvac_controller` automation, from the line `- id: office_hvac_controller` through the closing `mode: single` and the blank line after it. After deletion, the file should jump from the HVAC controllers banner directly to `- id: studio_hvac_controller`.

- [ ] **Step 2: Insert the new office controller in the same spot**

Paste this in place (right after the HVAC controllers banner comment, before the studio controller):

```yaml
- id: office_hvac_controller
  alias: Office HVAC Controller
  description: >-
    Drive the office heat pump (switch + climate) toward preferred ± swing.
    Fires only when setpoint, mode, preferred, or swing change, plus a 5-min
    safety heartbeat. Every Cielo API call is gated on a desired-vs-current
    delta.
  triggers:
  - trigger: state
    entity_id:
    - sensor.office_heat_pump_setpoint_temperature
    - input_number.office_preferred_temperature
    - input_number.office_temp_range
  - trigger: state
    entity_id: input_select.heat_pump_mode
    for:
      minutes: 2
  - trigger: time_pattern
    minutes: /5
  variables:
    current_temp:   "{{ states('sensor.office_baseboard_current_temperature') | float(0) }}"
    preferred:      "{{ states('input_number.office_preferred_temperature')   | float(0) }}"
    swing:          "{{ states('input_number.office_temp_range')              | float(0) }}"
    mode:           "{{ states('input_select.heat_pump_mode') }}"
    setpoint:       "{{ states('sensor.office_heat_pump_setpoint_temperature') | float(0) }}"
    too_cold:       "{{ current_temp < (preferred - swing) }}"
    too_hot:        "{{ current_temp > (preferred + swing) }}"
    desired_on:     "{{ (mode == 'heating' and too_cold) or (mode == 'cooling' and too_hot) }}"
    desired_off:    "{{ (mode == 'heating' and too_hot)  or (mode == 'cooling' and too_cold) }}"
    desired_hvac:   "{{ 'heat' if mode == 'heating' else 'cool' }}"
    switch_is_on:   "{{ is_state('switch.office_power', 'on') }}"
    current_hvac:   "{{ states('climate.office') }}"
    current_target: "{{ state_attr('climate.office', 'temperature') | float(none) }}"
  conditions:
  - "{{ mode in ['heating', 'cooling'] }}"
  - "{{ states('sensor.office_baseboard_current_temperature') not in ['unavailable', 'unknown'] }}"
  - "{{ states('sensor.office_heat_pump_setpoint_temperature') not in ['unavailable', 'unknown'] }}"
  - "{{ states('switch.office_power') not in ['unavailable', 'unknown'] }}"
  - "{{ states('climate.office') not in ['unavailable', 'unknown'] }}"
  actions:
  - choose:
    # Was off, need on → turn on + set mode + target atomically
    - conditions: "{{ desired_on and not switch_is_on }}"
      sequence:
      - action: switch.turn_on
        target:
          entity_id: switch.office_power
      - action: climate.set_temperature
        target:
          entity_id: climate.office
        data:
          temperature: "{{ setpoint }}"
          hvac_mode: "{{ desired_hvac }}"
    # Already on, mode or target drifted (subsumes office_temperature_sync)
    - conditions: >-
        {{ desired_on and switch_is_on and
           (current_hvac != desired_hvac or current_target != setpoint) }}
      sequence:
      - action: climate.set_temperature
        target:
          entity_id: climate.office
        data:
          temperature: "{{ setpoint }}"
          hvac_mode: "{{ desired_hvac }}"
    # Overshooting wrong direction → off
    - conditions: "{{ desired_off and switch_is_on }}"
      sequence:
      - action: switch.turn_off
        target:
          entity_id: switch.office_power
  mode: single
```

- [ ] **Step 3: Delete the office temperature sync automation**

Find and delete the entire `- id: office_temperature_sync` automation (currently around lines 410–436 *before* the deletions above; the line numbers will have shifted). Delete from `- id: office_temperature_sync` through its `mode: single` line, plus the trailing blank line.

The setpoint-sync section banner (`# Setpoint sync`) and its multi-line header comment should remain — there's still `studio_temperature_sync` underneath it until Task 3.

- [ ] **Step 4: Validate YAML locally**

```bash
python3 -c "import yaml; yaml.safe_load(open('/Users/gregn/Documents/office/automations.yaml'))"
```
Expected: no output. If errors, re-check indentation (HA YAML uses two-space indent inside list items).

- [ ] **Step 5: Deploy `automations.yaml` to the HA host**

Sync the file.

- [ ] **Step 6: Validate live HA config**

**Developer Tools → YAML → Check Configuration** → "Check Configuration".
Expected: "Configuration valid!"

- [ ] **Step 7: Reload automations**

**Developer Tools → YAML → Automations** → "Reload".

- [ ] **Step 8: Verify new automation is loaded and old ones are gone**

In **Settings → Automations & Scenes**, confirm:
- `Office HVAC Controller` exists, shows "Last triggered" updating
- `Office Temperature Sync` no longer appears
- `Studio HVAC Controller` still appears (will be replaced next task)
- The two "Switch Heat Pump mode to ..." automations still appear (will go next task)

- [ ] **Step 9: Observe office heat pump for at least 30 minutes**

Watch the Cielo Home activity feed (or HA's logbook entries for `switch.office_power` and `climate.office`):
- Setpoint changes should propagate within seconds (faster than today's 30 s sync).
- Switch should turn on/off when the room crosses `preferred ± swing`.
- No more than ~1 climate write per minute on average during steady state.

If anything looks wrong, `git revert HEAD` to the previous commit, sync, reload, and stop here.

- [ ] **Step 10: Commit**

```bash
cd /Users/gregn/Documents/office
git add automations.yaml
git commit -m "Rewrite office HVAC controller as event-driven

Replaces time-pattern + per-action device guards with state-change
triggers + a single desired-vs-current comparison. Subsumes the
office_temperature_sync automation. Adds 5-min safety heartbeat.
Cielo dedupe preserved by gating every API call on a real delta.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Replace studio HVAC controller; remove mode-switch automations

**What this task deletes:**
- `studio_hvac_controller` (the old one)
- `studio_temperature_sync` (subsumed)
- `'1765126659858'` "Switch Heat Pump mode to Cooling" (subsumed by mode trigger on new studio controller)
- `'1765126778404'` "Switch Heat Pump mode to Heating" (ditto)
- The `# Mode switching` banner comment block (no automations remain in that section)
- The `# Setpoint sync` banner comment block (no automations remain)

**What this task adds:**
- New `studio_hvac_controller` (mirror of office, with `studio` everywhere)

After this task, `automations.yaml` has sections: `# HVAC controllers`, `# Backup heat`, `# Humidity`.

**Files:**
- Modify: `automations.yaml`

- [ ] **Step 1: Delete the old studio controller**

Find and delete the entire `- id: studio_hvac_controller` automation (the second large block under `# HVAC controllers`).

- [ ] **Step 2: Insert the new studio controller in the same spot**

```yaml
- id: studio_hvac_controller
  alias: Studio HVAC Controller
  description: >-
    Drive the studio heat pump (switch + climate) toward preferred ± swing.
    Fires only when setpoint, mode, preferred, or swing change, plus a 5-min
    safety heartbeat. Every Cielo API call is gated on a desired-vs-current
    delta.
  triggers:
  - trigger: state
    entity_id:
    - sensor.studio_heat_pump_setpoint_temperature
    - input_number.studio_preferred_temperature
    - input_number.studio_temp_range
  - trigger: state
    entity_id: input_select.heat_pump_mode
    for:
      minutes: 2
  - trigger: time_pattern
    minutes: /5
  variables:
    current_temp:   "{{ states('sensor.studio_baseboard_current_temperature') | float(0) }}"
    preferred:      "{{ states('input_number.studio_preferred_temperature')   | float(0) }}"
    swing:          "{{ states('input_number.studio_temp_range')              | float(0) }}"
    mode:           "{{ states('input_select.heat_pump_mode') }}"
    setpoint:       "{{ states('sensor.studio_heat_pump_setpoint_temperature') | float(0) }}"
    too_cold:       "{{ current_temp < (preferred - swing) }}"
    too_hot:        "{{ current_temp > (preferred + swing) }}"
    desired_on:     "{{ (mode == 'heating' and too_cold) or (mode == 'cooling' and too_hot) }}"
    desired_off:    "{{ (mode == 'heating' and too_hot)  or (mode == 'cooling' and too_cold) }}"
    desired_hvac:   "{{ 'heat' if mode == 'heating' else 'cool' }}"
    switch_is_on:   "{{ is_state('switch.studio_power', 'on') }}"
    current_hvac:   "{{ states('climate.studio') }}"
    current_target: "{{ state_attr('climate.studio', 'temperature') | float(none) }}"
  conditions:
  - "{{ mode in ['heating', 'cooling'] }}"
  - "{{ states('sensor.studio_baseboard_current_temperature') not in ['unavailable', 'unknown'] }}"
  - "{{ states('sensor.studio_heat_pump_setpoint_temperature') not in ['unavailable', 'unknown'] }}"
  - "{{ states('switch.studio_power') not in ['unavailable', 'unknown'] }}"
  - "{{ states('climate.studio') not in ['unavailable', 'unknown'] }}"
  actions:
  - choose:
    - conditions: "{{ desired_on and not switch_is_on }}"
      sequence:
      - action: switch.turn_on
        target:
          entity_id: switch.studio_power
      - action: climate.set_temperature
        target:
          entity_id: climate.studio
        data:
          temperature: "{{ setpoint }}"
          hvac_mode: "{{ desired_hvac }}"
    - conditions: >-
        {{ desired_on and switch_is_on and
           (current_hvac != desired_hvac or current_target != setpoint) }}
      sequence:
      - action: climate.set_temperature
        target:
          entity_id: climate.studio
        data:
          temperature: "{{ setpoint }}"
          hvac_mode: "{{ desired_hvac }}"
    - conditions: "{{ desired_off and switch_is_on }}"
      sequence:
      - action: switch.turn_off
        target:
          entity_id: switch.studio_power
  mode: single
```

- [ ] **Step 3: Delete the Mode switching section**

Delete the entire `# Mode switching` banner comment block and both mode-switch automations beneath it:
- The banner comment (lines starting with `# =====...`, `# Mode switching`, the explanation, and the closing `# =====...`)
- `- id: '1765126659858'` (Switch Heat Pump mode to Cooling)
- `- id: '1765126778404'` (Switch Heat Pump mode to Heating)

After deletion, the `# HVAC controllers` section flows directly into `# Backup heat`.

- [ ] **Step 4: Delete the Setpoint sync section**

Delete the entire `# Setpoint sync` banner comment block and the remaining `- id: studio_temperature_sync` automation beneath it.

After this step, the only remaining sections in `automations.yaml` are `# HVAC controllers`, `# Backup heat`, and `# Humidity`.

- [ ] **Step 5: Validate YAML locally**

```bash
python3 -c "import yaml; yaml.safe_load(open('/Users/gregn/Documents/office/automations.yaml'))"
```
Expected: no output.

- [ ] **Step 6: Deploy `automations.yaml` to the HA host**

Sync the file.

- [ ] **Step 7: Validate live HA config**

**Developer Tools → YAML → Check Configuration**. Expected: "Configuration valid!"

- [ ] **Step 8: Reload automations**

**Developer Tools → YAML → Automations** → "Reload".

- [ ] **Step 9: Verify automation list is correct**

In **Settings → Automations & Scenes**, confirm:
- `Office HVAC Controller` ✅
- `Studio HVAC Controller` ✅
- `Disable Heat Pump in Cold Weather` ✅ (backup heat, untouched)
- `Enable Heat pump in warm weather` ✅ (backup heat, untouched)
- `Dehumidifier Controller` ✅ (will be replaced in Task 4)
- `Humidifier Controller` ✅ (will be replaced in Task 4)
- `Switch Heat Pump mode to Cooling` ❌ (gone)
- `Switch Heat Pump mode to Heating` ❌ (gone)
- `Office Temperature Sync` ❌ (gone)
- `Studio Temperature Sync` ❌ (gone)

- [ ] **Step 10: Test mode-switch behavior**

In HA UI, change `input_select.heat_pump_mode` from its current value to the other (e.g., heating → cooling). Wait 2 minutes 10 seconds. Both heat pumps should react if either is in `desired_on` territory; otherwise their internal hvac_mode will update on the next time the controller fires. Watch Developer Tools → Logbook for `climate.office` and `climate.studio` entries.

Set the input_select back to its original value when done testing.

- [ ] **Step 11: Observe both heat pumps for at least 30 minutes**

Same as Task 2's Step 9, now for both rooms.

- [ ] **Step 12: Commit**

```bash
cd /Users/gregn/Documents/office
git add automations.yaml
git commit -m "Rewrite studio HVAC controller; drop sync and mode-switch sections

Studio controller now mirrors the office event-driven pattern. The two
studio-only mode-switch automations are subsumed by the controllers'
mode-change trigger (with 2-min debounce preserved). Setpoint sync
automations are subsumed by the 'already on, drifted' branch.

automations.yaml now contains only three sections: HVAC controllers,
Backup heat, and Humidity.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Rewrite humidity controllers as ON/OFF pairs

**What this task deletes:**
- `Dehumidifier Controller` automation
- `Humidifier Controller` automation

**What this task adds:**
- `dehumidifier_on`, `dehumidifier_off`, `humidifier_on`, `humidifier_off` — four single-purpose automations.

**Files:**
- Modify: `automations.yaml` (replace the contents of the `# Humidity` section)

- [ ] **Step 1: Delete both humidity controllers**

In the `# Humidity` section at the bottom of `automations.yaml`, delete:
- The entire `- id: '1765216181800'` automation (Dehumidifier Controller)
- The entire `- id: '1765216369307'` automation (Humidifier Controller)

Keep the `# Humidity` banner comment block.

- [ ] **Step 2: Insert the four new automations after the Humidity banner**

```yaml
- id: dehumidifier_on
  alias: Dehumidifier ON
  description: >-
    Turn the dehumidifier on when humidity rises above set_point + tolerance.
  triggers:
  - trigger: numeric_state
    entity_id: sensor.tz3000_utwgoauk_snzb_02_humidity
    above: sensor.humidity_high_threshold
  conditions:
  - condition: state
    entity_id: switch.mini_plug_4_socket_1
    state: "off"
  actions:
  - action: switch.turn_on
    target:
      entity_id: switch.mini_plug_4_socket_1
  mode: single

- id: dehumidifier_off
  alias: Dehumidifier OFF
  description: >-
    Turn the dehumidifier off when humidity falls below set_point.
  triggers:
  - trigger: numeric_state
    entity_id: sensor.tz3000_utwgoauk_snzb_02_humidity
    below: input_number.humidity_set_point
  conditions:
  - condition: state
    entity_id: switch.mini_plug_4_socket_1
    state: "on"
  actions:
  - action: switch.turn_off
    target:
      entity_id: switch.mini_plug_4_socket_1
  mode: single

- id: humidifier_on
  alias: Humidifier ON
  description: >-
    Turn the humidifier on when humidity falls below set_point - tolerance.
  triggers:
  - trigger: numeric_state
    entity_id: sensor.tz3000_utwgoauk_snzb_02_humidity
    below: sensor.humidity_low_threshold
  conditions:
  - condition: state
    entity_id: switch.studio_humidifier_socket_1
    state: "off"
  actions:
  - action: switch.turn_on
    target:
      entity_id: switch.studio_humidifier_socket_1
  mode: single

- id: humidifier_off
  alias: Humidifier OFF
  description: >-
    Turn the humidifier off when humidity rises above set_point.
  triggers:
  - trigger: numeric_state
    entity_id: sensor.tz3000_utwgoauk_snzb_02_humidity
    above: input_number.humidity_set_point
  conditions:
  - condition: state
    entity_id: switch.studio_humidifier_socket_1
    state: "on"
  actions:
  - action: switch.turn_off
    target:
      entity_id: switch.studio_humidifier_socket_1
  mode: single
```

- [ ] **Step 3: Validate YAML locally**

```bash
python3 -c "import yaml; yaml.safe_load(open('/Users/gregn/Documents/office/automations.yaml'))"
```
Expected: no output.

- [ ] **Step 4: Deploy `automations.yaml`**

Sync the file.

- [ ] **Step 5: Validate live HA config**

**Developer Tools → YAML → Check Configuration**. Expected: "Configuration valid!"

- [ ] **Step 6: Reload automations**

**Developer Tools → YAML → Automations** → "Reload".

- [ ] **Step 7: Verify automation list is correct**

In **Settings → Automations & Scenes**, confirm:
- `Dehumidifier ON`, `Dehumidifier OFF`, `Humidifier ON`, `Humidifier OFF` ✅
- `Dehumidifier Controller`, `Humidifier Controller` ❌ (gone)

- [ ] **Step 8: Verify hysteresis still works**

Read the current values of:
- `sensor.tz3000_utwgoauk_snzb_02_humidity`
- `sensor.humidity_high_threshold` (should be `set_point + tolerance`)
- `sensor.humidity_low_threshold` (should be `set_point − tolerance`)
- `switch.mini_plug_4_socket_1` (dehumidifier)
- `switch.studio_humidifier_socket_1` (humidifier)

Confirm:
- If humidity > high threshold: dehumidifier should be on (or turn on within the next sensor update).
- If humidity < low threshold: humidifier should be on.
- In the band: both switches stay in whatever state they were in.

If the humidity is already in steady state, no transition will be observed immediately — that's fine. The next natural humidity drift across a threshold will exercise the new automations.

- [ ] **Step 9: Commit**

```bash
cd /Users/gregn/Documents/office
git add automations.yaml
git commit -m "Split humidity controllers into single-purpose ON/OFF automations

Replaces two template-triggered controllers with four numeric_state-
triggered automations referencing the new threshold template sensors.
Hysteresis bands preserved exactly:
- Dehumidifier: on > set_point + tolerance, off < set_point
- Humidifier: on < set_point - tolerance, off > set_point

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Fix the setpoint macro header comment

**Files:**
- Modify: `custom_templates/setpoint.jinja` (lines 1–13, the docstring at the top of the file)

- [ ] **Step 1: Open `custom_templates/setpoint.jinja` and replace the header comment**

Replace the existing header (everything from line 1 through and including the blank line after line 13) with:

```jinja
{# Heat pump setpoint calculation for a single room.

   Args:
     thermostat       — climate entity providing the room's current_temperature
                        attribute (the baseboard heater's built-in thermometer)
     base_sensor      — secondary indoor temperature sensor that anchors the
                        steering; the setpoint is computed relative to this
                        reading so the heat pump is steered toward `preferred`
                        as the room's actual temperature diverges from
                        `base_sensor`'s reading
     preferred_input  — input_number with the desired indoor temperature

   Returns the computed setpoint clamped to [17, 30] °C, rounded toward the
   side that pushes the heat pump harder (up when the room is too cold, down
   when the room is too warm). Backup-heat mode collapses to base_temp - 1. #}

```

The macro body below (`{% macro heat_pump_setpoint(...) %}` onward) is unchanged.

- [ ] **Step 2: Validate Jinja syntactically (HA-side)**

In HA UI: **Developer Tools → Template**, paste:
```jinja
{% from 'setpoint.jinja' import heat_pump_setpoint %}
{{ heat_pump_setpoint('climate.neviweb130_climate_th1123wf', 'sensor.office_temperature', 'input_number.office_preferred_temperature') }}
```
Expected: a number between 17 and 30 (the current office setpoint). If you get a template error, the comment is malformed — review the `{# ... #}` markers.

- [ ] **Step 3: Deploy and verify the setpoint sensors are unchanged**

Sync `setpoint.jinja` to the HA host. In HA UI: **Developer Tools → YAML → Template Entities** → "Reload".

In **Developer Tools → States**, check `sensor.office_heat_pump_setpoint_temperature` and `sensor.studio_heat_pump_setpoint_temperature`. Both should still produce sensible integer values in the 17–30 range. (The algorithm wasn't changed; only the docstring was.)

- [ ] **Step 4: Commit**

```bash
cd /Users/gregn/Documents/office
git add custom_templates/setpoint.jinja
git commit -m "Fix stale setpoint macro docstring

base_sensor is an indoor reference, not 'outdoor / building reference'.
The algorithm has used an indoor anchor for some time; the docstring
hadn't been updated.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` — the "Architecture" section, specifically:
  - The "two-stage heat-pump control loop" subsection (which actually has three stages today)
  - The "Mode switching has a subtle asymmetry" subsection (delete entirely)
  - The thematic banner-comment list in the "Conventions" section

- [ ] **Step 1: Rewrite the heat-pump control loop subsection**

Find the subsection beginning with `### The two-stage heat-pump control loop`. Replace from that heading through (and not including) `### Mode switching has a subtle asymmetry` with:

```markdown
### The two-stage heat-pump control loop

The heat pump's target temperature isn't the user's preferred room temperature — it's a *steering* value computed from how far the room is from preferred. The loop has two stages:

1. **Setpoint computation** (`custom_templates/setpoint.jinja`, exposed as `sensor.<room>_heat_pump_setpoint_temperature` in `configuration.yaml`)
   `setpoint = base_temp − (current_temp − preferred) × 1.25`, clamped to `[17, 30]` °C. `base_temp` is a secondary indoor temperature sensor (`sensor.<room>_temperature`); `current_temp` comes from the baseboard heater's built-in thermometer. The room temperature error pushes the setpoint *away* from preferred to make the pump work harder. Rounding is direction-aware: rounds up when the room is too cold, down when too warm. In backup-heat mode the setpoint collapses to `base_temp − 1`.

2. **Apply / gate** (HVAC controllers, event-driven)
   Each room's controller fires on state changes to its setpoint sensor, preferred, swing, or mode (with a 2-minute debounce on mode flapping), plus a 5-minute safety heartbeat. It reads desired state (`desired_on`, `desired_hvac`, `setpoint`) and current state (`switch.<room>_power`'s on/off, `climate.<room>`'s hvac_mode and target temperature), and acts only on real deltas — so every Cielo API call is justified.

The dead band (`swing` = `input_number.<room>_temp_range`) prevents thrash: inside `[preferred − swing, preferred + swing]`, neither `desired_on` nor `desired_off` is true, so no Cielo call is issued.
```

- [ ] **Step 2: Delete the "Mode switching has a subtle asymmetry" subsection entirely**

Find the heading `### Mode switching has a subtle asymmetry` and delete the heading plus its paragraph through (and not including) `### Backup heat mode`. After this edit, "two-stage heat-pump control loop" flows directly into "Backup heat mode".

- [ ] **Step 3: Update the Conventions banner-comment list**

In the "Conventions" section, find the bullet starting with `- The thematic banner comments in \`automations.yaml\``. Replace its list of banners with the current set:

```markdown
- The thematic banner comments in `automations.yaml` (`# HVAC controllers`, `# Backup heat`, `# Humidity`) are the file's structure — keep them and group new automations under the right one.
```

(Removed: `# Mode switching` and `# Setpoint sync`.)

- [ ] **Step 4: Spot-check the rest of CLAUDE.md for stale references**

Search the file for these strings; if any are still present, evaluate whether they need updating:
- "Setpoint sync" — should appear only as historical context if at all; the section is gone
- "Mode switching" / "asymmetry" — should be gone
- "every minute" / "per-minute" — only valid if it refers to something other than the HVAC controllers (it shouldn't)
- "outdoor / building reference" — must be gone (was in the setpoint description)

If you find any of these still active, fix them in the same task.

- [ ] **Step 5: Commit**

```bash
cd /Users/gregn/Documents/office
git add CLAUDE.md
git commit -m "Update CLAUDE.md for event-driven HVAC architecture

- Heat-pump loop is now two stages, not three (sync subsumed into
  the controllers)
- Drop the office/studio mode-switch asymmetry note (gone, both rooms
  handle mode changes uniformly)
- Banner-comment list reflects only the remaining three sections
- base_sensor described correctly as indoor, not outdoor reference

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] **Confirm line count target**

```bash
wc -l /Users/gregn/Documents/office/automations.yaml
```
Expected: ~270 lines (was 572). If significantly higher, audit for leftover dead automations.

- [ ] **Confirm no orphan banner comments**

```bash
grep -n "^# " /Users/gregn/Documents/office/automations.yaml
```
Expected: only the section headers for `# HVAC controllers`, `# Backup heat`, `# Humidity` and their explanation lines.

- [ ] **Observe for 24 hours**

Watch the Cielo Home activity feed and HA logbook over a full day, including at least one mode change if practical. Confirm:
- No spike in Cielo API calls
- No automation errors in Developer Tools → Logs
- Both rooms track `preferred ± swing` as before
- Humidifier/dehumidifier still cycle correctly across their bands
