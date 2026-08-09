# Incoherence

Why this skill is shaped the way it is. The lens catalog and workflow live in
`SKILL.md`.

## The problem

Documentation drifts from code silently. Nothing fails, no test goes red — a
command in a README simply stops working, a documented default stops being the
default, a doc keeps describing a subsystem that was deleted. The cost lands on
whoever trusts the doc.

## Detection was never the hard part

Measured on this repo against four planted, independently confirmed
incoherences, the fan-out found **all four**, most of them five to seven times
over, plus a dozen the plant list did not include. Recall is easy.

The cost was the problem. The original shape demanded **277 agents**: eight
detection agents producing 269 findings, then one verification agent per finding.
Those 269 findings covered roughly 168 distinct issues, so **38% of verification
spend re-confirmed something already confirmed** — a single dead link was reported
by seven lenses and would have cost seven agents each reading 100+ lines of
context to settle what `ls` answers in 40ms. Another 15% went on findings nobody
would edit a file over. Total waste: **52%**.

Reworked, the same scope cost **21 agents** — five lenses, 33 findings, 16
clusters — and still found 4 of 4. Three changes did it.

**Cluster before verifying.** The original said, as bare fiat with no rationale,
"Deduplication happens after verification, not here." Lenses overlap by
construction, so one defect surfaces once per lens that can see it. Grouping by
source pair as findings arrive collapsed 33 to 16 and saved 17 agents with no
recall loss.

**A triage gate at the source.** Detection agents were told to report "every
finding found, with no self-filtering." That is what let through `PYSPARK_PYTHON`
and `KUBERNETES_SERVICE_HOST` as "undocumented env vars". One question — would a
maintainer edit a file over this? — removes that class at zero cost. The gate now
also returns its drop list, because triage the caller cannot see is triage the
caller cannot correct.

**Resolve scope exclusions first.** A literal reading of "scope = `docs/`" spent
6% of one run's fan-out on gitignored local scratch and on an unfilled Linux
Foundation template still carrying `[Organization_Abbreviation]` placeholders.
Neither is incoherent; one is unwritten and the other is not shipped.

## Why verification must execute

Every finding that changed its own diagnosis did so by running something.

One verifier drove an actual `KedroSession` with the README's exact parameters,
captured `Failed to find the pipeline named 'ingestion'`, then `git blame`d the
snippet and found it **never worked at any commit** — reframing "the docs drifted"
into "this was born broken." Another loaded the project's own config resolver and
proved a documented default unreachable, where reading had concluded the doc and
the config agreed. A third stood up a throwaway MLflow registry and demonstrated
that `get_latest_versions()[0]` and the `Production` alias resolve to different
model versions.

The original asked verifiers only to "read both sources with 100+ lines of context
and extract exact quotes." It got execution because agents volunteered it. The
sharpest illustration: an `Explore` agent ran executables and **self-refuted three
of its own findings** — violating the skill's own "no self-filtering" clause to do
the single most valuable thing any detection agent did.

That agent type is gone. `Explore` is chartered to locate code, not to adjudicate
whether two sources conflict; it worked only by exceeding its brief.

## What testing changed after the rewrite

**Severity had lost its basis.** Forbidding agreement-as-priority was right —
measured, the cluster four lenses reported was LOW while a HIGH one, a documented
default that silently loads the wrong model, was seen by one lens. But removing
the only cross-cluster signal without supplying a replacement left severity
ungrounded. It is now the consequence of acting on the wrong claim: silent wrong
data is HIGH, a loud failure is MEDIUM, a self-correcting reader is LOW.

**The cap could hide a blind spot.** Capping lenses at four to six is what makes
the skill affordable, but one finding — a branch-diff document serving as a
subsystem's only reference — was visible to `dangling-refs` and to nothing else,
because its *content* was accurate and only its *shape* was wrong. The skill now
asks which lens is the sole cover for each defect class before dispatching.

**One number in the skill was wrong.** It claimed the naive shape cost 277 agents
"to produce four actionable findings." Four was how many verifications the baseline
run was *capped at*, not how many the skill found; the reworked run produced 16
actionable findings with 21 agents. A calibration figure a reader cannot check, and
that conflates a cap with a result, is worse than none.

## Division of labor

`incoherence` sweeps everything for contradictions between arbitrary source pairs
and resolves them interactively. `doc-sync` owns README files and the root
CLAUDE.md — whether they should exist and whether they are the right shape — and
every defect inside them. Fixing a stale command in a README that doc-sync is
already auditing is doc-sync's job.

## Usage

```
Use your incoherence skill on docs/ and the root README
Use your incoherence skill across the repo
```
