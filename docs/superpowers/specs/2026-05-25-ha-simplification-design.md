# Home Assistant configuration simplification — design

Date: 2026-05-25
Scope: `automations.yaml`, `configuration.yaml`, `custom_templates/setpoint.jinja`, `CLAUDE.md`

## Goal

Cut the line count and duplication that have accumulated in the office/studio
HA configuration without changing observable behavior. Specifically: preserve
hysteresis, preserve Cielo Home API dedupe, preserve backup-heat behavior,
preserve humidity hysteresis bands.

## Load-bearing constraints

1. **Cielo dedupe is required.** HA does not deduplicate service calls. Every
   `climate.set_temperature` / `switch.turn_on` / `switch.turn_off` call hits
   the Cielo cloud. Today's controllers guard every action with a
   `condition: device` check; any replacement must preserve the property that
   no Cielo call is issued when desired state already matches current state.
2. **The setpoint macro algorithm is correct as written**, despite the stale
   header comment describing `base_sensor` as "outdoor / building reference."
   It actually receives an indoor sensor that anchors the steering. Do not
   alter the math.
3. **Backup-heat behavior** (the `−12 °C / 20 min` trigger and the `−2.5 °C`
   offset that lets the heat pump take primary duty on warmup) is out of
   scope and untouched.

## Architecture changes

### 1. HVAC controllers become event-driven with one consolidated dedupe

The current `office_hvac_controller` and `studio_hvac_controller` automations
fire on `time_pattern: minutes: /1`, then check device state inside several
nested `if`/`condition: device` blocks before each action. They are
accompanied by a separate `*_temperature_sync` automation that fires at
`:15`/`:45` to write the drifted setpoint, and two named mode-switch
automations that handle `input_select.heat_pump_mode` flipping for the studio
only.

After:

- **Triggers**: state change on `sensor.<room>_heat_pump_setpoint_temperature`,
  `input_number.<room>_preferred_temperature`, `input_number.<room>_temp_range`,
  plus `input_select.heat_pump_mode` with `for: { minutes: 2 }` debounce, plus
  a `time_pattern: minutes: /5` safety heartbeat.
- **Body**: compute desired tuple (`desired_on`, `desired_hvac`, `setpoint`),
  read current tuple (`switch_is_on`, `states('climate.<room>')`,
  `state_attr('climate.<room>', 'temperature')`), then a three-branch
  `choose:` that acts only on real deltas.

The setpoint sensor is rounded to integers in `setpoint.jinja`, which acts as
a natural rate-limiter on the setpoint trigger. The 5-min heartbeat catches
edge cases where the room crosses `preferred ± swing` without the integer
setpoint flipping.

#### Final controller (office shown; studio is identical with names swapped)

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
      for: { minutes: 2 }
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
              target: { entity_id: switch.office_power }
            - action: climate.set_temperature
              target: { entity_id: climate.office }
              data:
                temperature: "{{ setpoint }}"
                hvac_mode: "{{ desired_hvac }}"
        # Already on, mode or target drifted (subsumes office_temperature_sync)
        - conditions: >-
            {{ desired_on and switch_is_on and
               (current_hvac != desired_hvac or current_target != setpoint) }}
          sequence:
            - action: climate.set_temperature
              target: { entity_id: climate.office }
              data:
                temperature: "{{ setpoint }}"
                hvac_mode: "{{ desired_hvac }}"
        # Overshooting wrong direction → off
        - conditions: "{{ desired_off and switch_is_on }}"
          sequence:
            - action: switch.turn_off
              target: { entity_id: switch.office_power }
  mode: single
```

#### Removed automations

- `office_temperature_sync`, `studio_temperature_sync` — subsumed by the
  "already on, drifted" branch.
- `'1765126659858'` (Switch Heat Pump mode to Cooling) and
  `'1765126778404'` (Switch Heat Pump mode to Heating) — subsumed by the
  mode-change trigger with `for: { minutes: 2 }`. The studio-only asymmetry
  documented in CLAUDE.md disappears: both rooms now react to mode changes
  the same way.

#### Latency trade-offs (deliberate, not "no behavior change")

Three observable timing changes vs. today:

- **Office mode-switch**: today the office controller picks up an
  `input_select.heat_pump_mode` change on its next 1-minute tick (no
  debounce). After: 2-minute debounce, matching the studio. This is a
  uniformity win at the cost of 1–2 minutes of latency on office mode flips.
- **Setpoint drift while on**: today, the sync writes drifted setpoints at
  `:15`/`:45` (up to 30 s lag). After: state-change trigger on the setpoint
  sensor writes within seconds. **Faster.**
- **Boundary crossing (room enters or leaves the dead band)**: today, the
  per-minute tick catches it within 60 s. After: the setpoint sensor's
  integer state usually flips during the transition (so the state-change
  trigger fires within seconds), but in the rare case it doesn't, the 5-min
  heartbeat is the worst-case bound. Worst-case latency for switch on→off
  on overshoot: 5 min vs. today's 1 min.

The third case is the only regression. It is acceptable because the dead
band absorbs short-term temperature drift — a 4-minute delay before turning
off on overshoot doesn't materially change room temperature.

#### Dedupe preservation argument

- `desired_on and not switch_is_on` branch fires only when transitioning
  off → on. One Cielo `switch.turn_on` + one `climate.set_temperature` call.
- `desired_on and switch_is_on and (current_hvac != desired_hvac or current_target != setpoint)`
  branch fires only when at least one of the two climate-side values
  actually differs. One Cielo `climate.set_temperature` call.
- `desired_off and switch_is_on` branch fires only when transitioning
  on → off. One Cielo `switch.turn_off` call.
- Inside the dead band (`current_temp` between `preferred − swing` and
  `preferred + swing`), `desired_on` and `desired_off` are both false; no
  branch fires; zero Cielo calls.
- The 5-min heartbeat tick re-evaluates without changing inputs; if every
  comparison is unchanged from the last evaluation, no branch fires.

#### Unavailability guard

All four top-level conditions must pass before any action is taken. When
`climate.office` becomes unavailable (Cielo connectivity drop),
`state_attr('climate.office', 'temperature') | float(none)` yields `None`;
the branch-2 comparison `current_target != setpoint` then evaluates
`None != <float>` as `True` and would fire a spurious `climate.set_temperature`
call on every heartbeat. At HA boot, if `sensor.office_heat_pump_setpoint_temperature`
is briefly unavailable, `| float(0)` yields `0.0` — which with `current_temp`
also defaulting to 0 could trigger branch 1 and send a 0 °C target to Cielo.
The four entity-state conditions (`not in ['unavailable', 'unknown']`) make the
controller a complete no-op when any critical input is unavailable — simpler
and safer than per-branch `none`-guards. The studio controller carries the
identical four conditions with `studio` names.

#### Behavior-preservation argument for hysteresis

The original hysteresis depends on the condition `too_cold or too_hot` being
checked before any action. In the new controller, that check is split across
the three choose-branches:
- `desired_on` is true only when `too_cold` (in heating) or `too_hot` (in
  cooling). False in the dead band and on the wrong overshoot.
- `desired_off` is true only on the wrong overshoot for the current mode.
- Both false in the dead band, so no branch fires there.

The result is the same hysteresis: pump turns on at one edge, stays on
through the dead band, turns off at the other edge.

### 2. Humidity controllers split into single-purpose ON/OFF automations

The current `Dehumidifier Controller` and `Humidifier Controller` each have
two template triggers (rising / falling threshold) and an internal `choose`
with two branches that duplicate the trigger templates as conditions. After:

- Add two template sensors for the hysteresis band thresholds.
- Replace each controller with two `numeric_state`-triggered automations,
  one ON and one OFF, each with a single condition and a single action.

#### New template sensors (added to `configuration.yaml` `template:` block)

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

#### New automations

```yaml
- id: dehumidifier_on
  alias: Dehumidifier ON
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
      target: { entity_id: switch.mini_plug_4_socket_1 }
  mode: single

- id: dehumidifier_off
  alias: Dehumidifier OFF
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
      target: { entity_id: switch.mini_plug_4_socket_1 }
  mode: single

- id: humidifier_on
  alias: Humidifier ON
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
      target: { entity_id: switch.studio_humidifier_socket_1 }
  mode: single

- id: humidifier_off
  alias: Humidifier OFF
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
      target: { entity_id: switch.studio_humidifier_socket_1 }
  mode: single
```

#### Behavior-preservation argument

The original hysteresis bands:
- Dehumidifier: ON when humidity > set_point + tolerance, OFF when < set_point
- Humidifier: ON when humidity < set_point − tolerance, OFF when > set_point

The new automations' triggers fire on the same threshold crossings (via
`numeric_state above:` / `below:`). The `condition: state` blocks ensure each
fires only on real transitions, not redundantly. The dead band — where both
devices stay in their previous state — is preserved.

### 3. Optional naming cleanup

The dehumidifier switch is currently named `switch.mini_plug_4_socket_1`
(generic, opaque). For symmetry with `switch.studio_humidifier_socket_1` the
user may rename it to `switch.studio_dehumidifier_socket_1` via Settings →
Devices & services → gear icon. **This is optional** and can be done
independently. If done, the spec's references to
`switch.mini_plug_4_socket_1` must be updated.

### 4. Documentation updates

**`custom_templates/setpoint.jinja`**: rewrite the header docstring to
describe `base_sensor` as the indoor reference that anchors the steering,
not as "outdoor / building reference."

**`CLAUDE.md`**:
- Stage 1 setpoint description: drop the "outdoor" framing.
- Stage 2 ("Apply / gate"): replace the per-minute description with the
  event-driven trigger list + 5-min heartbeat.
- Stage 3 ("Sync"): delete (replaced by the controller's "already on,
  drifted" branch).
- "Mode switching has a subtle asymmetry" subsection: delete (the asymmetry
  is gone — both rooms now use the same mode-change handling).
- Banner-comment list update: drop `# Mode switching` and `# Setpoint sync`
  from the documented section list.

## Out of scope

- The backup-heat automations and the `−2.5 °C` offset.
- The setpoint macro's algorithm.
- Renaming the dehumidifier switch (called out as optional in §3).
- Custom-integration installation (HACS).
- Helper migration (separate, already documented in `helpers.yaml`).

## Risk and rollback

Each section can be deployed and rolled back independently:

- Section 1 (HVAC controllers): swap the new controllers in, delete the old
  sync + mode-switch automations. To roll back, restore from the prior git
  commit and reload automations.
- Section 2 (humidity): add the two template sensors first, deploy the four
  new automations, then delete the old two. To roll back, do the reverse.
- Section 3 (doc fixes): pure markdown / comment changes, no runtime risk.

After deploy, watch the Cielo activity log for 1–2 days to confirm no
unexpected churn in API calls. Watch the heat pumps physically to confirm
mode changes still take effect within the 2-minute debounce.

## Final tally

| File | Before | After | Δ |
|---|---|---|---|
| `automations.yaml` | 572 | ~270 | **−302** |
| `configuration.yaml` | 93 | ~105 | +12 (template sensors) |
| `setpoint.jinja` | 32 | ~30 | −2 |
| `CLAUDE.md` | ~180 | ~140 | −40 |

About 47% line reduction in `automations.yaml`, every Cielo write gated on a
real delta, and the office/studio mode-switch asymmetry eliminated as a side
effect. Three deliberate latency changes (see §1's "Latency trade-offs"): two
are improvements, one is a worst-case 4-minute regression in a benign case.
