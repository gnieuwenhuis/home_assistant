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
- **It commands a setpoint, not a switch.** Each head is given a target
  temperature and the mini-split's variable-speed compressor eases off as the
  room arrives — working harder when the room is further away, gentler as it
  gets close. The office is commanded its bound; the studio is commanded 1.5 °C
  past its heat bound, because the studio head's own thermometer reads warm and
  without that nudge its compressor loafs and the room sags. That commanded
  number is not the cut-off point — the trusted baseboard thermometer is what
  switches a head off.
- **Short-cycle protection.** A compressor shouldn't switch on and off rapidly.
  A started head runs a little past its bound before cutting (1.0 °C in the
  office, 0.5 °C in the studio), each head then has a minimum off-time (a
  "lockout") before it can restart, and there's a minimum dwell before the
  system flips between heating and cooling.
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
ecobee-style **thermostat tile** (the dashboard layout itself isn't tracked in
this repo — see `CLAUDE.md`) showing that room's current temperature with its
heat and cool bounds as draggable handles — dragging them sets that room's
bounds, and the tile's status line (heating / cooling / idle) follows that
room's own head. The tile's **on/off control is the one master switch, not a
per-room one**: switching either tile off turns the whole heat-pump system
off — both rooms — and the other tile then reads `off` as well. There is no
heat-vs-cool choice to make anywhere; the coordinator decides.

## Repository layout

| Path | What it is |
|------|------------|
| `configuration.yaml` | Root HA config: template sensors, integrations, the thermostat-tile entities |
| `automations.yaml` | All automations: the HVAC coordinator, backup heat, humidity |
| `custom_templates/hvac.jinja` | The pure decision logic for the coordinator (heat/cool/idle), unit-tested |
| `helpers.yaml` | The input numbers / booleans / timers (bounds, master switch, etc.) |
| `tests/` | `pytest` suite covering the control logic |
| `docs/superpowers/specs/` | Dated design docs, oldest first. Start with `2026-06-15-ecobee-style-hvac-design.md`; it supersedes the earlier changeover-advisor and steering-loop designs. |
| `docs/superpowers/plans/` | Implementation plans, one per design — all six are merged. This is a history, not a queue; the `- [ ]` boxes were never ticked and mean nothing. Do not re-execute one. |
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
