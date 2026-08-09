# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **Home Assistant configuration** for a two-room space (office + studio), versioned in git. The goal is to mirror the live HA configuration here, with the exceptions called out below.

Tracked:

- `configuration.yaml` — root HA config, template sensors, `neviweb130` integration, notify group
- `automations.yaml` — all automations (HVAC coordinator, backup heat, humidity)
- `scripts.yaml`, `scenes.yaml` — included from `configuration.yaml`; currently empty
- `custom_templates/hvac.jinja` — the heat-pump coordinator decision macros
- `tests/`, `pytest.ini`, `requirements-dev.txt` — pytest harness (see "Tests")
- `ha-version.txt` — the HA release the live box runs, on one bare line. `tests/test_version_pin.py` asserts the `requirements-dev.txt` pin, its comment, and the *installed* harness all agree with it.
- `.yamllint.yml`, `.github/workflows/ci.yml` — the CI gate: yamllint over the three hand-edited config files, actionlint over the workflows, and the test suite
- `helpers.yaml` — `input_number` / `input_boolean` / `input_select` / `timer` definitions; wired into `configuration.yaml` as a package (see "Helpers migration" below)
- `secrets.yaml.example` — placeholder showing which `!secret` keys must exist
- `.env.example` — placeholder for the repo-root `.env` (see "Live Home Assistant API access")
- `docs/superpowers/specs/`, `docs/superpowers/plans/` — design docs and implementation plans (see below)
- `README.md` — human-facing overview of the space and the control model; its **Troubleshooting** section indexes the states that look like faults but aren't (timers mid-run, the mode helper vs. a running head, the coordinator short-circuiting on an unavailable entity) — start there when a symptom is reported
- `blueprints/` — HA's stock shipped blueprints, untouched
- `.gitignore` — the exclusion list the next section summarizes

`docs/superpowers/specs/` and `docs/superpowers/plans/` are the dated design record.
Every plan there is merged and none of their `- [ ]` checkboxes are ticked, so
checkbox state is not a to-do signal — with one carve-out.
`2026-08-09-cicd-github-actions.md` is the exception: its Tasks 5, 6 and 8 (merge,
tighten the GitHub ruleset, install the Git pull add-on on the host) are genuinely
outstanding and await the owner's go-ahead. Until Task 8 runs, nothing about this
repository is auto-deployed. Delete this carve-out when those tasks are done. The
changeover advisor
(`2026-06-07-changeover-advisor*`, both plan and spec) was built and then removed in
`f2d051b`; the ecobee coordinator replaces it. Don't resurrect it.

Not tracked — the entries that matter (see `.gitignore` for the full list):

- `secrets.yaml` — real credentials. Commit only the `.example`.
- `.env` — holds `HOME_ASSISTANT_TOKEN`, a live admin-scoped credential. Commit only the `.example`. Distinct from `secrets.yaml`: `secrets.yaml` feeds `!secret` lookups on the HA host, `.env` is read by tooling on *this* machine and HA never sees it.
- `home-assistant.log*`, `home-assistant_v2.db*`, `.HA_VERSION`, `.uuid`, `deps/`, `tts/`, `image/`, `.cloud/` — HA runtime artifacts
- `.storage/` — HA's internal state store; rewritten constantly, and `.storage/auth*` holds tokens
- `themes/` — the stock `frontend: themes:` include in `configuration.yaml`. Absent here and on a fresh HA install alike: `!include_dir_merge_named` on a missing directory loads as `{}` with no error or warning.

External entities that automations reference but that are defined elsewhere (Zigbee integrations, weather integrations, mobile companion app): `sensor.lethbridge_temperature` (outdoor, drives backup heat), `sensor.tz3000_utwgoauk_snzb_02_humidity`, `switch.studio_dehumidifier_socket_1` (dehumidifier plug), `switch.studio_humidifier_socket_1` (humidifier plug), `mobile_app_pixel_8`. Don't assume an entity is undefined just because it isn't grep-able locally.

## Tests

`pytest` covers the HVAC coordinator, the humidity controller, and the
`helpers.yaml` values. Level 2 tests render the `custom_templates/*.jinja` macros
against a real HA template engine (`pytest-homeassistant-custom-component`) —
heat/cool/idle resolution, the heating-wins conflict, differential hysteresis,
target clamps. Level 3 tests load the `hvac_coordinator` and
`studio_humidity_controller` automations **from the real YAML files** and exercise
their conditions and actions against mocked services (lockout blocking a
re-toggle, master enable / backup heat forcing both heads off, conflict resolving
to heat, the cross-device cooldown directions, the both-on safety). Each test
drives one run via `automation.trigger` with `skip_condition: False`; the
automation is turned **off** first, so trigger blocks are schema-validated at
setup but never fire — the 5-minute heartbeat and the `timer.finished` re-runs
have no behavioral coverage. `tests/test_helpers_yaml.py` validates `helpers.yaml`
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
step. Changes are deployed by syncing these
files to the HA instance and reloading: `automation.reload` for
`automations.yaml`, `template.reload` for the `template:` block in
`configuration.yaml`, and **`homeassistant.reload_custom_templates` for
`custom_templates/hvac.jinja`** — HA holds custom Jinja in an in-memory loader, so
an edited macro keeps rendering its old body, silently and with no error, until
that service runs. `homeassistant.reload_all` covers all three (it aborts if the
config is invalid).

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
plugs. Reads are free; writes move equipment.

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

Deploying is never an agent's call, in either deployment state. Until the Git
pull add-on is installed on the host (Task 8 of
`docs/superpowers/plans/2026-08-09-cicd-github-actions.md`), this repo is not
auto-deployed and an agent-issued `homeassistant.reload_all` would quietly make
it so. Once the add-on runs, `main` is the only sanctioned path to the box, and
a `reload_all` puts whatever the working tree holds onto the hardware ahead of
review.

A `401` means the token was revoked or replaced — the fix is a new token from the
HA UI, not a retry. A connection failure means the box is unreachable from this
network; treat live inspection as unavailable and fall back to the test suite
rather than working around it.

## Custom integrations (HACS)

Not vendored into this repo. If restoring from scratch, install HACS first, then add:

- **claudegel/sinope-130** (integration) → `custom_components/neviweb130` — Sinopé Wi-Fi baseboard heaters; referenced by the `neviweb130:` block in `configuration.yaml`
- **bodyscape/cielo_home** (integration) → `custom_components/cielo_home` — Cielo Home Wi-Fi controller for the heat pumps; provides `climate.office` / `climate.studio`, `switch.office_power` / `switch.studio_power`, and `sensor.office_target_temperature` / `sensor.studio_target_temperature`
- **Climate Template** (integration, platform `climate_template` — e.g. a maintained fork of jcwillox/hass-template-climate; confirm the most-maintained fork at install time) → provides the display/entry facade `climate.office_thermostat` / `climate.studio_thermostat` over the bound helpers, for the standard HA Thermostat card's ecobee-style dual-setpoint dial. Defined in the `climate:` block of `configuration.yaml`; issues no Cielo calls itself (all control stays in the coordinator). Which fields are per-room and which are global: `current_temperature` (that room's baseboard sensor), both bound helpers, and `hvac_action` (gated on that room's `switch.<room>_power`) are per-room; `hvac_mode` / `set_hvac_mode` both read and write the single `input_boolean.hvac_enable`, so `off` on either tile is a system-wide off and the other tile displays `off` too.
- **RomRider/apexcharts-card** (Lovelace plugin) → `www/community/apexcharts-card` — used by the dashboards

The Lovelace dashboards themselves are not restorable from this repo. They live in `.storage/lovelace*`, excluded above, so a from-scratch restore comes up with HA's auto-generated default dashboard and none of the tiles — including the ecobee thermostat tile and the apexcharts cards. Closing that gap means either exporting each dashboard's raw configuration into a tracked directory, or tracking `.storage/lovelace` and `.storage/lovelace_dashboards` per-file, which `.gitignore`'s own comment already anticipates.

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

Independent of the HVAC loop, both in the **studio**: dehumidifier plug `2c14c57df022faaf9f89c6390df4173f` and humidifier plug `60211ed7b46e92fd6dcadf60d8087fd0` share one Zigbee humidity sensor. Both are Tuya "Mini Plug" units on the Tuya cloud integration. The dehumidifier plug was replaced on 2026-08-09 after its relay failed — it began closing on its own (self-initiated `on` events with no controller command) and finally passed current with the switch commanded open. The retired unit was device `ab8b624cc66726276f8c0a35c7903c9f` / `switch.mini_plug_4_socket_1`; a compressor is an inductive load and these plugs' relays are the weak point, so treat a repeat of that signature as hardware, not logic.

### The ecobee-style HVAC coordinator

The control model is **two setpoints per room** — an ecobee, not a single preferred temperature with a swing. Per room the user sets `input_number.<room>_heat_bound` (lower; below it the room wants heat) and `input_number.<room>_cool_bound` (upper; above it the room wants cool). The room floats freely in the dead band between the two bounds. There is no `preferred` and no symmetric `swing`. Where a single comfort value is needed (the backup-heat baseboard target) it is the derived **comfort midpoint** `(heat_bound + cool_bound) / 2`.

Because the two heads share one outdoor compressor (a multi-split), **heat vs cool is a single system-wide decision** — both heads must be in the same mode at any instant, though either can independently idle. So a single `hvac_coordinator` automation owns both heads — one automation per physical compressor, because per-room controllers cannot express a shared-compressor constraint. Its decision macros live in `custom_templates/hvac.jinja` (pure, unit-tested):

- `room_demand(temp, heat_bound, cool_bound, differential, current)` → `heat` / `cool` / `none` for one room, using its reliable temperature `sensor.<room>_baseboard_current_temperature` and a hysteresis differential.
- `resolve_mode(office_demand, studio_demand)` → one system mode, `heat` / `cool` / `idle`, with **heating wins** conflicts: if either room wants heat the whole system heats; cooling runs only when neither room wants heat; a too-warm room whose mode is forbidden simply idles its head.
- `head_target(mode, heat_bound, cool_bound, lead)` → the temperature to command a head, clamped to `[17, 30]` — the same range the four bound helpers allow, so no bound can be set below what a head can be commanded. The `lead` is a **per-room, heat-only** offset set in the coordinator's `variables:` (`office_heat_lead` 0, `studio_heat_lead` 1.5; cooling always uses 0). Heat-only is a property of the wiring, not the macro: `head_target` moves the commanded setpoint toward the demand in both modes (`heat_bound + lead`, `cool_bound − lead`), so a cooling lead would be a **positive** number. The head's onboard sensor is unreliable and reads warm (it sits in the return airflow; when off it reads refrigerant-pipe temp driven by the *other* head), so at `lead 0` the large/slow studio's inverter loafs and the room sags ~1 °C under setpoint before the head commits. A positive heat lead opens enough onboard setpoint error to make the inverter pull real capacity. This does **not** cause overshoot: `lead` sets the commanded setpoint, but the **real cutoff** is `room_demand` against the reliable baseboard sensor at `heat_bound + differential` — independent of the commanded setpoint — so a higher lead changes how hard the head pulls, not where it shuts off. The small/fast office holds fine and stays at its bound. (Overshoot would follow only if the commanded setpoint *were* the cutoff; rationale in `docs/superpowers/specs/2026-06-22-asymmetric-heating-lead-design.md`. Distinct from the lockout over-cool that `test_overcool_turns_off_during_lockout` guards.) Two variable pairs, two roles: `office_heat_lead`/`studio_heat_lead` are the bare per-room constants — the tuning knob — and sit above `effective`; `office_lead`/`studio_lead` are the mode-gated values `{{ <room>_heat_lead if effective == 'heat' else 0 }}` and must sit *after* `effective`, since HA renders `variables:` top-to-bottom. Flattening the gated pair into literals would apply the lead in cool mode too.

The coordinator fires on the baseboard temp sensors, the four bound + two differential helpers, `input_boolean.hvac_enable`, `input_boolean.backup_heat`, the `timer.finished` of both head lockouts and the mode dwell, HA start, and a 5-minute safety heartbeat. It short-circuits when any critical baseboard sensor, `switch.<room>_power`, or `climate.<room>` is `unavailable` / `unknown`. It reads the stored mode from `input_select.system_hvac_mode`, resolves the desired mode, then issues the minimum Cielo calls per head to reach the desired state. Every branch is gated on a real delta: the off→on and the turn-off branches on the power-switch state, the already-on branch on a `climate.<room>` mode-or-target delta. The one exception is the `climate.set_temperature` that rides `switch.turn_on` in the off→on branch — it carries no climate-side gate, because HA renders the automation-level `variables:` block **once, before any action**, so the `climate.<room>` snapshot predates the power-on and cannot describe what the unit restores on power-up. That call is bounded to one per real head turn-on, itself rate-limited by the per-head lockout (the Cielo dedupe discipline).

**Master enable.** `input_boolean.hvac_enable` is a one-tap "all off" (away / windows open): when off, both heads are forced off regardless of demand. Both thermostat tiles' mode control is bound to `input_boolean.hvac_enable`, so it is reachable from either tile.

**Short-cycle protection (four layers):**

1. **Dead band** between the two bounds — the room must traverse it before the opposite action fires (the primary tuning knob).
2. **Per-room differential** `input_number.<room>_temp_differential` — a started head runs `d` degrees past its bound before cutting, lengthening the off-period. Office **1.0 °C** (fast room), studio **0.5 °C**.
3. **Per-head lockout** `timer.<room>_head_lockout` — a minimum **off**-time: armed on every head toggle (on or off), it gates the next turn-**on** until it expires (office 8 min, studio 6 min). It never blocks a turn-**off** — the coordinator turns a head off the instant demand ends, so the head can't be forced past the cutoff at `heat_bound + differential` (or `cool_bound − differential`). A safety force-off still arms the lockout, so a quick re-enable or a backup-heat flap can't restart the compressor immediately.
4. **Inverter modulation** — commanding a fixed setpoint and letting the head run (instead of chattering the power switch) lets the compressor ramp down near setpoint once the head's own sensor converges to room temp.

**Anti-flap (heat↔cool).** `timer.mode_min_dwell` (15 min) starts on every transition *into* an active mode: the gate is `effective != stored`, and `stored` also holds `idle`/`off`, so `heat → idle → heat` (or a re-enable out of `off`) re-arms a full 15-minute heat dwell even though the previous *active* mode was already heat — and cooling stays blocked for that window. That coarse comparison is what closes the idle-hop bypass. While it runs, the stored mode is **pinned** to the dwelling active mode and the opposite mode cannot be adopted — even transiently via `idle`. Heads still idle within the dwelling mode when there's no same-direction demand; once the dwell clears, the mode re-resolves freely.

**Observability.** `input_select.system_hvac_mode` (`heat` / `cool` / `idle` / `off`) is written only by the coordinator and holds the *system's permitted direction*, not a running indicator: it stays at the dwelling mode for the whole `mode_min_dwell` window with both heads off, and under heating-wins a too-warm room's head is off while the select still reads `heat`. Anything that means "is actually heating/cooling" must AND it with `switch.<room>_power` — which is what `hvac_action_template` in `configuration.yaml` does.

### Backup heat mode

Two automations share one threshold: `'1756873917108'` turns `input_boolean.backup_heat` **on** when `sensor.lethbridge_temperature` stays below −12 °C for 20 minutes, and `'1756874009383'` turns it **off** when the sensor stays above −12 °C for 20 minutes. There is no temperature gap — the hysteresis is the 20-minute `for:` on both sides, which is operationally fine. **Edit the two thresholds together.** `numeric_state` fires only on a crossing, so raising just the entry to −8 while the exit stays at −12 means a sustained −10 °C turns backup heat on, turns it off 20 minutes later, and can never re-arm — silently defeated across the whole −12…−8 band. Lowering just the entry is benign. On entry both baseboards are pushed to each room's **comfort midpoint** `(heat_bound + cool_bound) / 2`, and the coordinator independently forces **both heads off** (it reads `backup_heat` as a hard-safety force-off) so the baseboards lead. On warmup, baseboards are dropped to `heat_bound − 2.5 °C` so the heat pump leads again. The −2.5 °C offset is what lets the heat pump take primary duty without the baseboard fighting it — don't remove it casually.

### Humidity (independent of HVAC)

A single state-driven controller (`studio_humidity_controller` in `automations.yaml`)
reconciles the dehumidifier plug (`switch.studio_dehumidifier_socket_1`) and humidifier plug
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

## Conventions

- Per-room entity names follow `<sensor|input_number|...>.<room>_<thing>`: `sensor.<room>_baseboard_current_temperature`, `input_number.<room>_heat_bound`, `input_number.<room>_cool_bound`, `input_number.<room>_temp_differential`. Stay on this pattern when adding entities.
- The thematic banner comments in `automations.yaml` (`# HVAC controllers`, `# Backup heat`, `# Humidity`) are the file's structure — keep them and group new automations under the right one.
- Automations created in the HA UI get a numeric id (`'1756873917108'`); hand-written ones get descriptive ids (`hvac_coordinator`). Both are valid — match whichever style the section already uses.
