# Asymmetric per-room heating lead

Date: 2026-06-22
Status: approved, pre-implementation

## Problem

Overnight, the **studio** repeatedly sags to ~18 °C while its heat bound is 19 °C
(a full degree under setpoint) before the heat pump actually delivers heat. The
**office** (small, fast) holds at/above its 19 °C bound without trouble. The
asymmetry is physical: the office is ~1/3 the studio's volume and changes
temperature quickly; the studio is large and slow.

The coordinator's decision to turn the studio head *on* is correct and timely —
it fires off the reliable `sensor.studio_baseboard_current_temperature`. The
failure is downstream: once the head is on, **the head's own onboard controller
decides how hard to run**, comparing its commanded setpoint against its *own*
sensor. That onboard sensor sits in the return airflow and reads warm. Because
the coordinator commands the head to **exactly the bound** (`lead: 0`), the
onboard error is ~0, so the inverter loafs and the room drifts down before the
onboard sensor finally reads cold enough to make the unit pull real capacity.

This is a documented mini-split behavior. Inverter capacity/fan track
setpoint-minus-sensed error (a larger gap → higher capacity); the return-air
sensor reads warmer than the room so the head "appears satisfied when the room
is not"; the community remedy is to **command a higher setpoint** so the inverter
commits, while letting an **external sensor do the real cutoff**. The
coordinator's baseboard sensor already plays that external-cutoff role.

References:
- https://www.greenbuildingadvisor.com/question/mini-split-discharge-temp-and-fan-speed-how-does-it-modulate
- https://cielowigle.com/blog/do-mini-splits-turn-off-when-temperature-is-reached/
- https://community.home-assistant.io/t/mini-split-a-c-with-external-thermostat/571497

## Key insight: lead and cutoff are independent

`lead` sets the **commanded setpoint** handed to the head. The **cutoff** is a
separate mechanism: `room_demand` evaluated against the reliable baseboard
sensor, which ends heat demand at `heat_bound + differential` (studio 19 + 0.5 =
19.5). A positive heating lead therefore makes the head *commit* but does **not**
make the room overshoot — the coordinator still turns the head off at 19.5
regardless of what setpoint was commanded. The lead only changes how hard the
inverter pulls *toward* that cutoff.

The original `lead: 0` rationale (the "over-shoot yo-yo") conflated the
commanded setpoint with the cutoff. That fear only holds if the commanded
setpoint *is* the cutoff; here it is not.

## Design

A fixed, per-room, **heat-only** lead, defined in the coordinator's `variables:`.
No new helper (deliberate: fixed YAML value, retuned via a Developer Tools →
reload Automations). No change to the `head_target` macro.

```yaml
# Per-room heating lead. The slow/large studio's onboard sensor reads warm, so
# commanding the bound itself (lead 0) leaves the inverter loafing and the room
# sags ~1 °C under setpoint before the head commits. A positive heat lead opens
# enough setpoint error to make the inverter pull real capacity. The REAL cutoff
# is unchanged — room_demand against the reliable baseboard sensor at
# heat_bound + differential — so a higher lead does NOT cause overshoot; it only
# changes how hard the head pulls toward that cutoff. Office is small/fast and
# holds fine, so it stays at the bound. Cooling is unaffected (cool lead stays 0).
office_heat_lead: 0
studio_heat_lead: 1.5
office_lead: "{{ office_heat_lead if effective == 'heat' else 0 }}"
studio_lead: "{{ studio_heat_lead if effective == 'heat' else 0 }}"
```

The two `head_target(...)` calls take `office_lead` / `studio_lead` in place of
the shared `lead: 0`. Because the active mode is `cool` (or `idle`) for any
non-heat case, the lead resolves to 0 and cooling behavior is byte-for-byte
unchanged. `head_target` already applies `+lead` for heat and `−lead` for cool,
and is left untouched.

`studio_heat_lead` is the primary tuning knob: start at **1.5**; if the studio
still sags, raise toward 2.0–2.5.

## Scope of edits

1. `automations.yaml`
   - Replace `lead: 0` with the four variables above.
   - Update the rationale comment (currently lines 56–62, the `lead: 0`
     explanation) and the header comment that says "a small lead past the bound".
   - Feed `office_lead` / `studio_lead` into the respective `head_target` calls.
2. `tests/test_hvac_coordinator.py`
   - The Level-3 studio-heat assertion (commanded temp currently == 20 = bound)
     becomes `bound + 1.5`.
   - Add one test asserting the asymmetry: office heat commands its bound,
     studio heat commands bound + studio lead.
   - The office-heat assertion (lead 0) is unchanged.
3. `CLAUDE.md`
   - The `head_target` paragraph states "**`lead` is 0** — the head is commanded
     to the bound itself". Rewrite to describe the asymmetric heat lead (office
     0, studio 1.5), heat-only, and the lead-vs-cutoff independence.

`tests/test_hvac_macros.py` is unchanged (the macro is unchanged).

## Out of scope (YAGNI)

- No cooling lead.
- No new `input_number` helper.
- No change to lockouts, dwell, or differentials.
- The 6-minute studio lockout was considered as a possible secondary contributor
  to the dip but is **not** addressed here — the symptom ("head on but not
  heating") points at the loafing inverter, not the lockout. If a sag *below 19*
  persists *after* this fix, the lockout is the next thing to investigate, as a
  separate change.

## Success criteria

- The studio holds near 19 (cutoff 19.5, recovery before falling materially
  below 19) instead of dipping to ~18.
- No new cooling regressions (cool commands unchanged).
- All existing tests pass; the updated/added coordinator tests pass.
