# Changeover Advisor Forecast Blend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Blend EC's 24 h hourly forecast (near-term) with its 6-day daily forecast (multi-day persistence) so the changeover advisor only suggests when both regimes agree — restoring the "cold now *and* cold for 2 days" requirement that the 24 h hourly cap broke.

**Architecture:** A new pure macro `daily_means` reduces daily forecast entries to mean temps; the existing `cooling_degree_hours`/`heating_degree_hours`/`candidate_mode` macros are reused to derive a `daily_candidate`. `sensor.changeover_balance` gains a second `weather.get_forecasts type: daily` call and exposes `daily_cdh`/`daily_hdh`/`daily_forecast_days` attributes; the advisor computes `daily_candidate` and adds an agreement condition `candidate == daily_candidate`. Spec: `docs/superpowers/specs/2026-06-07-changeover-advisor-blend-addendum.md`.

**Tech Stack:** Home Assistant YAML + Jinja2, pytest, pytest-homeassistant-custom-component (HA 2026.6.1).

**Repo facts the executor needs:**
- Branch `changeover-blend` is checked out. The base feature already merged to main; these are incremental changes on top.
- Test venv requires Python 3.14 via uv; run tests with `.venv/bin/pytest`. Baseline before this plan: **35 passed**.
- The existing balance sensor and advisor are in `configuration.yaml:109-151` and `automations.yaml:444-509` (read them — line numbers may have shifted).
- Degree-hour macros already handle null/non-numeric inputs by defaulting (null forecast temps → neutral). `daily_means` must follow the same fail-safe pattern.
- Daily forecast entry shape (verified live): `{'temperature': <high>, 'templow': <low>, 'datetime': <iso>}`, 6 entries.
- Commit message style: plain imperative, no `feat:` prefix. End commits with the Co-Authored-By trailer.
- `"off"` in YAML must be quoted; daily deadband units are °C·day.

---

### Task 1: `daily_means` macro (TDD)

**Files:**
- Modify: `custom_templates/changeover.jinja` (append)
- Modify: `tests/test_changeover_macros.py` (append)

- [ ] **Step 1: Write the failing tests** — append to `tests/test_changeover_macros.py`:

```python
MEANS_IMPORT = "{% from 'changeover.jinja' import daily_means %}"


def means(hass, entries_literal):
    return render(hass, MEANS_IMPORT + "{{ daily_means(" + entries_literal + ") }}")


async def test_daily_means_basic(hass_repo):
    # (high + low) / 2 per entry
    entries = "[{'temperature': 20, 'templow': 10}, {'temperature': 4, 'templow': -2}]"
    assert means(hass_repo, entries) == [15.0, 1.0]


async def test_daily_means_null_field_is_neutral_skipped(hass_repo):
    # A flaky daily entry with a null field must not error the sensor. The
    # entry collapses to a neutral mean equal to whichever field is present;
    # if both are null it is dropped so it cannot fabricate a degree-day.
    entries = ("[{'temperature': 20, 'templow': 10}, "
               "{'temperature': none, 'templow': none}]")
    assert means(hass_repo, entries) == [15.0]


async def test_daily_means_one_null_field_uses_present(hass_repo):
    # Only templow missing → fall back to the present field (temperature),
    # so the day still contributes its real, known temperature.
    entries = "[{'temperature': 22, 'templow': none}]"
    assert means(hass_repo, entries) == [22.0]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/test_changeover_macros.py -k daily_means -v`
Expected: 3 FAIL (`no name 'daily_means'`).

- [ ] **Step 3: Append the macro to `custom_templates/changeover.jinja`**

```jinja

{# Reduce EC daily forecast entries to one mean temperature each, for the
   multi-day persistence regime. mean = (temperature + templow) / 2. A missing
   field falls back to the present one; an entry with neither is dropped so it
   cannot fabricate a degree-day (mirrors the null-hour neutrality of the
   degree-hour macros). Reuses cooling/heating_degree_hours + candidate_mode
   downstream — no daily-specific degree math needed. #}
{% macro daily_means(entries) -%}
  {%- set ns = namespace(out=[]) -%}
  {%- for e in entries -%}
    {%- set hi = e.temperature -%}
    {%- set lo = e.templow -%}
    {%- set hi_ok = hi is not none and hi == hi | float(none) -%}
    {%- set lo_ok = lo is not none and lo == lo | float(none) -%}
    {%- if hi_ok and lo_ok -%}
      {%- set ns.out = ns.out + [((hi | float) + (lo | float)) / 2] -%}
    {%- elif hi_ok -%}
      {%- set ns.out = ns.out + [hi | float] -%}
    {%- elif lo_ok -%}
      {%- set ns.out = ns.out + [lo | float] -%}
    {%- endif -%}
  {%- endfor -%}
  {{ ns.out }}
{%- endmacro %}
```

Note: `x == x | float(none)` is the HA-Jinja idiom for "is this numeric?" — `float(none)` returns None on unparseable input, and `x == None` is False, so non-numeric/None fields are correctly treated as not-ok. Verify this renders a real Python list (the test asserts `== [15.0, 1.0]`); if native rendering returns a string, the test will catch it — fix the macro (e.g. whitespace control), never the assertion.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_changeover_macros.py -v`
Expected: all prior macro tests + 3 new = pass.

- [ ] **Step 5: Commit**

```bash
git add custom_templates/changeover.jinja tests/test_changeover_macros.py
git commit -m "Add daily_means macro for multi-day forecast regime"
```

---

### Task 2: Helpers — daily deadband + retune hourly deadband (TDD)

**Files:**
- Modify: `helpers.yaml`
- Modify: `tests/test_helpers_yaml.py` (append)

- [ ] **Step 1: Write the failing test** — append to `tests/test_helpers_yaml.py`:

```python
async def test_changeover_daily_deadband_exists(hass_helpers):
    db = hass_helpers.states.get("input_number.changeover_daily_deadband")
    assert db is not None
    assert db.attributes["max"] == 10
    assert db.attributes["unit_of_measurement"] == "°C·day"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/pytest tests/test_helpers_yaml.py -v`
Expected: 1 FAIL (entity None).

- [ ] **Step 3: Edit `helpers.yaml`**

3a. Append to the `input_number:` block, after `changeover_deadband`:

```yaml
  # Daily (multi-day persistence) dead band, in °C·day. Default 1.0 =
  # 0.5 °C/day past balance over the 2-day daily regime — the daily mirror of
  # the hourly 0.5 °C/h sensitivity. Set value 1.0 when created in the UI.
  changeover_daily_deadband:
    name: Changeover Daily Deadband
    min: 0
    max: 10
    step: 0.5
    mode: box
    unit_of_measurement: "°C·day"
    icon: mdi:calendar-expand-horizontal
```

3b. Update the `changeover_deadband` comment (the hourly window is now 24 h):
find the existing comment line above `changeover_balance_point`/`changeover_deadband` and ensure the deadband's intent reads "24 °C·h was for a 48 h window; the live hourly forecast is 24 h, so the deployed value is 12 °C·h (~0.5 °C/h)." The helper's `min`/`max`/`step` are unchanged — only the comment, since the default is set in the UI at deployment. (If a comment edit can't be placed cleanly, add a one-line comment directly above `changeover_deadband:`.)

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_helpers_yaml.py -v`
Expected: all pass (existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git add helpers.yaml tests/test_helpers_yaml.py
git commit -m "Add daily-deadband helper; note hourly deadband retune to 12"
```

---

### Task 3: Balance sensor — daily forecast call + attributes (TDD)

**Files:**
- Modify: `configuration.yaml` (the `sensor.changeover_balance` block)
- Modify: `tests/test_changeover_balance_sensor.py`

- [ ] **Step 1: Extend the test fixture and add tests**

In `tests/test_changeover_balance_sensor.py`, update the `balance` fixture's
`fake_forecast` to serve BOTH forecast types from the `type` the caller
requests, and seed a daily set. Replace the `mode` dict and `fake_forecast`
with:

```python
    mode = {
        "fail": False,
        "temps": [-10.0] * 48,
        "daily": [{"temperature": 2.0, "templow": -8.0}] * 6,  # mean -3 → heating
    }

    async def fake_forecast(call):
        if mode["fail"]:
            raise HomeAssistantError("EC unreachable")
        forecast_type = call.data.get("type")
        if forecast_type == "daily":
            return {"weather.lethbridge": {"forecast": mode["daily"]}}
        return {
            "weather.lethbridge": {
                "forecast": [{"temperature": t} for t in mode["temps"]]
            }
        }
```

Then add these tests (the existing 3 stay; `test_balance_unavailable_when_forecast_fails` still holds because `fail` aborts both calls):

```python
async def test_daily_attributes_present(balance):
    hass, _ = balance
    await fire_hourly(hass)
    state = hass.states.get("sensor.changeover_balance")
    assert state.attributes["daily_forecast_days"] == 2          # clipped to 2
    # 2 daily means of -3.0, balance 16 → hdh (16 - -3) * 2 = 38, cdh 0
    assert state.attributes["daily_hdh"] == 38.0
    assert state.attributes["daily_cdh"] == 0.0


async def test_unavailable_when_daily_forecast_empty(balance):
    hass, mode = balance
    mode["daily"] = []
    await fire_hourly(hass)
    assert hass.states.get("sensor.changeover_balance").state == "unavailable"
```

- [ ] **Step 2: Run to verify the two new tests fail**

Run: `.venv/bin/pytest tests/test_changeover_balance_sensor.py -v`
Expected: `test_daily_attributes_present` and `test_unavailable_when_daily_forecast_empty` FAIL (attrs missing / sensor still available); the original 3 still pass.

- [ ] **Step 3: Edit the `sensor.changeover_balance` block in `configuration.yaml`**

3a. Add a second action after the hourly `weather.get_forecasts` (inside the same `actions:` list):

```yaml
      - action: weather.get_forecasts
        data:
          type: daily
        target:
          entity_id: weather.lethbridge
        response_variable: changeover_daily_forecast
        continue_on_error: true
```

3b. Replace the `availability:` template so it also requires the daily forecast with ≥ 2 entries:

```yaml
        availability: >-
          {{ changeover_forecast is defined
             and (changeover_forecast['weather.lethbridge']['forecast'] | count) > 0
             and changeover_daily_forecast is defined
             and (changeover_daily_forecast['weather.lethbridge']['forecast'] | count) >= 2 }}
```

3c. Add three attributes alongside the existing `cdh`/`hdh`/`forecast_hours` (inside the `attributes:` mapping):

```yaml
          daily_cdh: >-
            {% from 'changeover.jinja' import daily_means, cooling_degree_hours %}
            {% set means = daily_means(
                 changeover_daily_forecast['weather.lethbridge']['forecast'][:2]) | from_json %}
            {{ cooling_degree_hours(means,
                 states('input_number.changeover_balance_point') | float(16)) | float }}
          daily_hdh: >-
            {% from 'changeover.jinja' import daily_means, heating_degree_hours %}
            {% set means = daily_means(
                 changeover_daily_forecast['weather.lethbridge']['forecast'][:2]) | from_json %}
            {{ heating_degree_hours(means,
                 states('input_number.changeover_balance_point') | float(16)) | float }}
          daily_forecast_days: >-
            {{ changeover_daily_forecast['weather.lethbridge']['forecast'][:2] | count }}
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_changeover_balance_sensor.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/pytest -v`
Expected: all pass (38 + the 3 macro + 1 helper + 2 sensor added across Tasks 1-3 → recount; just confirm green, no failures).

- [ ] **Step 6: Commit**

```bash
git add configuration.yaml tests/test_changeover_balance_sensor.py
git commit -m "Add daily forecast call and daily degree-day attributes to balance sensor"
```

---

### Task 4: Advisor — daily_candidate variable + agreement gate (TDD)

**Files:**
- Modify: `automations.yaml` (the `heat_pump_mode_advisor` block)
- Modify: `tests/test_advisor_automations.py`

- [ ] **Step 1: Update existing tests' fixtures + add agreement tests**

In `tests/test_advisor_automations.py`:

1a. Extend `BALANCE_ATTRS` so the default scene's daily regime AGREES with the hourly cooling candidate, and so existing tests keep passing:

```python
BALANCE_ATTRS = {
    "cdh": 50.0, "hdh": 6.0, "forecast_hours": 48,
    "daily_cdh": 4.0, "daily_hdh": 0.0, "daily_forecast_days": 2,
}
```

1b. In `arrange()`, add `changeover_daily_deadband` to the `input_number.set_value` loop (so `candidate_mode(4, 0, 1.0)` → cooling, agreeing):

```python
        ("input_number.changeover_daily_deadband", 1.0),
```

1c. Add two new tests:

```python
async def test_no_suggestion_when_daily_disagrees(advisor):
    hass, notify_calls, _ = advisor
    # Hourly says cooling (cdh 50/hdh 6) but the 2-day daily trend is cold
    # (daily_hdh dominant) → regimes disagree → no suggestion.
    await arrange(hass)
    hass.states.async_set(
        "sensor.changeover_balance", "44",
        {**BALANCE_ATTRS, "daily_cdh": 0.0, "daily_hdh": 8.0},
    )
    await run_advisor(hass)
    assert notify_calls == []


async def test_suggests_when_both_regimes_agree(advisor):
    hass, notify_calls, _ = advisor
    # Explicit agreement scene (mirrors the default arrange, kept for clarity).
    await arrange(hass)
    await run_advisor(hass)
    assert len(notify_calls) == 1
    assert notify_calls[0].data["data"]["actions"][0]["action"] == "CHANGEOVER_ACCEPT_cooling"
```

Note: after `arrange()` calls `hass.states.async_set('sensor.changeover_balance', ...)` with the default `BALANCE_ATTRS`, `test_no_suggestion_when_daily_disagrees` overrides it; ensure the override happens AFTER arrange (it does, above). Keep `await hass.async_block_till_done()` semantics from `run_advisor`.

- [ ] **Step 2: Run to verify the disagreement test fails**

Run: `.venv/bin/pytest tests/test_advisor_automations.py -v`
Expected: `test_no_suggestion_when_daily_disagrees` FAILS (advisor still suggests — no agreement gate yet). `test_suggests_when_both_regimes_agree` passes. Some existing tests may now also fail if `daily_candidate` is undefined and the new condition isn't there yet — that's fine, they go green in Step 4.

- [ ] **Step 3: Edit `heat_pump_mode_advisor` in `automations.yaml`**

3a. Add a `daily_candidate` variable after the `candidate` variable (in the `variables:` block):

```yaml
    daily_candidate: >-
      {% from 'changeover.jinja' import candidate_mode %}
      {{- candidate_mode(
            state_attr('sensor.changeover_balance', 'daily_cdh') | float(0),
            state_attr('sensor.changeover_balance', 'daily_hdh') | float(0),
            states('input_number.changeover_daily_deadband') | float(1.0)) -}}
```

3b. Add the agreement condition immediately after the `candidate != current_mode` condition:

```yaml
  - "{{ candidate == daily_candidate }}"
```

3c. Update the notification `message` to mention the multi-day agreement. Replace the existing message body with:

```yaml
      message: >-
        Next 24 h: {{ cdh | round(0) | int }} cooling vs {{ hdh | round(0) | int }}
        heating degree-hours, and the 2-day trend agrees
        ({{ state_attr('sensor.changeover_balance', 'daily_cdh') | round(0) | int }} vs
        {{ state_attr('sensor.changeover_balance', 'daily_hdh') | round(0) | int }} °C·day).
        Office 2 h mean {{ states('sensor.office_temperature_2h_mean') }} °C, studio
        1 h mean {{ states('sensor.studio_temperature_1h_mean') }} °C. Switch to
        {{ candidate }}?
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/pytest tests/test_advisor_automations.py -v`
Expected: all advisor tests pass (existing + 2 new).

- [ ] **Step 5: Run full suite**

Run: `.venv/bin/pytest -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add automations.yaml tests/test_advisor_automations.py
git commit -m "Gate advisor on hourly/daily regime agreement"
```

---

### Task 5: Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `automations.yaml` (the `# Changeover advisor` banner comment) and `configuration.yaml` (balance sensor comment) — fix the stale "48 h" references

- [ ] **Step 1: Fix stale 48 h references**

In `automations.yaml` the `# Changeover advisor` banner says "from 48 h of EC hourly forecast degree-hours" — change to "from 24 h of EC hourly forecast degree-hours plus a 2-day daily-forecast agreement gate". In `configuration.yaml` the balance sensor comment says "degree-hour balance over the next 48 h" — change to "over the next 24 h of EC hourly forecast, plus a 2-day daily regime (attributes daily_cdh/daily_hdh)".

- [ ] **Step 2: Update the CLAUDE.md changeover subsection**

In the "### Changeover advisor (suggest + confirm)" subsection, replace the first paragraph's "next 48 h of Environment Canada hourly forecast" with the blend description: hourly degree-hours over 24 h give an hourly candidate; the next 2 daily entries (mean of high/low) give a daily candidate via the same macros; the advisor suggests only when `hourly_candidate == daily_candidate` (the agreement gate). Mention the new `input_number.changeover_daily_deadband` (°C·day) and that `changeover_deadband` deploys as 12 (24 h window). Keep it to 3-4 sentences, matching the existing terse voice.

- [ ] **Step 3: Add the daily helper to the helpers-status sentence**

Wherever CLAUDE.md lists the changeover helpers (the humidity-helpers paragraph extension from the prior task), add `input_number.changeover_daily_deadband` to that list.

- [ ] **Step 4: Run the suite (docs change, but confirm nothing broke)**

Run: `.venv/bin/pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md automations.yaml configuration.yaml
git commit -m "Document forecast blend; fix stale 48 h references"
```

---

### Task 6: Update the live deployment checklist (plan Task 8 of the base plan)

**Files:**
- Modify: `docs/superpowers/plans/2026-06-07-changeover-advisor.md` (Task 8 section)

- [ ] **Step 1: Amend Task 8 in the base plan**

- Step 1 (verify weather entity): add verifying `weather.get_forecasts type: daily` returns ≥ 2 days with `temperature` + `templow`.
- Step 2 (create UI helpers): change `changeover_deadband` set value from **24 to 12**; add new helper `changeover_daily_deadband` — min 0, max 10, step 0.5, box, °C·day, **set value 1.0**.
- Step 3 (sync files): unchanged list (configuration.yaml, automations.yaml, changeover.jinja) — all already in the sync set.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/plans/2026-06-07-changeover-advisor.md
git commit -m "Update deployment checklist for forecast blend (daily deadband, deadband=12)"
```

---

## Self-review notes

- **Spec coverage:** `daily_means` macro (T1, with null-field neutrality), daily-deadband helper + hourly retune note (T2), daily forecast call + attributes + availability (T3), `daily_candidate` + agreement gate + message (T4), docs incl. stale-48h fixes (T5), deployment checklist (T6).
- **Type consistency:** `daily_cdh`/`daily_hdh` are floats (°C·day) on both the sensor (T3) and the advisor's `candidate_mode` call (T4); `daily_means` returns a list consumed by `cooling_degree_hours`/`heating_degree_hours`; `changeover_daily_deadband` default 1.0 used identically in T2/T3-tests/T4.
- **Reuse:** no new degree math — `candidate_mode` and the degree-hour macros are reused for the daily regime; only `daily_means` is new.
- **Known intentional gaps:** the daily regime, like the hourly, isn't exercised against a live recorder; covered by the shadow phase. The agreement gate's interaction with confirmation/holds is unchanged and already tested.
