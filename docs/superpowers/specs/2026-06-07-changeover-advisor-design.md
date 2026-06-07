# Changeover Advisor — Design

**Date:** 2026-06-07
**Status:** Approved design, pending implementation plan

## Problem

`input_select.heat_pump_mode` (heating / cooling) is flipped manually. This was
deliberate: no algorithm the user trusted could decide when to change over
without flapping near threshold conditions. The goals for automating it:

- Robustly determine when the building's regime is heating, cooling, or
  neither — without bouncing between modes near thresholds.
- Never recommend air conditioning when it is cold outside, or heating when it
  is warm outside (open windows instead).
- Tolerate the outdoor data source: Environment Canada observations/forecasts
  from a station a few kilometres away (systematic offset, no local
  microclimate).
- Respect physical reality: both rooms share one outdoor heat-pump unit
  (multi-split), so the mode is global by necessity, not just policy.

## Decision

A **suggest + confirm advisor**, not an autonomous switcher. The system
computes the recommended mode and sends an actionable notification to
`mobile_app_pixel_8`; a human gates every changeover, so flapping is impossible
by construction and "robustness" reduces to *never nagging without cause*.

The decision engine is the tried-and-true building-automation pattern:
**seasonal changeover by degree-hours** (Approach B) with **demand-based
confirmation from equipment duty cycle**, voiced in plain forecast language in
the notification (Approach C). Three regimes: `heating` / `cooling` / `off`
(open windows).

## Section 1 — Decision signals

### Forecast nomination

A trigger-based template sensor, `sensor.changeover_balance`, refreshes hourly
and on HA start by calling `weather.get_forecasts` (hourly) on the Environment
Canada weather entity and computing over the next 48 hours:

- `HDH = Σ max(0, balance_point − T_hour)` — heating degree-hours
- `CDH = Σ max(0, T_hour − balance_point)` — cooling degree-hours
- state = `CDH − HDH`; `hdh`, `cdh`, and a short forecast summary are kept as
  attributes for the notification text.

`balance_point` = `input_number.changeover_balance_point`, default **16 °C**
(the residential convention — below indoor preferred because internal and
solar gains are free heat above it).

Candidate regime, with dead zone `K` = `input_number.changeover_deadband`
(default **24 °C·h** ≈ averaging 0.5 °C past balance for 48 h):

| `CDH − HDH` | Candidate |
|---|---|
| `> +K` | cooling |
| `< −K` | heating |
| inside `±K` | off / windows |

Properties that fall out of the math:

- The outdoor gates are free: a cold forecast cannot nominate cooling, a warm
  forecast cannot nominate heating.
- Chinooks lose: one warm afternoon cannot outweigh 60 cold hours in a 48 h
  integral.
- No trailing observed-outdoor component. The recent past is encoded in the
  building's thermal state (measured by the confirmation signals below), and
  EC's hour-0 forecast ≈ current conditions. This also removes the EC
  station's current-reading offset from the picture entirely.

### Indoor confirmation — duty cycle as the load witness

Indoor temperature is a regulated variable: while the pump actively conditions
a room it oscillates inside `preferred ± swing` (with overshoot — the office
head is oversized for its small room and overshoots hard) and carries no
information about outdoor load. The standard substitute is **equipment
runtime**: if the system is in heating mode and the pump hasn't called for
heat in 24 h, there is no heating load.

New sensors:

- `sensor.office_heat_pump_duty_24h`, `sensor.studio_heat_pump_duty_24h` —
  `history_stats` ratio of time `switch.<room>_power` was `on` over the last
  24 h.
- `sensor.office_temperature_2h_mean`, `sensor.studio_temperature_1h_mean` —
  `statistics` time-weighted means of `sensor.<room>_baseboard_current_temperature`
  (the same signal the HVAC controllers use). The office gets the longer
  window because its oversized head produces larger transients; the studio is
  the better-behaved witness.

Temperature is only treated as evidence where the control loop *cannot* act,
and only with a duty-cycle alibi (the pump cannot be the culprit):

| Candidate | Confirmed when |
|---|---|
| cooling | a room's smoothed temp `> preferred + swing` **and** that room's `duty_24h ≈ 0` |
| heating | a room's smoothed temp `< preferred − swing` **and** that room's `duty_24h ≈ 0` |
| off | **both** rooms' `duty_24h ≈ 0` (building coasting unassisted) |

"≈ 0" means below a small floor (~2 %), so a single 5-minute heartbeat blip
cannot poison the alibi. The zero-vs-nonzero test is robust to head sizing —
an oversized head's duty is naturally low but not zero when there is load.

### Assumption to verify on the live HA instance

The EC integration's weather entity name (likely `weather.lethbridge`) and
that it serves **hourly** forecasts. Not grep-able in this repo.

## Section 2 — Advisor automation and notification flow

New banner section in `automations.yaml`: `# Changeover advisor`.

### `heat_pump_mode_advisor`

- **Triggers:** hourly time pattern (matches the balance sensor's cadence);
  `timer.finished` on `timer.changeover_hold` (so a blocked suggestion isn't
  delayed up to an hour after the hold expires).
- **Variables:** candidate from `sensor.changeover_balance` vs `±K`;
  confirmation per the table above; current mode from
  `input_select.heat_pump_mode`.
- **Conditions** (all must hold, controller-style short-circuit):
  1. `candidate != current_mode`
  2. confirmation satisfied for the candidate
  3. `timer.changeover_hold` is idle
  4. balance sensor, room means, and duty sensors not
     `unavailable`/`unknown`
  5. `input_boolean.backup_heat` is off (the math already makes cooling
     impossible at −12 °C; the guard documents intent)
- **Action:** actionable notification to `mobile_app_pixel_8`, phrased from
  the balance sensor's attributes, e.g.:

  > "Next 48 h is mostly cooling load (CDH 38 vs HDH 6) and the studio has
  > averaged 24.8 °C for the past hour. Switch to cooling?"
  > **[Switch to cooling] [Not now]**

  The action id carries the candidate (`CHANGEOVER_ACCEPT_cooling`), then the
  advisor immediately starts `timer.changeover_hold` for **12 h** (so an
  ignored notification still produces a quiet period).

### `heat_pump_mode_advisor_response` (`mode: queued`)

Handles the notification action events:

- **Accept** → set `input_select.heat_pump_mode` to the candidate carried in
  the action id. Honored even hours later — accepting a stale offer is a
  deliberate human act, treated like a manual flip.
- **Not now** → nothing further (the 12 h hold is already running).

### `heat_pump_mode_changed`

Triggers on any `input_select.heat_pump_mode` state change (advisor-driven or
manual) and:

1. (re)starts `timer.changeover_hold` for **24 h** — the minimum time-in-mode.
   Manual flips get the same protection from second-guessing.
2. if the new mode is `off`: turns off `switch.office_power` /
   `switch.studio_power`, each call gated on the switch currently being `on`
   (preserving the Cielo API dedupe discipline).

### Hold semantics (one timer, two durations)

`timer.changeover_hold` blocks all suggestions while running:

- suggestion sent → 12 h (nag floor, regardless of taps)
- mode changed (any source) → 24 h (min time-in-mode)

Net guarantees: at most one suggestion per 12 h; a fresh mode gets a full day
before the advisor may second-guess it; even a chinook that survived the 48 h
integral cannot round-trip the mode within a day.

### New helpers

UI-defined now, mirrored in `helpers.yaml` with the usual migration note:

- `off` option added to `input_select.heat_pump_mode`
- `input_number.changeover_balance_point` (default 16 °C)
- `input_number.changeover_deadband` (default 24 °C·h)
- `timer.changeover_hold` (`restore: true`)

## Section 3 — Integration, edge cases, validation

### Changes to existing config (deliberately minimal)

- The HVAC controllers need **zero changes** for the new `off` mode —
  `mode in ['heating', 'cooling']` already short-circuits everything.
- Pump power-off on entering `off` mode is handled by
  `heat_pump_mode_changed` (above).
- Setpoint sensors keep computing in `off` mode; harmless, nothing reads them.

### Failure modes (fail-safe = stay in current mode)

- **EC forecast unavailable / service call fails** →
  `sensor.changeover_balance` goes `unavailable`; advisor condition 4
  short-circuits. No suggestion is ever produced from stale or missing data.
- **HA restart** → balance sensor re-triggers on start;
  `timer.changeover_hold` restores, so a restart cannot erase a hold and
  re-open the nag window.
- **Stale notification taps** → action payload carries the candidate, so the
  response automation sets exactly what was offered.
- **Backup heat** → advisor condition 5.

### Staged deployment

1. **Shadow phase:** deploy only the five sensors (balance + 2 duty + 2
   means); watch on a dashboard for a few days. Verify degree-hour totals
   against EC's published forecast and duty cycles against the switch history.
2. **Notification round-trip test:** temporarily drop `changeover_deadband`
   to ~0 and raise the duty floor to force a suggestion; confirm both buttons
   work on the Pixel 8; restore values.
3. **Enable.** Suggestion volume is self-limiting (≥ 12 h apart by
   construction), so live observation for a couple of weeks is the soak test.

## Section 4 — Unit testing

The riskiest parts of the design are pure logic; they get extracted and tested.

### Macro extraction

The brains move into `custom_templates/changeover.jinja` (same convention as
`setpoint.jinja`) as pure macros taking inputs as arguments:

- `degree_hours(forecast_list, balance_point)` → `(hdh, cdh)`
- `candidate_mode(cdh, hdh, deadband)` → `heating | cooling | off`
- `confirmation(candidate, room_states, duty_cycles, bands)` → bool

The template sensor and advisor automation become thin callers of these
macros.

### Test harness

`pytest` + **`pytest-homeassistant-custom-component`** (pinned to match the
live HA version), which provides a real HA instance as a fixture — the genuine
HA Jinja environment, not a plain-Jinja approximation.

- **Level 2 — macro tests (the bulk):** set entity states, render macros,
  assert outputs. Every scenario from this design becomes a named regression
  test: the chinook afternoon, the office overshoot alibi, the dead-zone hold,
  the backup-heat guard, the unavailable-forecast short-circuit.
- **Level 3 — automation wiring tests (advisor only):** load the actual
  `automations.yaml` into the test instance, set states, fire the hourly
  trigger with time-travel helpers, assert the mocked `notify` service
  was/wasn't called and `input_select.heat_pump_mode` changed. This is the
  only level that catches a wrong entity id in a condition.

New repo artifacts: `tests/` directory, `requirements-dev.txt` pinning the
test dependency. CLAUDE.md gains a short "Running tests" section
(`pytest tests/`) and this design's architecture summary. The shadow phase in
Section 3 remains — unit tests verify the logic; the shadow phase verifies
EC's data feeding it. As a side benefit, `setpoint.jinja` becomes testable
with the same harness later.

## Out of scope

- Autonomous switching (could be revisited once suggestion accuracy is
  trusted; the "auto with veto window" middle ground was considered and
  parked).
- Per-room modes — physically impossible on a shared outdoor unit.
- Humidity interaction — the humidity controller is independent by design.
