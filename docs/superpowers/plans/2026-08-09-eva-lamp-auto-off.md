# Eva Lamp Auto-Off Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch the Eva lamp's Tuya plug off 30 minutes after any person turns it on, while leaving automation-commanded turn-ons alone.

**Architecture:** One `timer` helper in `helpers.yaml` plus one automation in `automations.yaml` with three branches — arm on a human turn-on, cancel on turn-off, switch off when the timer finishes. "Human" is decided by inspecting the state change's context: only an automation-commanded change carries a `parent_id`. No new template macros, no new integration.

**Tech Stack:** Home Assistant YAML (2026.8-era `triggers:` / `conditions:` / `actions:` syntax), Jinja2 templates, pytest with `pytest-homeassistant-custom-component==0.13.355`.

Spec: `docs/superpowers/specs/2026-08-09-eva-lamp-auto-off-design.md`

## Global Constraints

- Target entity is `switch.eva_lamp_socket_1`. It does **not exist yet** — see Prerequisite below. Every test in this plan sets its state directly, so the suite passes regardless.
- Timer entity is `timer.eva_lamp_auto_off`, duration exactly `"00:30:00"`, `restore: true`.
- Automation id is `eva_lamp_auto_off` (descriptive style, not the UI numeric style), alias `Eva Lamp Auto Off`.
- Use the modern HA keys the rest of `automations.yaml` uses: `triggers:` / `conditions:` / `actions:`, and `- trigger: state` / `- action: switch.turn_off` inside them. Do **not** use the legacy `trigger:` / `action:` block names.
- Comments follow `.claude/rules/code-comments.md`: timeless present, no change narrative.
- Run tests with `/Users/gregn/Documents/office/.venv/bin/pytest` — the venv lives in the main checkout, not in this worktree.
- Do not call any Home Assistant service against the live instance. This plan is repo-only; deployment is manual and belongs to the user.

## Prerequisite (manual, user-performed — not a code task)

The plug is currently registered as `switch.rabbitry_heater_socket_1` and is
`unavailable`. Entity IDs live in HA's entity registry under `.storage/`, which
is gitignored, so this rename cannot be done from the repo:

> Settings → Devices & services → Entities → `switch.rabbitry_heater_socket_1`
> → rename entity ID to `switch.eva_lamp_socket_1`, friendly name to `Eva Lamp`.

Until that is done the automation targets an entity that does not exist and
silently never fires. The tests do not depend on it.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `helpers.yaml` | Modify (append to the `timer:` block, currently ends line 158) | Declares `timer.eva_lamp_auto_off` |
| `tests/test_helpers_yaml.py` | Modify (append) | Asserts the timer exists with the right duration and restore |
| `automations.yaml` | Modify (append after line 542) | The `# Lamps` banner and the `eva_lamp_auto_off` automation |
| `tests/test_eva_lamp_auto_off.py` | Create | Behavior coverage for all three branches and the context discriminator |
| `CLAUDE.md` | Modify | Architecture + external-entity + helper-list entries |
| `README.md` | Modify | Human-facing description and a troubleshooting entry |

---

### Task 1: The timer helper

**Files:**
- Modify: `helpers.yaml` (append to the `timer:` block, after line 158)
- Test: `tests/test_helpers_yaml.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: entity `timer.eva_lamp_auto_off`, duration 30 minutes, `restore: true`. Task 2's automation targets it by that exact ID.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_helpers_yaml.py`:

```python
async def test_eva_lamp_auto_off_timer(hass_helpers):
    s = hass_helpers.states.get("timer.eva_lamp_auto_off")
    assert s is not None
    assert s.attributes["duration"] == "0:30:00"
    assert s.attributes["restore"] is True
```

Note the attribute is HA's normalized `"0:30:00"` (a `str(timedelta)`), not the
`"00:30:00"` written in YAML.

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/gregn/Documents/office/.venv/bin/pytest tests/test_helpers_yaml.py::test_eva_lamp_auto_off_timer -v`

Expected: FAIL — `assert None is not None`, because the entity does not exist yet.

- [ ] **Step 3: Add the helper**

Append to the `timer:` block at the end of `helpers.yaml`:

```yaml

  # Auto-off for the Eva lamp: armed by any human turn-on, cancelled when the
  # lamp is switched off. restore: true carries a running cutoff across a
  # restart, so a lamp switched on before a reboot still goes off on schedule.
  eva_lamp_auto_off:
    name: Eva Lamp Auto Off
    duration: "00:30:00"
    restore: true
```

Keep it as its own group separated by a blank line, matching how the humidity
timers and the HVAC timers are grouped in that block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/gregn/Documents/office/.venv/bin/pytest tests/test_helpers_yaml.py -v`

Expected: PASS — the new test plus all seven existing ones. `test_obsolete_helpers_removed` must still pass; the new timer is not in its list.

- [ ] **Step 5: Commit**

```bash
git add helpers.yaml tests/test_helpers_yaml.py
git commit -m "Add the eva_lamp_auto_off timer helper"
```

---

### Task 2: The automation

**Files:**
- Modify: `automations.yaml` (append after line 542)
- Create: `tests/test_eva_lamp_auto_off.py`

**Interfaces:**
- Consumes: `timer.eva_lamp_auto_off` from Task 1.
- Produces: automation entity `automation.eva_lamp_auto_off`, id `eva_lamp_auto_off`. Trigger ids `manual_on`, `lamp_off`, `timer_done` are internal to the automation; nothing else references them.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_eva_lamp_auto_off.py`:

```python
"""Level 3 tests: eva_lamp_auto_off loaded from automations.yaml.

Unlike the other Level 3 suites, these leave the automation ENABLED and drive
real state changes carrying an explicit Context. The rule under test — whether a
turn-on was commanded by an automation — reads trigger.to_state.context, which
`automation.trigger` never populates, so the automation.trigger pattern used by
test_hvac_coordinator.py and test_humidity_controller.py cannot reach it. Firing
the triggers for real is also the only coverage in this repo of a trigger block.

Context shapes, and what each one means:
    Context()                     physical button on the plug   -> arms
    Context(user_id="...")        HA dashboard / UI toggle      -> arms
    Context(parent_id="...")      an automation commanded it    -> does not arm
"""
from datetime import timedelta

import pytest
import yaml
from homeassistant.core import Context
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_mock_service

from tests.conftest import REPO_ROOT

LAMP = "switch.eva_lamp_socket_1"
TIMER = "timer.eva_lamp_auto_off"


@pytest.fixture
async def lamp(hass_helpers):
    hass = hass_helpers
    autos = yaml.safe_load((REPO_ROOT / "automations.yaml").read_text())
    chosen = [a for a in autos if a.get("id") == "eva_lamp_auto_off"]
    assert len(chosen) == 1, "eva_lamp_auto_off missing from automations.yaml"
    assert await async_setup_component(hass, "automation", {"automation": chosen})
    hass.states.async_set(LAMP, "off")
    await hass.async_block_till_done()
    calls = {"off": async_mock_service(hass, "switch", "turn_off")}
    yield hass, calls
    await hass.services.async_call(
        "automation", "turn_off", {"entity_id": "all"}, blocking=True
    )
    await hass.services.async_call(
        "timer", "cancel", {"entity_id": TIMER}, blocking=True
    )
    await hass.async_block_till_done()


async def press(hass, state, context):
    """Drive a real state change so the automation's triggers fire."""
    hass.states.async_set(LAMP, state, context=context)
    await hass.async_block_till_done()


def _entities(call):
    e = call.data.get("entity_id")
    return e if isinstance(e, list) else [e]


# --- the discriminator ---------------------------------------------------

async def test_physical_press_arms_the_timer(lamp):
    hass, _ = lamp
    await press(hass, "on", Context())
    assert hass.states.get(TIMER).state == "active"


async def test_ui_toggle_arms_the_timer(lamp):
    hass, _ = lamp
    await press(hass, "on", Context(user_id="a1b2c3"))
    assert hass.states.get(TIMER).state == "active"


async def test_automation_commanded_on_does_not_arm_the_timer(lamp):
    hass, _ = lamp
    await press(hass, "on", Context(parent_id="01JABCDEF0123456789ABCDEFG"))
    assert hass.states.get(TIMER).state == "idle"


async def test_reconnect_already_on_arms_the_timer(lamp):
    # The plug rests `unavailable`; coming back already on is device-originated,
    # so it earns a cutoff rather than staying on indefinitely.
    hass, _ = lamp
    await press(hass, "unavailable", Context())
    await press(hass, "on", Context())
    assert hass.states.get(TIMER).state == "active"


# --- cancellation --------------------------------------------------------

async def test_turning_the_lamp_off_cancels_the_timer(lamp):
    hass, _ = lamp
    await press(hass, "on", Context())
    assert hass.states.get(TIMER).state == "active"
    await press(hass, "off", Context())
    assert hass.states.get(TIMER).state == "idle"


# --- the cutoff ----------------------------------------------------------

async def test_timer_finished_switches_the_lamp_off(lamp):
    hass, calls = lamp
    await press(hass, "on", Context())
    hass.bus.async_fire("timer.finished", {"entity_id": TIMER})
    await hass.async_block_till_done()
    assert len(calls["off"]) == 1
    assert LAMP in _entities(calls["off"][0])


async def test_timer_finished_is_a_no_op_when_already_off(lamp):
    # Guards against a redundant call at the Tuya cloud: HA does not dedupe
    # service calls, so the branch checks the lamp is still on.
    hass, calls = lamp
    hass.bus.async_fire("timer.finished", {"entity_id": TIMER})
    await hass.async_block_till_done()
    assert calls["off"] == []


async def test_second_press_gives_a_fresh_full_window(lamp, freezer):
    hass, _ = lamp
    await press(hass, "on", Context())
    freezer.tick(timedelta(minutes=10))
    await press(hass, "off", Context())
    await press(hass, "on", Context())
    finishes = dt_util.parse_datetime(
        hass.states.get(TIMER).attributes["finishes_at"]
    )
    remaining = finishes - dt_util.utcnow()
    assert timedelta(minutes=29) < remaining <= timedelta(minutes=30)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/Users/gregn/Documents/office/.venv/bin/pytest tests/test_eva_lamp_auto_off.py -v`

Expected: every test FAILS at the fixture with `AssertionError: eva_lamp_auto_off missing from automations.yaml`.

- [ ] **Step 3: Add the automation**

Append to the end of `automations.yaml`:

```yaml

# ============================================================
# Lamps
# ------------------------------------------------------------
# The Eva lamp's plug switches itself off 30 minutes after a
# person turns it on. Home Assistant attaches a context to every
# state write, and only an automation-commanded change carries a
# parent_id — so a single `parent_id is none` check admits both
# the physical button (no user, no parent) and the dashboard
# (user, no parent) while excluding a commanded turn-on. An
# automation triggered with no triggering context of its own (a
# time trigger, or HA start) also reports no parent and would
# read as human; nothing commands this plug, so that gate is
# unreachable. Switching the lamp off cancels the pending cutoff,
# and the cutoff re-checks the lamp is on, so neither path fires
# a redundant call at the Tuya cloud.
# ============================================================

- id: eva_lamp_auto_off
  alias: Eva Lamp Auto Off
  description: >-
    Switch the Eva lamp off 30 minutes after a person turns it on. The physical
    button and the Home Assistant UI both arm the cutoff; a turn-on commanded by
    an automation does not. Switching the lamp off cancels a pending cutoff.
  triggers:
  - trigger: state
    entity_id: switch.eva_lamp_socket_1
    to: 'on'
    id: manual_on
  - trigger: state
    entity_id: switch.eva_lamp_socket_1
    to: 'off'
    id: lamp_off
  - trigger: event
    event_type: timer.finished
    event_data:
      entity_id: timer.eva_lamp_auto_off
    id: timer_done
  actions:
  - choose:
    # Jinja `and` short-circuits, so trigger.to_state is only read on the
    # branch whose trigger actually carries one.
    - conditions: >-
        {{ trigger.id == 'manual_on'
           and trigger.to_state.context.parent_id is none }}
      sequence:
      - action: timer.start
        target:
          entity_id: timer.eva_lamp_auto_off
    - conditions: "{{ trigger.id == 'lamp_off' }}"
      sequence:
      - action: timer.cancel
        target:
          entity_id: timer.eva_lamp_auto_off
    - conditions: >-
        {{ trigger.id == 'timer_done'
           and is_state('switch.eva_lamp_socket_1', 'on') }}
      sequence:
      - action: switch.turn_off
        target:
          entity_id: switch.eva_lamp_socket_1
  mode: queued
```

Two details that matter and are easy to get wrong:

- `to: 'on'` must be quoted. Unquoted `on` is YAML boolean `true`, and the
  trigger then never matches the string state `"on"`.
- A state trigger carrying `to:` does not fire on attribute-only changes, so a
  lamp already `on` cannot re-arm itself.

- [ ] **Step 4: Run tests to verify they pass**

Run: `/Users/gregn/Documents/office/.venv/bin/pytest tests/test_eva_lamp_auto_off.py -v`

Expected: PASS, all eight.

- [ ] **Step 5: Run the whole suite**

Run: `/Users/gregn/Documents/office/.venv/bin/pytest`

Expected: PASS. `automations.yaml` is parsed by the HVAC and humidity suites too, so a YAML error there fails those as well — this step is what catches it.

- [ ] **Step 6: Commit**

```bash
git add automations.yaml tests/test_eva_lamp_auto_off.py
git commit -m "Switch the Eva lamp off 30 minutes after a human turns it on"
```

---

### Task 3: Documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: the entity and automation names from Tasks 1 and 2.
- Produces: nothing code-facing.

- [ ] **Step 1: Record the entity in CLAUDE.md's external-entity list**

In the paragraph beginning "External entities that automations reference but
that are defined elsewhere", add `switch.eva_lamp_socket_1` (Eva lamp plug) to
the list. It is a Tuya cloud entity like the two humidity plugs, so it is not
grep-able locally.

- [ ] **Step 2: Add a CLAUDE.md architecture subsection**

Add a `### The Eva lamp auto-off` subsection under `## Architecture`, after
`### Humidity (independent of HVAC)`:

```markdown
### The Eva lamp auto-off

A third Tuya Mini Plug drives the Eva lamp. `eva_lamp_auto_off` in
`automations.yaml` switches it off 30 minutes after a person turns it on, using
`timer.eva_lamp_auto_off` (30 min, `restore: true`).

"A person" is read off the state change's context: HA gives an
automation-commanded change a `parent_id`, so `parent_id is none` admits both
the physical button (no user, no parent) and the dashboard (user, no parent)
while excluding a commanded turn-on. That context survives the Tuya cloud
round-trip. The gate has one hole — an automation triggered with no triggering
context of its own, such as a time trigger or HA start, also reports no parent —
which is unreachable while nothing commands this plug. Wiring any automation to
this plug means revisiting it, and `input_boolean.*_intended` in
`studio_humidity_manual_detector` is the precise alternative.

Switching the lamp off cancels a pending cutoff, and the cutoff re-checks the
lamp is on before calling, so neither path issues a redundant Tuya call. A plug
that reconnects already `on` arms a fresh 30 minutes rather than staying on
indefinitely.

The entity is `switch.eva_lamp_socket_1` — named for the device rather than a
room, unlike the paired per-room HVAC entities.
```

- [ ] **Step 3: Note the helper in CLAUDE.md**

The bulleted helper list under `## Helpers migration` covers the HVAC helpers
only — the humidity helpers live in their own section's closing paragraph — so
the Eva lamp's helper goes in its own subsection, not in that list. The Step 2
text already carries it (`timer.eva_lamp_auto_off` (30 min, `restore: true`)).
Confirm it appears exactly once across the whole file:

Run: `grep -c "eva_lamp_auto_off" CLAUDE.md`

Expected: `2` — once in the automation reference, once for the timer.

- [ ] **Step 4: Add the README description**

Add a `## The Eva lamp` section to `README.md` after `## How humidity works
(studio)`:

```markdown
## The Eva lamp

The Eva lamp runs off a Tuya plug that switches itself off 30 minutes after
anyone turns it on — whether from the button on the plug or from the Home
Assistant dashboard. Turning it off early cancels the pending switch-off, and
turning it on again always gives a fresh 30 minutes rather than the remainder of
the last one.

There is no way to run it indefinitely short of disabling the
`Eva Lamp Auto Off` automation.
```

- [ ] **Step 5: Add the troubleshooting entry**

`README.md`'s `## Troubleshooting` section indexes states that look like faults
but are not. Add an entry in the same style as the existing ones:

```markdown
**The Eva lamp switched itself off / went off after a reboot.**
Working as designed — it switches off 30 minutes after being turned on. A plug
that drops offline and reconnects while still on counts as a turn-on and starts
a fresh 30 minutes, which is why an unreliable connection can look like a lamp
that switches off at odd times.
```

- [ ] **Step 6: Add the rename to the deployment notes**

`## How changes reach the box` lists three "consequences worth knowing", the
last being **Adding a secret is a box-first operation.** An entity rename is the
same shape, so add a fourth in the same style, immediately after it:

```markdown
**Renaming an entity is a box-first operation.** Entity IDs live in Home
Assistant's own registry, not in this repo, so nothing here can rename one.
Rename it under Settings → Devices & services → Entities *before* merging the
change that references the new name — the reverse order leaves an automation
pointed at an entity that does not exist, which fires nothing and logs nothing.
```

Then, under `## Working on it` where the manual reload steps live, note that a
**Timer** domain reload must precede an **Automations** reload when a change
adds a timer: `timer.start` fails against a timer that does not exist yet, so a
press landing between the two reloads leaves the lamp with no cutoff armed. A
full restart — what the Git pull add-on does — has no such ordering problem.

- [ ] **Step 7: Verify nothing broke**

Run: `/Users/gregn/Documents/office/.venv/bin/pytest`

Expected: PASS. No test reads the markdown, so this only confirms Task 2 is still green.

- [ ] **Step 8: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "Document the Eva lamp auto-off plug"
```

---

## Deployment (manual, after all tasks)

1. Rename the entity on the host (see Prerequisite). **Nothing works until this is done, and it fails silently.**
2. Sync `helpers.yaml` and `automations.yaml` to the HA instance.
3. Developer Tools → YAML → reload **Timer**, *then* reload **Automations**.
4. Verify: press the button on the plug, then confirm `timer.eva_lamp_auto_off` reads `active` with ~30 minutes remaining.

## Verification checklist

- [ ] `/Users/gregn/Documents/office/.venv/bin/pytest` passes
- [ ] `timer.eva_lamp_auto_off` is the only helper added, and `test_obsolete_helpers_removed` is untouched
- [ ] `to: 'on'` and `to: 'off'` are quoted in `automations.yaml`
- [ ] The `# Lamps` banner matches the width and `=`/`-` rule style of the other three banners
- [ ] No comment added anywhere describes a change, a previous state, or an intent (`.claude/rules/code-comments.md`)
