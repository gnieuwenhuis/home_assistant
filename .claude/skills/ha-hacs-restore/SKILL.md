---
name: ha-hacs-restore
description: Use when rebuilding this Home Assistant instance from scratch, or when checking which custom HACS integrations and Lovelace plugins the tracked config depends on but does not vendor - the neviweb130 baseboard integration, the cielo_home heat-pump controller, the Climate Template facade, and apexcharts-card.
---

# Custom integrations (HACS)

Not vendored into this repo. If restoring from scratch, install HACS first, then add:

- **claudegel/sinope-130** (integration) → `custom_components/neviweb130` — Sinopé Wi-Fi baseboard heaters; referenced by the `neviweb130:` block in `configuration.yaml`
- **bodyscape/cielo_home** (integration) → `custom_components/cielo_home` — Cielo Home Wi-Fi controller for the heat pumps; provides `climate.office` / `climate.studio`, `switch.office_power` / `switch.studio_power`, and `sensor.office_target_temperature` / `sensor.studio_target_temperature`
- **Climate Template** (integration, platform `climate_template` — e.g. a maintained fork of jcwillox/hass-template-climate; confirm the most-maintained fork at install time) → provides the display/entry facade `climate.office_thermostat` / `climate.studio_thermostat`, defined in the `climate:` block of `configuration.yaml`. Its per-room / global field split is in CLAUDE.md under "Two rooms, two device pairs per room".
- **RomRider/apexcharts-card** (Lovelace plugin) → `www/community/apexcharts-card` — used by the dashboards

## The dashboards do not restore from this repo

The Lovelace dashboards themselves are not restorable from this repo. They live in `.storage/lovelace*`, excluded by `.gitignore`, so a from-scratch restore comes up with HA's auto-generated default dashboard and none of the tiles — including the ecobee thermostat tile and the apexcharts cards. Closing that gap means either exporting each dashboard's raw configuration into a tracked directory, or tracking `.storage/lovelace` and `.storage/lovelace_dashboards` per-file, which `.gitignore`'s own comment already anticipates.

Reading a dashboard's stored config to export it goes through the WebSocket API — see the `ha-websocket-api` skill.
