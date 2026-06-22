# Asymmetric Per-Room Heating Lead Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the slow studio head actually commit to heating instead of loafing at the bound, by commanding its onboard controller a fixed degree above the heat bound while the reliable baseboard-sensor cutoff stays unchanged.

**Architecture:** Replace the coordinator's single `lead: 0` variable with per-room, heat-only lead variables (office 0, studio 1.5) computed in `automations.yaml`'s `variables:` block. The `head_target` Jinja macro is untouched — it already applies `+lead` for heat / `−lead` for cool; we simply feed it a per-room value that is non-zero only for studio heating. The cutoff (`room_demand` against the baseboard sensor at `heat_bound + differential`) is independent of `lead`, so a positive lead changes how hard the inverter pulls but not where the head shuts off — no overshoot.

**Tech Stack:** Home Assistant YAML automations + Jinja `custom_templates/hvac.jinja`; pytest via `pytest-homeassistant-custom-component` (run with `.venv/bin/pytest`).

## Global Constraints

- Python ≥ 3.14; run tests with `.venv/bin/pytest` (env set up per CLAUDE.md "Tests").
- Per-room entity naming `<domain>.<room>_<thing>` — do not introduce new entity names here (this change adds no helpers; leads are plain Jinja `variables:`).
- `head_target` macro and `tests/test_hvac_macros.py` MUST remain unchanged (the macro is correct; only the values fed to it change).
- Cooling behavior MUST remain byte-for-byte unchanged (lead resolves to 0 for any non-heat mode).
- Final values: `office_heat_lead: 0`, `studio_heat_lead: 1.5`.
- Test fixtures (`tests/test_hvac_coordinator.py` `DEFAULTS`) use `studio_heat_bound = 20`, so the studio heat command becomes `20 + 1.5 = 21.5`; `office_heat_bound = 20` stays `20`.

---

### Task 1: Asymmetric heating lead in the coordinator

**Files:**
- Modify: `tests/test_hvac_coordinator.py` (assertions at lines ~123 and ~194; add one new test)
- Modify: `automations.yaml` (the `lead: 0` variable + comment, lines ~56–62; the two `head_target(...)` calls, lines ~98 and ~101; header comment line ~10)
- Modify: `CLAUDE.md` (the `head_target` bullet in the coordinator section)

**Interfaces:**
- Consumes: `head_target(mode, heat_bound, cool_bound, lead)` from `custom_templates/hvac.jinja` — unchanged. For `mode == 'heat'` returns `clamp(heat_bound + lead, 17, 30)`; for `mode == 'cool'` returns `clamp(cool_bound − lead, 17, 30)`.
- Produces: new coordinator `variables:` `office_heat_lead` (0), `studio_heat_lead` (1.5), `office_lead`, `studio_lead`. `office_lead`/`studio_lead` evaluate to the room's heat lead when `effective == 'heat'`, else `0`. These feed the `office_target_raw` / `studio_target_raw` `head_target` calls.

- [ ] **Step 1: Update the two existing studio-heat assertions to expect bound + lead (failing test)**

In `tests/test_hvac_coordinator.py`, change the assertion in `test_cold_studio_heats_studio_only` (currently line ~123):

```python
    heat_calls = [c for c in calls["temp"] if c.data.get("hvac_mode") == "heat"]
    assert heat_calls and heat_calls[0].data["temperature"] == 21.5  # studio heat_bound 20 + studio lead 1.5
```

And in `test_drift_resends_target_without_toggle` (currently line ~194):

```python
    assert any(c.data.get("temperature") == 21.5 for c in calls["temp"])  # studio heat_bound 20 + studio lead 1.5
```

- [ ] **Step 2: Add a new test asserting the office/studio asymmetry**

Append to `tests/test_hvac_coordinator.py`:

```python
async def test_heat_lead_is_asymmetric_office_zero_studio_positive(coordinator):
    hass, calls = coordinator
    # Both rooms cold → system heats, both heads on. Office (fast) is commanded
    # its bound; studio (slow) is commanded its bound + 1.5 so the inverter commits.
    await arrange(hass, office_temp=18, studio_temp=18)
    await run(hass)
    assert hass.states.get("input_select.system_hvac_mode").state == "heat"
    office_heat = [c for c in calls["temp"]
                   if "climate.office" in _entities(c) and c.data.get("hvac_mode") == "heat"]
    studio_heat = [c for c in calls["temp"]
                   if "climate.studio" in _entities(c) and c.data.get("hvac_mode") == "heat"]
    assert office_heat and office_heat[0].data["temperature"] == 20    # office bound 20, lead 0
    assert studio_heat and studio_heat[0].data["temperature"] == 21.5  # studio bound 20 + lead 1.5
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_hvac_coordinator.py -k "cold_studio_heats or drift_resends or heat_lead_is_asymmetric" -v`
Expected: FAIL — current YAML commands `20` for the studio (lead 0), so the three assertions expecting `21.5` fail (the office `20` assertion in the new test passes).

- [ ] **Step 4: Replace `lead: 0` with the per-room lead variables in `automations.yaml`**

In `automations.yaml`, replace the comment block + `lead: 0` (currently lines ~56–62):

```yaml
    # Command each head to the bound itself (no lead past it). The head's own
    # sensor is unreliable and state-dependent (off: reads refrigerant-pipe temp
    # driven by the other head; running: converges to room temp). Steering past
    # the bound made a running head drive the room well past it (the over-cool
    # yo-yo). At the bound, a running head eases off near the bound on its own,
    # and the baseboard backstop (prompt turn-off) catches the startup transient.
    lead: 0
```

with:

```yaml
    # Per-room HEATING lead (cooling unaffected). The large/slow studio's onboard
    # sensor reads warm (it sits in the return airflow), so commanding the bound
    # itself leaves the inverter loafing and the room sags ~1 C under setpoint
    # before the head commits. A positive heat lead opens enough setpoint error to
    # make the inverter pull real capacity. This is SAFE because lead != cutoff:
    # the real cutoff is room_demand against the reliable baseboard sensor at
    # heat_bound + differential (studio 19.5), independent of the commanded
    # setpoint — so a higher lead changes how hard the head pulls, NOT where it
    # shuts off. The small/fast office holds fine, so it stays at its bound.
    # Tuning knob: raise studio_heat_lead toward 2.0-2.5 if the studio still sags.
    office_heat_lead: 0
    studio_heat_lead: 1.5
    office_lead: "{{ office_heat_lead if effective == 'heat' else 0 }}"
    studio_lead: "{{ studio_heat_lead if effective == 'heat' else 0 }}"
```

- [ ] **Step 5: Feed the per-room leads into the two `head_target` calls**

In `automations.yaml`, change the `office_target_raw` call (currently line ~98) from `lead` to `office_lead`:

```yaml
    office_target_raw: >-
      {% from 'hvac.jinja' import head_target %}
      {{- head_target(effective, office_hb, office_cb, office_lead) -}}
```

and the `studio_target_raw` call (currently line ~101) from `lead` to `studio_lead`:

```yaml
    studio_target_raw: >-
      {% from 'hvac.jinja' import head_target %}
      {{- head_target(effective, studio_hb, studio_cb, studio_lead) -}}
```

- [ ] **Step 6: Update the file header comment**

In `automations.yaml`, the header comment (line ~10) currently reads:

```
# drives each head's power switch + climate target toward its
# bound (a small lead past the bound keeps the inverter
# committed). Short-cycle protection comes from per-head lockout
```

Change the parenthetical to reflect the heat-only asymmetric lead:

```
# drives each head's power switch + climate target toward its
# bound (a per-room heating lead — studio above the bound, office
# at it — keeps the inverter committed; the baseboard sensor does
# the real cutoff). Short-cycle protection comes from per-head lockout
```

- [ ] **Step 7: Run the full test suite to verify everything passes**

Run: `.venv/bin/pytest`
Expected: PASS — all tests green, including the three updated/added assertions and the untouched `tests/test_hvac_macros.py`.

- [ ] **Step 8: Update CLAUDE.md**

In `CLAUDE.md`, the `head_target` bullet in the "ecobee-style HVAC coordinator" section currently states `**lead is 0** — the head is commanded to the bound itself, *not* past it`. Replace that bullet's lead discussion to describe the asymmetric heat lead. Replace:

```
- `head_target(mode, heat_bound, cool_bound, lead)` → the temperature to command a head, clamped to `[17, 30]`. **`lead` is 0** — the head is commanded to the bound itself, *not* past it. The head's onboard sensor is unreliable and state-dependent (off: it reads refrigerant-pipe temp driven by the *other* head on the shared compressor; running: the fan converges it toward room temp), so we never steer past the bound — a running head would drive the room well past it (the over-cool yo-yo). At the bound, a running head eases off near the bound on its own once its sensor converges; the coordinator does the **real cutoff** against the reliable baseboard sensor as the backstop.
```

with:

```
- `head_target(mode, heat_bound, cool_bound, lead)` → the temperature to command a head, clamped to `[17, 30]`. The `lead` is a **per-room, heat-only** offset set in the coordinator's `variables:` (`office_heat_lead` 0, `studio_heat_lead` 1.5; cooling always uses 0). The head's onboard sensor is unreliable and reads warm (it sits in the return airflow; when off it reads refrigerant-pipe temp driven by the *other* head), so at `lead 0` the large/slow studio's inverter loafs and the room sags ~1 °C under setpoint before the head commits. A positive heat lead opens enough onboard setpoint error to make the inverter pull real capacity. This does **not** cause overshoot: `lead` sets the commanded setpoint, but the **real cutoff** is `room_demand` against the reliable baseboard sensor at `heat_bound + differential` — independent of the commanded setpoint — so a higher lead changes how hard the head pulls, not where it shuts off. The small/fast office holds fine and stays at its bound. (The old `lead 0` "over-cool yo-yo" concern conflated the commanded setpoint with the cutoff; it only applied when the two were assumed equal.)
```

- [ ] **Step 9: Commit**

```bash
git add automations.yaml tests/test_hvac_coordinator.py CLAUDE.md
git commit -m "Add asymmetric per-room heating lead (studio 1.5, office 0)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Notes for the deploy (not part of the code change)

After merging, sync the files to the HA instance and reload Automations
(Developer Tools → YAML → Reload Automations, or restart). `studio_heat_lead`
is the primary tuning knob — start at 1.5 and watch an overnight chart; raise
toward 2.0–2.5 if the studio still sags below 19.
