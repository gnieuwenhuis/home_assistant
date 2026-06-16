# Office + Studio Home Assistant config

This repository is the [Home Assistant](https://www.home-assistant.io/)
configuration for a small two-room workspace — an **office** and a **studio** —
versioned in git. It controls heating, cooling, and humidity for the two rooms
and mirrors what runs on the live Home Assistant box.

If you're an AI coding agent, read [`CLAUDE.md`](CLAUDE.md) instead — it has the
working conventions and entity-naming rules. This README is the human-friendly
overview of how the space is set up and how the automation behaves.

## The space

Two rooms with quite different thermal behavior:

- **Office** — small (~⅓ the studio's size). It heats up fast on its own:
  it's occupied most of the workday and the computers in it throw off a lot of
  heat. So it often needs *cooling* even when the studio doesn't.
- **Studio** — larger, more thermally stable, but with more exterior wall area,
  so it loses heat faster in winter and tends to drive the *heating* demand.

That asymmetry (office runs warm, studio runs cool) is the situation the HVAC
control is built around.

## The hardware

Each room has two heating/cooling devices:

1. **A heat-pump head (mini-split)** — the primary comfort device, controlled
   through the [Cielo Home](https://www.cielowigle.com/) Wi-Fi controller.
   **Important:** the two heads share **one outdoor compressor** (a multi-split).
   That means the whole system can only be **heating or cooling at any one
   moment** — the two heads can never run in opposite modes at the same time,
   though either head can idle (turn off) independently.
2. **A Sinopé Wi-Fi baseboard heater** — the *backup* heat source. It only does
   real work in very cold weather (see "Backup heat" below). Its built-in
   thermometer is also the **trusted room-temperature reading** for control,
   because the heat-pump head's own sensor is unreliable (when the head is off,
   it reads refrigerant-pipe temperature driven by the *other* head; it only
   reflects room temperature once it's been running a while).

The **studio** additionally has a **humidifier** and a **dehumidifier** (smart
plugs) sharing one humidity sensor.

Outdoor temperature comes from a Lethbridge weather sensor and drives the
cold-weather backup behavior.

## How heating & cooling works

The control mimics an **ecobee** thermostat, adapted for the shared-compressor
constraint. For each room you set **two temperatures**:

- a **heat bound** (lower) — below it, the room wants heat;
- a **cool bound** (upper) — above it, the room wants cooling.

Between the two bounds the room just floats — nothing runs. A single automation,
the **HVAC coordinator**, looks at both rooms and decides what the shared system
should do:

- **Automatic mode.** It picks heating vs. cooling on its own from the two
  rooms' temperatures — there is no manual "heat/cool/off" switch to flip with
  the seasons.
- **Heating wins.** Because both heads share one compressor, if *either* room is
  below its heat bound the whole system heats; cooling only runs when *neither*
  room wants heat. A room that wants the opposite just sits idle (its head off)
  until the conflict clears.
- **It holds at the bound, it doesn't overshoot.** Each head is commanded to its
  room's bound and lets the mini-split's variable-speed compressor ease off as
  the room arrives — working harder when the room is further away, gentler as it
  gets close. The trusted baseboard thermometer is the backstop that switches a
  head off if it goes past the bound.
- **Short-cycle protection.** A compressor shouldn't switch on and off rapidly,
  so each head has a minimum off-time (a "lockout") before it can restart, and
  there's a minimum dwell before the system flips between heating and cooling.
- **Master switch.** One toggle turns the whole heat-pump system off (for "away"
  or windows-open); the baseboards' backup behavior is separate.

### Backup heat (very cold weather)

Heat pumps lose efficiency in deep cold. When the outdoor temperature stays
below **−12 °C**, the system switches the heat-pump heads **off** and lets the
**Sinopé baseboard heaters** carry the heating instead. When it warms back up,
the baseboards step down and the heat pump leads again.

## How humidity works (studio)

A separate controller keeps the studio's humidity near a set point using the
humidifier and dehumidifier:

- runs the **dehumidifier** when it's too humid, the **humidifier** when it's
  too dry, and neither inside a comfortable dead band;
- never runs both at once;
- waits a cooldown after switching a device off before starting the other (so it
  doesn't ping-pong), and respects a manual switch flip for a while.

It's independent of the heating/cooling system.

## How you interact with it

Everything is driven by Home Assistant **helpers** (the per-room bounds, the
master on/off, the humidity set point, etc.). On the dashboard, each room has an
ecobee-style **thermostat tile** showing the current room temperature with the
heat and cool bounds as draggable handles — dragging them sets that room's
bounds. You normally never touch heat-vs-cool; the coordinator decides.

## Repository layout

| Path | What it is |
|------|------------|
| `configuration.yaml` | Root HA config: template sensors, integrations, the thermostat-tile entities |
| `automations.yaml` | All automations: the HVAC coordinator, backup heat, humidity |
| `custom_templates/hvac.jinja` | The pure decision logic for the coordinator (heat/cool/idle), unit-tested |
| `helpers.yaml` | The input numbers / booleans / timers (bounds, master switch, etc.) |
| `tests/` | `pytest` suite covering the control logic |
| `docs/superpowers/specs/` | Design docs — start with the ecobee-style HVAC design |
| `docs/superpowers/plans/` | The implementation plan for the current design |
| `CLAUDE.md` | Conventions and guidance for working in this repo |

Some devices and sensors are provided by HACS custom integrations (Cielo Home,
Sinopé/neviweb, a template-climate integration for the tiles) — see `CLAUDE.md`
for the install list.

## Working on it

This config is **not** auto-deployed. Changes are made here, then synced to the
live Home Assistant box and reloaded (or HA restarted). The control logic has a
test suite:

```sh
uv venv .venv --python 3.14 --seed
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

See `CLAUDE.md` for the full setup, conventions, and the helper-migration notes.
