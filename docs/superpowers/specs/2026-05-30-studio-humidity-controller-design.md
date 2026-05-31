# Studio humidity controller — design

**Date:** 2026-05-30
**Status:** Approved (design); implementation plan pending

## Problem

The studio dehumidifier and humidifier were observed running **at the same time**, with
the dehumidifier stuck on while humidity was already below set point. This state should be
impossible.

### Root cause

The four humidity automations (`dehumidifier_on`, `dehumidifier_off`, `humidifier_on`,
`humidifier_off`) are **edge-triggered** `numeric_state` automations. Each device is turned
off by exactly one event — the humidity reading *crossing* a threshold. If that single
crossing is ever missed, the device stays in the wrong state until some later crossing
happens to occur. Crossings get missed on:

- sensor dropout (`unavailable`/`unknown` gap on the battery Zigbee humidity sensor — an
  `unavailable → value` change is not a numeric crossing and does not fire the trigger),
- HA restart / automation reload while the reading is already past the threshold,
- set-point / tolerance changes (the triggers listen only to the humidity sensor, not the
  threshold entities).

Nothing cross-checks the two devices: each automation inspects only its own switch, so there
is **no mutual-exclusion invariant**. Once one device is stranded on, the other can also turn
on, producing the both-on state.

The most recent incident was muddied by manual flips of the dehumidifier switch, but the
working theory is **humidifier overshoot**: the humidifier ran until humidity rose past set
point, overshot through the (possibly narrow) dead band, and tripped the dehumidifier ON
threshold — with no relaxation period between the humidifier stopping and the dehumidifier
starting.

## Requirements

1. The dehumidifier and humidifier must **never be on at the same time**.
2. When one device turns off, the other must **not turn on immediately** — a forced
   relaxation period must elapse first.
3. **Manual switch flips** are respected for a grace window before the controller resumes
   automatic control (exception: a manual flip that produces both-on is corrected at once).

### Decisions

- Relaxation (cross-device cooldown): **15 minutes**.
- No separate anti-chatter min-on/min-off — the cooldown is sufficient.
- Manual-flip grace window: **15 minutes**.
- Heartbeat safety reconcile: **5 minutes** (matches the HVAC controllers).

## Approach

Replace the four edge-triggered automations with a **state-driven controller** that mirrors
the existing HVAC controller pattern in this repo: event-driven + periodic heartbeat,
short-circuits on `unavailable` inputs, and acts only on real deltas. The bad state becomes
impossible *by construction* rather than merely guarded.

## Entities

Existing:

- Humidity sensor — `sensor.tz3000_utwgoauk_snzb_02_humidity` (`H`)
- Dehumidifier switch — `switch.mini_plug_4_socket_1`
- Humidifier switch — `switch.studio_humidifier_socket_1`
- Set point — `input_number.humidity_set_point` (`S`)
- Tolerance — `input_number.humidity_tolerance` (`T`)
- Thresholds — `sensor.humidity_high_threshold` (`S+T`), `sensor.humidity_low_threshold` (`S−T`)

New helpers (5):

- `timer.humidity_cooldown` — 15 min; the cross-device relaxation period.
- `timer.dehumidifier_manual_grace` — 15 min.
- `timer.humidifier_manual_grace` — 15 min.
- `input_boolean.dehumidifier_intended` — mirror of the controller's last commanded
  dehumidifier state.
- `input_boolean.humidifier_intended` — mirror of the controller's last commanded
  humidifier state.

> Helper-migration note: per CLAUDE.md the live helpers are still UI-defined and
> `helpers.yaml` is not yet included from `configuration.yaml`. New helpers must therefore be
> created in the HA UI to match the current source of truth, **and** mirrored into the repo
> (`input_boolean`s into `helpers.yaml`; `timer`s recorded for the eventual migration). Timers
> live in their own `timer:` domain, not under the existing `input_*` blocks.

## Automations

Two automations under the `# Humidity` banner replace the four existing ones.

### `studio_humidity_controller` — reconciler

**Mode:** `single`.

> **Why `single`, not `restart`:** the controller triggers on the same switches it commands.
> Under `restart`, the controller turning a switch off mid-sequence would restart its own run
> and could cancel the line that starts the cooldown timer — defeating the relaxation. Under
> `single`, the controller's own switch-change events are dropped while it is running (the run
> finishes, including starting the cooldown), and the deferred turn-on is driven later by the
> `timer.finished` trigger and the heartbeat. Matches the HVAC controllers, which are also
> `single`.

**Triggers:**

- state change of `sensor.tz3000_utwgoauk_snzb_02_humidity`
- state change of `input_number.humidity_set_point`, `input_number.humidity_tolerance`
- state change of `switch.mini_plug_4_socket_1`, `switch.studio_humidifier_socket_1`
  (catches a manual both-on immediately)
- `timer.finished` for `timer.humidity_cooldown`, `timer.dehumidifier_manual_grace`,
  `timer.humidifier_manual_grace` (so a deferred turn-on happens the moment the window ends)
- Home Assistant start
- a 5-minute periodic heartbeat

**Derive desired state** with hysteresis (computed in `variables:`):
- dehumidifier: want ON when `H ≥ S+T`, OFF when `H < S`, else hold current
- humidifier: want ON when `H ≤ S−T`, OFF when `H > S`, else hold current
- (both can never want ON simultaneously since `T > 0`)

**Action: one `choose:` that performs at most ONE action per run** (first matching branch
wins). Doing a single action per run is what makes the relaxation race-free: an off-branch
starts the cooldown *before* its run ends, so any later turn-on (driven by a subsequent
trigger) sees the cooldown active. The prioritized branches:

1. **Short-circuit** if `H`, `S`, or `T` is `unavailable`/`unknown` → no writes (this is in
   `conditions:`, so the whole automation is skipped).
2. **Mutual-exclusion safety (overrides cooldown *and* grace):** if both switches are on,
   humidity decides the winner — `H > S` → turn the **humidifier** off; otherwise turn the
   **dehumidifier** off; then start the cooldown timer.
3. **Dehumidifier turn-OFF:** `desired_dehum` false, dehum on, no dehum grace → set mirror
   off, turn off, start cooldown.
4. **Humidifier turn-OFF:** `desired_humid` false, humid on, no humid grace → set mirror off,
   turn off, start cooldown.
5. **Dehumidifier turn-ON:** `desired_dehum` true, dehum off, humidifier off (mutual
   exclusion), no dehum grace, cooldown **not** active → set mirror on, turn on.
6. **Humidifier turn-ON:** `desired_humid` true, humid off, dehumidifier off (mutual
   exclusion), no humid grace, cooldown **not** active → set mirror on, turn on.

In every branch the `*_intended` mirror is set *before* the switch command so the controller's
own action is never mis-read as manual. Turn-ON branches additionally require the opposite
device to be off, so a turn-on can never *create* a both-on state — branch 2 is only a backstop
for externally-induced both-on (e.g. two simultaneous manual flips).

### `studio_humidity_manual_detector` — manual-flip detection

**Triggers:** state change of either switch (to `on`/`off`; ignore `unavailable`/`unknown`).

**Logic:** if the switch's new state ≠ its `*_intended` mirror, the change was manual:

- update the mirror to the new (manual) reality, and
- start that switch's 15-minute grace timer.

The detector does **not** touch `timer.humidity_cooldown`. The cooldown is started only by the
controller's own turn-off branches, which keeps it race-free (it is set within the same run,
before any later turn-on is evaluated). This means the relaxation period covers
**controller-driven** turn-offs — including the overshoot ping-pong that caused the incident
(humidifier turns off at set point → dehumidifier turn-on is held for 15 min). A purely
**manual** turn-off does not arm the cooldown; manual changes are instead protected by the
grace window.

## How the requirements are met

- **Never both on:** step 2 runs every cycle and on every switch change, overriding cooldown
  and grace. A manual flip into both-on self-heals within seconds.
- **Forced relaxation:** a controller-driven off starts the 15-min cooldown; turn-ons are
  blocked while it runs, giving an overshoot time to settle before the opposite device can
  engage. (Manual offs rely on the grace window instead.)
- **Respect manual flips:** a manually changed switch is left alone for 15 min (except the
  both-on safety), then the heartbeat reconciles it back to the humidity-driven state.

## Trade-offs

- A manual override only persists for 15 minutes, then the controller reasserts the
  humidity-driven state.
- 5 new helpers and 2 automations replace 4 automations — more entities, but the resulting
  control loop is robust and matches the HVAC pattern already in the repo.

## Open / follow-up

- Confirm current `S` and `T` values. If `T` is only 1–2 %, widen the dead band on top of the
  cooldown so normal humidifier overshoot cannot reach the dehumidifier ON threshold.

## Out of scope

- Office/room HVAC behavior (unchanged).
- The helpers-migration to `!include` (separate task per CLAUDE.md), beyond mirroring the new
  helpers into the repo.
