# Ecobee-style auto heat/cool for the multi-split heat pump

**Date:** 2026-06-15
**Status:** Design — approved for spec review
**Supersedes:** the changeover advisor (`2026-06-07-changeover-advisor-design.md`
and its blend addendum) and the two-stage steering control loop described in
`2026-05-25-ha-simplification-design.md`.

## Problem

The current control loop has one mode (`heating` / `cooling` / `off`), one
`preferred` temperature per room, and one symmetric `swing` per room. In cooling
mode the head turns on at `preferred + swing` and runs all the way down to
`preferred − swing` — a full `2 × swing` drop — so a wide swing makes the room
"very cold" (and the mirror problem overheats in heating mode). The
`setpoint.jinja` macro compounds this: it deliberately steers the head's target
*past* preferred (`base − error × 1.25`) to make the pump work harder.

Mode is also a manual decision, nudged by the **changeover advisor** — a Pixel 8
text-message system (degree-hour forecast balance + duty-cycle confirmation)
that the user finds unnecessarily complex and does not want to maintain.

The user wants the behavior of their household **ecobee** thermostat: set a
lower heating bound and an upper cooling bound; the system decides heat vs cool
automatically and recovers to a bound without driving past it; no overshoot.

## Key physical constraint

The two heads are a **multi-split**: one outdoor compressor serves both rooms,
so **heat vs cool is a single system-wide decision**. Both heads must be in the
same mode at any instant. Each head can independently be on/off (idle) and hold
its own setpoints, but they can never run in opposite modes simultaneously. This
is the central fact the design is built around.

## Decisions (from brainstorming)

1. **Two setpoints per room, no middle "preferred"** (true ecobee). Heat runs up
   to the lower bound and stops; cool runs down to the upper bound and stops; the
   room floats freely in the dead band between.
2. **Fully automatic** mode selection from both rooms' demand — no seasonal
   switch, no notifications.
3. **Heating wins conflicts.** If either room is below its heat bound the whole
   system heats; cooling only runs when *neither* room wants heat. A too-warm
   room simply idles its head.
4. **Short-cycle protection** is mandatory (the office heats/cools fast):
   per-bound differential + per-head lockout timer + inverter modulation.
5. **Master enable** switch for a one-tap "all off" (away / windows open).
6. **Backup heat → heads fully off** below −12 °C (baseboards lead); replaces
   today's "aim the pump at a collapsed low target" behavior.
7. **Ecobee-style thermostat tile** via a HACS template-climate integration.
8. **Remove the changeover advisor entirely** (this is the requested revert),
   done as deletions within this redesign rather than `git revert` of the merge
   commits.

## Control model

Per room the user sets two values:

- `input_number.<room>_heat_bound` — lower bound. Below it, the room wants heat.
- `input_number.<room>_cool_bound` — upper bound. Above it, the room wants cool.

Plus a per-room differential `input_number.<room>_temp_differential` (hysteresis,
see short-cycle protection).

There is **no `preferred`**. Where the old design needed a single comfort value
(backup-heat baseboard target), use the derived **comfort midpoint**
`(heat_bound + cool_bound) / 2`.

### Per-room demand (with hysteresis)

For each room, given its reliable temperature `t`
(`sensor.<room>_baseboard_current_temperature`), bounds, differential `d`, and
whether it is currently active in that direction:

```
should_heat = t <= heat_bound  or  (currently_heating and t < heat_bound + d)
should_cool = t >= cool_bound  or  (currently_cooling and t > cool_bound - d)
```

The differential means a head that has started does not stop the instant it
touches the bound — it runs `d` degrees past it before cutting, lengthening the
off-period before it can re-trigger.

### System mode resolution (heating wins)

```
if  office.should_heat or studio.should_heat:  desired = heat
elif office.should_cool or studio.should_cool: desired = cool
else:                                          desired = idle
```

### Anti-flap (minimum time between heat↔cool)

`timer.mode_min_dwell` (default 15 min) starts whenever the system enters an
active mode (heat or cool) that differs from the previous active mode. While the
dwell is active, the stored mode is **pinned to that active mode** and the
opposite active mode cannot be adopted — even transiently via idle. Pinning
means: during the dwell, `input_select.system_hvac_mode` is **not** relabeled to
`idle` when same-direction demand drops; it stays at the dwelling mode and the
heads are simply driven by current demand within that mode (so they idle when
there is no same-direction demand, but the opposite mode stays forbidden). This
closes the idle-hop bypass — a blocked reversal cannot sneak through `idle`.
Once the dwell clears, the mode re-resolves freely (to the opposite mode, which
starts a fresh dwell, or to `idle`). The cost is that genuine opposite demand
waits up to the dwell window; acceptable for compressor protection, and the dead
band plus differential already make rapid flips unlikely.

### Per-head application

Given the resolved system mode, for each room:

- **heat:** head on iff `should_heat`; head target = `clamp(heat_bound + lead)`.
- **cool:** head on iff `should_cool`; head target = `clamp(cool_bound − lead)`.
- **idle / master-off / backup-heat:** head off.

`lead` (default 2 °C, a macro constant, clamped to `[17, 30]`) commits the
inverter: the head's onboard sensor reads warm in heat / cool, so without a lead
the pump quits early. The coordinator does the **real cutoff** against the
reliable room sensor at the bound, so the lead never causes overshoot past the
bound by more than the differential.

A room that wants the *opposite* of the resolved mode (e.g. office wants cool
while the system is heating for the studio) simply has its head **off** — it
cannot be served until the conflict clears. This is the direct, intended
consequence of "heating wins."

### Short-cycle protection (four layers)

1. **Dead band** between the two bounds — the room must traverse it before the
   opposite action fires (primary user tuning knob).
2. **Per-bound differential** `input_number.<room>_temp_differential` — runs the
   head past the bound before cutting. Default **office 1.0 °C** (fast room),
   **studio 0.5 °C**.
3. **Per-head lockout** `timer.<room>_head_lockout` — started on **every** head
   toggle (on or off); the coordinator will not toggle that head again until it
   expires. Hard-caps cycle frequency regardless of how fast the room moves and
   protects the compressor from rapid restarts. Default **office 8 min**,
   **studio 6 min** (durations set in the timer definitions). The **only**
   override is a hard-safety force-**off** (master-off or backup-heat) — lockout
   never blocks turning a head *off* for safety, and never permits an *on*.
4. **Inverter modulation** — commanding the head a target with a lead and
   letting it run (instead of chattering the power switch) lets the compressor
   ramp down on its own near setpoint.

Trade-off (accepted): the lockout and the wider office differential let the room
drift a little past a bound during a forced-off window. Both are tunable.

## Architecture

### Single HVAC coordinator automation

The two per-room controllers are replaced by **one** `hvac_coordinator`
automation, because on a multi-split the mode decision and the per-head
decisions are interdependent (mode depends on each room's `should_*`, and each
head's action depends on the resolved mode). One automation for one physical
compressor is the honest boundary.

**Triggers:**
- state of `sensor.office_baseboard_current_temperature`,
  `sensor.studio_baseboard_current_temperature`
- state of the four bound helpers + two differential helpers
- state of `input_boolean.hvac_enable`, `input_boolean.backup_heat`
- `timer.finished` for `timer.mode_min_dwell`,
  `timer.office_head_lockout`, `timer.studio_head_lockout`
- `homeassistant` start
- `time_pattern` every 5 min (safety heartbeat)

**Guard conditions** (short-circuit on missing data, preserving the existing
discipline): both baseboard temp sensors, both `switch.<room>_power`, both
`climate.<room>` not in `unavailable` / `unknown`.

**Body:**
1. Read stored mode from `input_select.system_hvac_mode`; derive
   `currently_heating_<room>` / `currently_cooling_<room>` from
   `switch.<room>_power` + stored mode.
2. Compute `should_heat` / `should_cool` per room via the macros.
3. Resolve desired mode; apply anti-flap (if the dwell is active, pin to the
   dwelling active mode and forbid the opposite mode — do not relabel to idle).
4. If `hvac_enable` is off **or** `backup_heat` is on → force both heads off,
   set stored mode `off`/`idle`, done.
5. Otherwise write the resolved mode to `input_select.system_hvac_mode` (start
   `timer.mode_min_dwell` when it becomes an active mode that changed), and for
   each room issue the minimum Cielo calls to reach the desired head state:
   - off→on: `switch.turn_on` + `climate.set_temperature` (hvac_mode + target)
   - on, drifted: `climate.set_temperature` (mode/target)
   - on→off: `switch.turn_off`
   - each toggle starts `timer.<room>_head_lockout`; **skip any toggle whose
     lockout is active** (except safety force-off in step 4).
6. Every call gated on a real desired-vs-current delta (switch on/off, climate
   hvac_mode, climate target) — the [[feedback_cielo_api_dedupe]] discipline.

`mode: single`.

### Decision macros — `custom_templates/hvac.jinja`

Pure, unit-testable macros (same pattern the deleted `changeover.jinja` used):

- `should_heat(t, heat_bound, differential, currently_heating)`
- `should_cool(t, cool_bound, differential, currently_cooling)`
- `resolve_mode(off_should_heat, st_should_heat, off_should_cool, st_should_cool)`
- `head_target(mode, heat_bound, cool_bound, lead)` → clamped to `[17, 30]`

### Ecobee thermostat tile — template climate entities

Add per-room template climate entities `climate.office_thermostat` /
`climate.studio_thermostat` via a HACS **Climate Template** custom integration
(e.g. `litinoveweedle/hass-template-climate`, a maintained fork of the original
jcwillox/Tobias component — confirm the most-maintained fork at install time).
Each entity is a **display/entry facade** over the helpers; it issues **no**
direct Cielo calls — all control stays in the coordinator.

Mapping:
- `current_temperature` → `sensor.<room>_baseboard_current_temperature`
- `target_temp_low` → `input_number.<room>_heat_bound`
- `target_temp_high` → `input_number.<room>_cool_bound`
- `hvac_modes` → `["off", "heat_cool"]`
- `hvac_mode` → `heat_cool` when `input_boolean.hvac_enable` is on, else `off`
- `hvac_action` → `heating` / `cooling` / `idle` / `off` derived from
  `input_boolean.hvac_enable`, `input_select.system_hvac_mode`, and that room's
  `switch.<room>_power`
- `set_temperature` → write `target_temp_low`/`target_temp_high` back to the two
  bound helpers (dragging the dial handles sets the bounds)
- `set_hvac_mode` → `heat_cool` turns `hvac_enable` on, `off` turns it off

Dropping this on a dashboard with the standard HA **thermostat card** gives the
ecobee dual-handle dial: current temp, heat handle, cool handle, and the current
action — recognized automatically because the entity advertises a heat/cool
range, exactly like the ecobee integration does.

### Backup heat

The two backup-heat automations stay, retargeted off the removed `preferred`:
- below −12 °C: baseboards → **comfort midpoint** `(heat_bound + cool_bound)/2`
  per room; the coordinator independently forces both heads off (it reads
  `backup_heat`).
- on warmup: baseboards → `heat_bound − 2.5 °C` per room, so the heat pump leads
  and the baseboards only catch deep cold (preserves the existing −2.5 °C
  "pump leads" intent).

### Humidity

Untouched.

## Helpers

The repo's "UI-defined now, mirrored in `helpers.yaml` for the eventual
migration" status is unchanged for all helpers below.

**Add:**
- `input_boolean.hvac_enable` — master on/off (default on)
- `input_number.office_heat_bound`, `office_cool_bound`,
  `studio_heat_bound`, `studio_cool_bound` (min 15, max 30, step 0.5)
- `input_number.office_temp_differential` (default 1.0),
  `studio_temp_differential` (default 0.5) (min 0, max 3, step 0.1)
- `input_select.system_hvac_mode` — options `heat` / `cool` / `idle` / `off`,
  written only by the coordinator (observability + dwell/stored-mode tracking)
- `timer.mode_min_dwell` (15 min, restore: true)
- `timer.office_head_lockout` (8 min, restore: true),
  `timer.studio_head_lockout` (6 min, restore: true)

**Remove:**
- `input_number.office_temp_range`, `studio_temp_range` (swing)
- `input_number.office_preferred_temperature`, `studio_preferred_temperature`
- `input_number.changeover_balance_point`, `changeover_deadband`,
  `changeover_daily_deadband`
- `input_select.heat_pump_mode`
- `timer.changeover_hold`

**Default bound seeds** (tune live on device): office heat 20 / cool 24,
studio heat 20 / cool 23.

## Sensors (`configuration.yaml`)

**Remove:**
- `sensor.office_heat_pump_setpoint_temperature`,
  `sensor.studio_heat_pump_setpoint_temperature`
- `sensor.changeover_balance` and its trigger-based weather-fetch block
- `sensor.office_temperature_2h_mean`, `sensor.studio_temperature_1h_mean`
- `sensor.office_heat_pump_duty_24h`, `sensor.studio_heat_pump_duty_24h`

**Keep:** baseboard current-temperature sensors, energy/energy-count sensors,
humidity high/low threshold sensors.

## Automations (`automations.yaml`)

**Remove:** `office_hvac_controller`, `studio_hvac_controller`,
`heat_pump_mode_advisor`, `heat_pump_mode_advisor_response`,
`heat_pump_mode_changed`, and the "Changeover advisor" banner.

**Add:** `hvac_coordinator` under the `# HVAC controllers` banner (retitle the
banner's body comment to describe the coordinator/two-setpoint model).

**Keep:** the two backup-heat automations (retargeted as above), both humidity
automations.

## Files

**Remove:** `custom_templates/setpoint.jinja`, `custom_templates/changeover.jinja`,
`tests/test_advisor_automations.py`, `tests/test_changeover_balance_sensor.py`,
`tests/test_changeover_macros.py`.

**Add:** `custom_templates/hvac.jinja`,
`tests/test_hvac_macros.py` (Level 2: macro rendering — heat/cool/idle
resolution, the office-hot + studio-cold conflict resolving to **heat**,
differential hysteresis, target clamps),
`tests/test_hvac_coordinator.py` (Level 3: load `hvac_coordinator` from the real
YAML and exercise — cold studio → studio head on in heat / office idle; lockout
blocks a rapid re-toggle; `hvac_enable` off → both heads off; `backup_heat` on →
both heads off; conflict → heat with office head off).

**Update:** `tests/test_helpers_yaml.py` for the new helper set.

The template climate entities are display-only and depend on a not-installed
custom integration, so they are verified manually on device rather than in the
pytest harness.

## Documentation

- Rewrite the affected `CLAUDE.md` sections: the two-stage control loop →
  single coordinator + two-setpoint model; backup heat (heads off); delete the
  changeover-advisor section; the conventions/entity-name list; add the HACS
  **Climate Template** integration to the HACS list; update the helpers list.
- After implementation, update the `[[project_changeover_advisor_status]]`
  memory (the advisor is removed, not pending deployment).

## Deployment / migration notes

- New helpers are added in the HA UI and mirrored in `helpers.yaml` (status
  unchanged); removed helpers are deleted from the UI and from `helpers.yaml`.
- Install the HACS Climate Template integration before adding the template
  climate platform to `configuration.yaml`.
- Reload Template, Input Number/Boolean/Select, Timer, and Automations (or
  restart HA). Seed bound defaults, then tune live.

## Out of scope / YAGNI

- No seasonal lock and no outdoor-temperature guard (fully automatic, per the
  brainstorm).
- No "away" preset with alternate bounds (master enable only).
- `lead`, the differential floor, and lockout/dwell durations are simple
  constants/helpers, not a tuning subsystem.
