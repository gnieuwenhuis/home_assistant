# CI/CD: GitHub Actions checks and pull-based deployment

Date: 2026-08-09
Status: approved, pre-implementation

## Problem

Config reaches the live Home Assistant box by hand — edit here, sync, reload.
Nothing verifies a change before it takes control of two heat-pump heads, two
baseboard heaters, and the studio's humidity. The pytest suite exists and is
good, but it runs only when someone remembers to run it, which is precisely not
when it is needed.

Two outcomes are wanted:

1. Every pull request is linted and tested, and a failing one cannot merge.
2. Every commit that lands on `main` reaches the box without a manual step.

## The constraint that shapes everything

The box is not reachable from GitHub. `external_url` is unset,
`homeassistant.local` is mDNS, and the installation is HAOS/Supervised
(`hassio` is loaded) running HA 2026.8.1. GitHub-hosted runners cannot open a
connection to it under any configuration.

So "deploy on push" cannot be a push at all. Three ways around it were weighed:

| Approach | Why not chosen |
|---|---|
| Self-hosted runner on the LAN | Works, and gives true push-triggered deploys — but requires an always-on host to keep alive and patched, adding a machine to the failure surface of a two-room workspace. |
| Tailscale from a hosted runner | Works, and keeps everything inside Actions — but stores a tailnet auth key and an SSH key in GitHub secrets. Those are credentials that reach into the home network, held by a third party, to deploy a thermostat config. |
| **Pull-based (Git pull add-on)** | **Chosen.** Nothing inbound, no runner host, no credential leaves the house. The repo is public, so the add-on needs no deploy key at all. |

The cost of the pull model is that deployment is not instantaneous — it happens
on the add-on's polling interval — and that GitHub Actions never "deploys"
anything. Actions decides what is *allowed* to become `main`; the box decides
when to take it.

## Architecture

```
  you ──PR──▶ GitHub ──▶ CI: yamllint · actionlint · pytest · config validation
                             │
                             ├─ red ──▶ merge blocked (required status checks, strict)
                             │
                             └─ green ─▶ squash-merge to main (linear history)
                                              │
                                              ▼
                        Git pull add-on polls main every 5 minutes
                                              │
                                    git reset --hard origin/main  in /config
                                              │
                                    tracked files replaced; secrets.yaml,
                                    .storage/, custom_components/ untouched
                                              │
                                    auto_restart ──▶ HA Core restarts
                                              │
                                    homeassistant.start fires ──▶ hvac_coordinator
                                    and studio_humidity_controller reconcile;
                                    timers restore (restore: true)
```

Three properties the design leans on:

**`.gitignore` already separates code from state.** `secrets.yaml`, `.storage/`,
`custom_components/`, `www/community/`, the database and every runtime artifact
are excluded. A hard reset in `/config` therefore replaces only tracked files
and cannot touch credentials, HA's state store, or HACS-installed integrations.
This is what makes the pull model safe here; it would not be safe in a repo that
tracked `.storage/`.

**`main` is the deployment record.** With linear history and squash-only merges,
"what was the box running at 14:30" is a single commit. No separate deploy
branch to keep synchronised.

**`reset --hard`, not `pull`.** The box converges on `main` unconditionally and
cannot wedge on a merge conflict from a hand-edit. Since the config has been
synced manually until now, local drift is likely, and this makes `main`
authoritative rather than negotiating with whatever is on the box.

## What CI checks

One workflow, `.github/workflows/ci.yml`, two parallel jobs.

```yaml
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]        # a bypassed merge still reports, and the
                            # `workflows` ruleset rule has runs to match
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
permissions:
  contents: read

jobs:
  lint:                     # ~20s, no HA install
    - yamllint automations.yaml helpers.yaml configuration.yaml
    - actionlint .github/workflows/
  test:                     # ~90s, dominated by the HA dependency install
    - setup-python 3.14, cache: pip
    - pip install -r requirements-dev.txt
    - pytest
```

**The job names `lint` and `test` are the required status check contexts.**
Renaming a job silently disarms the gate until the ruleset is updated to match,
so the workflow carries a comment saying so.

**yamllint** needs a `.yamllint.yml` relaxing line length — `automations.yaml`
carries long template expressions and long-form comments. The rule that earns
its place is duplicate-key detection: a duplicated key silently changes HA
config and is caught by neither pytest nor human review.

**actionlint** validates the workflow itself. With required checks in force, a
malformed workflow means checks never report, which blocks every merge; catching
that before it lands is worth one step.

**ruff is deliberately not included.** Six Python files, all tests. It would be
process for its own sake.

## New test coverage

### `tests/test_configuration_yaml.py`

`automations.yaml` and `helpers.yaml` are already well covered — the Level 3
tests load them through real `async_setup_component`, which schema-validates
them. `configuration.yaml` has no coverage at all, and it is the only file whose
breakage prevents HA from starting. Choosing restart-on-every-deploy makes
closing that gap a precondition, not a nicety.

The test parses `configuration.yaml` with HA's own loader
(`homeassistant.util.yaml`), which resolves `!include` and
`!include_dir_merge_named` natively. `!secret` is resolved by pointing HA's
`Secrets` class at `secrets.yaml.example` rather than writing a real
`secrets.yaml` into the repo — which also asserts the example file stays
complete, which is its purpose.

Four assertions, in increasing value:

1. The file parses and every `!include` target exists.
2. The `template:` block sets up against a real hass. The entities its six
   sensors reference do not exist in the test; templates resolve to unknown and
   setup still succeeds, so this catches schema errors specifically.
3. Every Jinja string in the `climate:` block renders. `climate_template` is a
   HACS integration and cannot be set up in CI, but the templates are strings —
   a syntax error in `hvac_action_template` is a runtime failure this catches
   statically.
4. Structural assertions on the blocks that cannot be set up: `climate:` and
   `neviweb130:` carry their required keys, and `climate:`'s `min_temp` equals
   the `head_target` clamp floor in `custom_templates/hvac.jinja`.

Assertion 4 is a regression test for the invariant fixed in `63dda20`: the bound
minimums were 15 while the clamp floor was 17, so a `cool_bound` below 17 could
never be commanded and cooling demand would never clear. Nothing currently stops
those two numbers drifting apart again.

### `tests/test_version_pin.py`

`requirements-dev.txt` pins `pytest-homeassistant-custom-component` and its
comment records which HA release that maps to. Its own instructions say to keep
the pin matching the live HA version. Nothing enforces it.

A tracked `ha-version.txt` holds the live version as a bare string and nothing
else — `2026.8.1`, one line, no key, no comment. The test reads it, parses the
`# → HA <version>` comment on the `pytest-homeassistant-custom-component` line
in `requirements-dev.txt`, and asserts the two are equal. Both formats are
load-bearing and the test asserts each parses before comparing, so a reformatted
comment fails loudly rather than silently skipping the check.

Upgrading HA then fails CI until the pin is bumped, and bumping the pin forces
its comment to be updated.

The file is named `ha-version.txt`, not `.ha-version`, because HA writes its own
gitignored `.HA_VERSION` into `/config`. Once `/config` is a git checkout those
two sit in the same directory differing only in punctuation.

**This test goes red on introduction.** The box runs 2026.8.1 while the pin maps
to 2026.6.1, so the suite currently validates against a two-release-old schema.
The pin must be bumped to the release matching 2026.8.1 first. That upgrade may
surface its own test failures, so it is sequenced as a separate step rather than
bundled with the CI work.

## Branch protection

The existing ruleset on `main` (id 20613372, active) has `deletion`,
`non_fast_forward`, and `pull_request` with 0 required approvals. It has no
required status checks, so a red PR merges today.

| Rule | State |
|---|---|
| `deletion`, `non_fast_forward` | keep |
| `pull_request` | keep 0 approvals; narrow `allowed_merge_methods` to squash only |
| `required_linear_history` | add |
| `required_status_checks` | add — contexts `lint` and `test`, strict policy |
| `workflows` | add — require `.github/workflows/ci.yml` at ref `refs/heads/main` |
| `bypass_actors` | RepositoryRole 5: `always` → `pull_request` |

Zero required approvals is correct for a single-maintainer repo: the check suite
is the reviewer.

### Why the bypass stays

GitHub offers two bypass modes. `always` lets an admin bypass everywhere,
including direct pushes. `pull_request` blocks direct pushes to `main` but still
permits deliberately merging a PR whose checks are red.

`pull_request` is the right setting. It removes the accidental path — no more
pushing straight to `main`, which is how three commits landed on 2026-08-09 —
while keeping a deliberate override that requires explicitly choosing it in the
PR UI. A rule that prevents mistakes without preventing decisions.

It also removes the need for a break-glass procedure. Under a full bypass
removal, a GitHub Actions outage would make every merge impossible including the
fix, requiring the ruleset be disabled to recover. With `pull_request`, the
override *is* the recovery path.

The residual risk is worth stating once: a deliberately-merged red PR still
auto-deploys to live HVAC control within one polling interval. The bypass is a
conscious act with a physical consequence.

## How the box applies a change

The config spans four reload semantics:

| Changed file | Requires |
|---|---|
| `automations.yaml` | `automation.reload` |
| `helpers.yaml` (package) | per-domain reloads |
| `custom_templates/hvac.jinja` | `homeassistant.reload_custom_templates` |
| `configuration.yaml` → `climate:`, `neviweb130:` | full restart |

The Git pull add-on can restart HA but cannot call reload services, and no
reload covers the platform blocks. **Full restart on every deploy** is therefore
the only option that is correct for all four.

It is safe here. Both coordinators trigger on `homeassistant.start` and reconcile
immediately on boot; all timers use `restore: true`, so lockouts, cooldowns and
the mode dwell carry across; and the 5-minute heartbeat backs both up. A restart
during an active lockout still honours it.

The cost is 30–60 seconds per deploy with no HVAC or humidity control, and the
risk that an invalid config means HA does not come back at all.

### Add-on configuration

```yaml
repository: https://github.com/gnieuwenhuis/home_assistant_config.git
git_branch: main
git_command: reset
auto_restart: true
restart_ignore:
  - .github/
  - docs/
  - tests/
  - README.md
  - CLAUDE.md
  - LICENSE
  - .gitignore
  - pytest.ini
  - requirements-dev.txt
  - ha-version.txt
  - secrets.yaml.example
  - .env.example
repeat: {active: true, interval: 5}
```

`restart_ignore` does real work: without it a README typo restarts HVAC control.

### One-time host setup

1. Take a full Supervisor backup.
2. Make `/config` a git checkout of the repo and hard-checkout `main`.
3. Install and configure the Git pull add-on as above.
4. Confirm the helpers cutover is complete.

Step 2 deploys everything currently undeployed in one restart. `63dda20`
changed `configuration.yaml` (`min_temp` 15→17) and `helpers.yaml` (bound
minimums, `initial:` values); if those were never synced they land together.

Step 4 exists because CLAUDE.md still describes the UI-helper deletion as
pending, while the live system has `timer.dehumidify_cooldown` at exactly the
30 minutes `helpers.yaml` specifies and no `_2` duplicates — evidence the
package is loaded and the cutover is done. The documentation is stale rather
than the system being broken, but that should be confirmed and CLAUDE.md
corrected rather than assumed.

Confirming it means two checks: Settings → Devices & services → Helpers lists
no helper whose name matches one defined in `helpers.yaml`, and the entity
registry contains no `input_number.*_2` / `input_boolean.*_2` / `timer.*_2`
duplicate. If either turns up, the cutover is genuinely outstanding and must be
completed before the checkout, because a UI helper and a YAML helper competing
for one `entity_id` is exactly the collision the package migration was meant to
end.

### The box becomes read-only for tracked files

Any hand-edit in File Editor or Studio Code Server is reverted within one
polling interval. This is the intent — the repo becomes genuinely authoritative
— but it ends the quick-fix-on-the-box habit and belongs in the README.

## Failure modes

**Rollback cannot be done at the box.** A `git reset` in `/config` during an
incident is undone within five minutes when the add-on re-pulls `main`. To hold
a rollback, either stop the add-on first, or revert on `main` and let it flow
through — which means a PR and a CI cycle. Under pressure, stopping the add-on
is faster, so that ordering belongs in the README troubleshooting section.

**A bad config that passes CI.** HA fails to start, all HVAC and humidity control
is lost, and no notification arrives because the thing that would notify is down.
Recovery requires physical or SSH access. `test_configuration_yaml.py` is the
main mitigation; the pre-checkout Supervisor backup is the floor. This is the
residual risk that restart-on-every-deploy buys.

**Secrets drift.** A change adding a new `!secret` key is caught by the config
test only insofar as `secrets.yaml.example` must list it. Nothing verifies the
box's real `secrets.yaml` has it, and that combination starts HA into a failure.
Adding a secret is a box-first operation.

**Deploy lag.** Up to five minutes between merge and effect.

## Rollout order

The order is forced by two chicken-and-egg constraints: required status checks
cannot be configured until GitHub has seen those check names run at least once,
and the `workflows` rule references a file that must already exist on `main`.
Tightening the ruleset first would lock the repo.

1. Bump `pytest-homeassistant-custom-component` to the release matching HA
   2026.8.1; fix any resulting test failures. Add `ha-version.txt`.
2. Add `tests/test_configuration_yaml.py` and `tests/test_version_pin.py`.
3. Add `.github/workflows/ci.yml` and `.yamllint.yml`. Land under today's
   looser ruleset; confirm both jobs run green.
4. Tighten the ruleset: required status checks, `workflows`, linear history,
   squash-only, bypass to `pull_request`.
5. Host setup: backup, `/config` checkout, add-on install, helpers-cutover check.
6. Document in README: the read-only box, the rollback ordering, box-first
   secrets.

Steps 1–4 are reversible from this machine. Step 5 is the irreversible one and
is gated on 1–4 being green.

## Out of scope

- **The heat-pump/humidity interaction.** Under observation for the coming
  weeks by decision on 2026-08-09; unrelated to delivery mechanics.
- **Dashboard export.** Lovelace lives in `.storage/` and is not restorable from
  this repo — a real gap CLAUDE.md already records, but a separate piece of work.
- **`hass --script check_config` in CI.** Cannot run: `neviweb130`,
  `cielo_home` and `climate_template` are HACS-installed and not vendored, so
  the check fails on those platforms regardless of whether the config is sound.
  `test_configuration_yaml.py` is the achievable subset.
