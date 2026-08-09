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

## Troubleshooting

Most of what looks broken here is a timer doing its job. Both controllers also
re-run on a 5-minute heartbeat, so once whatever was blocking clears, the system
corrects itself within five minutes — you rarely need to intervene.

**Nothing responds at all.** The coordinator refuses to act on bad data: if any
of six entities reads `unavailable` or `unknown` it stops before doing anything,
leaving both heads exactly as they were. The six are the two baseboard
temperature sensors, both heat-pump power switches, and both heat-pump `climate`
entities. Check those first — it's usually Wi-Fi or the Cielo cloud. It retries
every five minutes on its own.

**A head won't restart right after it shut off.** That's the lockout — a minimum
*off*-time of 8 minutes for the office, 6 for the studio, armed every time a head
toggles. It never delays a shut-off, only a restart.

**Cooling won't start although the room is above its cool bound.** Two normal
causes. Either the other room is below its heat bound, and heating wins the
shared compressor; or the system entered heating recently and the 15-minute mode
dwell hasn't expired. Note the dwell re-arms on *every* entry into heating,
including heat → idle → heat, so it can be up to 15 minutes from the last such
hop rather than from the last real mode change.

**The system mode says `heat` but both heads are off.** `system_hvac_mode` is the
compressor's permitted *direction*, not a running indicator. It stays on the
dwelling mode for the full dwell window, and under heating-wins a too-warm room's
head is off while the mode still reads `heat`. The thermostat tiles show the true
state — their status line checks each head's power switch as well.

**The studio head is set to 21.5 when its bound is 20.** The 1.5 °C heat lead,
deliberate. The commanded number is not the cut-off; the baseboard thermometer is.

**The room drifts past its heat bound before the head stops.** Also deliberate —
1.0 °C in the office, 0.5 in the studio. Cutting exactly at the bound would
short-cycle the compressor.

**Both thermostat tiles went to `off` together.** There is one master switch, and
both tiles' on/off control writes it.

**The baseboards are heating and the heat pump is off.** Backup heat: the outdoor
sensor stayed below −12 °C for 20 minutes. It sends a phone notification on the
way in and on the way out, and clears once outdoors holds above −12 °C for 20
minutes.

**The humidifier won't start after the dehumidifier stopped.** A 30-minute
cross-device cooldown, so a turn-off overshoot settles before the opposite device
reacts. A device's own cooldown never blocks itself.

**A humidity plug ignores the controller.** Flipping a plug by hand is detected
and buys a 15-minute grace period, during which the controller leaves it alone.
The only exception is the safety that stops both running at once.

**The dehumidifier stops at the set point rather than below it.** By design, and
the hysteresis is asymmetric: `tolerance` decides where a device *starts*, the set
point is where it *stops*. Widening the tolerance will not lower the stop point.

**You edited `custom_templates/hvac.jinja` and nothing changed.** Home Assistant
holds custom Jinja in memory. Reloading automations or template entities does not
re-read the file and raises no error — the old macro just keeps running. Call
`homeassistant.reload_custom_templates` (or `homeassistant.reload_all`).

**A config change I made on the box disappeared.** Expected. The Git pull
add-on reverts `/config` to `main` every five minutes. Make the change in the
repository instead — see "How changes reach the box".

**Home Assistant restarted on its own.** Also expected, if a commit landed on
`main` in the last five minutes. Documentation-only commits do not restart it;
`restart_ignore` in the add-on config lists what is exempt.

## Repository layout

| Path | What it is |
|------|------------|
| `configuration.yaml` | Root HA config: template sensors, integrations, the thermostat-tile entities |
| `automations.yaml` | All automations: the HVAC coordinator, backup heat, humidity |
| `custom_templates/hvac.jinja` | The pure decision logic for the coordinator (heat/cool/idle), unit-tested |
| `helpers.yaml` | The input numbers / booleans / timers (bounds, master switch, etc.) |
| `tests/` | `pytest` suite covering the control logic |
| `ha-version.txt` | The Home Assistant release the box runs; the test harness is pinned and asserted against it |
| `.yamllint.yml` | yamllint rules for the three hand-edited HA config files |
| `.github/workflows/ci.yml` | CI: yamllint, actionlint and the test suite, on every pull request and on `main` |
| `.env.example` | Template for the gitignored `.env` holding your Home Assistant API token |
| `docs/superpowers/specs/` | Dated design docs, oldest first. Start with `2026-06-15-ecobee-style-hvac-design.md`; it supersedes the earlier changeover-advisor and steering-loop designs. |
| `docs/superpowers/plans/` | Implementation plans, one per design. Mostly history rather than a queue; the `- [ ]` boxes were never ticked and mean nothing. Do not re-execute one. The exception is `2026-08-09-cicd-github-actions.md`, whose host-setup task is genuinely outstanding — see "How changes reach the box". |
| `CLAUDE.md` | Conventions and guidance for working in this repo |

Some devices and sensors are provided by HACS custom integrations (Cielo Home,
Sinopé/neviweb, a template-climate integration for the tiles) — see `CLAUDE.md`
for the install list.

## Working on it

Changes are made here, then reach the live Home Assistant box as "How changes
reach the box" below describes. The control logic has a test suite:

```sh
uv venv .venv --python 3.14 --seed
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

See `CLAUDE.md` for the full setup, conventions, and the helper-migration notes.

## How changes reach the box

**Not active yet.** Everything in this section starts applying once the Git
pull add-on is installed on the Home Assistant host. Until then a merge to
`main` reaches nothing: changes get to the box by copying the files across and
reloading by hand.

This config deploys itself. The Home Assistant **Git pull add-on** checks
`main` every five minutes, hard-resets `/config` to it, and restarts Home
Assistant. Changes reach the hardware without a manual sync.

Three consequences worth knowing before you edit anything:

**The box is read-only for tracked files.** Editing `automations.yaml` in File
Editor or Studio Code Server works for about five minutes, then the add-on
reverts it. Change it here, open a PR, let it merge.

**A deploy restarts Home Assistant.** Roughly 30–60 seconds with no heating,
cooling or humidity control. Both coordinators re-run on startup and all timers
restore, so the system reconciles itself — but an invalid config means HA does
not come back at all, which is why `main` is gated on CI.

**Adding a secret is a box-first operation.** Put the real value in
`secrets.yaml` on the host *before* merging the change that references it.
The reverse order starts HA into a failure.

### Rolling back

**Do not roll back on the box.** A `git reset` in `/config` is undone within
five minutes when the add-on re-pulls `main`. Either:

1. **Stop the Git pull add-on first**, then reset `/config`. Fastest under
   pressure, and the box stays put until you restart the add-on.
2. **Revert on `main`** — a PR, a CI cycle, then the add-on picks it up. The
   durable fix, but slower.

Do (1) to stop the bleeding, then (2) to make it stick.

## Talking to the live Home Assistant

The test suite covers the control logic in isolation, but some questions only the
running system can answer — what a sensor actually reads right now, how a
temperature moved overnight, what a `custom_templates/hvac.jinja` macro renders
to against live state. Home Assistant exposes all of that over a REST API at
`http://homeassistant.local:8123`, authenticated with a **long-lived access
token**.

The token is per-person, not shared: generate your own, and revoke it when you
stop working on this.

### Generating a token

1. Open `http://homeassistant.local:8123` and sign in.
2. Click your user name at the bottom of the sidebar to open your profile.
3. Go to the **Security** tab.
4. Scroll to **Long-lived access tokens** and click **Create token**.
5. Name it after the machine you'll use it from, so it can be revoked
   individually later.
6. **Copy the token immediately.** Home Assistant displays it exactly once; if
   you close the dialog without copying, delete it and create another.

A token inherits the permissions of the account that created it — one made from
an admin account can do anything you can do in the UI. It stays valid for ten
years unless you revoke it, which is done from that same screen.

### Storing it

Copy `.env.example` to `.env` in the repo root and paste the token in:

```sh
cp .env.example .env
$EDITOR .env          # set HOME_ASSISTANT_TOKEN=...
```

`.env` is gitignored, like `secrets.yaml`. The two are not interchangeable:
`secrets.yaml` lives on the Home Assistant host and fills in `!secret` lookups in
`configuration.yaml`, while `.env` never leaves your machine and only
authenticates API calls made from here.

Confirm it works — this reads the coordinator's current resolved mode and changes
nothing:

```sh
set -a; . ./.env; set +a
curl -s -H "Authorization: Bearer $HOME_ASSISTANT_TOKEN" \
  http://homeassistant.local:8123/api/states/input_select.system_hvac_mode
```

A `401` means the token is wrong or revoked. No response at all means the box
isn't reachable from your network.

AI coding agents working in this repo read the same `.env`. They inspect state
freely and ask before calling any service, since a service call either commands
real hardware or deploys config; [`CLAUDE.md`](CLAUDE.md) has the exact rule and
the useful endpoints.

## If you found this and want to reuse it

You're welcome to — it's MIT licensed (see [`LICENSE`](LICENSE)). But read this
first, because it is **not** a general-purpose Home Assistant package and it will
not work if you drop it into your own config unchanged.

It is written against one specific installation:

- Two named rooms, `office` and `studio`, with a **shared-compressor multi-split**.
  The single system-wide heat/cool decision — the core of the coordinator — only
  makes sense because both heads share one outdoor unit. If your heads are
  independent, this design is wrong for you.
- Specific hardware and HACS integrations: Sinopé baseboards via `neviweb130`,
  heat-pump heads via `cielo_home`, Tuya plugs, one Zigbee humidity sensor. Entity
  IDs are hard-coded throughout `automations.yaml`.
- Constants tuned by observation in *this* building — the per-room differentials,
  the studio's heating lead, the lockout and dwell durations, the humidity band.
  They encode this space's thermal mass and sensor placement, not general truths.

The tests are the honest description of what is actually verified. Run them:
they exercise the decision macros and load the automations from the real YAML,
but they mock every service call, so nothing here has been proven against real
hardware other than by running it in this one space.

It controls real heating, cooling, and humidification equipment. If you adapt it,
verify it against your own hardware before trusting it unattended.
