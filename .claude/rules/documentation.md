---
globs:
  - "**/*.md"
---

# Documentation Conventions

## One CLAUDE.md, at the root

This repository has exactly one CLAUDE.md and it lives at the repo root.

**Never create a CLAUDE.md in a subdirectory.** Claude Code auto-loads a nested
CLAUDE.md whenever a file beneath it is read, so a hierarchy of them is a
context tax charged on every turn, to do what `Glob` and `Grep` already do.

The root file is a project instruction file — setup, commands, architecture,
gotchas, and agent-facing policy. It is **not** a navigation index; do not
convert it into one, and do not migrate its prose out into README files. If a
directory needs explaining, that is a README.

## README.md

### When one is warranted

A README marks a **boundary** — a different tool, runtime, or audience starts
here. Absence is the default; a boundary is what overrides it.

Boundaries that justify one: a separate runtime or dependency set (`dags/`), a
separate build artifact (`report/`), an external audience, non-code assets
needing provenance (`src/places_signals/data/`), a document genre with its own
process, or a subsystem whose design is not obvious from its code.

A directory that is merely organizational does not get one. A thin README is
worse than no README.

### What goes in one

Genre follows depth — do not apply one content rule to all of them.

| Location | Genre | Contains |
|---|---|---|
| Repo root | Operator manual | Setup, commands, runbooks, troubleshooting |
| Mid-tree | Boundary contract + runbook | What this owns vs. the caller, and how to run it |
| Under `src/` | Design doc | Data flow, invariants, and any design decision whose rationale you can source |

The "delete anything a developer could learn from the source" test applies to
`src/` design docs **only**. It is wrong for an operator manual, where ordering,
preconditions, and consumer-facing contracts earn their place even when each
line is individually derivable.

Every README opens with an H1 and one or two sentences saying what this is,
before any heading. Name the audience only where it is not obvious — an external
reader, a specific downstream consumer. Under `src/` the audience is whoever
edits the code, and saying so is filler. A pipeline or workflow README earns a
diagram right after that.

Rationale goes under a heading that names it (`## Design Decisions`, `### Why
This Separation?`). A rationale is by definition not in the code, so it has to be
sourced — an ADR under `design/architectural_design_records/`, `git log -S` and
the commit body, the PR, or a docstring you quote and attribute. Where a rejected
alternative is recorded, state it and why it lost. Where none is recorded, say
that instead; do not supply one.

### Do not write

- Line-number citations — every one in this repo is now stale
- Node or function names without the file that registers them
- Runnable invocations that restate a Makefile target; point at the target
- "Comparison with the original" — migration notes belong in the PR
- The module docstring restated as an intro

Prefer names that survive refactors: directories, datasets, Makefile targets,
catalog entries.

## docs/ owns the long form

`docs/` holds the depth. A README carries the shortest correct pointer plus any
warning a reader would miss by following the link instead. Do not inline a
`docs/` guide into a README.

## Naming agents

Refer to an agent by its backticked bare name — `technical-writer`, `developer`.
This covers every markdown file, agent definitions and skill bodies included.

Never use the at-mention form: an at-sign followed by `agent-<name>`. The harness
parses it as a request to dispatch that agent, and markdown gets quoted — a
subagent auditing this repo pulls the string into the caller's context, where it
fires as an instruction the user never gave. Measured: one occurrence in one
agent definition produced spurious dispatch instructions across five separate
audit agents.

When quoting text that already carries it, including output from `git show`,
write it `[at]agent-<name>`.
