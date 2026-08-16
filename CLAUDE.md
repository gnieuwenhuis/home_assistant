# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **Home Assistant configuration** for a two-room space (office + studio), versioned in git. The goal is to mirror the live HA configuration here, with the exceptions called out below.

README's **Repository layout** table lists every tracked path. What it does not
say, and what matters here:

- `ha-version.txt` — the HA release the live box runs, on one bare line. `tests/test_version_pin.py` asserts the `requirements-dev.txt` pin, its comment, and the *installed* harness all agree with it.
- `helpers.yaml` — wired into `configuration.yaml` as a package, not per-domain includes (see "Helpers migration" below)
- `README.md` — its **Troubleshooting** section indexes the states that look like faults but aren't (timers mid-run, the mode helper vs. a running head, the coordinator short-circuiting on an unavailable entity) — start there when a symptom is reported
- `blueprints/` — HA's stock shipped blueprints, untouched

`docs/superpowers/specs/` and `docs/superpowers/plans/` are the dated design record.
Every plan there is merged and none of their `- [ ]` checkboxes are ticked, so
checkbox state is not a to-do signal. The changeover advisor
(`2026-06-07-changeover-advisor*`, both plan and spec) was built and then removed in
`f2d051b`; the ecobee coordinator replaces it. Don't resurrect it.

Not tracked — the entries that matter (see `.gitignore` for the full list):

- `secrets.yaml` — real credentials. Commit only the `.example`.
- `.env` — holds `HOME_ASSISTANT_TOKEN`, a live admin-scoped credential. Commit only the `.example`. Distinct from `secrets.yaml`: `secrets.yaml` feeds `!secret` lookups on the HA host, `.env` is read by tooling on *this* machine and HA never sees it.
- `home-assistant.log*`, `home-assistant_v2.db*`, `.HA_VERSION`, `.uuid`, `deps/`, `tts/`, `image/`, `.cloud/` — HA runtime artifacts
- `.storage/` — HA's internal state store; rewritten constantly, and `.storage/auth*` holds tokens
- `themes/` — the stock `frontend: themes:` include in `configuration.yaml`. Absent here and on a fresh HA install alike: `!include_dir_merge_named` on a missing directory loads as `{}` with no error or warning.

External entities that automations reference but that are defined elsewhere (Zigbee, Z-Wave, and weather integrations, mobile companion app): `sensor.lethbridge_temperature` (outdoor, drives backup heat), `sensor.tz3000_utwgoauk_snzb_02_humidity`, `switch.studio_dehumidifier` (dehumidifier switch), `switch.studio_humidifier_socket_1` (humidifier plug), `switch.eva_lamp_socket_1` (Eva lamp plug), `mobile_app_pixel_8`. Don't assume an entity is undefined just because it isn't grep-able locally.

## Tests

`pytest` covers the HVAC coordinator, the humidity controller, and the
`helpers.yaml` values. Level 2 tests render the `custom_templates/*.jinja` macros
against a real HA template engine (`pytest-homeassistant-custom-component`) —
heat/cool/idle resolution, the heating-wins conflict, differential hysteresis,
target clamps, Fahrenheit-grid snapping, and the studio slew filter
(`tests/test_slew_filter.py`). Level 3 tests load the `hvac_coordinator`,
`studio_humidity_controller` and `baseboard_standby_setpoint` automations **from
the real YAML files** and exercise their conditions and actions against mocked
services (lockout blocking a re-toggle, master enable / backup heat forcing both
heads off, conflict resolving to heat, the cross-device cooldown directions, the
both-on safety, and both arms of the baseboard setpoint branch). Each test
drives one run via `automation.trigger` with `skip_condition: False`; the
automation is turned **off** first, so trigger blocks are schema-validated at
setup but never fire — the 5-minute heartbeat and the `timer.finished` re-runs
have no behavioral coverage. `tests/test_eva_lamp_auto_off.py` is the exception:
it leaves `eva_lamp_auto_off` **enabled** and drives real state changes carrying
an explicit `Context`, which is what that automation's manual-vs-automation gate
reads and what `automation.trigger` cannot supply — so it is also the repo's only
coverage of a trigger block firing. `tests/test_automations_yaml.py` carries both
the whole-file schema load and the `baseboard_standby_setpoint` behaviour — each
arm's commanded values, the per-baseboard delta gate, and the midpoint's half-up
rounding to the 0.5 °C step — plus two pinning tests holding the four copies of
the `− 2.5` standby offset and the four copies of the comfort midpoint identical
across the automations that spell them. Its **known gap**: nothing pins the
`state: 'off'` guard on the standby arm, so a mutant replacing it with an
unconditional catch-all passes the suite. What the guard buys is that an
indeterminate `backup_heat` writes no setpoint; an `input_boolean` always
restores to a boolean, so this is coverage owed rather than a live risk.
`tests/test_helpers_yaml.py` validates `helpers.yaml`
against a real HA setup — bounds, differentials, the tuned `initial:` values,
`system_hvac_mode` options, the timers, and `test_obsolete_helpers_removed`, which
keeps retired pre-ecobee helpers from creeping back.

```sh
uv python install 3.14                       # once; HA 2026.8 needs Python ≥ 3.14
uv venv .venv --python 3.14 --seed
.venv/bin/pip install -r requirements-dev.txt   # keep pinned to the live HA version
.venv/bin/pytest
```

`.github/workflows/ci.yml` runs the same suite on every pull request and on
`main`, alongside yamllint (`.yamllint.yml`, over `automations.yaml`,
`helpers.yaml`, `configuration.yaml`) and actionlint. There is no other build
step. A merge to `main` reaches the box on its own (see "Deployment").

A deploy restarts HA, which applies every config file at once. The reload
services each cover one slice of that: `automation.reload` for
`automations.yaml`, `template.reload` for the `template:` block in
`configuration.yaml`, and **`homeassistant.reload_custom_templates` for
`custom_templates/hvac.jinja`** — HA holds custom Jinja in an in-memory loader,
so an edited macro keeps rendering its old body, silently and with no error,
until that service runs. `homeassistant.reload_all` covers all three (it aborts
if the config is invalid).

## Deployment

`main` is what the box runs, and a merged config change reaches live hardware on
the Git pull add-on's next poll, reviewed by nothing but CI. README's **How
changes reach the box** holds the mechanism: the stage timings, what survives the
reset, the box-first rules for `!secret` keys and entity renames, and the
split-state failure a deploy shows when HA's config check rejects the new commit.
**Read that section before changing anything that deploys.** Its **Rolling back**
subsection covers driving the add-on from the host, including the Supervisor
panel 404 and the add-on quirks (`ha addons` has no `options` subcommand;
`repository` is compared to `origin` as a literal string).

Two agent-facing points README does not carry:

- Read drift as `git diff origin/main`, explicitly. A bare `git diff` compares
  against `HEAD`, which can sit on an old commit and read as "in sync" while the
  working tree is many files behind. Either spelling proves file drift, not
  runtime drift: a hand-edit that was reloaded before the reset discarded it
  leaves the running instance ahead of every file on disk.
- The add-on's `repeat.interval` is in **seconds** (`300`) — a bare `5` would
  re-checkout `/config` twelve times a minute.

The merge gate is the ruleset on `main`, active, GitHub's id `20613372`, its
payload recorded in `.github/rulesets/main.json`. That file records what was
applied and nothing keeps it in step afterwards — read the live rules with `gh
api repos/gnieuwenhuis/home_assistant_config/rulesets/20613372`. **The two
required contexts are the job names in `.github/workflows/ci.yml`** — renaming a
job disarms the gate silently until the ruleset is updated to match.

The design in `docs/superpowers/specs/2026-08-09-cicd-github-actions-design.md`
also specifies a `workflows` rule pinning `.github/workflows/ci.yml` by path.
GitHub rejects it with a `422` on this repository: Required Workflows is an
organization-level feature and this repository is user-owned. It is unavailable
rather than misconfigured — the call cannot succeed, so don't retry it.

## Live Home Assistant API access

A Home Assistant **long-lived access token** is available to agents in `.env` at
the repo root, under the key `HOME_ASSISTANT_TOKEN`. The file is gitignored;
`.env.example` is the tracked template. The base URL is **not** in `.env` — it is
`http://homeassistant.local:8123`. Token generation is documented for humans in
README.md ("Talking to the live Home Assistant").

Load it into the environment rather than interpolating it into a command, so the
value stays out of transcripts, logs, and shell history:

```sh
set -a; . ./.env; set +a
curl -s -H "Authorization: Bearer $HOME_ASSISTANT_TOKEN" \
  http://homeassistant.local:8123/api/states/input_select.system_hvac_mode
```

Never `cat` or `echo` `.env`, never copy the token into a file, a commit, or a
message to the user, and never send it anywhere other than
`homeassistant.local`. To confirm the key is present without revealing it, grep
for the key name.

**This reaches the real house.** The entities behind this API are physical
hardware — two heat-pump heads on a shared compressor, two baseboards, two Tuya
plugs and a Z-Wave switch. Reads are free; writes move equipment.

**Read without asking:**

- `GET /api/states/<entity_id>` — one entity's state and attributes
- `GET /api/states` — everything (large; prefer a specific entity)
- `GET /api/config` — HA version, and whether it is `RUNNING`
- `GET /api/history/period/<ISO8601>?filter_entity_id=<entity_id>` — how a value actually moved, which is how to check a tuning claim
- `GET /api/logbook/<ISO8601>?entity=<entity_id>` — coordinator runs, head toggles, and timer arms in order, for reconstructing a short-cycle or a flap
- `POST /api/template` with `{"template": "..."}` — renders against live state

The two time-series endpoints spell their filter differently — `filter_entity_id`
for history, **`entity`** for logbook — and each ignores the other's spelling
silently instead of erroring, returning the whole instance. A logbook response
far larger than the entity could produce means the filter was dropped, not that
the entity was busy. (`/api/error_log` does not exist on this version; it 404s.)

`POST /api/template` is the highest-value one here: it is the only way to
evaluate a `custom_templates/hvac.jinja` macro against real sensor values
without deploying. It renders and returns; it changes nothing. It renders from
HA's **in-memory** copy of the macros, so it reports what the live instance
currently does, not what an edited working-tree file says.

**Ask the user before any of these**, every time — approval for one does not
carry to the next:

- `POST /api/services/<domain>/<service>` — covers the reload services, which
  deploy config changes, and any `climate.*` / `switch.*` call, which commands
  hardware
- `POST /api/states/<entity_id>` — overwrites HA's stored state, desynchronizing
  it from the device until the integration next polls

Deploying is never an agent's call: `main` is the only sanctioned path to the box
(see "Deployment"). A reload service re-applies whatever `/config` holds at that
moment — a hand-edit on the box included — onto live hardware, ahead of CI, review
and the add-on's next poll.

### The WebSocket API

The **entity and device registries**, the **Lovelace dashboard configs**, the
**energy dashboard prefs**, and the **recorder's statistic metadata** are absent
from REST and live only behind `http://homeassistant.local:8123/api/websocket` —
the protocol, the readable message types, and the `.local` resolver and IPv6
gotchas are in the `ha-websocket-api` skill. Every write there
(`config/entity_registry/update`, `config/device_registry/update`,
`lovelace/config/save`, `energy/save_prefs`) needs the user's approval, every
time, and approval for one does not carry to the next.

## Custom integrations (HACS)

Four HACS packages the tracked config depends on but does not vendor —
`neviweb130` (baseboards), `cielo_home` (heat-pump heads), Climate Template (the
thermostat facade), and apexcharts-card. The install list, and why the Lovelace
dashboards cannot be restored from this repo at all, are in
`.claude/skills/ha-hacs-restore/SKILL.md` — read the file directly. It is a
from-scratch restore reference only; this instance is already set up, so the
skill is switched off in `.claude/settings.local.json` and will not be offered.

## Helpers migration

`helpers.yaml` is wired into `configuration.yaml` as a **package**:

```yaml
homeassistant:
  packages:
    helpers: !include helpers.yaml
```

The whole file (its `input_number:` / `input_boolean:` / `input_select:` / `timer:` top-level keys) merges into the config in one shot — no per-domain `!include` lines, and the single-file shape is what `tests/conftest.py` loads, so it stays the source of truth for tests too. (Don't use `input_number: !include helpers.yaml` per-domain — that pastes all four domain keys under each domain and is invalid.)

`helpers.yaml` is the sole source of truth for these entities; no UI-defined copies compete for their entity IDs. Edit there, not in the UI, and apply with a Developer Tools → YAML domain reload (Input Number / Input Boolean / Input Select / Timer) or a restart.

The HVAC helpers, all defined in `helpers.yaml`:

- `input_number.<room>_heat_bound` / `<room>_cool_bound` — the two per-room setpoints (lower / upper), range `[17, 30]`. These four deliberately carry no `initial:`: the thermostat facade writes them at runtime, and `initial:` would short-circuit restore on every restart and reload, reverting whatever the user dialed in.
- `input_number.<room>_temp_differential` — per-room hysteresis; the values ship as `initial:` in `helpers.yaml` (office 1.0, studio 0.5).
- `input_boolean.hvac_enable` — master on/off.
- `input_select.system_hvac_mode` — the single resolved system mode (`heat` / `cool` / `idle` / `off`), written only by the coordinator.
- `timer.mode_min_dwell` (15 min) — minimum heat↔cool dwell.
- `timer.office_head_lockout` (8 min) / `timer.studio_head_lockout` (6 min) — per-head short-cycle lockouts.

## Architecture

### Two rooms, two device pairs per room

Each room has:

1. A **Sinopé Wi-Fi baseboard heater** via the `neviweb130` integration — `climate.neviweb130_climate_th1123wf` (office) / `th1124wf` (studio). Provides `current_temperature`, `hourly_kwh`, and in cold-weather backup mode actually does the heating.
2. A **heat-pump head** (mini-split) controlled via the `cielo_home` HACS integration. Each unit exposes both a `climate` entity (`climate.office`, `climate.studio`) and a power `switch` (`switch.office_power`, `switch.studio_power`) — same physical device, two entities. The HVAC coordinator references these by entity name (`climate.office` / `climate.studio` for the climate side; `switch.office_power` / `switch.studio_power` for the power switch). The two heads share **one outdoor compressor** — a multi-split — so they can never run in opposite modes at the same time (see below).

Over both rooms sits a **Climate Template** facade — `climate.office_thermostat` / `climate.studio_thermostat`, defined in the `climate:` block of `configuration.yaml`. It is display and entry only, for the standard HA Thermostat card's ecobee-style dual-setpoint dial, and issues no Cielo calls itself; all control stays in the coordinator. Which fields are per-room and which are global: `current_temperature` (the office's baseboard sensor; the studio's filtered `sensor.studio_control_temperature`), both bound helpers, and `hvac_action` (gated on that room's `switch.<room>_power`) are per-room; `hvac_mode` / `set_hvac_mode` both read and write the single `input_boolean.hvac_enable`, so `off` on either tile is a system-wide off and the other tile displays `off` too.

Independent of the HVAC loop, both in the **studio**, sharing one Zigbee humidity sensor:

- **Dehumidifier** — a **Zooz ZEN15** 15 A appliance switch (device `93bb9684cf6a9114c07d9d502ddc35a2`) on the `zwave_js` integration: `switch.studio_dehumidifier`. It also reports W / A / V / kWh (`sensor.studio_dehumidifier_electric_consumption_*`) and an over-current binary sensor; nothing here consumes those yet.
- **Humidifier** — a Tuya "Mini Plug" (device `60211ed7b46e92fd6dcadf60d8087fd0`) on the Tuya cloud integration: `switch.studio_humidifier_socket_1`.

The dehumidifier is on a 15 A switch because a compressor is an inductive load and the Mini Plug relay is the weak point against it. One died that way on 2026-08-09: device `ab8b624cc66726276f8c0a35c7903c9f` / `switch.mini_plug_4_socket_1` began closing on its own (self-initiated `on` events with no controller command), and finally passed current with the switch commanded open. Treat a repeat of that signature as hardware, not logic. Its Tuya replacement carried the load unfailed until the ZEN15 took over on 2026-08-14 and is parked in HA, unwired, as device "Unused Plug" / `switch.unused_plug_socket_1`.

The dehumidifier's exhaust reaches the studio baseboard thermostat, so a run shows up as a spike of about 3 °C on `sensor.studio_baseboard_current_temperature` while the room is unchanged — the Zigbee humidistat in the same room stays flat through it. That sensor is unfiltered and still feeds both its own history and the filter below it, but nothing controls from it: the coordinator and the studio thermostat tile both read `sensor.studio_control_temperature` (see **Sensor filtering** below).

### The ecobee-style HVAC coordinator

The control model is **two setpoints per room** — an ecobee, not a single preferred temperature with a swing. Per room the user sets `input_number.<room>_heat_bound` (lower; below it the room wants heat) and `input_number.<room>_cool_bound` (upper; above it the room wants cool). The room floats freely in the dead band between the two bounds. There is no `preferred` and no symmetric `swing`. Where a single comfort value is needed (the backup-heat baseboard target) it is the derived **comfort midpoint** `(heat_bound + cool_bound) / 2`.

Because the two heads share one outdoor compressor (a multi-split), **heat vs cool is a single system-wide decision** — both heads must be in the same mode at any instant, though either can independently idle. So a single `hvac_coordinator` automation owns both heads — one automation per physical compressor, because per-room controllers cannot express a shared-compressor constraint. Its decision macros live in `custom_templates/hvac.jinja` (pure, unit-tested):

- `room_demand(temp, heat_bound, cool_bound, differential, current)` → `heat` / `cool` / `none` for one room, using that room's control temperature — `sensor.office_baseboard_current_temperature` for the office, `sensor.studio_control_temperature` for the studio (see **Sensor filtering** below) — and a hysteresis differential.
- `resolve_mode(office_demand, studio_demand)` → one system mode, `heat` / `cool` / `idle`, with **heating wins** conflicts: if either room wants heat the whole system heats; cooling runs only when neither room wants heat; a too-warm room whose mode is forbidden simply idles its head.
- `head_target(mode, heat_bound, cool_bound, lead)` → the temperature to command a head, clamped to `[17, 30]` — the same range the four bound helpers allow, so no bound can be set below what a head can be commanded — and then passed through `snap_to_head_grid` (next bullet). The `lead` is a **per-room, heat-only** offset set in the coordinator's `variables:` (`office_heat_lead` 0, `studio_heat_lead` 1.5; cooling always uses 0). Heat-only is a property of the wiring, not the macro: `head_target` moves the commanded setpoint toward the demand in both modes (`heat_bound + lead`, `cool_bound − lead`), so a cooling lead would be a **positive** number. The head's onboard sensor is unreliable and reads warm (it sits in the return airflow; when off it reads refrigerant-pipe temp driven by the *other* head), so at `lead 0` the large/slow studio's inverter loafs and the room sags ~1 °C under setpoint before the head commits. A positive heat lead opens enough onboard setpoint error to make the inverter pull real capacity. This does **not** cause overshoot: `lead` sets the commanded setpoint, but the **real cutoff** is `room_demand` against that room's control sensor at `heat_bound + differential` — independent of the commanded setpoint — so a higher lead changes how hard the head pulls, not where it shuts off. The small/fast office holds fine and stays at its bound. (Overshoot would follow only if the commanded setpoint *were* the cutoff; rationale in `docs/superpowers/specs/2026-06-22-asymmetric-heating-lead-design.md`. Distinct from the lockout over-cool that `test_overcool_turns_off_during_lockout` guards.) Two variable pairs, two roles: `office_heat_lead`/`studio_heat_lead` are the bare per-room constants — the tuning knob — and sit above `effective`; `office_lead`/`studio_lead` are the mode-gated values `{{ <room>_heat_lead if effective == 'heat' else 0 }}` and must sit *after* `effective`, since HA renders `variables:` top-to-bottom. Flattening the gated pair into literals would apply the lead in cool mode too.
- `snap_to_head_grid(celsius)` → the °C value to command so the head lands on the intended step. The head's grid is **whole degrees Fahrenheit** and it **truncates**, so the °C spelling rounds up: 63 °F is 17.2222 °C, and commanding 17.2 gives 62.96 °F, one step low, so the macro commands 17.3. `head_target` returns its clamped result through this, which is what carries a configured lead to the hardware: a bound of 19 with `studio_heat_lead` 1.5 is 20.5 °C, which unsnapped truncates to 68 °F (20.0 °C) for an effective lead of 1.0, and snapped reaches the intended 69 °F. 30 °C is exactly 86 °F, so snapping cannot escape the upper clamp. The °F rounding is spelled half-up — `(f + 0.5) | round(0, 'floor')` — rather than Jinja's `round`, which breaks an exact tie to even. Three points on the 0.5 °C bound grid are exact half-degrees Fahrenheit (17.5, 22.5, 27.5 °C), and only **22.5** lands differently under the two spellings: 72.5 °F reaches 73 half-up where tie-to-even takes it to 72, which is where a 22.0 °C request already sits. The other two round up under either rule, because 64 and 82 are even; half-up pins all three by construction rather than by parity. This does not remove grid collisions and is not aimed at them: 0.5 °C is 0.9 °F, less than one grid step, so exactly 3 of the 27 points on the `[17, 30]` bound grid share a °F step with the point below them whichever way ties break. What it removes is a downward bias at the ties, and with it a dead step in the Phase 2 retune range — `head_target('heat', 19, 23, 3.0)` commands 72 °F and `3.5` commands 73 °F, so a half-step lead increase is visible at the hardware.
- `command_step(celsius)` / `report_step(celsius)` → the whole-°F step behind a °C value, from each side of the head: `floor` for what the head does with a command, `round` for what HA reports back. A commanded 17.3 and a reported 17.2 are the same 63 °F, so the already-on branch compares `<room>_target_step` against `<room>_device_step` rather than Celsius. A Celsius comparison never settles — while a head is powered, every heartbeat and every sensor update re-issues `climate.set_temperature`, which is the call volume the branch gating exists to prevent — and no epsilon substitutes: one loose enough to absorb a 0.556 °C step also swallows a genuine 0.5 °C bound change. Rationale and the measured figures are in `docs/superpowers/specs/2026-08-15-studio-heat-sag-design.md`.

The coordinator fires on the two control temperature sensors, the four bound + two differential helpers, `input_boolean.hvac_enable`, `input_boolean.backup_heat`, the `timer.finished` of both head lockouts and the mode dwell, HA start, and a 5-minute safety heartbeat. It short-circuits when any of six entities — either control temperature sensor, `switch.<room>_power`, `climate.<room>` — is `unavailable` / `unknown`. It reads the stored mode from `input_select.system_hvac_mode`, resolves the desired mode, then issues the minimum Cielo calls per head to reach the desired state. Every branch is gated on a real delta: the off→on and the turn-off branches on the power-switch state, the already-on branch on a `climate.<room>` mode delta or a whole-°F step delta. The one exception is the `climate.set_temperature` that rides `switch.turn_on` in the off→on branch — it carries no climate-side gate, because HA renders the automation-level `variables:` block **once, before any action**, so the `climate.<room>` snapshot predates the power-on and cannot describe what the unit restores on power-up. That call is bounded to one per real head turn-on, itself rate-limited by the per-head lockout (the Cielo dedupe discipline).

**Master enable.** `input_boolean.hvac_enable` is a one-tap "all off" (away / windows open): when off, both heads are forced off regardless of demand. Both thermostat tiles' mode control is bound to `input_boolean.hvac_enable`, so it is reachable from either tile.

**Short-cycle protection (four layers):**

1. **Dead band** between the two bounds — the room must traverse it before the opposite action fires (the primary tuning knob).
2. **Per-room differential** `input_number.<room>_temp_differential` — a started head runs `d` degrees past its bound before cutting, lengthening the off-period. Office **1.0 °C** (fast room), studio **0.5 °C**.
3. **Per-head lockout** `timer.<room>_head_lockout` — a minimum **off**-time: armed on every head toggle (on or off), it gates the next turn-**on** until it expires (office 8 min, studio 6 min). It never blocks a turn-**off** — the coordinator turns a head off the instant demand ends, so the head can't be forced past the cutoff at `heat_bound + differential` (or `cool_bound − differential`). A safety force-off still arms the lockout, so a quick re-enable or a backup-heat flap can't restart the compressor immediately.
4. **Inverter modulation** — commanding a fixed setpoint and letting the head run (instead of chattering the power switch) lets the compressor ramp down near setpoint once the head's own sensor converges to room temp.

**Sensor filtering (studio only).** The studio baseboard thermostat sits in the dehumidifier's exhaust path, which lifts its reading about 3 °C above the room for ~15 minutes and looks exactly like a satisfied room — on 2026-08-14/15 that phantom warmth ended two live heat cycles and blocked a turn-on. `sensor.studio_control_temperature`, defined in the `- trigger:` block of `configuration.yaml`, is the coordinator's studio input. It renders `slew_filter(raw, raw_at, last_good, value_at, hold_since, pending, pending_at, now_iso, reject, reenter, max_hold)` at reject **1.0 °C**, re-enter **0.5 °C**, max hold **20 minutes**: a reading further than `reject` from the last accepted value starts a hold, and while holding, a reading must come back inside the tighter `reenter` band to be accepted. Two bands rather than one is what rejects the decaying tail of a plume — a reading 0.6 °C above the held value passes a single 1.0 °C threshold while still a degree above the room. A hold reaching `max_hold` resyncs to the raw reading, so a genuine step change is not held forever. The sensor is trigger-based rather than a plain `- sensor:` because the filter reads its own previous output (`this.state`) and its own four attributes — `hold_since`, `value_at`, `pending`, `pending_at`; the `time_pattern` trigger is what expires a hold when the source stops changing. `hold_since` stays the operator-visible signal: non-empty exactly while a hold is running. **The value and all four attributes survive a restart.** `TriggerSensorEntity` inherits `RestoreSensor`, `TriggerEntity.async_added_to_hass` calls `async_restore_last_state()`, and `template/entity.py` restores the custom attributes alongside the state — so a restart resumes on the restored value, and a hold in flight resumes on its **original** `hold_since` clock rather than a fresh 20 minutes. **A restored value can still be too old to use.** `value_at` stamps when a value was accepted and rides along unchanged whenever a held value is republished, so it measures age from acceptance rather than from the last render. Outside a hold, a value older than `max_hold` describes a room that has since moved and counts as absent, which sends the seeding path. That test is skipped mid-hold, where `max_hold` already bounds the stale window: `value_at` keeps the pre-hold acceptance stamp and a hold starts no earlier than it, so by the time the cap expires the stamp is always older than `max_hold` and the age test would fire first on every hold — making the cap dead code, and trading a resync to the raw reading for a wait on two fresh source updates. **Seeding takes two source updates.** It runs where nothing usable is restored — the entity's first-ever deploy, a source dropout that outlasts `max_hold`, and a restart whose restored value is stale. A lone reading is unusable there: taken inside a plume it latches the contaminant as the room for the full 20-minute hold, the inverse of what the filter is for. So the filter requires **two readings within the `reject` band of each other drawn from two different source updates**, seeds from the second, and holds the unmatched candidate in `pending` with that reading's source `last_changed` in `pending_at`. Counting source updates rather than renders is what `pending_at` buys: the `/5` heartbeat re-renders an unchanged source value, which agrees with itself trivially, so a candidate cannot be confirmed by a render sharing its timestamp — without that, a plume plateau confirms its own peak. Replayed against the measured plume it declines the 22.4 peak and seeds at 19.0; on a quiet start the second source update lands about 4 minutes in. A non-numeric source rides out the same hold, after which the filter emits a JSON `null`. The coordinator's availability condition tests **both** `unavailable` and `unknown`, so the short-circuit fires on either — and `unknown` is where the entity settles, with no validator error logged, because a real `None` is what the template sensor's `_validate_state` accepts where any string raises. Three costs, all accepted: for up to 20 minutes the coordinator acts on a held or restored value; a dehumidifier run longer than the cap resyncs mid-spike; and wherever the seeding path runs the studio has no control temperature until a pair agrees, which holds the coordinator for a source update or two. The office has no exhaust source beside its thermostat and reads `sensor.office_baseboard_current_temperature` directly. The Zigbee humidistat in the same room is the cleaner signal but reports on a ~15-minute cadence from a battery, too slow to be the cutoff input for a head that must stop within a 0.5 °C differential; that and the measured constants are in `docs/superpowers/specs/2026-08-15-studio-heat-sag-design.md`.

**Anti-flap (heat↔cool).** `timer.mode_min_dwell` (15 min) starts on every transition *into* an active mode: the gate is `effective != stored`, and `stored` also holds `idle`/`off`, so `heat → idle → heat` (or a re-enable out of `off`) re-arms a full 15-minute heat dwell even though the previous *active* mode was already heat — and cooling stays blocked for that window. That coarse comparison is what closes the idle-hop bypass. While it runs, the stored mode is **pinned** to the dwelling active mode and the opposite mode cannot be adopted — even transiently via `idle`. Heads still idle within the dwelling mode when there's no same-direction demand; once the dwell clears, the mode re-resolves freely.

**Observability.** `input_select.system_hvac_mode` (`heat` / `cool` / `idle` / `off`) is written only by the coordinator and holds the *system's permitted direction*, not a running indicator: it stays at the dwelling mode for the whole `mode_min_dwell` window with both heads off, and under heating-wins a too-warm room's head is off while the select still reads `heat`. Anything that means "is actually heating/cooling" must AND it with `switch.<room>_power` — which is what `hvac_action_template` in `configuration.yaml` does.

### Backup heat mode

Two automations share one threshold: `'1756873917108'` turns `input_boolean.backup_heat` **on** when `sensor.lethbridge_temperature` stays below −12 °C for 20 minutes, and `'1756874009383'` turns it **off** when the sensor stays above −12 °C for 20 minutes. There is no temperature gap — the hysteresis is the 20-minute `for:` on both sides, which is operationally fine. **Edit the two thresholds together.** `numeric_state` fires only on a crossing, so raising just the entry to −8 while the exit stays at −12 means a sustained −10 °C turns backup heat on, turns it off 20 minutes later, and can never re-arm — silently defeated across the whole −12…−8 band. Lowering just the entry is benign. On entry both baseboards are pushed to each room's **comfort midpoint** `(heat_bound + cool_bound) / 2`, rounded half-up to the baseboards' 0.5 °C step, and the coordinator independently forces **both heads off** (it reads `backup_heat` as a hard-safety force-off) so the baseboards lead. On warmup, baseboards are dropped to `heat_bound − 2.5 °C` so the heat pump leads again. The −2.5 °C offset is what lets the heat pump take primary duty without the baseboard fighting it — don't remove it casually. Both edges write a value derived from bounds the user can move at any time, and neither edge is where either value is *maintained*: `baseboard_standby_setpoint` re-derives whichever one the current `backup_heat` state calls for, the midpoint included, on every bound change (next paragraph).

Each edge automation writes its *derived* baseboard setpoint once, so both values go stale the moment a bound moves afterwards. `baseboard_standby_setpoint` maintains them: it triggers on **all four** bound helpers and branches on `input_boolean.backup_heat` — `on` writes each room's comfort midpoint, `off` writes `heat_bound − 2.5`. The two cool bounds are triggers because the midpoint reads them, which is what makes a bound moved *during* backup heat re-derive the midpoint instead of leaving the entry edge's value in place. The automation carries no `conditions:` block; the `choose:` is the whole gate, and its second arm is an explicit `state: 'off'` rather than a `default:`, so a `backup_heat` reading `unknown` or `unavailable` writes no setpoint at all — an indeterminate safety flag does not get to command resistive heat. A stale value is harmless while the bound stays above it; a bound dropped below it puts the baseboard in competition with the heat pump, which is the condition the offset exists to prevent. Inside each arm every `climate.set_temperature` sits behind an `if:` comparing the derived value against that baseboard's own `temperature` attribute, so one thermostat-card drag that writes two bounds commands only the baseboard whose setpoint actually moved; the attribute is read with `float(0)`, and 0 sits below every settable setpoint, so a baseboard holding no target gets written. The midpoint is rounded **half-up onto the baseboards' 0.5 °C step**, here and in `'1756873917108'`: `(heat_bound + cool_bound) / 2` lands on 0.25 steps, a device holding 0.5 can never report one back, and the delta gate would then rewrite an unchanged setpoint on every trigger — the same defect shape as the Cielo Fahrenheit grid. Its alias is `Baseboard Standby Setpoint`, which slugifies to its `id`, so the entity is `automation.baseboard_standby_setpoint`. HA derives the entity_id from the **alias** (it becomes `_attr_name`) and makes the `id` the `unique_id`; every hand-written automation here is aliased so the two agree, which is what makes `automation.<id>` safe to reference. `tests/test_automations_yaml.py` pins all four triggers (`test_baseboard_setpoint_tracks_all_four_bounds`), both arms' commanded values, the delta gate, and the rounding. Background in `docs/superpowers/specs/2026-08-15-studio-heat-sag-design.md`, "Baseboard standby setpoint (independent)".

### Humidity (independent of HVAC)

A single state-driven controller (`studio_humidity_controller` in `automations.yaml`)
reconciles the dehumidifier switch (`switch.studio_dehumidifier`) and humidifier plug
(`switch.studio_humidifier_socket_1`) from the current reading of the shared Zigbee humidity
sensor — the same reconcile-on-delta pattern as the HVAC controllers. Reconciling from the
current reading rather than from threshold-crossing edges is what makes a missed crossing
harmless: an edge-triggered design strands a device on, and can leave both running.

Asymmetric hysteresis around `input_number.humidity_set_point` with
`input_number.humidity_tolerance`:

- Dehumidifier: on at `humidity ≥ set_point + tolerance`, off at `humidity < set_point`;
  holds its last state in `[set_point, set_point + tolerance)`
- Humidifier: on at `humidity ≤ set_point − tolerance`, off at `humidity > set_point`;
  holds its last state in `(set_point − tolerance, set_point]`
- The two hold regions abut at `set_point` and together cover the open interval
  `(set_point − tolerance, set_point + tolerance)`, but each device holds over only its
  own half: `tolerance` sets where a device **starts**, `set_point` is where it **stops**.
  Widening `humidity_tolerance` raises the dehumidifier's ON point and lowers the
  humidifier's ON point — it moves neither OFF point.

Three invariants are enforced by construction:

- **Never both on.** Turn-on branches require the opposite device to be off; a mutual-exclusion
  safety branch turns off the wrong device (humidity decides) if both are ever on.
- **Cross-device relaxation cooldown.** There are **two** cooldown timers (30 min each):
  `timer.dehumidify_cooldown` is armed when the dehumidifier turns off and blocks the
  **humidifier** turn-on; `timer.humidify_cooldown` is armed when the humidifier turns off and
  blocks the **dehumidifier** turn-on. A turn-off overshoot (e.g. the dehumidifier coasting
  below the humidifier ON point under high outdoor humidity) thus recovers before the opposite
  device can react. Crucially, a device's **own** cooldown never gates that same device — the
  active device re-engages at its threshold instead of drifting while a cooldown runs — so
  same-device cycling is bounded only by the tight `tolerance`-wide hold region, which keeps
  the room near `set_point` (the studio holds ~42 % for the instruments). The controller is
  `mode: single` so its own switch events don't restart it mid-run; the deferred turn-on is
  driven by the `timer.finished` trigger and the 5-min heartbeat.
- **Respect manual flips.** `studio_humidity_manual_detector` compares each switch change
  against an `input_boolean.<device>_intended` mirror (set by the controller before it
  commands) to tell manual changes apart from controller ones, and arms a 15-min
  `timer.<device>_manual_grace`; the controller leaves a switch alone while its grace timer is
  active (except the both-on safety).

The humidity helpers (`input_number.humidity_set_point`, `input_number.humidity_tolerance`,
`input_boolean.dehumidifier_intended`, `input_boolean.humidifier_intended`, and the four
`timer.*` entities — `dehumidify_cooldown`, `humidify_cooldown`,
`dehumidifier_manual_grace`, `humidifier_manual_grace`) are defined in `helpers.yaml` like
the rest; the two `input_number`s ship tuned `initial:` values (set point 42, tolerance 1.5).

**Relay watchdog.** `studio_dehumidifier_relay_failure` notifies when
`sensor.studio_dehumidifier_electric_consumption_w` exceeds **20 W** for 3 minutes while
`switch.studio_dehumidifier` reads `off` — a welded relay, which is the failure mode this
load produces (see the hardware notes above). It is outside the control loop by nature:
no reconcile can open fused contacts, so the automation only reports. The 20 W threshold
appears **twice**, in the trigger's `above:` and in the `leak_watts` variable, because a
trigger cannot read `variables:` — HA renders those only after a trigger fires. The
condition is what the tests exercise, since `automation.trigger` bypasses trigger blocks
entirely; `test_trigger_threshold_matches_condition_threshold` is what keeps the pair in
step.

### The Eva lamp auto-off

A third Tuya Mini Plug drives the Eva lamp. `eva_lamp_auto_off` in
`automations.yaml` switches it off 30 minutes after a person turns it on, using
`timer.eva_lamp_auto_off` (30 min, `restore: true`).

"A person" is read off the state change's context: HA gives an
automation-commanded change a `parent_id`, so `parent_id is none` admits both the
physical button (no user, no parent) and the dashboard (user, no parent) while
excluding a commanded turn-on. That context survives the Tuya cloud round-trip.
The gate has one hole — an automation triggered with no triggering context of its
own, such as a time trigger or HA start, also reports no parent — which is
unreachable while nothing commands this plug. Wiring any automation to this plug
means revisiting it, and `input_boolean.*_intended` in
`studio_humidity_manual_detector` is the precise alternative.

Switching the lamp off cancels a pending cutoff, and the cutoff re-checks the
lamp is on before calling, so neither path issues a redundant Tuya call. A plug
that reconnects already `on` arms a fresh 30 minutes rather than staying on
indefinitely.

The entity is `switch.eva_lamp_socket_1` — named for the device rather than a
room, because the `<room>_<thing>` convention covers entities that come paired
across office and studio and the lamp is a single unpaired unit. Entity IDs live
in HA's registry under `.storage/`, so nothing in this repo defines or renames
one; an automation pointed at an ID the registry does not carry fires nothing and
logs nothing.

## Conventions

- Per-room entity names follow `<sensor|input_number|...>.<room>_<thing>`: `sensor.<room>_baseboard_current_temperature`, `input_number.<room>_heat_bound`, `input_number.<room>_cool_bound`, `input_number.<room>_temp_differential`. Stay on this pattern when adding entities.
- The thematic banner comments in `automations.yaml` (`# HVAC controllers`, `# Backup heat`, `# Humidity`, `# Lamps`) are the file's structure — keep them and group new automations under the right one.
- Automations created in the HA UI get a numeric id (`'1756873917108'`); hand-written ones get descriptive ids (`hvac_coordinator`). Both are valid — match whichever style the section already uses.
