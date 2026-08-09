# Design record

Dated spec/plan pairs, one per change to the HVAC and humidity control: a spec
states the design, and the plan beside it is the task-by-task build. This file is
aimed at whoever opens one of these documents directly — the directory is a
history, not a work queue, and nothing inside the files themselves says so.

## Don't execute these plans

All six plans have been carried out. The subject of each is live in the config
today — `studio_humidity_controller` and `studio_heat_lead` in
`automations.yaml`, `hvac_coordinator` across `automations.yaml` and
`custom_templates/hvac.jinja`, the helpers package in `configuration.yaml` —
except the changeover advisor, which was removed. See below.

Two signals inside the files point the wrong way:

- **Checkboxes.** 206 `- [ ]` and zero `- [x]` across the six plans. None was
  ever ticked, including in plans whose work shipped, so checkbox state tracks
  nothing.
- **The opening banner.** All six carry `REQUIRED SUB-SKILL: Use
  superpowers:subagent-driven-development ... to implement this plan
  task-by-task`. That is authoring boilerplate carried in at creation, not a
  standing instruction.

## The changeover advisor was removed

`plans/2026-06-07-changeover-advisor.md`, its `-blend` companion, and both
matching specs describe a forecast-driven heat-pump changeover advisor. It was
built over six commits ending `7ac1ca4` and removed whole in `f2d051b`. Nothing
in `automations.yaml`, `configuration.yaml`, `helpers.yaml`, or
`custom_templates/` references it today.

Both its specs still read `**Status:** Approved design, pending implementation
plan`, which is wrong in both directions. Don't resurrect it.

## Which document is current

`specs/2026-06-15-ecobee-style-hvac-design.md` is the design in force. Its own
header records what it displaced: "the changeover advisor ... and the two-stage
steering control loop described in `2026-05-25-ha-simplification-design.md`".
`specs/2026-06-22-asymmetric-heating-lead-design.md` amends it with the per-room
heating lead.

For what the system does *now*, read the root `CLAUDE.md` — it tracks the live
config. These documents record what was decided on a date; later work that
changes the answer is not back-ported into them, which is why the changeover
specs still call themselves pending.
