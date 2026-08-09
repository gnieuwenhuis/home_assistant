# Skills

Five project-specific skills, each a declarative `SKILL.md` — no Python
scripts, no step counters, nothing to invoke. Claude reads the phases in the
file directly.

For which system owns which workflow — this repo's skills vs. the
superpowers plugin — see [`../README.md`](../README.md#division-of-labor).
That table is not duplicated here; this file covers per-skill detail only.

## refactor

**Trigger:** code feels messy after a feature lands, a simple change touches
many files, or a review turns up duplication, god functions, unclear naming,
or weak module boundaries.

**Inspects:** the given file, directory, subsystem, or whole codebase across 11
weighted dimensions. Scope decides which are eligible and caps how many agents
run — a single file gets at most 4, and never Architecture or Module Boundaries,
which need more than one file to mean anything. One `general-purpose` agent per
selected dimension runs in parallel, each required to prove behavioural claims
by executing them. Findings are deduplicated before scoring, ranked
`severity × weight`, then turned into proposals tested against a
composability/precision/no-speculation/simplicity philosophy.

**Outputs:** tiered recommendations (Critical / Recommended / Consider), each
with location, evidence, and an execution transcript. Unproven claims are
labelled UNVERIFIED and cannot reach Critical. No code changes — it proposes
edits, it does not make them.

**Not this skill:** stale docstrings and doc rot (`doc-sync`); production-risk
review (`quality-reviewer` agent).

```
Use your refactor skill on src/places_signals/helpers/timestamp_utils.py
Use your refactor skill on src/ -- focus on shared abstractions
```

## incoherence

**Trigger:** documentation contradicts code, a spec and its implementation
have drifted apart, or CLAUDE.md describes behavior the codebase no longer
has.

**Inspects:** docs, code, types/schemas, and specs through a catalog of 13 named
lenses — `doc-vs-code`, `config-drift`, `dangling-refs`, `doc-vs-doc` and others.
Four to six run, one `general-purpose` agent each, after scope exclusions are
resolved (gitignored scratch and unfilled templates are not incoherent). Detection
gates on "would a maintainer edit a file over this?" and returns its drop list.
Findings are then **clustered by source pair before any verification**, so one
defect costs one agent however many lenses saw it, and verifiers must **run**
anything executable — a documented command, path, or pipeline name — rather than
reason about it.

**Outputs:** resolution is interactive — confirmed clusters are batched and
presented via `AskUserQuestion`, grouped by shared root cause. Approved
resolutions are applied to their target files (`technical-writer` for docs,
`developer` for code). Ends with counts, the agent spend, and a table of every
cluster with severity, status, and reason.

**Cost:** measured on `docs/` + the root README, one-agent-per-finding demanded
277 agents with 52% of the spend on duplicates and non-issues. Clustering first
does the same scope in 21, with identical recall against known ground truth.

## doc-sync

**Trigger:** a README has gone stale after a refactor, a new subsystem or
non-code asset landed with no documentation, or a periodic audit.

**Inspects:** README.md placement and shape, repository-wide or under a given
path — whether a boundary justifies each file existing, whether its genre
matches its depth (operator manual at the root, boundary contract mid-tree,
design doc under `src/`), and rot: line-number citations, node names that no
longer resolve, invocations that restate a Makefile target. Also spot-checks
the root CLAUDE.md's commands and pipeline names.

**Outputs:** fixes rot and writes warranted READMEs directly; reports what it
audited, what it created, and which boundaries it deliberately left
undocumented. It never creates a subdirectory CLAUDE.md — this repo has exactly
one, at the root.

**Not this skill:** contradictions outside these files — code, configs, schemas,
`docs/`. That is `incoherence`, which sweeps repo-wide and resolves
interactively. Inside a README doc-sync is auditing, fixing a false claim is
doc-sync's job.

```
Use your doc-sync skill to audit documentation across this repository
Use your doc-sync skill on src/places_signals/pipelines/
```

## decision-critic

**Trigger:** an architectural choice, technology selection, or tradeoff
you're not fully confident in, before committing to something expensive to
reverse.

**Inspects:** a single decision, stated as one explicit sentence, reduced to one
list of the statements it rests on — each tagged evidence / value-trade-off /
fixed-limit, and marked load-bearing or not. There are no quotas: an empty class
is reported rather than filled. Evidence-settleable items are checked by running
something wherever possible, including rebuilding whatever evidence the author
cited. The decision then faces a case against it, a case for it, and a pass at
the problem statement itself.

**Outputs:** a verdict (Stand / Revise / Escalate) and the strongest falsifier in
the first ten lines, then the breaking items split blocking vs additive, each
naming the concrete input that triggers it and whether that input is OBSERVED or
CONSTRUCTIBLE. Per-item verification goes to an appendix. No file changes.

**The rule that matters:** every objection names its triggering input, or it is
dropped. Measured on a sound decision, the previous version returned REVISE with
4 of 10 objections self-scored as manufactured; with the rule it drops the
unfounded ones and returns Stand.

## prompt-engineer

**Trigger:** a sub-agent definition or skill body that isn't behaving as
intended, or a review of agent/skill prompts for clarity and consistency.

**Inspects:** one prompt file at a time. Asks first for a run of the thing
misbehaving, then reads the target cold — before any technique reference, to avoid
pattern-shopping. An **executability** pass leads: formulas whose operands are
undefined, named agents whose charter excludes the ask, validation steps whose
result cannot vary, fan-out unbounded by what is consumed, assets nothing loads.
Structural, behavioural and stylistic follow. Technique references load lazily —
selection guides only, full sections on cite or on reject.

**Outputs:** findings tiered by evidence — OBSERVED (seen to misbehave), DERIVED
(follows necessarily from the text), SPECULATIVE (neither, and below the fold).
Each carries the concrete failure it causes, a technique or an explicit NONE with
the near-match that was rejected, before/after text, and a tradeoff. Presented for
approval; nothing is applied without explicit sign-off.

**Measured:** on a 67-line target the old flow read ~3,950 reference lines to
produce 9 quotes — 97% of tokens reference, 1% the artifact — and proposed four
technique-led changes it would not defend. The rework reads 6.5% of the corpus and
found 6 of 6 empirically-established defects plus 5 more.

```
Use your prompt engineer skill on .claude/agents/developer.md
```
