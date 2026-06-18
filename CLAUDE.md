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
- `helpers.yaml` — `input_number` / `input_boolean` / `input_select` definitions; **not yet wired** into `configuration.yaml` (see "Helpers migration" below)
- `secrets.yaml.example` — placeholder showing which `!secret` keys must exist

Not tracked (in `.gitignore`):

- `secrets.yaml` — real credentials. Commit only the `.example`.
- `home-assistant.log*`, `home-assistant_v2.db*`, `.HA_VERSION`, `.uuid`, `deps/`, `tts/`, `image/`, `.cloud/` — HA runtime artifacts
- `.storage/` — HA's internal state store; rewritten constantly, and `.storage/auth*` holds tokens

External entities that automations reference but that are defined elsewhere (Zigbee integrations, weather integrations, mobile companion app): `sensor.lethbridge_temperature` (outdoor, drives backup heat), `sensor.tz3000_utwgoauk_snzb_02_humidity`, `mobile_app_pixel_8`. Don't assume an entity is undefined just because it isn't grep-able locally.

## Tests

`pytest` covers the HVAC coordinator logic: Level 2 tests render the
`custom_templates/*.jinja` macros against a real HA template engine
(`pytest-homeassistant-custom-component`) — heat/cool/idle resolution, the
heating-wins conflict, differential hysteresis, target clamps; Level 3 tests
load the `hvac_coordinator` automation **from the real YAML files** and exercise
triggers/conditions/actions with mocked services (lockout blocking a re-toggle,
master enable / backup heat forcing both heads off, conflict resolving to heat).

```sh
uv python install 3.14                       # once; HA 2026.6 needs Python ≥ 3.14
uv venv .venv --python 3.14 --seed
.venv/bin/pip install -r requirements-dev.txt   # keep pinned to the live HA version
.venv/bin/pytest
```

There is no other build / lint pipeline. Changes are deployed by syncing these
files to the HA instance and reloading the relevant domain (automations,
template entities) from the HA UI or via `homeassistant.reload_*` services.

## Custom integrations (HACS)

Not vendored into this repo. If restoring from scratch, install HACS first, then add:

- **claudegel/sinope-130** (integration) → `custom_components/neviweb130` — Sinopé Wi-Fi baseboard heaters; referenced by the `neviweb130:` block in `configuration.yaml`
- **bodyscape/cielo_home** (integration) → `custom_components/cielo_home` — Cielo Home Wi-Fi controller for the heat pumps; provides `climate.office` / `climate.studio`, `switch.office_power` / `switch.studio_power`, and `sensor.office_target_temperature` / `sensor.studio_target_temperature`
- **Climate Template** (integration, platform `climate_template` — e.g. a maintained fork of jcwillox/hass-template-climate; confirm the most-maintained fork at install time) → provides the display/entry facade `climate.office_thermostat` / `climate.studio_thermostat` over the bound helpers, for the standard HA Thermostat card's ecobee-style dual-setpoint dial. Defined in the `climate:` block of `configuration.yaml`; issues no Cielo calls itself (all control stays in the coordinator).
- **RomRider/apexcharts-card** (Lovelace plugin) → `www/community/apexcharts-card` — used by the dashboards

## Helpers migration

`helpers.yaml` is wired into `configuration.yaml` as a **package**:

```yaml
homeassistant:
  packages:
    helpers: !include helpers.yaml
```

The whole file (its `input_number:` / `input_boolean:` / `input_select:` / `timer:` top-level keys) merges into the config in one shot — no per-domain `!include` lines, and the single-file shape is what `tests/conftest.py` loads, so it stays the source of truth for tests too. (Don't use `input_number: !include helpers.yaml` per-domain — that pastes all four domain keys under each domain and is invalid.)

**Remaining one-time host cutover** (the repo side is done; until this runs, the UI-defined helper and the YAML helper collide on the same `entity_id`): deploy the files, then in Settings → Devices & services → Helpers **delete every helper that's defined in `helpers.yaml`** (the UI copies), then **restart HA** so the package loads.

After cutover, `helpers.yaml` is the source of truth — edit there, not in the UI, and apply with a Developer Tools → YAML domain reload (Input Number / Input Boolean / Input Select / Timer) or a restart.

The HVAC helpers (all in the same UI-defined-now, mirrored-in-`helpers.yaml` status):

- `input_number.<room>_heat_bound` / `<room>_cool_bound` — the two per-room setpoints (lower / upper).
- `input_number.<room>_temp_differential` — per-room hysteresis (office 1.0, studio 0.5).
- `input_boolean.hvac_enable` — master on/off.
- `input_select.system_hvac_mode` — the single resolved system mode (`heat` / `cool` / `idle` / `off`), written only by the coordinator.
- `timer.mode_min_dwell` (15 min) — minimum heat↔cool dwell.
- `timer.office_head_lockout` (8 min) / `timer.studio_head_lockout` (6 min) — per-head short-cycle lockouts.

## Architecture

### Two rooms, two device pairs per room

Each room has:

1. A **Sinopé Wi-Fi baseboard heater** via the `neviweb130` integration — `climate.neviweb130_climate_th1123wf` (office) / `th1124wf` (studio). Provides `current_temperature`, `hourly_kwh`, and in cold-weather backup mode actually does the heating.
2. A **heat-pump head** (mini-split) controlled via the `cielo_home` HACS integration. Each unit exposes both a `climate` entity (`climate.office`, `climate.studio`) and a power `switch` (`switch.office_power`, `switch.studio_power`) — same physical device, two entities. The HVAC coordinator references these by entity name (`climate.office` / `climate.studio` for the climate side; `switch.office_power` / `switch.studio_power` for the power switch). The two heads share **one outdoor compressor** — a multi-split — so they can never run in opposite modes at the same time (see below).

Independent of the rooms: dehumidifier plug `ab8b624cc66726276f8c0a35c7903c9f` and humidifier plug `60211ed7b46e92fd6dcadf60d8087fd0` share one Zigbee humidity sensor.

### The ecobee-style HVAC coordinator

The control model is **two setpoints per room** — an ecobee, not a single preferred temperature with a swing. Per room the user sets `input_number.<room>_heat_bound` (lower; below it the room wants heat) and `input_number.<room>_cool_bound` (upper; above it the room wants cool). The room floats freely in the dead band between the two bounds. There is no `preferred` and no symmetric `swing`. Where a single comfort value is needed (the backup-heat baseboard target) it is the derived **comfort midpoint** `(heat_bound + cool_bound) / 2`.

Because the two heads share one outdoor compressor (a multi-split), **heat vs cool is a single system-wide decision** — both heads must be in the same mode at any instant, though either can independently idle. So the old per-room controllers are replaced by **one** `hvac_coordinator` automation (one automation for one physical compressor). Its decision macros live in `custom_templates/hvac.jinja` (pure, unit-tested):

- `room_demand(temp, heat_bound, cool_bound, differential, current)` → `heat` / `cool` / `none` for one room, using its reliable temperature `sensor.<room>_baseboard_current_temperature` and a hysteresis differential.
- `resolve_mode(office_demand, studio_demand)` → one system mode, `heat` / `cool` / `idle`, with **heating wins** conflicts: if either room wants heat the whole system heats; cooling runs only when neither room wants heat; a too-warm room whose mode is forbidden simply idles its head.
- `head_target(mode, heat_bound, cool_bound, lead)` → the temperature to command a head, clamped to `[17, 30]`. **`lead` is 0** — the head is commanded to the bound itself, *not* past it. The head's onboard sensor is unreliable and state-dependent (off: it reads refrigerant-pipe temp driven by the *other* head on the shared compressor; running: the fan converges it toward room temp), so we never steer past the bound — a running head would drive the room well past it (the over-cool yo-yo). At the bound, a running head eases off near the bound on its own once its sensor converges; the coordinator does the **real cutoff** against the reliable baseboard sensor as the backstop.

The coordinator fires on the baseboard temp sensors, the four bound + two differential helpers, `input_boolean.hvac_enable`, `input_boolean.backup_heat`, the three short-cycle timers' `timer.finished`, HA start, and a 5-minute safety heartbeat. It short-circuits when any critical baseboard sensor, `switch.<room>_power`, or `climate.<room>` is `unavailable` / `unknown`. It reads the stored mode from `input_select.system_hvac_mode`, resolves the desired mode, then issues the minimum Cielo calls per head to reach the desired state, gating every call on a real desired-vs-current delta — so every Cielo API call is justified (the Cielo dedupe discipline).

**Master enable.** `input_boolean.hvac_enable` is a one-tap "all off" (away / windows open): when off, both heads are forced off regardless of demand.

**Short-cycle protection (four layers):**

1. **Dead band** between the two bounds — the room must traverse it before the opposite action fires (the primary tuning knob).
2. **Per-room differential** `input_number.<room>_temp_differential` — a started head runs `d` degrees past its bound before cutting, lengthening the off-period. Office **1.0 °C** (fast room), studio **0.5 °C**.
3. **Per-head lockout** `timer.<room>_head_lockout` — a minimum **off**-time: armed on every head toggle (on or off), it gates the next turn-**on** until it expires (office 8 min, studio 6 min). It never blocks a turn-**off** — the coordinator turns a head off the instant demand ends, so the head can't be forced to overshoot the bound. A safety force-off still arms the lockout, so a quick re-enable or a backup-heat flap can't restart the compressor immediately.
4. **Inverter modulation** — commanding the bound and letting the head run (instead of chattering the power switch) lets the compressor ramp down near setpoint once the head's own sensor converges to room temp. The per-head lockout is a minimum **off**-time only: it gates the next turn-**on**, and never blocks a turn-**off** (blocking the off forced the head to over-shoot past the bound).

**Anti-flap (heat↔cool).** `timer.mode_min_dwell` (15 min) starts whenever the system enters an active mode that differs from the previous active mode. While it runs, the stored mode is **pinned** to the dwelling active mode and the opposite mode cannot be adopted — even transiently via `idle` (closing the idle-hop bypass). Heads still idle within the dwelling mode when there's no same-direction demand; once the dwell clears, the mode re-resolves freely.

**Observability.** `input_select.system_hvac_mode` (`heat` / `cool` / `idle` / `off`) is written only by the coordinator and tracks the current system mode for the dwell logic and the thermostat tile.

### Backup heat mode

When `sensor.lethbridge_temperature < −12 °C` for 20 minutes, `input_boolean.backup_heat` turns on, both baseboards are pushed to each room's **comfort midpoint** `(heat_bound + cool_bound) / 2`, and the coordinator independently forces **both heads off** (it reads `backup_heat` as a hard-safety force-off) so the baseboards lead. On warmup, baseboards are dropped to `heat_bound − 2.5 °C` so the heat pump leads again. The −2.5 °C offset is what lets the heat pump take primary duty without the baseboard fighting it — don't remove it casually.

### Humidity (independent of HVAC)

A single state-driven controller (`studio_humidity_controller` in `automations.yaml`)
reconciles the dehumidifier plug (`switch.mini_plug_4_socket_1`) and humidifier plug
(`switch.studio_humidifier_socket_1`) from the current reading of the shared Zigbee humidity
sensor — the same reconcile-on-delta pattern as the HVAC controllers. It replaced four
edge-triggered on/off automations that could strand a device (and run both at once) when a
threshold crossing was missed.

Asymmetric hysteresis around `input_number.humidity_set_point` with
`input_number.humidity_tolerance`:

- Dehumidifier: wants on when humidity `≥ set_point + tolerance`, off when `< set_point`
- Humidifier: wants on when humidity `≤ set_point − tolerance`, off when `> set_point`
- Inside `[set_point − tolerance, set_point + tolerance]` each device holds its last state —
  the intentional dead band.

Three invariants are enforced by construction:

- **Never both on.** Turn-on branches require the opposite device to be off; a mutual-exclusion
  safety branch turns off the wrong device (humidity decides) if both are ever on.
- **Relaxation cooldown.** Any controller turn-off starts `timer.humidity_cooldown` (15 min);
  turn-ons are blocked while it runs, so an overshoot can't immediately trip the opposite
  device. The controller is `mode: single` so its own switch events don't restart it mid-run;
  the deferred turn-on is driven by the `timer.finished` trigger and the 5-min heartbeat.
- **Respect manual flips.** `studio_humidity_manual_detector` compares each switch change
  against an `input_boolean.<device>_intended` mirror (set by the controller before it
  commands) to tell manual changes apart from controller ones, and arms a 15-min
  `timer.<device>_manual_grace`; the controller leaves a switch alone while its grace timer is
  active (except the both-on safety).

The humidity helpers (`input_boolean.dehumidifier_intended`, `input_boolean.humidifier_intended`,
and the three `timer.*` entities) follow the same "UI-defined now, mirrored in `helpers.yaml`
for the eventual migration" status as the other helpers.

## Conventions

- Per-room entity names follow `<sensor|input_number|...>.<room>_<thing>`: `sensor.<room>_baseboard_current_temperature`, `input_number.<room>_heat_bound`, `input_number.<room>_cool_bound`, `input_number.<room>_temp_differential`. Stay on this pattern when adding entities.
- The thematic banner comments in `automations.yaml` (`# HVAC controllers`, `# Backup heat`, `# Humidity`) are the file's structure — keep them and group new automations under the right one.
- Automations created in the HA UI get a numeric id (`'1765126659858'`); hand-written ones get descriptive ids (`hvac_coordinator`). Both are valid — match whichever style the section already uses.
