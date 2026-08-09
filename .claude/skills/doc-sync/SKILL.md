---
name: doc-sync
description: Use when a README has gone stale after a refactor, when a new subsystem or non-code asset has landed with no documentation, or for a periodic documentation audit
---

# Doc Sync

Maintains README.md files and the root CLAUDE.md, end to end — whether each
should exist, whether it is the right shape, and whether its claims still hold.

The split with `incoherence` is **scope, not problem type**. This skill owns a
short list of files and every defect in them, including false statements.
`incoherence` sweeps the whole repository — code, configs, schemas, specs,
`docs/` — for contradictions between arbitrary source pairs, and resolves them
interactively. Reach for it when the target is broader than READMEs, or when a
finding needs a human to adjudicate which side is wrong. Fixing a stale command
in a README you are already auditing is this skill's job; do not defer it.

Scope is by file, not by path: every README belongs to this skill wherever it
sits, including one under `docs/`. The long-form guides beside it do not.

## One CLAUDE.md, at the root

**Never create a CLAUDE.md in a subdirectory. Never convert the root CLAUDE.md
into a navigation index.**

Claude Code auto-loads a nested CLAUDE.md whenever a file under it is read, so
a hierarchy of them is a recurring context tax paid on every turn. This repo
deliberately has exactly one, at the root, and it is a project instruction file
— setup, commands, architecture, gotchas, and agent-facing policy. It is not a
table of contents, and directory navigation is not its job.

No exceptions:
- Not "just for the big directories"
- Not "an index would help an LLM find things" — `Glob` and `Grep` already do
- Not as a stub pointing at the README

If a directory needs explaining, that is a README.

## When a README is warranted

The trigger is a **boundary**: a different tool, runtime, or audience begins
here. Every README in this repo sits on one.

| Boundary | Example |
|---|---|
| Separate runtime or dependency set | `dags/` — own `pyproject.toml` and venv |
| Separate build artifact | `report/` — Docker + Quarto |
| External audience | `docs/contributor_bucket_access/` — written for a contributor |
| Non-code assets with provenance | `src/places_signals/data/` — where the CSV came from, how to update it |
| A document genre with its own process | `design/architectural_design_records/` |
| A subsystem whose design is not visible in its code | A stage split across two runtimes; an auto-discovery contract |

No README for a directory that is merely organizational. Absence is the default;
a boundary is what overrides it.

The model to copy is `src/places_signals/data/README.md`: seventeen lines
naming where the asset came from, how to update it, and what consumes it. It has
stayed correct across every change to the thing it documents. Design docs under
`src/` have not — treat their current contents as suspect, not as templates.

## What goes in one

Genre follows depth. Do not apply one content rule to all of them.

| Location | Genre | Contains |
|---|---|---|
| Repo root | Operator manual | Setup, commands, runbooks, troubleshooting |
| Mid-tree (`dags/`, `report/`) | Boundary contract + runbook | What this owns vs. what the caller owns, and how to run it |
| Under `src/` | Design doc | Data flow, invariants, and any design decision whose rationale you can source — see below |

Universal, in every README here: **an H1, then one or two sentences saying what
this is, before any heading.** Name the audience only where it is not obvious —
an external reader, a specific downstream consumer. For a design doc under
`src/` the audience is whoever edits the code, and saying so is filler.

A diagram goes immediately after that intro when the thing being documented moves
data through named stages in a fixed order — ASCII for one runtime, mermaid when
it crosses runtimes. A directory of independent classes earns no diagram, however
central it is; that says nothing about whether it earns a README.

Rationale goes under a heading of its own that names it: `## Design Decisions`,
`### Why This Separation?`. Where a rejected alternative is recorded, state it and
why it lost — that is the part no reader can recover from the code. Where none is
recorded, say that instead; do not supply one.

### Where a reason comes from

A rationale is by definition not in the code, so it has to be sourced. In order:

1. `design/architectural_design_records/` — this repo keeps ADRs
2. `git log -S'<symbol>' -- <path>`, and the body of the commit that introduced it
3. `gh pr view <n>` for that commit
4. A docstring or comment stating the reason — quote it, and attribute it to the
   docstring rather than restating it as fact
5. Ask.

**"No rationale is recorded" is a correct and expected result** — often the most
common one, in a repo whose history is squashed. Write it. A README saying "why
this is split in two is not recorded; the mechanism is X" is worth more than one
carrying an invented reason a reader will then trust. Finding zero sourced
rationales across a whole directory is a legitimate outcome, not a shortfall.

A near-miss is worth recording too: an ADR whose *filename* looks like the
rationale for this code but whose contents are about something else. Say so, and
save the next reader the same detour.

## What rots — do not write it

Ranked by observed breakage in this repo.

| Never | Why |
|---|---|
| Line-number citations (`see nodes.py:82-105`) | Every one of these in the repo is now wrong |
| A pipeline stage or node name with no file named beside it | Half the node names in one pipeline README no longer exist. Method and parameter names are fine — a design doc cannot avoid them — as long as the file is named too |
| Spelling out a raw command a Makefile target already wraps, or one that no longer runs | Documented `kedro run --pipeline inference`; only `inference_{source}` is registered, so the command fails. Naming the target is right; transcribing what it wraps is not |
| "Comparison with the original / old approach" | Compares against a deleted file. Migration notes belong in the PR |
| Restating a module docstring as the intro | Costs a paragraph, adds nothing |

Prefer names that survive refactors: directory names, dataset names, Makefile
targets, catalog entries. Those have held across every refactor here.

Commands: point at a Makefile target where one fits. Where none does, write the
literal command and name what verifies it — then **go read that source before you
write the command down.** What rots is an unchecked command, not a command.

### Two checks before any claim goes in

**A claim reaching outside the file in front of you needs a search.** Accuracy
inside an open file is easy; every fabrication observed in testing was a claim
reaching past the file in hand.

The tell is any word that quantifies over code you are not looking at, and it is
usually a small one — `only`, `never`, `always`, `all`, `every`, `nothing else`,
`the sole`, `instead`. Adverbs count: "is only exercised by", "the only escape
hatch" and "serves the report only" are scope claims wearing hedges. Run the grep
and name it in the text, or delete the word.

**Every causal connective is a claim.** "because", "so that", "therefore",
"instead", "correspondingly" each assert a link. Two true halves joined by an
unverified connective is still a fabrication — and it is the part readers trust
most, because it reads as the insight. Establish the link, or use a full stop.

The highest-value, lowest-rot content in the repo is provenance and update
procedure for non-code assets — where it came from, how to change it, what
consumes it. Generalize that pattern.

## Long form lives in docs/

`docs/` owns the depth. A README carries the shortest correct pointer plus any
warning a reader must not miss by following a link instead — the run_id
collision, the coordination hazard. Do not inline a `docs/` guide into a README;
do not leave a bare link where a one-line warning was the point.

## Workflow

1. **Scope** — repository-wide unless the request names a path.
2. **Inventory** — find existing READMEs (`fd -H readme.md -i` or `git ls-files`),
   and list candidate boundaries from the table above that have none.
3. **Audit each existing README** against the rot table and the genre table.
   Record: genre mismatch, missing intro paragraph, rot instances with
   `file:line`, and content that belongs in `docs/` instead.
4. **Decide coverage** — for each boundary with no README, judge whether one is
   warranted. Say no when the boundary is weak; a thin README is worse than none.
   **Writing zero READMEs is a valid result for a scoped run** — a named scope is
   not an instruction to produce a file. Report what you declined and why.
5. **Write** — fix the rot, add missing intros, create warranted READMEs. Cite
   durable names only. Leave a note for anything requiring a decision you cannot
   make from the code.

   Patch a README when its claims are mostly sound. **Rewrite it from the code
   when a load-bearing claim is fictional** — a node, column, or invariant that
   does not exist. Editing around invented content preserves its framing and
   costs more than starting from what the code actually does. The root CLAUDE.md
   is the exception: correct it in place, never restructure it.
6. **Check the root CLAUDE.md** — its Architecture, Gotchas, and Commands
   sections are the parts that go stale. Verify pipeline names against
   `kedro registry list` and commands against the Makefile. Do not restructure it.

## Output

```
## Doc Sync Report — [scope]

### READMEs audited: [n]
| File | Genre | Issues | Action |
|---|---|---|---|

### Created: [paths, with the boundary that justified each]
### Boundaries left undocumented: [path — why a README was not warranted]
### Root CLAUDE.md: [VERIFIED | n corrections]
### Needs a human decision: [anything unresolvable from the code]
```

## Common mistakes

| Mistake | Fix |
|---|---|
| Creating a CLAUDE.md hierarchy | One CLAUDE.md, at the root. Explain directories in READMEs |
| Applying "invisible knowledge only" everywhere | That rule fits `src/` design docs. It would delete ~85% of the root operator manual |
| Deferring a stale command to `incoherence` | Inside a README you are auditing, fixing it is this skill's job. Defer only what reaches outside these files or needs a human to adjudicate |
| Editing around a fictional invariant | If a load-bearing claim does not exist in the code, rewrite from the code |
| Writing a README because a directory looked bare | Absence is the default. A boundary is what justifies one |
| Writing a plausible rationale you did not source | The single most common self-inflicted rot. Source it from the ADRs, `git log -S`, or the PR — or record that none is written down |
| A "because" or "instead" joining two facts you checked separately | The connective is the claim. Establish it or split the sentence |
| "The only place that does X" without running the grep | Every fabrication in testing was a claim reaching past the open file |
| Writing a command without opening the Makefile or registry first | Two seconds of reading beats an assertion about a file you could have read |
