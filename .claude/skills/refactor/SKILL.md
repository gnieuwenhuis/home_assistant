---
name: refactor
description: Use when code feels messy after a feature lands, when a simple change requires touching many files, or when reviewing for duplication, god functions, unclear naming, or weak module boundaries
---

# Refactor

Finds structural debt an author cannot see in their own code — duplication
across files, a rule reimplemented four ways, boundaries in the wrong place.
Analysis only: it proposes edits, it does not make them.

Its findings are trustworthy only when they are **executed, not argued**. A
behavioral claim without a transcript proving it is a guess.

## Scope decides the dimensions

Select dimensions **before** dispatching. Every agent you dispatch should be one
whose findings you intend to read.

| Scope | Eligible dimensions | Dispatch at most |
|---|---|---|
| One file | Naming & Semantics, Extraction & Composition, Conditional Complexity, Error Handling, Type & Interface Design, Testability, Readability & LLM Comprehension | 4 |
| Module or directory | the above, plus Abstraction & Pattern Unification and Modernization | 6 |
| Subsystem or whole repo | all 11 | 8 |

Architecture and Module Boundaries need more than one file to mean anything — a
leaf module has no cycles, no layers, no components. Never dispatch them on a
single-file scope.

From the eligible set, pick only dimensions the code can actually exhibit. A
71-line stdlib-only module cannot have layer violations or deprecated APIs.
Say in one line why each dimension was picked; if you cannot, do not dispatch it.

If more dimensions qualify than the cap allows, take the highest weight first;
break ties by running that dimension's reference greps and preferring the one
that actually hits.

## Dimensions

Detection detail lives in `references/` — grep patterns, thresholds, explicit
"not a smell" carve-outs, and a stop condition per section. **The carve-outs are
the highest-value part of this skill**; they are what separates a finding from a
style opinion. Each agent reads only its own sections.

| Dimension | Focus | Weight | Detection detail |
|---|---|---|---|
| Naming & Semantics | Names that mislead, obscure intent, or sit at the wrong abstraction level | 1 | `baseline` §1, `coherence` §2 |
| Extraction & Composition | Code that resists change through duplication, mixed responsibilities, or complexity | 1 | `baseline` §2, `coherence` §1 §8 |
| Conditional Complexity | Conditionals signalling missing abstractions, weak domain modelling, or implicit state | 2 | `baseline` §3 §4 §6 §7 §8, `coherence` §5 |
| Testability | Code that is hard to test in isolation; tests that assert nothing | 1 | `baseline` §9 §15 |
| Type & Interface Design | Missing domain concepts, primitive obsession, leaky abstractions | 2 | `baseline` §5 §10 §17, `coherence` §7 |
| Error Handling | Inconsistent, swallowed, or poorly located error handling | 2 | `baseline` §11, `coherence` §6 |
| Module Boundaries | Circular dependencies, wrong cohesion, layer violations | 3 | `drift` §1 |
| Modernization | Outdated patterns, deprecated APIs, missed language features | 1 | `baseline` §12 |
| Architecture | Wrong boundaries, scaling bottlenecks, structural constraints | 3 | `drift` §2 §5 |
| Readability & LLM Comprehension | Code needing external context to understand | 1 | `baseline` §13, `drift` §3 |
| Abstraction & Pattern Unification | Repeated patterns across files that one abstraction would unify | 3 | `coherence` §3 §4, `drift` §4 |

`coherence` thresholds come in file and codebase scopes — use the file column for
single-file reviews, codebase for anything wider.

Documentation rot is not this skill's. A docstring that contradicts its code goes
to `incoherence`; a stale README or missing asset provenance goes to `doc-sync`.
Do not open a dimension for either.

## Workflow

### 1. Scope and select
Resolve what is in play, then pick dimensions per the table above.

### 2. Dispatch
One `general-purpose` agent per selected dimension, all in a single message.
Not `Explore` — that agent is specified to locate code, not audit it, and cannot
be relied on to verify a claim.

Each agent's prompt must carry:
- its dimension, and the `references/` sections to read **before** searching.
  Copy the section numbers from the table verbatim — a mistyped number silently
  changes what the agent reads and nothing detects it.
- **"Prove every behavioural claim by running it. Include the command and its
  real output. A claim you did not execute must be labelled UNVERIFIED."**
- **"Test what the code claims, not only what you claim. Run the docstring's
  promises and its examples. A documented behaviour that does not hold is a
  finding."**
- **"Defang agent-mention syntax inside quotes: write an at-sign followed by
  `agent-<name>` as `[at]agent-<name>`."** Your report re-enters the caller's
  context, where that syntax is parsed as a request to dispatch that agent.
- **"Report anything you find, even outside your dimension — label it
  out-of-dimension and score it normally. Never suppress a real defect because
  it belongs to another lens. Before assigning it a severity, read the reference
  section that owns it; if you cannot, mark it `carve-outs unchecked`."**
- **"If a section's greps return nothing in scope, say so in one line and move
  on. Do not manufacture a finding to justify the section."**
- the user's focus area, if given, as `FOCUS: {area}. Prioritise findings
  relevant to this goal.`

Agents return findings as: location, evidence, execution transcript, severity
(`low` / `medium` / `high`), and the reference section that justifies it.

If an agent has not returned once the others are done, proceed without it and
name the missing dimension in the report. A silent gap reads as a clean bill.

### 3. Deduplicate — before scoring
Merge every finding describing the same underlying defect into one entry. Keep
the clearest statement, union the locations, and record how many dimensions
found it. Do this first: without it, the defect that most agents notice
dominates the ranking purely by being noticed a lot.

### 4. Rank
Score each deduplicated defect:

```
score    = severity × weight
severity = high 3, medium 2, low 1 — if agents disagree, take the highest
weight   = the weight of the dimension the defect BELONGS to, not the
           dimension that happened to report it
tiebreak = more reporting dimensions wins; then, the fix that unblocks the most
           other defects
```

Finding count never enters the arithmetic — splitting one defect into three must
not beat stating it once. Agreement breaks ties only; it cannot promote a defect
past a more severe one.

Look up the owning dimension's weight even when it was ineligible for this
scope. A dead export is Abstraction's (weight 3) whether or not Abstraction ran;
scoring it by whoever tripped over it makes the ranking depend on dispatch luck.

### 5. Verify
Re-read the code for the top defects and confirm each transcript reproduces.
Discard what does not hold.

UNVERIFIED attaches to a **claim**, not a defect. A proven code-level defect can
be Critical while a secondary claim about it — does this input actually occur in
production? — stays unproven; state the unproven part inline rather than
demoting the finding. A defect whose *core* claim is unproven cannot be Critical.

Two agents can reach opposite conclusions and both transcripts reproduce — they
disagree on reachability or interpretation, not fact. Decide it yourself and
record both positions.

### 6. Propose and validate
Give each surviving defect a concrete edit — the rename, the extraction, the
type to introduce. Then test it:

| Principle | Test |
|---|---|
| COMPOSABILITY | Does the piece combine cleanly with what is already there? |
| PRECISION | Does the new name create a semantic level you can be exact in? |
| NO SPECULATION | Are the repetitions observed, or predicted? |
| SIMPLICITY | Is this the minimum the current task needs? |

Drop what fails, and say what you dropped and which principle killed it.

### 7. Synthesize
Look across the surviving proposals for one abstraction that resolves several.
Tier as **Critical** / **Recommended** / **Consider** and present together.

## Gates

Run `make check` (ruff, ruff-format, mypy strict). Never spend a finding on what
it already enforces — that is noise.

Do **not** run `make run-tests` to validate findings. This skill changes no code,
so the suite's result is fixed before it starts; it costs minutes and proves
nothing. A green suite is not evidence a finding is wrong — on this repo, 688
passing tests at 100% branch coverage coexisted with five wrong outputs in the
file under review.

## Common mistakes

| Mistake | Fix |
|---|---|
| Dispatching all 11 dimensions, then picking 5 | Select before dispatch. Discarded agent work is pure cost |
| Scoring before deduplicating | One defect, one score, however many agents saw it |
| Letting finding count into the score | `severity × weight` only |
| Accepting a behavioural claim you did not run | Execute it or label it UNVERIFIED |
| An agent scoring a real bug `none` because it is another dimension's problem | Instruct agents to report out-of-dimension findings |
| Scoring an out-of-dimension defect by the reporter's weight | Use the weight of the dimension it belongs to |
| Only testing claims the agents made | Run what the docstring promises too — that is where the unexamined bugs sit |
| Dropping a proven defect because a secondary claim is unproven | UNVERIFIED attaches to a claim, not the defect |
| Dispatching Architecture at single-file scope | It has nothing to find there |
| Proposing an abstraction from one instance | NO SPECULATION. Observed repetitions only |
