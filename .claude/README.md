# `.claude/` — Shared Claude Code Configuration

This directory holds the agent definitions, skills, and conventions Claude
Code uses in this repository. It is tracked in git so the whole team works
from the same setup.

Adapted from [solatis/claude-config](https://github.com/solatis/claude-config).
See `LICENSE` for the original license. Substantially modified for this
repo — see git history for what changed.

## Setup

This configuration requires the superpowers plugin:

    /plugin install superpowers@claude-plugins-official

Without it, the plan/review/debug workflow this repo assumes is missing —
the skills that used to provide it were deleted in favor of superpowers'
`brainstorming`, `writing-plans`, `executing-plans`, and
`systematic-debugging`. Two process frameworks competing for the same
triggers is worse than either alone.

## Why This Structure Exists

Four principles shape the agents and skills below.

### Context Hygiene

Sub-agents start every call with a fresh context, so anything they need to
know has to be encoded somewhere persistent rather than assumed from prior
conversation. The convention: one CLAUDE.md, at the repo root, carrying project
instructions — never a hierarchy of them, since a nested CLAUDE.md is auto-loaded
on every read beneath it. README.md files mark boundaries where a different tool,
runtime, or audience begins, and their genre follows depth: operator manual at
the root, boundary contract mid-tree, design doc under `src/`.
`rules/documentation.md` is the spec; the `technical-writer` agent and the
`doc-sync` skill both follow it.

### Planning Before Execution

Separating planning from execution surfaces ambiguities while they are still
cheap to fix. A plan written to a file captures decisions, rejected
alternatives, and accepted risks, so that reasoning survives clearing
context. Covered by `superpowers:writing-plans` and
`superpowers:executing-plans`.

### Review Cycles

Execution proceeds in reviewed milestones rather than one pass validated at
the end — one early oversight otherwise compounds through everything built
on top of it. The `quality-reviewer` agent checks production risk,
conformance, and structural quality; the `technical-writer` agent checks
documentation clarity. Covered by `superpowers:requesting-code-review`
before merge.

### Delegation

The three agents below run with a fresh, narrow context for one job each —
implementation, review, or documentation — instead of one agent carrying an
entire task. Debugging is not among them: `superpowers:systematic-debugging`
owns that trigger, and a second framework competing for it is worse than either
alone. Sub-agents inherit the session's model; there is no routing to a cheaper
model for simpler tasks.

## Division of Labor

Two systems cover this workflow between them. Do not add a skill that
duplicates either column.

| Need | Use |
|---|---|
| Explore a design before building | `superpowers:brainstorming` |
| Write / execute an implementation plan | `superpowers:writing-plans`, `executing-plans` |
| Debug a failure | `superpowers:systematic-debugging` |
| Review before merge | `superpowers:requesting-code-review` |
| Find structural debt | `refactor` (this repo) |
| A README or the root CLAUDE.md is missing, stale, or the wrong shape | `doc-sync` (this repo) — audits those files and owns every defect in them |
| Contradictions anywhere else — code, configs, schemas, `docs/` | `incoherence` (this repo) — repo-wide sweep, interactive resolution |
| Stress-test a decision | `decision-critic` (this repo) |
| An agent is misbehaving | `prompt-engineer` (this repo) |

## What's Here

| Path | Contains |
|---|---|
| `rules/` | Project conventions Claude Code loads on its own — see below |
| `hooks/` | Scripts run by the harness on tool events; registered in `settings.json` |
| `agents/` | 3 sub-agent definitions, see below |
| `skills/` | 5 skills this repo owns; see `skills/README.md` for what each inspects and outputs |
| `settings.json` | Shared settings (hook registration). Personal permissions belong in the gitignored `settings.local.json` |
| `LICENSE` | Upstream license — see attribution above |

### How each mechanism reaches the model

The four surfaces differ in *when* they load, and that is the whole reason for
the split. Reference material that nothing loads is dead weight.

| Surface | Loads | Cost |
|---|---|---|
| Root `CLAUDE.md` | Every session, always | Paid on every turn — keep it lean |
| `rules/*.md` with `globs:` | Automatically, when a file matching the globs is touched | Paid only on relevant work |
| `rules/*.md` without `globs:` | Every session, like CLAUDE.md | Same as CLAUDE.md |
| `skills/*/SKILL.md` | The `description` is always in context; the body loads when the skill is invoked | Description only, until used |
| `skills/*/references/*.md` | Only when the skill body tells an agent to read them | Nothing until needed |
| `agents/*.md` | When that sub-agent is dispatched | Nothing until dispatched |
| `hooks/` | On the matching tool event, outside the model | No context cost at all |

Current rules:

| Rule | Globs | Covers |
|---|---|---|
| `rules/documentation.md` | `**/*.md` | One root CLAUDE.md only; when a README is warranted and what genre it takes |
| `rules/code-comments.md` | `**/*.py` | Timeless-present framing; the detection heuristic behind change-narrative comments |

Put a convention in `rules/` when it applies to a file type. Put it in an
agent or skill body when it applies to a *task*. Do not create a directory of
reference markdown that only a prose sentence points at — nothing guarantees
it gets read.

### Hooks

`hooks/check_new_comments.py` runs after every `Write`/`Edit` and inspects only
the comments in the text just written, in `.py` files inside the repo. It flags
leftover TODO markers, change-narrative phrasing, and comment blocks over four
lines, then asks the model to fix or justify them. It never inspects untouched
code, so existing violations stay quiet until someone rewrites them, and it
ignores scratch files outside the project tree — those are not repo code.

Patterns are deliberately conservative — a missed violation costs less than a
false one. To disable, delete the `PostToolUse` entry from `settings.json`.

### Agents

Each is a Claude Code sub-agent (Task tool `subagent_type`). Invoke one
directly (`Use the quality-reviewer agent to...`) or let a superpowers workflow
delegate to it.

| Agent | Use for |
|---|---|
| `developer` | Implements a spec into working code, with tests when the spec calls for them |
| `quality-reviewer` | Reviews code or plans for production risk, conformance, and structural quality |
| `technical-writer` | Authors documentation optimized for LLM consumption, and applies approved `incoherence` resolutions to markdown. `doc-sync` decides whether a README or the root CLAUDE.md exists and what shape it takes |
