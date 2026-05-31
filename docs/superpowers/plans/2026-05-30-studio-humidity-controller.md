# Studio Humidity Controller Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the four edge-triggered humidity automations with one state-driven controller (plus a manual-flip detector) so the studio humidifier and dehumidifier can never run at once, a 15-min relaxation cooldown separates a controller turn-off from the opposite device starting, and manual switch flips are respected for 15 min.

**Architecture:** A reconciling controller derives each device's desired state from the *current* humidity level (hysteresis around `input_number.humidity_set_point` ± `input_number.humidity_tolerance`) and drives the switches to match, acting on real deltas only — the same pattern as the existing HVAC controllers. A prioritized `choose:` performs at most one action per run; turn-off branches start `timer.humidity_cooldown`; turn-on branches are gated on the cooldown, the opposite device being off, and a per-switch manual-grace timer. A separate detector tells controller-issued switch changes apart from manual ones via `*_intended` mirror booleans and arms the grace timers.

**Tech Stack:** Home Assistant YAML (automations, template sensors, `timer`/`input_boolean` helpers). No build/test pipeline; verification is YAML lint + HA "Check Configuration" + Developer Tools scenario tests.

**Spec:** `docs/superpowers/specs/2026-05-30-studio-humidity-controller-design.md`

**Entities (reference):**
- Humidity sensor: `sensor.tz3000_utwgoauk_snzb_02_humidity`
- Dehumidifier switch: `switch.mini_plug_4_socket_1`
- Humidifier switch: `switch.studio_humidifier_socket_1`
- Set point / tolerance: `input_number.humidity_set_point`, `input_number.humidity_tolerance`

**File structure:**
- `helpers.yaml` — add 2 `input_boolean` mirrors + a new `timer:` block (3 timers); update migration note.
- `automations.yaml` — replace the `# Humidity` section (lines ~245–324: four automations) with the banner + two new automations.
- `CLAUDE.md` — update the "Humidity (independent of HVAC)" section to describe the controller.

---

## Task 1: Add the new helpers (UI + repo mirror)

**Files:**
- Modify: `helpers.yaml` (add to `input_boolean:` block; add new top-level `timer:` block; update the migration comment)

- [ ] **Step 1: Create the helpers in the Home Assistant UI**

In **Settings → Devices & services → Helpers → + Create helper**, create:

| Type | Name | Resulting entity_id | Notes |
|---|---|---|---|
| Toggle | `Dehumidifier Intended` | `input_boolean.dehumidifier_intended` | |
| Toggle | `Humidifier Intended` | `input_boolean.humidifier_intended` | |
| Timer | `Humidity Cooldown` | `timer.humidity_cooldown` | Duration `0:15:00` |
| Timer | `Dehumidifier Manual Grace` | `timer.dehumidifier_manual_grace` | Duration `0:15:00` |
| Timer | `Humidifier Manual Grace` | `timer.humidifier_manual_grace` | Duration `0:15:00` |

Confirm each entity_id matches the table exactly (HA derives it from the name; rename the entity if needed). UI timers do not expose `restore`; that is acceptable — after an HA restart the timers reset to idle and the HA-start trigger + heartbeat reconcile state.

- [ ] **Step 2: Mirror the two booleans into `helpers.yaml`**

Add under the existing `input_boolean:` block (after `backup_heat:`):

```yaml
  dehumidifier_intended:
    name: Dehumidifier Intended
    icon: mdi:air-humidifier-off
  humidifier_intended:
    name: Humidifier Intended
    icon: mdi:air-humidifier
```

- [ ] **Step 3: Add the `timer:` block to `helpers.yaml`**

Append a new top-level block at the end of the file:

```yaml
timer:
  humidity_cooldown:
    name: Humidity Cooldown
    duration: "00:15:00"
    restore: true
  dehumidifier_manual_grace:
    name: Dehumidifier Manual Grace
    duration: "00:15:00"
    restore: true
  humidifier_manual_grace:
    name: Humidifier Manual Grace
    duration: "00:15:00"
    restore: true
```

(`restore: true` makes the eventual YAML-defined timers survive restarts; it only takes effect once `helpers.yaml` is wired in — see Step 4.)

- [ ] **Step 4: Update the migration comment in `helpers.yaml`**

The migration note currently lists three `!include` lines. Replace that list so the `timer:` domain is included too. Change:

```yaml
#   2. Add these three lines to configuration.yaml (top level):
#        input_number:  !include helpers.yaml
#        input_boolean: !include helpers.yaml
#        input_select:  !include helpers.yaml
#      (HA reads each top-level key from the included file.)
```

to:

```yaml
#   2. Add these four lines to configuration.yaml (top level):
#        input_number:  !include helpers.yaml
#        input_boolean: !include helpers.yaml
#        input_select:  !include helpers.yaml
#        timer:         !include helpers.yaml
#      (HA reads each top-level key from the included file.)
```

And in step 3 of that comment, add "Timer" to the list of helpers to reload.

- [ ] **Step 5: Lint `helpers.yaml`**

Run: `python3 -c "import yaml; yaml.safe_load(open('helpers.yaml')); print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add helpers.yaml
git commit -m "Add humidity controller helpers (intended mirrors + timers)"
```

---

## Task 2: Replace the four humidity automations with the controller + detector

**Files:**
- Modify: `automations.yaml` — replace the entire `# Humidity` section (the banner comment block plus `dehumidifier_on`, `dehumidifier_off`, `humidifier_on`, `humidifier_off`).

- [ ] **Step 1: Replace the `# Humidity` banner and the four automations**

Delete everything from the `# Humidity` banner (`# ===...` block starting at the `# Humidity` line) through the end of the `humidifier_off` automation, and replace with the following.

```yaml
# ============================================================
# Humidity
# ------------------------------------------------------------
# One state-driven controller reconciles the studio humidifier
# and dehumidifier from the current humidity level (it replaced
# four edge-triggered on/off automations). It:
#   - never lets both run at once (mutual-exclusion safety),
#   - forces a 15-min relaxation cooldown after a controller
#     turn-off before the opposite device may start (stops the
#     overshoot ping-pong), and
#   - respects a manual switch flip for 15 min before resuming.
# Hysteresis around input_number.humidity_set_point with
# input_number.humidity_tolerance:
#   dehumidifier ON at set_point+tol, OFF below set_point
#   humidifier   ON at set_point-tol, OFF above set_point
# The manual detector tells controller-issued switch changes
# apart from manual ones via the *_intended mirror booleans.
# ============================================================

- id: studio_humidity_controller
  alias: Studio Humidity Controller
  description: >-
    Reconcile the studio humidifier/dehumidifier from the current humidity
    level. Enforces mutual exclusion (never both on), a 15-min cross-device
    relaxation cooldown after a controller turn-off, and a 15-min grace window
    after a manual switch flip. Fires on humidity/setpoint/switch/timer changes,
    HA start, and a 5-min heartbeat. Performs at most one action per run, gated
    on real deltas.
  triggers:
  - trigger: state
    entity_id:
    - sensor.tz3000_utwgoauk_snzb_02_humidity
    - input_number.humidity_set_point
    - input_number.humidity_tolerance
    - switch.mini_plug_4_socket_1
    - switch.studio_humidifier_socket_1
  - trigger: event
    event_type: timer.finished
    event_data:
      entity_id: timer.humidity_cooldown
  - trigger: event
    event_type: timer.finished
    event_data:
      entity_id: timer.dehumidifier_manual_grace
  - trigger: event
    event_type: timer.finished
    event_data:
      entity_id: timer.humidifier_manual_grace
  - trigger: homeassistant
    event: start
  - trigger: time_pattern
    minutes: /5
  variables:
    humidity:        "{{ states('sensor.tz3000_utwgoauk_snzb_02_humidity') | float(0) }}"
    set_point:       "{{ states('input_number.humidity_set_point') | float(0) }}"
    tolerance:       "{{ states('input_number.humidity_tolerance') | float(0) }}"
    dehum_on:        "{{ is_state('switch.mini_plug_4_socket_1', 'on') }}"
    humid_on:        "{{ is_state('switch.studio_humidifier_socket_1', 'on') }}"
    cooldown_active: "{{ is_state('timer.humidity_cooldown', 'active') }}"
    dehum_grace:     "{{ is_state('timer.dehumidifier_manual_grace', 'active') }}"
    humid_grace:     "{{ is_state('timer.humidifier_manual_grace', 'active') }}"
    desired_dehum: >-
      {{ true if humidity >= (set_point + tolerance)
         else false if humidity < set_point
         else dehum_on }}
    desired_humid: >-
      {{ true if humidity <= (set_point - tolerance)
         else false if humidity > set_point
         else humid_on }}
  conditions:
  - "{{ states('sensor.tz3000_utwgoauk_snzb_02_humidity') not in ['unavailable', 'unknown'] }}"
  - "{{ states('input_number.humidity_set_point') not in ['unavailable', 'unknown'] }}"
  - "{{ states('input_number.humidity_tolerance') not in ['unavailable', 'unknown'] }}"
  - "{{ states('switch.mini_plug_4_socket_1') not in ['unavailable', 'unknown'] }}"
  - "{{ states('switch.studio_humidifier_socket_1') not in ['unavailable', 'unknown'] }}"
  actions:
  - choose:
    # 1) Mutual-exclusion safety — both on: humidity picks the loser.
    #    Overrides cooldown and grace. Backstop for externally-induced both-on.
    - conditions: "{{ dehum_on and humid_on }}"
      sequence:
      - if: "{{ humidity > set_point }}"
        then:
        - action: input_boolean.turn_off
          target:
            entity_id: input_boolean.humidifier_intended
        - action: switch.turn_off
          target:
            entity_id: switch.studio_humidifier_socket_1
        else:
        - action: input_boolean.turn_off
          target:
            entity_id: input_boolean.dehumidifier_intended
        - action: switch.turn_off
          target:
            entity_id: switch.mini_plug_4_socket_1
      - action: timer.start
        target:
          entity_id: timer.humidity_cooldown
    # 2) Dehumidifier should turn OFF (respect manual grace). Start cooldown.
    - conditions: "{{ not desired_dehum and dehum_on and not dehum_grace }}"
      sequence:
      - action: input_boolean.turn_off
        target:
          entity_id: input_boolean.dehumidifier_intended
      - action: switch.turn_off
        target:
          entity_id: switch.mini_plug_4_socket_1
      - action: timer.start
        target:
          entity_id: timer.humidity_cooldown
    # 3) Humidifier should turn OFF (respect manual grace). Start cooldown.
    - conditions: "{{ not desired_humid and humid_on and not humid_grace }}"
      sequence:
      - action: input_boolean.turn_off
        target:
          entity_id: input_boolean.humidifier_intended
      - action: switch.turn_off
        target:
          entity_id: switch.studio_humidifier_socket_1
      - action: timer.start
        target:
          entity_id: timer.humidity_cooldown
    # 4) Dehumidifier should turn ON. Gated on: humidifier off (mutual
    #    exclusion), no dehum grace, cooldown not active.
    - conditions: >-
        {{ desired_dehum and not dehum_on and not humid_on
           and not dehum_grace and not cooldown_active }}
      sequence:
      - action: input_boolean.turn_on
        target:
          entity_id: input_boolean.dehumidifier_intended
      - action: switch.turn_on
        target:
          entity_id: switch.mini_plug_4_socket_1
    # 5) Humidifier should turn ON. Gated on: dehumidifier off (mutual
    #    exclusion), no humid grace, cooldown not active.
    - conditions: >-
        {{ desired_humid and not humid_on and not dehum_on
           and not humid_grace and not cooldown_active }}
      sequence:
      - action: input_boolean.turn_on
        target:
          entity_id: input_boolean.humidifier_intended
      - action: switch.turn_on
        target:
          entity_id: switch.studio_humidifier_socket_1
  mode: single

- id: studio_humidity_manual_detector
  alias: Studio Humidity Manual Detector
  description: >-
    Detect manual flips of the studio humidifier/dehumidifier switches (any
    change the controller did not command, identified via the *_intended
    mirrors) and arm that switch's 15-min grace window so the controller leaves
    a manual override alone.
  triggers:
  - trigger: state
    entity_id: switch.mini_plug_4_socket_1
  - trigger: state
    entity_id: switch.studio_humidifier_socket_1
  conditions:
  - "{{ trigger.to_state.state in ['on', 'off'] }}"
  - "{{ not trigger.from_state or trigger.from_state.state != trigger.to_state.state }}"
  actions:
  - choose:
    - conditions: >-
        {{ trigger.entity_id == 'switch.mini_plug_4_socket_1'
           and trigger.to_state.state != states('input_boolean.dehumidifier_intended') }}
      sequence:
      - action: "input_boolean.turn_{{ trigger.to_state.state }}"
        target:
          entity_id: input_boolean.dehumidifier_intended
      - action: timer.start
        target:
          entity_id: timer.dehumidifier_manual_grace
    - conditions: >-
        {{ trigger.entity_id == 'switch.studio_humidifier_socket_1'
           and trigger.to_state.state != states('input_boolean.humidifier_intended') }}
      sequence:
      - action: "input_boolean.turn_{{ trigger.to_state.state }}"
        target:
          entity_id: input_boolean.humidifier_intended
      - action: timer.start
        target:
          entity_id: timer.humidifier_manual_grace
  mode: queued
```

- [ ] **Step 2: Confirm the four old automations are gone**

Run: `grep -n -E "id: (dehumidifier_on|dehumidifier_off|humidifier_on|humidifier_off)" automations.yaml`
Expected: no output (the four old ids are removed).

Run: `grep -n -E "id: (studio_humidity_controller|studio_humidity_manual_detector)" automations.yaml`
Expected: two lines (the two new automations are present).

- [ ] **Step 3: Lint `automations.yaml`**

Run: `python3 -c "import yaml; yaml.safe_load(open('automations.yaml')); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add automations.yaml
git commit -m "Replace edge-triggered humidity automations with state-driven controller"
```

---

## Task 3: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` — the "### Humidity (independent of HVAC)" subsection.

- [ ] **Step 1: Rewrite the Humidity architecture subsection**

Replace the existing "### Humidity (independent of HVAC)" subsection body with:

```markdown
### Humidity (independent of HVAC)

A single state-driven controller (`studio_humidity_controller` in `automations.yaml`)
reconciles the dehumidifier plug (`switch.mini_plug_4_socket_1`) and humidifier plug
(`switch.studio_humidifier_socket_1`) from the current reading of the shared Zigbee humidity
sensor — the same reconcile-on-delta pattern as the HVAC controllers. It replaced four
edge-triggered on/off automations that could strand a device (and run both at once) when a
threshold crossing was missed.

Asymmetric hysteresis around `input_number.humidity_set_point` with
`input_number.humidity_tolerance`:

- Dehumidifier: wants on when humidity `≥ set_point + tolerance`, off when `< set_point`
- Humidifier: wants on when humidity `≤ set_point − tolerance`, off when `> set_point`
- Inside `[set_point − tolerance, set_point + tolerance]` each device holds its last state —
  the intentional dead band.

Three invariants are enforced by construction:

- **Never both on.** Turn-on branches require the opposite device to be off; a mutual-exclusion
  safety branch turns off the wrong device (humidity decides) if both are ever on.
- **Relaxation cooldown.** Any controller turn-off starts `timer.humidity_cooldown` (15 min);
  turn-ons are blocked while it runs, so an overshoot can't immediately trip the opposite
  device. The controller is `mode: single` so its own switch events don't restart it mid-run;
  the deferred turn-on is driven by the `timer.finished` trigger and the 5-min heartbeat.
- **Respect manual flips.** `studio_humidity_manual_detector` compares each switch change
  against an `input_boolean.<device>_intended` mirror (set by the controller before it
  commands) to tell manual changes apart from controller ones, and arms a 15-min
  `timer.<device>_manual_grace`; the controller leaves a switch alone while its grace timer is
  active (except the both-on safety).

The new helpers (`input_boolean.dehumidifier_intended`, `input_boolean.humidifier_intended`,
and the three `timer.*` entities) follow the same "UI-defined now, mirrored in `helpers.yaml`
for the eventual migration" status as the other helpers.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Document state-driven humidity controller in CLAUDE.md"
```

---

## Task 4: Deploy and verify on Home Assistant

**Files:** none (deploy + runtime verification)

- [ ] **Step 1: Sync files to HA and check configuration**

Sync `automations.yaml` and `helpers.yaml` to the HA instance (your normal sync method).
In **Developer Tools → YAML → Check Configuration**, run the check.
Expected: "Configuration valid!". If not, read the error, fix in the repo, re-sync.

- [ ] **Step 2: Reload automations**

In **Developer Tools → YAML**, reload **Automations** (helpers were created in the UI in Task 1,
so no helper reload is needed unless/until the `helpers.yaml` migration is performed).
Verify in **Settings → Automations** that `Studio Humidity Controller` and
`Studio Humidity Manual Detector` are present and the four old humidity automations are gone.

- [ ] **Step 3: Seed the intended mirrors to match current switch states**

The mirrors default to `off`. Align them with reality once, so the detector reasons correctly
from the start. In **Developer Tools → Actions**:

- If `switch.mini_plug_4_socket_1` is on → call `input_boolean.turn_on` on
  `input_boolean.dehumidifier_intended`; else `input_boolean.turn_off`.
- If `switch.studio_humidifier_socket_1` is on → call `input_boolean.turn_on` on
  `input_boolean.humidifier_intended`; else `input_boolean.turn_off`.

- [ ] **Step 4: Verify the desired-state math (no side effects)**

In **Developer Tools → Template**, paste and confirm the values look right for the current
humidity / set point / tolerance:

```jinja
{% set humidity = states('sensor.tz3000_utwgoauk_snzb_02_humidity') | float(0) %}
{% set s = states('input_number.humidity_set_point') | float(0) %}
{% set t = states('input_number.humidity_tolerance') | float(0) %}
humidity={{ humidity }} set_point={{ s }} tol={{ t }}
high(on dehum)={{ s + t }}  low(on humid)={{ s - t }}
desired_dehum_on_threshold_met={{ humidity >= s + t }}
desired_humid_on_threshold_met={{ humidity <= s - t }}
```

Expected: thresholds equal `set_point ± tolerance`; at most one "threshold_met" is true.

- [ ] **Step 5: Verify mutual-exclusion safety**

In **Developer Tools → Actions**, turn **both** switches on
(`switch.turn_on` on `switch.mini_plug_4_socket_1` and `switch.studio_humidifier_socket_1`).
Expected: within a few seconds the controller (triggered by the switch change) turns one off,
leaving exactly one on. Which one: if current humidity `> set_point`, the humidifier is turned
off; otherwise the dehumidifier. Confirm `timer.humidity_cooldown` is now `active`.

- [ ] **Step 6: Verify the relaxation cooldown blocks the opposite turn-on**

Immediately after Step 5 (cooldown active), in **Developer Tools → States** temporarily set
`sensor.tz3000_utwgoauk_snzb_02_humidity` to a value that *would* turn the opposite device on
(e.g. above `set_point + tolerance` to demand the dehumidifier).
Expected: the opposite device does **not** turn on while `timer.humidity_cooldown` is `active`.
When the cooldown reaches `idle` (its `timer.finished` event fires), the controller turns the
demanded device on (if the demand still holds).
Note: the overridden sensor state is replaced on the sensor's next real report.

- [ ] **Step 7: Verify the manual-flip grace window**

With the controller idle, in **Developer Tools → Actions** manually flip one switch to the
state the controller would *not* currently choose (e.g. turn the dehumidifier on when humidity
is below `set_point`).
Expected: `studio_humidity_manual_detector` sets that switch's `*_intended` mirror to the new
state and starts its `timer.*_manual_grace` (now `active`); the controller does **not** revert
the switch on its next heartbeat while the grace timer is active. After the grace timer reaches
`idle`, the next heartbeat (≤5 min) reconciles the switch back to the humidity-driven state.
(To avoid a 15-min wait, you may temporarily set the grace timer's duration shorter in the UI
for this test, then restore `0:15:00`.)

- [ ] **Step 8: Verify clean idle behavior (no thrash)**

Leave the system for ~15 minutes with humidity in a steady state. In **Settings → Automations**,
check the controller's "Last triggered" — heartbeats fire every 5 min but should produce **no**
switch state changes when nothing needs to change (delta-only). Confirm the switches are not
toggling.

- [ ] **Step 9: Final confirmation**

Confirm: the two devices are never both on across the tests above, and both
`input_boolean.*_intended` mirrors match their switches. No commit needed (no file changes in
this task).

---

## Notes for the implementer

- **No automated test framework exists** for this repo (per CLAUDE.md). The `python3 -c "import yaml..."` lint only checks YAML well-formedness; the real validation is HA's Check Configuration plus the Developer Tools scenario tests in Task 4. `configuration.yaml` itself cannot be `safe_load`ed locally because it uses `!include`/`!secret` tags — do not lint it that way; rely on HA's checker for it.
- **Tuning follow-up (from the spec):** if `input_number.humidity_tolerance` turns out to be very small (1–2 %), normal humidifier overshoot can still reach the dehumidifier ON threshold once the cooldown expires. Consider widening the dead band; this plan does not change the tolerance value.
- **Timer restore:** UI-created timers reset to idle on HA restart. The HA-start trigger and the 5-min heartbeat reconcile device state after a restart, so a lost cooldown only means one skipped relaxation window immediately after a restart.
```
