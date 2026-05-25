# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A **Home Assistant configuration** for a two-room space (office + studio), versioned in git. The goal is to mirror the live HA configuration here, with the exceptions called out below.

Tracked:

- `configuration.yaml` — root HA config, template sensors, `neviweb130` integration, notify group
- `automations.yaml` — all automations (HVAC controllers, backup heat, humidity)
- `scripts.yaml`, `scenes.yaml` — included from `configuration.yaml`; currently empty
- `custom_templates/setpoint.jinja` — the heat-pump setpoint macro
- `helpers.yaml` — `input_number` / `input_boolean` / `input_select` definitions; **not yet wired** into `configuration.yaml` (see "Helpers migration" below)
- `secrets.yaml.example` — placeholder showing which `!secret` keys must exist

Not tracked (in `.gitignore`):

- `secrets.yaml` — real credentials. Commit only the `.example`.
- `home-assistant.log*`, `home-assistant_v2.db*`, `.HA_VERSION`, `.uuid`, `deps/`, `tts/`, `image/`, `.cloud/` — HA runtime artifacts
- `.storage/` — HA's internal state store; rewritten constantly, and `.storage/auth*` holds tokens

External entities that automations reference but that are defined elsewhere (Zigbee integrations, weather integrations, mobile companion app): `sensor.lethbridge_temperature`, `sensor.office_temperature`, `sensor.studio_temperature`, `sensor.tz3000_utwgoauk_snzb_02_humidity`, `mobile_app_pixel_8`. Don't assume an entity is undefined just because it isn't grep-able locally.

There is no build / test / lint pipeline. Changes are deployed by syncing these files to the HA instance and reloading the relevant domain (automations, template entities) from the HA UI or via `homeassistant.reload_*` services.

## Custom integrations (HACS)

Not vendored into this repo. If restoring from scratch, install HACS first, then add:

- **claudegel/sinope-130** (integration) → `custom_components/neviweb130` — Sinopé Wi-Fi baseboard heaters; referenced by the `neviweb130:` block in `configuration.yaml`
- **bodyscape/cielo_home** (integration) → `custom_components/cielo_home` — Cielo Home Wi-Fi controller for the heat pumps; provides `climate.office` / `climate.studio`, `switch.office_power` / `switch.studio_power`, and `sensor.office_target_temperature` / `sensor.studio_target_temperature`
- **RomRider/apexcharts-card** (Lovelace plugin) → `www/community/apexcharts-card` — used by the dashboards

## Helpers migration

`helpers.yaml` is committed with values copied verbatim from `.storage/` on the host, but is **not yet included** from `configuration.yaml` because the same helpers are still defined in the UI. To switch over, follow the migration steps at the top of `helpers.yaml`: delete the UI-defined helpers, add three `!include` lines to `configuration.yaml`, then reload from Developer Tools.

Once that's done, `helpers.yaml` becomes the source of truth — edit there, not in the UI.

## Architecture

### Two rooms, two device pairs per room

Each room has:

1. A **Sinopé Wi-Fi baseboard heater** via the `neviweb130` integration — `climate.neviweb130_climate_th1123wf` (office) / `th1124wf` (studio). Provides `current_temperature`, `hourly_kwh`, and in cold-weather backup mode actually does the heating.
2. A **heat pump** (mini-split) controlled via the `cielo_home` HACS integration. Each unit exposes both a `climate` entity (`climate.office`, `climate.studio`) and a power `switch` (`switch.office_power`, `switch.studio_power`) — same physical device, two entities. The automations reference these by their opaque device IDs (office `cd83ce32…`, studio `6aef9334…`); the inline `# office heat pump SWITCH / CLIMATE` comments in `automations.yaml` are the only key tying device IDs to friendly names — preserve them when editing.

Independent of the rooms: dehumidifier plug `ab8b624cc66726276f8c0a35c7903c9f` and humidifier plug `60211ed7b46e92fd6dcadf60d8087fd0` share one Zigbee humidity sensor.

### The two-stage heat-pump control loop

The heat pump's target temperature isn't the user's preferred room temperature — it's a *steering* value computed from how far the room is from preferred. The loop has two stages:

1. **Setpoint computation** (`custom_templates/setpoint.jinja`, exposed as `sensor.<room>_heat_pump_setpoint_temperature` in `configuration.yaml`)
   `setpoint = base_temp − (current_temp − preferred) × 1.25`, clamped to `[17, 30]` °C. `base_temp` comes from a secondary indoor temperature sensor (`sensor.<room>_temperature`); `current_temp` comes from the baseboard heater's built-in thermometer. The room temperature error pushes the setpoint *away* from preferred to make the pump work harder. Rounding is direction-aware: rounds up when the room is too cold, down when too warm. In backup-heat mode the setpoint collapses to `base_temp − 1`.

2. **Apply / gate** (HVAC controllers, event-driven)
   Each room's controller fires on state changes to its setpoint sensor, preferred, swing, or mode (with a 2-minute debounce on mode flapping), plus a 5-minute safety heartbeat. It reads desired state (`desired_on`, `desired_hvac`, `setpoint`) and current state (`switch.<room>_power`'s on/off, `climate.<room>`'s hvac_mode and target temperature), and acts only on real deltas — so every Cielo API call is justified. The controller short-circuits when any critical sensor, switch, or climate entity is `unavailable` or `unknown`, to avoid spurious writes.

The dead band (`swing` = `input_number.<room>_temp_range`) prevents thrash: inside `[preferred − swing, preferred + swing]`, neither `desired_on` nor `desired_off` is true, so no Cielo call is issued.

### Backup heat mode

When `sensor.lethbridge_temperature < −12 °C` for 20 minutes, `input_boolean.backup_heat` turns on, both baseboards are pushed to each room's `preferred` temperature, and the setpoint macro collapses (so the HVAC controllers stop driving the heat pumps hard). On warmup, baseboards are dropped to `preferred − 2.5 °C` so the heat pump leads again. The −2.5 °C offset is what lets the heat pump take primary duty without the baseboard fighting it — don't remove it casually.

### Humidity (independent of HVAC)

Asymmetric hysteresis around `input_number.humidity_set_point` with `input_number.humidity_tolerance`:

- Dehumidifier: on when humidity `> set_point + tolerance`, off when `< set_point`
- Humidifier: on when humidity `< set_point − tolerance`, off when `> set_point`

So inside `[set_point − tolerance, set_point + tolerance]` both stay in whatever state they were last in — that's the intentional dead band.

## Conventions

- Per-room entity names follow `<sensor|input_number|...>.<room>_<thing>`: `sensor.<room>_baseboard_current_temperature`, `sensor.<room>_heat_pump_setpoint_temperature`, `input_number.<room>_preferred_temperature`, `input_number.<room>_temp_range`. Stay on this pattern when adding entities.
- The thematic banner comments in `automations.yaml` (`# HVAC controllers`, `# Backup heat`, `# Humidity`) are the file's structure — keep them and group new automations under the right one.
- Automations created in the HA UI get a numeric id (`'1765126659858'`); hand-written ones get descriptive ids (`office_hvac_controller`). Both are valid — match whichever style the section already uses.
