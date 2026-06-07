# Changeover Advisor — Forecast Blend Addendum

**Date:** 2026-06-07
**Status:** Approved design, pending implementation plan
**Amends:** 2026-06-07-changeover-advisor-design.md (Section 1 forecast nomination)

## Why

Deployment (Task 8 step 1) revealed Environment Canada's **hourly** forecast for
`weather.lethbridge` reaches only **24 h**, not the 48 h the original design
integrated over. A pure-hourly window can see ~1 day ahead, which undercuts the
core requirement — "if it is cold now *and* it will be cold for the next 2 days,
switch to heating." The EC **daily** forecast returns **6 days**, each with
`temperature` (daytime high), `templow` (overnight low), and `datetime`.

## Decision — blend two regimes that must agree

The near-term signal and the multi-day signal are computed **independently** and
the advisor only suggests a changeover when they **agree**:

- **Hourly regime** (unchanged, now honestly 24 h): degree-hours over the next
  24 h of hourly forecast → `hourly_candidate` via `candidate_mode`.
- **Daily regime** (new): the next **2** daily entries are each reduced to a
  mean `(temperature + templow) / 2`; those 2 means feed the *same*
  `cooling_degree_hours` / `heating_degree_hours` / `candidate_mode` macros
  (now in °C·day units) → `daily_candidate`.

**Agreement rule:** the advisor's candidate is valid only when
`hourly_candidate == daily_candidate`. This single rule covers every case:

| Hourly | Daily (2-day) | Result |
|---|---|---|
| heating | heating | suggest **heating** — cold now and staying cold ✅ |
| cooling | cooling | suggest **cooling** |
| off | off | suggest **off** (open windows) |
| cooling | off / heating | **no suggestion** — warm blip, not a sustained spell |
| heating | off / cooling | **no suggestion** |

Indoor confirmation (duty-cycle alibi), the 12 h / 24 h holds, the backup-heat
guard, and the `mode != candidate` check are all unchanged — this only makes the
candidate harder to earn.

## Changes by file

### `custom_templates/changeover.jinja`
Add one pure macro, `daily_means(forecast_entries)`, returning the list of
`(temperature + templow) / 2` per entry (null/unparseable fields default to
neutral so a flaky daily entry can't error the sensor, mirroring the existing
null-hour handling). The existing degree-hour and `candidate_mode` macros are
reused as-is for the daily regime.

### `helpers.yaml` (+ live UI)
- New `input_number.changeover_daily_deadband` — min 0, max 10, step 0.5, box,
  unit `°C·day`, **default 1.0** (= 0.5 °C/day past balance over 2 days, the
  daily mirror of the hourly 0.5 °C/h sensitivity).
- `input_number.changeover_deadband` **default changes 24 → 12 °C·h** — the
  hourly window is now 24 h, so 12 °C·h preserves the original ~0.5 °C/h
  sensitivity. (Comment updated; the UI value entered at deployment is 12.)

### `configuration.yaml` — `sensor.changeover_balance`
- Add a second action: `weather.get_forecasts` `type: daily` →
  `response_variable: changeover_daily_forecast` (also `continue_on_error`).
- `availability` now also requires the daily forecast present with ≥ 2 entries.
- New attributes (state stays the hourly `CDH − HDH`): `daily_cdh`, `daily_hdh`,
  `daily_forecast_days`. Computed via `daily_means(...[:2])` then the existing
  degree-hour macros against the same `changeover_balance_point`.

### `automations.yaml` — `heat_pump_mode_advisor`
- New variable `daily_candidate` from `daily_cdh` / `daily_hdh` /
  `changeover_daily_deadband` via `candidate_mode`.
- New condition `{{ candidate == daily_candidate }}` (the agreement gate).
- Notification message gains a short multi-day note (e.g. the daily degree-days)
  so the suggestion explains *why* it's confident.

### Docs
- CLAUDE.md changeover subsection: 24 h hourly window, the agreement gate, the
  new helper.
- Plan Task 8: verify the daily forecast (≥ 2 days, `temperature` + `templow`);
  create `changeover_daily_deadband` (1.0); enter `changeover_deadband` as 12.

## Testing

- **Macro (Level 2):** `daily_means` — normal entries, null/missing field
  neutrality; reuse of `candidate_mode` on daily means needs no new macro test.
- **Sensor (Level 3):** extend `test_changeover_balance_sensor.py` with a daily
  forecast stub; assert `daily_cdh` / `daily_hdh` / `daily_forecast_days`, and
  that a missing daily forecast makes the sensor `unavailable`.
- **Advisor (Level 3):** new tests — agreement → suggests; hourly/daily
  disagreement → no suggestion. Existing advisor tests' `BALANCE_ATTRS` gain
  agreeing `daily_cdh`/`daily_hdh`, and `arrange()` sets
  `changeover_daily_deadband`.

## Out of scope
Synthesizing hourly temps from daily high/low (the rejected "Synthesize"
option); changing the indoor-confirmation or hold logic.
