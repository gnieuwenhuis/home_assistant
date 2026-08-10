# Eva Lamp auto-off plug

Date: 2026-08-09
Status: approved, pre-implementation

## Problem

A spare Tuya "Mini Plug", registered as `switch.rabbitry_heater_socket_1` and
currently `unavailable`, is being repurposed to drive the Eva lamp. The lamp
should not be left on indefinitely: whenever a person turns it on, it should
switch itself off 30 minutes later.

The plug is a third unit of the same hardware as the two studio humidity plugs —
Tuya Mini Plug on the Tuya cloud integration, `device_class: outlet`, entity
suffix `_socket_1`.

Nothing in this repo commands the plug today. Its whole behavior is the one
automation described here.

## Scope

In scope: a 30-minute auto-off that arms on a human turn-on, the timer helper
behind it, and tests.

Out of scope: brightness or color (the plug is a dumb relay), scheduling,
presence, and any tie to the HVAC or humidity loops. The lamp is independent of
both.

## Entity rename (host cutover)

The plug keeps its Tuya device identity but is renamed:

| | Before | After |
|---|---|---|
| Device name | Rabbitry Heater | Eva Lamp |
| Entity ID | `switch.rabbitry_heater_socket_1` | `switch.eva_lamp_socket_1` |
| Display name | Rabbitry Heater Socket 1 | Eva Lamp Socket 1 |

The display name is not stored on the entity. The Tuya entity carries the
original name `Socket 1` and no name of its own, so what HA shows is the device
name followed by that — which is why renaming the device is what carries the
display name, and why the result matches the two studio plugs
("Studio Dehumidifier Socket 1"). Setting a name on the entity instead would
leave the device reading `Rabbitry Heater` in every device-scoped view.

Both registries live under `.storage/`, which is gitignored, so this rename
**cannot be made from this repo**. It is a host-side step, the same shape as the
helpers migration: Settings → Devices & services → rename the device, then its
entity. Until it is done, the automation below targets an entity ID that does
not exist and silently never fires.

The name breaks the repo's `<domain>.<room>_<thing>` convention. That convention
exists for the per-room HVAC and humidity entities, which are paired across
office and studio; the lamp is a single unpaired device identified by what it is
rather than which room holds it.

## Behavior

One automation, `eva_lamp_auto_off`, over three triggers:

| Trigger | Condition | Action |
|---|---|---|
| `switch.eva_lamp_socket_1` → `on` | turn-on was not automation-commanded | start `timer.eva_lamp_auto_off` |
| `switch.eva_lamp_socket_1` → `off` | — | cancel `timer.eva_lamp_auto_off` |
| `timer.eva_lamp_auto_off` finished | switch is still `on` | `switch.turn_off` |

Consequences worth stating explicitly:

- **A second turn-on while the timer runs restarts the full 30 minutes.**
  `timer.start` on a running timer restarts it, which is the wanted behavior: a
  person touching the switch gets a fresh 30 minutes rather than the remainder of
  someone else's.
- **Turning the lamp off cancels the timer**, so a later `timer.finished` cannot
  fire a `switch.turn_off` at an already-off plug. The still-`on` gate on the
  turn-off branch is the second half of the same guard. Both exist because HA
  does not dedupe service calls and this repo treats not spamming a cloud device
  API as load-bearing.
- **A reconnect or restart with the lamp on arms the timer.** The plug is
  `unavailable` at rest; when it comes back already `on`, or when HA restarts
  with the lamp on, that `unavailable → on` transition is device-originated and
  arms a 30-minute cutoff. The alternative — requiring a literal `off → on` edge
  — leaves the lamp on forever in exactly the case the feature exists to prevent.

## The manual-vs-automation discriminator

The turn-on branch is gated on:

```jinja
{{ trigger.to_state.context.parent_id is none }}
```

HA attaches a context to every state write. The three cases:

| Origin | `user_id` | `parent_id` | Arms timer |
|---|---|---|---|
| Physical button on the plug | none | none | yes |
| HA dashboard / UI toggle | set | none | yes |
| Automation-commanded | none | set | no |

A single `parent_id is none` check therefore admits both human paths and
excludes the automation path, without needing to enumerate users.

This context survives the Tuya cloud round-trip — it is not stripped when the
command leaves HA and the new state comes back. Verified against the sibling
plug on the live instance: every `switch.studio_humidifier_socket_1` transition
in the logbook carries `context_event_type: automation_triggered` naming
`automation.studio_humidity_controller`.

**Known limitation.** An automation triggered with no triggering context of its
own — a time trigger, or Home Assistant start — produces `parent_id: none` and
would be read as human. Nothing commands this plug, so the hole is unreachable
today. The alternative is the `input_boolean.<device>_intended` mirror that
`studio_humidity_manual_detector` uses, which is precise but only pays for itself
when a controller is actually issuing commands to compare against. If an
automation is ever given control of this plug, revisit this gate before wiring
it up.

## Components

### `helpers.yaml`

```yaml
timer:
  eva_lamp_auto_off:
    name: Eva Lamp Auto Off
    duration: "00:30:00"
    restore: true
```

`restore: true` matches every other timer in the file and carries a running
cutoff across an HA restart.

The duration is fixed rather than driven by an `input_number`. All seven existing
timers hardcode theirs, retuned by editing this file and reloading the Timer
domain; a helper would add a dashboard control and a test surface for a value
that has no reason to move.

### `automations.yaml`

A new `# Lamps` banner section, since none of `# HVAC controllers`,
`# Backup heat`, or `# Humidity` covers it. The automation takes the descriptive
id `eva_lamp_auto_off`, matching the hand-written convention rather than the
UI-generated numeric one.

`mode: queued`, as with `studio_humidity_manual_detector`: a rapid on/off pair
must process both edges rather than drop the second.

## Testing

New file `tests/test_eva_lamp_auto_off.py`, loading the automation from the real
`automations.yaml` like the other Level 3 tests.

**It departs from the existing Level 3 pattern in one way, deliberately.** The
other Level 3 tests turn the automation *off* and drive a single run via
`automation.trigger` with `skip_condition: False`, which never populates
`trigger.*`. The discriminator here reads `trigger.to_state.context`, so that
pattern cannot exercise it at all. This file leaves the automation **on** and
drives real state changes with an explicit `Context(...)`, which exercises the
trigger block as well — the first such coverage in the repo.

Cases:

| Case | Context on the state write | Expect |
|---|---|---|
| Physical button press | `user_id=None, parent_id=None` | timer running |
| UI toggle | `user_id="<user>"` | timer running |
| Automation-commanded | `parent_id="<ctx>"` | timer idle |
| Turn-off while timer runs | any | timer idle |
| `timer.finished`, lamp on | — | one `switch.turn_off` |
| `timer.finished`, lamp already off | — | no service call |
| Second press while running | human | timer restarted, full duration |

`tests/test_helpers_yaml.py` gains an assertion for `timer.eva_lamp_auto_off` —
presence, 30-minute duration, and `restore: true` — alongside the existing timer
checks.

## Deployment

1. Rename the entity on the host (see above). **Nothing works until this is
   done.**
2. Sync `helpers.yaml` and `automations.yaml` to the HA instance.
3. Developer Tools → YAML → reload **Timer**, then reload **Automations**.

A new timer helper is a new entity, so the Timer domain reload must precede the
automation reload. The `timer.finished` trigger is an **event** trigger matching
on `event_data.entity_id`, following the two existing controllers, so a missing
timer costs it nothing — it simply never matches. The `timer.start` action is
what breaks: it fails at runtime against an entity that does not exist yet, so a
press between the two reloads would leave the lamp on with no cutoff armed.
