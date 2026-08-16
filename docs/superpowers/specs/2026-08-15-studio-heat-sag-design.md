# Studio heat sag: sensor contamination and setpoint quantization

Date: 2026-08-15
Status: approved, pre-implementation

## Problem

Overnight 2026-08-14/15 the system ran in heat. The office held its bound. The
studio sat below its 19 °C heat bound for long stretches — including while its
head was powered and commanded to heat — reaching 18.5 °C on the baseboard
sensor and 18.69 °C on an independent sensor.

The asymmetric heating lead (`studio_heat_lead: 1.5`,
`2026-06-22-asymmetric-heating-lead-design.md`) exists to prevent exactly this.
Investigation shows the lead's arithmetic and evaluation order are correct, and
that three separate defects sit between the configured intent and the hardware.

## Evidence

Read from the live instance over `2026-08-14T20:00−06:00 … 2026-08-15T09:00−06:00`.
Times below are UTC, matching the API's `last_changed`.

### The head was commanded 20.0 °C, not the configured 20.5 °C

`climate.studio` reported `temperature: 20.0` for the entire night.
`head_target('heat', 19.0, 23.0, 1.5)` renders **20.5** against HA's live
in-memory macro. The head advertises `target_temp_step: 1` and works in whole
degrees Fahrenheit, truncating: 20.5 °C is 68.9 °F, which floors to 68 °F =
20.0 °C. The office shows the same effect at `lead: 0` — commanded 19.0 °C
(66.2 °F) lands on 66 °F and reports back 18.9 °C.

The effective studio lead is therefore **1.0 °C, not 1.5** — and the rounding
runs downward, against the room that is already sagging.

### The head ignored the command for 70 minutes

The clearest window is 11:33–12:52, head powered continuously:

| Time | Head onboard sensor | Baseboard sensor | Commanded |
|---|---|---|---|
| 11:33 | 23.9 | 19.0 | 20.0 |
| 11:57 | 22.2 | 18.7 | 20.0 |
| 12:26 | 21.1 | 18.6 | 20.0 |
| 12:43 | 19.4 | 18.5 | 20.0 |
| 12:48 | — | 19.2 | 20.0 |

The head delivered nothing until its own sensor fell *below* the commanded
setpoint at 12:43; real heat arrived five minutes later. The onboard sensor runs
2–4 °C above the room while the head is running, so a 1.0 °C effective lead
never opens a setpoint error at all. This is the mechanism the lead design
describes, with a constant roughly half the size the hardware needs.

### The dehumidifier drives the studio's control sensor

Every temperature spike on `sensor.studio_baseboard_current_temperature`
overnight maps one-to-one onto a `switch.studio_dehumidifier` run. The studio
baseboard's own `hvac_action` read `idle` throughout, so the baseboard element is
not the source; the dehumidifier's warm exhaust reaches the wall thermostat.

| Dehumidifier | Baseboard sensor | Effect on the head |
|---|---|---|
| 05:05:52–05:15:56 | 19.3 → 22.4 | blocked a turn-on |
| 07:59:35–08:09:32 | 19.0 → 22.4 | cut off at 08:00:52 |
| 10:58:36–11:08:46 | 18.7 → 22.4 | **terminated a live cycle at 11:04:12** |
| 14:45:37–14:56:08 | 18.6 → 21.6 | **terminated a live cycle at 14:49:12** |

`sensor.tz3000_utwgoauk_snzb_02_temperature` (the Zigbee humidistat, same room)
read **18.94 °C at 11:01** while the baseboard read 22.4, and stayed within
18.69–19.84 across the whole night. The spikes are an artifact of thermostat
placement, not room temperature.

At 11:04:12 the room was genuinely 18.7 °C and rising when a phantom 21.6 °C
reading ended heat demand and armed a 6-minute lockout.

### The Cielo dedupe gate can never be satisfied

The coordinator's already-on branch re-commands when
`current_<room>_target != <room>_target`. That compares the device-reported
value against the commanded one, across the quantization boundary:

- studio: `20.0 != 20.5` — permanently true
- office: `18.9 != 19.0` — permanently true, **even at `lead: 0`**

So while either head is powered, every coordinator run issues a
`climate.set_temperature`: the 5-minute heartbeat plus every baseboard sensor
update (~4 minutes). This is precisely the Cielo call volume the branch gating
was built to prevent.

`tests/test_hvac_coordinator.py::test_drift_resends_target_without_toggle`
covers the resend direction only. Nothing asserts silence when a head already
sits at its target, and the mocked `climate.set_temperature` never quantizes, so
the suite cannot observe this.

## Decisions

| Question | Choice | Rejected |
|---|---|---|
| Sensor contamination | Slew-rate filter on the baseboard reading | Cross-check against the Zigbee sensor; switching to the Zigbee sensor outright; a dehumidifier-aware demand gate |
| Forcing constant | Fix the defects, then retune from one clean night | Raising `studio_heat_lead` to 3.0 immediately; correcting `number.studio_temperature_offset` |

The Zigbee humidistat is the cleaner signal but reports on a ~15-minute median
cadence (25-minute maximum gap) and is a battery device, which is too slow and
too fragile to be the sole cutoff input for a head that must stop within a
0.5 °C differential.

Retuning is deferred because last night's data is contaminated: two heat cycles
were ended by phantom readings, so any lead derived from it would be
compensating for a defect that this change removes.

## Design

### Whole-degree-Fahrenheit snapping

`head_target` snaps its result onto the head's actual grid: convert to °F, round
to the nearest whole degree, convert back, and round the °C spelling **upward**
to one decimal so the head's truncation lands on the intended step.

The upward rounding matters. 63 °F is 17.222 °C; sending 17.2 gives 62.96 °F,
which truncates to 62 °F — one step low. Sending 17.3 gives 63.14 °F, which
truncates to 63 °F as intended.

Verified against the live template engine across `[17.0, 19.0, 20.0, 20.5, 21.0,
22.5, 23.0, 24.0, 29.8, 30.0]`; every value lands on its intended °F step, and
snapping never escapes the `[17, 30]` clamp (30.0 °C is exactly 86 °F).

The °F rounding is spelled half-up — `floor(f + 0.5)` — rather than Jinja's
`round`, which breaks an exact tie to even. Three points on the 0.5 °C bound grid
are exact half-degrees Fahrenheit: 17.5 (63.5 °F), 22.5 (72.5 °F) and 27.5
(81.5 °F). Only 22.5 lands differently under the two rules — 73 °F half-up
against 72 °F to-even, and 72 °F is where a 22.0 °C request already sits. The
other two round up under either rule, because 64 and 82 are even; half-up pins
all three by construction rather than by parity.

Grid collisions survive this, and closing them is not on offer: 0.5 °C is 0.9 °F,
less than one step, so exactly 3 of the 27 points in `[17, 30]` share a °F step
with the point below them under either rule. What half-up removes is a downward
bias at the ties, and with it a dead step in the retune range below —
`head_target('heat', 19, 23, 3.0)` commands 72 °F and `3.5` commands 73 °F, so a
half-step lead increase reaches the hardware.

This alone restores the studio's intended lead: 20.5 °C snaps to 20.6 °C
(69 °F) rather than truncating to 20.0 °C (68 °F).

### Comparing on the device grid

The commanded °C and the reported °C can differ in spelling while naming the
same physical step — 17.3 sent, 17.2 displayed, both 63 °F. Comparing °C values
is therefore the wrong test at any tolerance: an epsilon loose enough to absorb a
0.556 °C step also swallows a genuine 0.5 °C bound change.

The gate instead compares whole-°F integers, modelling each side's rounding:

- `command_step(c)` — `floor(c × 9/5 + 32)`, what the head will do with a command
- `report_step(c)` — `round(c × 9/5 + 32)`, recovering the step behind a reading

Verified: every snapped value satisfies `command_step(sent) == report_step(shown)`,
so the gate settles, while a bound change that crosses a °F step still resends.

### The slew filter

A new `sensor.studio_control_temperature`, a trigger-based template sensor,
filters the baseboard reading and becomes the studio's control input. The
decision is a pure macro in `custom_templates/hvac.jinja`, unit-tested like the
rest: `slew_filter(raw, raw_at, last_good, value_at, hold_since, pending,
pending_at, now_iso, reject, reenter, max_hold)`, returning JSON the sensor
spreads across its state and four attributes — `hold_since`, `value_at`,
`pending`, `pending_at`. `hold_since` is the operator-visible "is it holding"
signal; the other three are the filter's own bookkeeping.

It is a Schmitt trigger, not a plain threshold. A plain
`|new − last_good| > reject` filter admits the tail of a decaying spike: at
11:16:40 the sensor read 20.0 against a last-good 19.4, a 0.6 delta that passes a
1.0 threshold while still 1 °C above the real room. Two bands close that:

- **reject 1.0 °C** — a reading this far from the last accepted value starts a hold
- **re-enter 0.5 °C** — while holding, a reading must come back this close to be accepted

Measured genuine slew in this room peaks at ~0.7 °C per 4-minute reporting
interval, so 1.0 does not reject real movement, and the tighter re-entry band
only applies once a hold is already underway.

- **max hold 20 minutes** — a hold this long is a real shift, not an exhaust
  plume; the filter resyncs to the raw reading. Without it, a genuine step change
  that never returns within the re-entry band would hold forever.

Replayed against the four measured spikes: the 11:04 cycle survives to 11:20
(+16 minutes of heating, accepting 19.5 against a true ~19.2), and the 14:49
cycle survives the entire dehumidifier run instead of being cut at its start.

Source unavailability reuses the hold: the last good value carries for up to the
same 20 minutes — covering the 04:46:20 blip seen overnight — after which the
macro emits a JSON `null` and the entity settles at `unknown`, with no validator
error logged. A real `None` is what the template sensor's `_validate_state`
accepts; any string there errors on every render. The coordinator's availability
condition tests both `unavailable` and `unknown`, so its short-circuit takes over
either way.

**The filter's state survives a restart.** `TriggerSensorEntity` inherits
`RestoreSensor`, `TriggerEntity.async_added_to_hass` calls
`async_restore_last_state()`, and `template/entity.py` restores the custom
attributes alongside the state. A restart therefore resumes on the value and all
four attributes it had, and a hold in flight resumes on its original `hold_since`
clock rather than a fresh 20 minutes.

**A restored value is discarded once it is stale.** `value_at` stamps when a
value was accepted and rides along unchanged whenever a held value is
republished, so it measures age from acceptance rather than from the last render.
Outside a hold, a value older than `max_hold` describes a room that has since
moved and is treated as absent, sending the seeding path.

The check is skipped mid-hold, where `max_hold` already bounds the stale window.
`value_at` keeps the pre-hold acceptance stamp, and a hold starts no earlier than
that stamp, so by the time the cap expires the stamp is always older than
`max_hold` — the age test would fire first on every hold, making the cap dead
code. Worse, its outcome is the seeding path: instead of resyncing to the raw
reading at the cap, the sensor would drop its value and wait for two source
updates. Applying it mid-hold lengthens the window with no usable value rather
than shortening it.

**Seeding takes two source updates.** It runs where nothing usable is restored:
the entity's first-ever deploy, a source dropout that outlasts `max_hold`, and a
restart whose restored value is stale by the test above. A lone reading is
unusable there — taken inside a plume it latches the plume peak for the whole
hold, the inverse of the filter's purpose. Seeding therefore requires two raw
readings within the `reject` band of each other drawn from two *different* source
updates, and starts from the second; the unmatched candidate rides in a `pending`
key of the macro's JSON and a matching sensor attribute, with that reading's
source `last_changed` in `pending_at`. The timestamp is the whole gate: the
sensor's own `/5` time_pattern re-renders an unchanged source value, which agrees
with itself, so a candidate confirmable by a render sharing its timestamp would
let a plume plateau seed its own peak. The value stays null until a pair agrees.
Replayed against the 05:05 plume from a cold start, the filter declines the 22.4
peak and seeds at 19.0. On a quiet start the pair lands on the second source
update, roughly 4 minutes, and the coordinator holds both heads as they are until
it does.

### Residual limitations

- **A hold is a stale reading.** For up to 20 minutes the coordinator acts on a
  held value. Held low while the room genuinely rises, the head keeps heating;
  bounded by the resync and by the cool bound above it.
- **A restored value carries the same staleness bound.** A restart resumes on
  whatever was last accepted, and only an age past `max_hold` rejects it, so the
  coordinator can act on a reading up to 20 minutes old. That is the window a
  hold already opens, not a wider one.
- **A dehumidifier run longer than the hold cap** resyncs mid-spike and behaves
  as the system does today — no worse, not better.
- **One contaminated reading can still be accepted** where a spike decays into
  the re-entry band, as at 03:56 (19.8 accepted against a true 19.65).
- **Seeding costs a control temperature.** Wherever the seeding path runs the
  studio has none until two source updates agree — roughly one reporting
  interval — and the coordinator's availability short-circuit holds both heads as
  they are for that window.

### Baseboard standby setpoint (independent)

Unrelated to the sag, found alongside it. The warmup automation
(`'1756874009383'`) writes each baseboard to `heat_bound − 2.5` only on the
backup-heat exit edge. `studio_heat_bound` has since moved 20 → 19, so the studio
baseboard sits at **17.5** where the design intends 16.5. Harmless while the bound
stays above it; a bound dropped below 17.5 would put the baseboard in
competition with the heat pump, which is the exact condition the −2.5 offset
exists to prevent.

Both baseboard setpoints derive from bounds, so both are re-derived whenever a
bound moves. `baseboard_standby_setpoint` triggers on all four bound helpers and
branches on `input_boolean.backup_heat`: on, each room's comfort midpoint
`(heat_bound + cool_bound) / 2`; off, `heat_bound − 2.5`. The cool bounds are
triggers because the midpoint reads them — a bound moved *during* backup heat
re-derives the midpoint, where the entry edge on its own leaves whatever that
edge wrote.

The off arm is an explicit `state: 'off'` rather than a `default:`, so a
`backup_heat` reading `unknown` or `unavailable` writes no setpoint at all. A
safety flag in an indeterminate state is not grounds to command resistive heat.

Every `climate.set_temperature` inside both arms is gated on a real delta against
that baseboard's own reported target, so a bound change that moves no setpoint
issues no cloud write and one thermostat-card drag of two bounds commands at most
the setpoint it moved. A baseboard reporting no target reads 0 through a
`float(0)` default, below every settable setpoint, so the gate opens and the
write goes through.

The comfort midpoint is rounded half-up onto the baseboards' 0.5 °C step, in the
backup-heat entry automation and in `baseboard_standby_setpoint` alike.
`(heat_bound + cool_bound) / 2` lands on 0.25 steps, which a 0.5-step device
cannot hold and therefore never reports back, so an unrounded midpoint would
leave the delta gate permanently open and rewrite an unchanged setpoint on every
trigger — the same class of defect as the Cielo Fahrenheit grid above.

## Deferred

`number.studio_temperature_offset` (currently 0 °F) would correct the head's
onboard warm bias at source and let the lead return to 0. Whether Cielo applies
it to the control loop or only to the reported value is unverified. It is the
better long-term shape and belongs in the retune, not here.

## Phase 2: retune procedure

After one night with the fixes live and no `switch.studio_dehumidifier`-aligned
spikes in `sensor.studio_control_temperature`, read from the API:

1. Minimum `sensor.studio_control_temperature` against the 19.0 bound.
2. Time from each `switch.studio_power` turn-on to the room actually rising.
3. `climate.studio` onboard `current_temperature` versus the commanded target
   during each on-cycle — the setpoint error the inverter actually sees.

Raise `studio_heat_lead` until (3) stays positive for the first half of a cycle.
The 2026-06-22 design already sanctions 2.0–2.5; the measured onboard offset
suggests 3.0 or higher. The cutoff is unaffected by the lead, so the risk of
raising it is inverter runtime, not overshoot.
