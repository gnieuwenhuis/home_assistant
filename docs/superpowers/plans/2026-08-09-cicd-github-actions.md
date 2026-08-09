# CI/CD via GitHub Actions and pull-based deployment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every pull request is linted and tested and cannot merge red; every commit that reaches `main` reaches the Home Assistant box without a manual step.

**Architecture:** GitHub-hosted runners cannot reach the box, so deployment inverts. GitHub Actions decides only what is *allowed* to become `main`; the Home Assistant Git pull add-on polls `main` every five minutes, hard-resets `/config` to it, and restarts HA. `.gitignore` already separates tracked config from runtime state, so a hard reset replaces config files and cannot touch `secrets.yaml`, `.storage/`, or `custom_components/`.

**Tech Stack:** GitHub Actions, yamllint, actionlint, pytest with `pytest-homeassistant-custom-component`, Python 3.14, GitHub repository rulesets, Home Assistant Git pull add-on.

**Design spec:** `docs/superpowers/specs/2026-08-09-cicd-github-actions-design.md`

## Global Constraints

- Python **3.14**. HA 2026.6+ requires it; the venv is built with `uv venv .venv --python 3.14 --seed`.
- The live box runs Home Assistant **2026.8.1**. The matching harness pin is **`pytest-homeassistant-custom-component==0.13.355`** (verified: that release pins `homeassistant==2026.8.1`).
- CI job names are **`lint`** and **`test`**, exactly. They become the required status check contexts; renaming a job silently disarms the gate.
- The repo is **public** at `https://github.com/gnieuwenhuis/home_assistant_config.git`. The add-on needs no deploy key.
- Never commit `secrets.yaml` or `.env`. Only the `.example` files are tracked.
- `ha-version.txt` holds a **bare one-line version string** and nothing else.
- The `requirements-dev.txt` pin line format is load-bearing and parsed by a test:
  `pytest-homeassistant-custom-component==<pin>  # → HA <version>` (note the `→` character).
- Tests run from the repo root: `.venv/bin/pytest`.
- Do not edit working config purely to satisfy a linter — a `configuration.yaml` change triggers an HA restart on deploy.

---

### Task 1: Pin the harness to the live HA version and enforce it

The suite currently validates against HA 2026.6.1 while the box runs 2026.8.1 — two releases of schema drift. This task closes that and makes the drift impossible to reintroduce silently.

**Files:**
- Create: `ha-version.txt`
- Create: `tests/test_version_pin.py`
- Modify: `requirements-dev.txt` (the pin line and its comment)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `ha-version.txt` at repo root containing a bare HA version string; later tasks add it to the add-on's `restart_ignore` list.

- [ ] **Step 1: Write the failing test**

Create `tests/test_version_pin.py`:

```python
"""The harness pin must match the Home Assistant version the live box runs.

`requirements-dev.txt` pins pytest-homeassistant-custom-component, and the
comment on that line records which Home Assistant release the pin maps to.
`ha-version.txt` records what the box actually runs. When the two diverge the
suite is validating automations against a schema the box no longer has.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PIN_LINE = re.compile(
    r"^pytest-homeassistant-custom-component==(?P<pin>[\d.]+)"
    r"\s+#\s*→\s*HA\s+(?P<ha>[\d.]+)\s*$",
    re.MULTILINE,
)
BARE_VERSION = re.compile(r"\d{4}\.\d+\.\d+")


def _ha_version_file() -> str:
    return (REPO_ROOT / "ha-version.txt").read_text()


def test_ha_version_file_holds_a_bare_version():
    raw = _ha_version_file()
    assert raw.strip(), "ha-version.txt is empty"
    assert len(raw.strip().splitlines()) == 1, (
        "ha-version.txt holds one line and nothing else — no key, no comment"
    )
    assert BARE_VERSION.fullmatch(raw.strip()), (
        f"ha-version.txt must be a bare version like 2026.8.1, "
        f"got {raw.strip()!r}"
    )


def test_requirements_pin_line_is_parseable():
    text = (REPO_ROOT / "requirements-dev.txt").read_text()
    assert PIN_LINE.search(text), (
        "requirements-dev.txt needs a line of exactly this shape:\n"
        "  pytest-homeassistant-custom-component==<pin>  # → HA <version>\n"
        "The comment is parsed by this test; reformatting it disables the "
        "drift check."
    )


def test_pin_matches_the_live_ha_version():
    match = PIN_LINE.search((REPO_ROOT / "requirements-dev.txt").read_text())
    assert match is not None, "pin line unparseable; see the previous test"
    live = _ha_version_file().strip()
    assert match.group("ha") == live, (
        f"requirements-dev.txt pins {match.group('pin')} "
        f"(HA {match.group('ha')}) but ha-version.txt says the box runs "
        f"HA {live}. Bump the pin to the matching release and update its "
        f"comment, or update ha-version.txt if the box was upgraded."
    )
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/bin/pytest tests/test_version_pin.py -v`

Expected: `test_ha_version_file_holds_a_bare_version` and
`test_pin_matches_the_live_ha_version` FAIL with `FileNotFoundError` —
`ha-version.txt` does not exist yet.

- [ ] **Step 3: Create `ha-version.txt`**

```
2026.8.1
```

One line, no trailing content. Write it with a single trailing newline.

- [ ] **Step 4: Run the test again to confirm it now fails for the right reason**

Run: `.venv/bin/pytest tests/test_version_pin.py -v`

Expected: the first two tests PASS; `test_pin_matches_the_live_ha_version`
FAILS with `pins 0.13.337 (HA 2026.6.1) but ha-version.txt says the box runs
HA 2026.8.1`.

This is the proof the test has teeth — it is detecting the real drift that
exists today, not passing vacuously.

- [ ] **Step 5: Bump the pin**

In `requirements-dev.txt`, replace the pin line:

```
pytest-homeassistant-custom-component==0.13.355  # → HA 2026.8.1
```

Leave the surrounding comment block unchanged.

- [ ] **Step 6: Reinstall dependencies at the new pin**

Run: `.venv/bin/pip install -r requirements-dev.txt`

Then confirm the HA version actually installed:

Run: `.venv/bin/python -c "import homeassistant.const as c; print(c.__version__)"`
Expected: `2026.8.1`

- [ ] **Step 7: Run the full suite on the new HA version**

Run: `.venv/bin/pytest -q`

Expected: 54 passed (51 existing + 3 from `test_version_pin.py`).

**The upgrade has been verified clean**: the 51 existing tests were run against
`0.13.355` / HA 2026.8.1 in a scratch venv on 2026-08-09 and all passed. So a
failure here is unexpected and means something in this task went wrong — most
likely a partial install. Re-run Step 6 and confirm
`homeassistant.const.__version__` reports `2026.8.1` before investigating
further.

Should a genuine behaviour difference surface anyway, do **not** loosen an
assertion to make it pass without understanding why the behaviour moved — the
coordinator tests encode real safety properties (lockouts, both-on exclusion,
heating-wins).

- [ ] **Step 8: Commit**

```bash
git add ha-version.txt tests/test_version_pin.py requirements-dev.txt
git commit -m "Pin the test harness to the live HA version and enforce it

The suite validated against HA 2026.6.1 while the box runs 2026.8.1. The pin
moves to 0.13.355, which pins homeassistant==2026.8.1 exactly.

ha-version.txt records what the box runs, and test_version_pin.py asserts it
against the HA version recorded beside the pin, so upgrading one without the
other fails CI instead of silently validating against a stale schema."
```

---

### Task 2: Test coverage for `configuration.yaml`

`automations.yaml` and `helpers.yaml` are already loaded through real
`async_setup_component` by the Level 3 tests. `configuration.yaml` has no
coverage at all, and it is the only file whose breakage stops HA from booting —
which the restart-on-every-deploy design turns into an outage.

**Files:**
- Create: `tests/test_configuration_yaml.py`
- Test: itself

**Interfaces:**
- Consumes: `tests/conftest.py`'s `hass_repo` fixture (a `hass` whose
  `config_dir` is the repo root, with custom templates loaded).
- Produces: `ExampleSecrets`, a `homeassistant.util.yaml.loader.Secrets`
  subclass resolving `!secret` from `secrets.yaml.example`. No later task
  consumes it.

- [ ] **Step 1: Write the test**

Create `tests/test_configuration_yaml.py`:

```python
"""configuration.yaml must stay loadable and structurally sound.

This is the only tracked file whose breakage prevents Home Assistant from
starting, and deploys restart HA. The HACS platforms (`climate_template`,
`neviweb130`, `cielo_home`) are not installed in CI, so they cannot be set up;
what can be checked is that the file parses, that everything it includes
exists, that the blocks which CAN be set up do set up, and that every Jinja
string in the blocks which cannot at least renders.
"""
from pathlib import Path

import pytest
import yaml as pyyaml
from homeassistant.helpers.template import Template
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import loader

from tests.conftest import REPO_ROOT

# The head_target macro in custom_templates/hvac.jinja clamps commanded
# setpoints to this floor. A bound below it can never be commanded, so demand
# in that direction would never clear.
HEAD_TARGET_CLAMP_FLOOR = 17


class ExampleSecrets(loader.Secrets):
    """Resolve !secret from secrets.yaml.example so CI needs no real secrets.

    Doubles as an assertion that the example file lists every key the config
    actually uses, which is the example file's entire purpose.
    """

    def __init__(self, config_dir: Path) -> None:
        super().__init__(config_dir)
        self._example = pyyaml.safe_load(
            (config_dir / "secrets.yaml.example").read_text()
        )

    def get(self, requester_path: str, secret: str) -> str:
        if secret not in self._example:
            raise AssertionError(
                f"configuration.yaml uses !secret {secret}, but "
                f"secrets.yaml.example does not list it. Add it there, and "
                f"add the real value to secrets.yaml on the HA host before "
                f"deploying."
            )
        return self._example[secret]


@pytest.fixture
def config():
    """configuration.yaml with !include and !secret resolved."""
    return loader.load_yaml_dict(
        REPO_ROOT / "configuration.yaml", ExampleSecrets(REPO_ROOT)
    )


def test_configuration_parses_and_includes_resolve(config):
    assert "automation" in config, "automations.yaml failed to include"
    assert len(config["automation"]) >= 1
    assert "homeassistant" in config
    assert config["homeassistant"]["packages"]["helpers"], (
        "helpers.yaml package include resolved empty"
    )


def test_included_files_exist():
    for name in ("automations.yaml", "scripts.yaml", "scenes.yaml",
                 "helpers.yaml"):
        assert (REPO_ROOT / name).exists(), f"{name} is included but missing"


async def test_template_block_sets_up(hass_repo, config):
    """The template: sensors schema-validate against a real HA.

    The entities they read do not exist here; templates resolve to unknown and
    setup still succeeds, so a failure here is a schema error.
    """
    assert await async_setup_component(
        hass_repo, "template", {"template": config["template"]}
    ), "the template: block failed to set up"


async def test_climate_templates_render(hass_repo, config):
    """Every *_template string in the climate: block is valid Jinja.

    climate_template is a HACS integration and cannot be set up in CI, but its
    templates are ordinary strings — a syntax error here is a runtime failure
    that this catches statically. Only top-level *_template keys are rendered;
    the set_temperature / set_hvac_mode action blocks reference runtime
    variables that do not exist outside a service call.
    """
    rendered = 0
    for entry in config["climate"]:
        for key, value in entry.items():
            if key.endswith("_template"):
                Template(value, hass_repo).async_render(parse_result=False)
                rendered += 1
    assert rendered >= 10, (
        f"expected at least 10 climate templates across both rooms, "
        f"rendered {rendered}"
    )


def test_climate_min_temp_matches_head_target_clamp(config):
    """A cool_bound below the clamp floor could never be commanded.

    head_target clamps to [17, 30]; if a thermostat tile let the user dial a
    bound under that floor, cooling demand would never clear.
    """
    for entry in config["climate"]:
        assert entry["min_temp"] == HEAD_TARGET_CLAMP_FLOOR, (
            f"{entry['name']} min_temp is {entry['min_temp']} but "
            f"head_target clamps to {HEAD_TARGET_CLAMP_FLOOR}"
        )


def test_climate_entries_have_required_keys(config):
    required = {
        "platform", "name", "unique_id", "modes", "min_temp", "max_temp",
        "current_temperature_template", "target_temperature_low_template",
        "target_temperature_high_template", "hvac_mode_template",
        "hvac_action_template", "set_temperature", "set_hvac_mode",
    }
    for entry in config["climate"]:
        missing = required - set(entry)
        assert not missing, f"{entry.get('name')} is missing {sorted(missing)}"


def test_neviweb130_block_has_required_keys(config):
    required = {"username", "password", "network", "scan_interval",
                "homekit_mode", "stat_interval", "notify"}
    missing = required - set(config["neviweb130"])
    assert not missing, f"neviweb130: is missing {sorted(missing)}"
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/pytest tests/test_configuration_yaml.py -v`

Expected: 7 passed. This is a guard test over config that is already correct,
so passing immediately is the expected outcome — Step 3 is what proves it has
teeth.

- [ ] **Step 3: Prove the test detects a real break (mutation check)**

Temporarily change `min_temp: 17` to `min_temp: 15` on the Office Thermostat
entry in `configuration.yaml`.

Run: `.venv/bin/pytest tests/test_configuration_yaml.py -v`
Expected: `test_climate_min_temp_matches_head_target_clamp` FAILS with
`Office Thermostat min_temp is 15 but head_target clamps to 17`.

Now temporarily rename `helpers.yaml` to `helpers.yaml.bak`.

Run: `.venv/bin/pytest tests/test_configuration_yaml.py -v`
Expected: collection or `test_included_files_exist` FAILS.

**Revert both mutations before continuing.** Confirm with `git diff` that
`configuration.yaml` is unmodified and `helpers.yaml` is back.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: 61 passed (54 + 7).

- [ ] **Step 5: Commit**

```bash
git add tests/test_configuration_yaml.py
git commit -m "Add configuration.yaml validation test

configuration.yaml is the only tracked file whose breakage prevents HA from
starting, and it had no coverage. Deploys restart HA, so an invalid config is
an outage rather than a failed reload.

Resolves !secret against secrets.yaml.example, which also asserts the example
file lists every key the config uses. Sets up the template: block against a
real hass, renders every Jinja string in the climate: block that HACS-only
platforms prevent setting up, and asserts climate min_temp equals the
head_target clamp floor."
```

---

### Task 3: yamllint configuration

**Files:**
- Create: `.yamllint.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: `.yamllint.yml` at repo root; Task 4's `lint` job invokes
  `yamllint` which discovers it automatically.

- [ ] **Step 1: Create `.yamllint.yml`**

```yaml
extends: default

rules:
  # The humidity controller's `variables:` block aligns values into a column.
  # That alignment is deliberate and reads better than single-spacing.
  colons: disable
  # HA template expressions and the long-form comments both run past 80.
  line-length: disable
  # Banner comments sit at a different indent than the block they introduce.
  comments-indentation: disable
  document-start: disable
  truthy:
    # HA config idiomatically writes True/False alongside true/false.
    allowed-values: ["true", "false", "True", "False"]
  indentation:
    spaces: consistent
    indent-sequences: whatever
```

Each disabled rule carries the reason it is disabled. The rule that earns this
file's existence is `key-duplicates` (inherited from `default`): a duplicated
key silently changes HA config and is caught by neither pytest nor review.

- [ ] **Step 2: Run yamllint**

Run: `uvx yamllint -f parsable automations.yaml helpers.yaml configuration.yaml`

Expected: no output, exit 0.

If violations appear, fix the **lint config**, not the working config —
editing `configuration.yaml` for style triggers an HA restart on deploy for no
functional gain. The two known violations this config already accounts for are
the aligned `variables:` block in `automations.yaml` (lines ~392–405) and
`homekit_mode: False` in `configuration.yaml`.

- [ ] **Step 3: Verify the duplicate-key rule actually fires**

Temporarily add a duplicate key to `helpers.yaml` — a second
`humidity_set_point:` entry under `input_number:`.

Run: `uvx yamllint -f parsable helpers.yaml`
Expected: an error mentioning `duplication of key "humidity_set_point"`.

**Revert the mutation.** Confirm with `git diff` that `helpers.yaml` is clean.

- [ ] **Step 4: Commit**

```bash
git add .yamllint.yml
git commit -m "Add yamllint configuration

key-duplicates is what earns this file: a duplicated key silently changes HA
config and neither pytest nor review reliably catches it.

Disables colons (the humidity controller's variables: block is deliberately
column-aligned), line-length (HA templates and long-form comments), and
comments-indentation (banner comments sit at a different indent than the block
they introduce), and accepts True/False as HA config idiomatically writes them."
```

---

### Task 4: The CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `.yamllint.yml` (Task 3), `requirements-dev.txt` (Task 1),
  `pytest.ini`.
- Produces: two status check contexts named exactly `lint` and `test`. Task 6
  references those names in the ruleset.

- [ ] **Step 1: Create the workflow**

```yaml
---
name: CI

# The job names below (`lint`, `test`) are the required status check contexts
# in the `main` ruleset. Renaming a job silently disarms the merge gate until
# the ruleset is updated to match.

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

permissions:
  contents: read

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - name: Install yamllint
        run: pipx install yamllint

      - name: Lint HA configuration
        run: yamllint -f github automations.yaml helpers.yaml configuration.yaml

      - name: Lint workflows
        uses: raven-actions/actionlint@v2

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5

      - uses: actions/setup-python@v6
        with:
          python-version: '3.14'
          cache: pip
          cache-dependency-path: requirements-dev.txt

      - name: Install dependencies
        run: pip install -r requirements-dev.txt

      - name: Run tests
        run: pytest -q
```

- [ ] **Step 2: Validate the workflow locally**

Run: `uvx --from actionlint-py actionlint .github/workflows/ci.yml`

Expected: no output, exit 0.

If `actionlint-py` is unavailable, run
`docker run --rm -v "$PWD":/repo -w /repo rhysd/actionlint:latest -color`
instead. Do not skip this — a malformed workflow means checks never report,
and once Task 6 lands that blocks every merge.

- [ ] **Step 3: Confirm the yamllint invocation matches what Step 2 of Task 3 ran**

Run: `uvx yamllint -f github automations.yaml helpers.yaml configuration.yaml`

Expected: no output, exit 0. (`-f github` only changes output formatting; it
must still pass.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "Add CI workflow: lint and test on PRs and main

Two parallel jobs so feedback is fast and each becomes its own required status
check. Job names are load-bearing — they are the contexts the main ruleset
requires — and the workflow says so in a comment.

Runs on push to main as well as pull_request, so a deliberately bypassed merge
still reports and the ruleset's workflows rule has runs to match."
```

---

### Task 5: Land on `main` and confirm CI is green

Required status checks cannot be configured until GitHub has seen those check
names run at least once, and the `workflows` rule references a file that must
already exist on `main`. So the workflow lands under today's looser ruleset,
and only then can Task 6 tighten it.

**Files:** none — this task is repository operations.

**Interfaces:**
- Consumes: Tasks 1–4, all committed on `worktree-ci+github-actions`.
- Produces: `lint` and `test` check contexts registered with GitHub;
  `.github/workflows/ci.yml` present on `main`.

- [ ] **Step 1: Push the branch**

```bash
git push -u origin worktree-ci+github-actions
```

- [ ] **Step 2: Open the pull request**

```bash
gh pr create --base main --title "Add CI and pull-based deployment groundwork" --body "$(cat <<'EOF'
Implements `docs/superpowers/specs/2026-08-09-cicd-github-actions-design.md`,
repo side.

- Harness pinned to HA 2026.8.1 (`0.13.355`), enforced by `ha-version.txt` and
  `tests/test_version_pin.py`
- `tests/test_configuration_yaml.py` — first coverage of the only file that can
  prevent HA from starting
- `.yamllint.yml` and `.github/workflows/ci.yml` (`lint` + `test`)

Ruleset tightening and the host-side Git pull add-on follow separately; the
ruleset cannot require check names GitHub has not yet seen.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Watch the checks**

```bash
gh pr checks --watch
```

Expected: both `lint` and `test` report success. If `test` fails on the runner
but passed locally, suspect the Python version — confirm the runner resolved
3.14 and not a 3.13 fallback, by reading the "Set up Python" step log.

- [ ] **Step 4: Merge**

```bash
gh pr merge --squash --delete-branch
```

Squash is deliberate: it is the merge method the ruleset will require in
Task 6, and it keeps `main` one commit per change, which matters because
`main` is about to become the deployment record.

- [ ] **Step 5: Confirm the check contexts are registered**

```bash
gh api repos/gnieuwenhuis/home_assistant_config/commits/main/check-runs \
  --jq '.check_runs[].name'
```

Expected output includes `lint` and `test`. Task 6 depends on these exact
strings.

---

### Task 6: Tighten the `main` ruleset

The existing ruleset (id `20613372`) has `deletion`, `non_fast_forward`, and
`pull_request` with 0 approvals — but no required status checks, so a red PR
merges today.

**Files:**
- Create: `.github/rulesets/main.json` (a tracked record of the applied ruleset)

**Interfaces:**
- Consumes: the `lint` and `test` check contexts registered in Task 5.
- Produces: an enforced merge gate. No later task consumes it.

- [ ] **Step 1: Capture the current state before changing it**

```bash
gh api repos/gnieuwenhuis/home_assistant_config/rulesets/20613372 \
  > /tmp/ruleset-before.json
git rev-parse origin/main | tee /tmp/main-sha-before.txt
```

Keep both until Step 5 confirms the new ruleset works. The JSON is the ruleset
rollback; the SHA is what Step 5 needs if a direct push unexpectedly succeeds.

- [ ] **Step 2: Write the new ruleset definition**

Create `.github/rulesets/main.json`:

```json
{
  "name": "main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
  "bypass_actors": [
    {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}
  ],
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {"type": "required_linear_history"},
    {
      "type": "pull_request",
      "parameters": {
        "allowed_merge_methods": ["squash"],
        "required_approving_review_count": 0,
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_review_thread_resolution": false
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          {"context": "lint"},
          {"context": "test"}
        ]
      }
    },
    {
      "type": "workflows",
      "parameters": {
        "do_not_enforce_on_create": false,
        "workflows": [
          {
            "path": ".github/workflows/ci.yml",
            "repository_id": null,
            "ref": "refs/heads/main"
          }
        ]
      }
    }
  ]
}
```

`repository_id` must be this repository's numeric id. Get it with:

```bash
gh api repos/gnieuwenhuis/home_assistant_config --jq .id
```

Substitute that number for `null` before applying.

`bypass_mode` is `pull_request`, not removed: it blocks accidental direct
pushes to `main` while keeping a deliberate red-PR override, which is also the
recovery path if GitHub Actions is down.

- [ ] **Step 3: Apply the ruleset**

```bash
gh api --method PUT \
  repos/gnieuwenhuis/home_assistant_config/rulesets/20613372 \
  --input .github/rulesets/main.json
```

- [ ] **Step 4: Verify what was actually applied**

```bash
gh api repos/gnieuwenhuis/home_assistant_config/rulesets/20613372 \
  --jq '{enforcement, bypass: [.bypass_actors[].bypass_mode], rules: [.rules[].type]}'
```

Expected: `enforcement: "active"`, bypass `["pull_request"]`, and rules
containing `deletion`, `non_fast_forward`, `required_linear_history`,
`pull_request`, `required_status_checks`, `workflows`.

- [ ] **Step 5: Prove the gate binds**

Confirm a direct push to `main` is now refused. Do this **without switching
branches** — the work is happening in a worktree, and checking out `main` here
would move the worktree off its own branch:

```bash
git push origin HEAD:main
```

This attempts to fast-forward `main` to the current branch head without
touching any local branch.

Expected: **rejected**, with a message naming the ruleset — typically
`Changes must be made through a pull request`.

If the push *succeeds*, the bypass is still `always`. Undo it immediately:

```bash
git push --force-with-lease origin <sha-from-step-1>:main
```

using the `main` SHA recorded before the attempt, then re-check Step 3's output
and re-apply.

Do not proceed to Task 8 until this check fails as intended. From Task 8 onward
anything on `main` reaches live HVAC control.

- [ ] **Step 6: Commit the ruleset record**

The ruleset lives in GitHub, not in the repo — this file is documentation of
what was applied, so it is reviewable and restorable.

```bash
git checkout -b ci/ruleset-record
git add .github/rulesets/main.json
git commit -m "Record the applied main ruleset

The ruleset lives in GitHub's API, not the repo. Tracking the definition makes
it reviewable in diffs and restorable if it is changed by hand in the UI.

bypass_mode is pull_request rather than removed: it blocks accidental direct
pushes while keeping a deliberate red-PR override, which doubles as the
recovery path during a GitHub Actions outage."
gh pr create --base main --title "Record the applied main ruleset" --fill
```

---

### Task 7: Document the operational changes

Three behaviours change for a human operator, and none is discoverable from the
code.

**Files:**
- Modify: `README.md` (add a deployment section; extend Troubleshooting)
- Modify: `CLAUDE.md` (correct the stale helpers-migration section)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Add a deployment section to `README.md`**

Insert after the existing "Working on it" section:

```markdown
## How changes reach the box

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
```

- [ ] **Step 2: Add a troubleshooting entry to `README.md`**

Append to the Troubleshooting section:

```markdown
**A config change I made on the box disappeared.** Expected. The Git pull
add-on reverts `/config` to `main` every five minutes. Make the change in the
repository instead — see "How changes reach the box".

**Home Assistant restarted on its own.** Also expected, if a commit landed on
`main` in the last five minutes. Documentation-only commits do not restart it;
`restart_ignore` in the add-on config lists what is exempt.
```

- [ ] **Step 3: Correct the stale helpers-migration section in `CLAUDE.md`**

`CLAUDE.md` describes the UI-helper deletion as a pending one-time cutover.
The live system has `timer.dehumidify_cooldown` at exactly the 30 minutes
`helpers.yaml` specifies and no `_2` duplicate entities, which means the
package is loaded and the cutover is done.

**Verify before editing** — Task 8 Step 3 performs this check. If the
verification has not run yet, do that first; if it shows the cutover is
genuinely outstanding, skip this step and leave `CLAUDE.md` alone.

Once verified, replace the "Remaining one-time host cutover" paragraph with a
statement that the cutover is complete and `helpers.yaml` is authoritative,
keeping the guidance about editing there rather than in the UI.

- [ ] **Step 4: Run the full suite**

Run: `.venv/bin/pytest -q`
Expected: 61 passed. Documentation changes should not affect tests; a failure
here means something else was touched.

- [ ] **Step 5: Commit and open a PR**

```bash
git checkout -b docs/deployment-model
git add README.md CLAUDE.md
git commit -m "Document the deployment model and its operational consequences

The box becomes read-only for tracked files, deploys restart HA, and adding a
secret must happen on the host first. None of that is discoverable from the
code.

Rollback ordering gets its own section because the intuitive move — resetting
/config on the box — is undone within five minutes by the next poll.

Corrects the helpers-migration section, which described a cutover the live
system shows is already complete."
gh pr create --base main --title "Document the deployment model" --fill
```

---

### Task 8: Host setup

Everything up to here is reversible from this machine. This task is not: after
it, commits on `main` reach live HVAC control automatically. Do not start it
until Task 6 Step 5 has demonstrated the gate rejects a direct push.

**Files:** none in the repo — this runs on the Home Assistant host.

**Interfaces:**
- Consumes: `main` containing the CI workflow, and a verified ruleset.
- Produces: a `/config` that tracks `main`.

- [ ] **Step 1: Take a full Supervisor backup**

Settings → System → Backups → Create backup → Full backup. Wait for
completion and confirm it is listed before continuing. This is the floor under
every later step.

- [ ] **Step 2: Inventory local drift before overwriting it**

Over SSH (or the Terminal add-on), from `/config`:

```bash
cd /config
ls -la
```

The first checkout replaces every tracked file with `main`'s version. `63dda20`
changed `configuration.yaml` (`min_temp` 15→17) and `helpers.yaml` (bound
minimums, `initial:` values); if those were never synced they land now, in one
restart, along with everything else. Copy anything hand-edited that you want to
keep somewhere outside `/config` first.

- [ ] **Step 3: Verify the helpers cutover is complete**

Two checks, both must pass:

1. Settings → Devices & services → Helpers lists **no** helper whose name
   matches one defined in `helpers.yaml`.
2. Developer Tools → States shows **no** `input_number.*_2`,
   `input_boolean.*_2`, `input_select.*_2` or `timer.*_2` entity.

If either turns up, the cutover is genuinely outstanding: delete the UI copies
and restart before continuing. A UI helper and a YAML helper competing for one
`entity_id` is exactly the collision the package migration was meant to end.

- [ ] **Step 4: Make `/config` a checkout of `main`**

```bash
cd /config
git init
git remote add origin https://github.com/gnieuwenhuis/home_assistant_config.git
git fetch origin
git checkout -f -b main origin/main
```

Then confirm nothing untracked was destroyed:

```bash
ls -la /config/secrets.yaml /config/.storage /config/custom_components
```

All three must still exist. They are gitignored, so `checkout -f` cannot touch
them — this is a verification that the `.gitignore` assumption held, not a
formality.

- [ ] **Step 5: Restart HA and confirm it comes back**

Developer Tools → Actions → `homeassistant.restart`.

Wait for the UI to return, then confirm in Developer Tools → States:
- `automation.hvac_coordinator` is `on`
- `automation.studio_humidity_controller` is `on`
- `input_number.studio_heat_bound` has a sensible value (restored, not reset)

If HA does not come back, restore the Step 1 backup.

- [ ] **Step 6: Install and configure the Git pull add-on**

Settings → Add-ons → Add-on Store → **Git pull** → Install. Then in its
Configuration tab:

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
  - .yamllint.yml
repeat:
  active: true
  interval: 5
```

Start the add-on, then read its log. Expected: a successful fetch and "nothing
to do" — `/config` already matches `main` from Step 4.

- [ ] **Step 7: End-to-end verification with a harmless change**

From this machine, open a PR changing only `README.md` (a typo fix is ideal),
let CI pass, and squash-merge it.

Then watch the add-on's log for the next poll. Expected: it pulls the commit
and does **not** restart Home Assistant, because `README.md` is in
`restart_ignore`. Confirm HA's uptime did not reset (Developer Tools → States,
`sensor.uptime` or the Supervisor log).

This proves the pull path works before a restart-triggering change ever
depends on it.

- [ ] **Step 8: Confirm a config change does restart**

Only when Step 7 has passed. Make a genuinely trivial `automations.yaml`
change — reword a comment, nothing behavioural — and merge it.

Expected: the add-on pulls and restarts HA. Confirm afterwards that both
coordinators are `on` and the studio's bounds survived.

---

## Notes for the implementer

**The order is not arbitrary.** Required status checks cannot reference check
names GitHub has never seen, and the `workflows` rule cannot reference a file
absent from `main`. Tightening the ruleset before Task 5 lands would lock the
repository. Task 8 is gated on Task 6 Step 5 for a different reason: from that
point on, `main` reaches physical equipment.

**This repository controls real hardware** — two heat-pump heads on a shared
compressor, two baseboard heaters, two Tuya plugs in a studio holding
instruments at ~42% RH. Reads against the live API are free; writes move
equipment. `CLAUDE.md`'s "Live Home Assistant API access" section governs what
may be called without asking.

**If a test fails after the HA upgrade in Task 1**, the coordinator and humidity
tests encode real safety properties — the both-on exclusion, the lockout
minimum-off behaviour, heating-wins conflict resolution. Understand why the
behaviour moved before changing an assertion.
