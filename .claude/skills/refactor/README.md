# Refactor

Why this skill is shaped the way it is. The dimension table, workflow, and
scoring rules live in `SKILL.md` — they are not repeated here, because the two
files had already drifted to different dimension names once.

## The problem it exists for

LLM-generated code accumulates structural debt faster than hand-written code.
The model does not see duplication across files, does not notice a function
growing past its purpose, and cannot tell that three modules implement the same
rule three different ways. This skill hunts that.

## What a measured run changed

The first version dispatched one agent per dimension for all eleven dimensions,
then triaged down to three to five. Run against a single 71-line utility module
it dispatched nine agents and discarded four — 44% of the work paid for and
thrown away — where four agents would have produced the same output.

Four further defects showed up in that run, and the current design is mostly a
response to them.

**Ranking counted the same bug repeatedly.** Twenty findings covered about ten
distinct defects; one defect was reported by seven of nine agents. Because the
score summed findings, that one bug inflated seven dimensions at once, and the
top five became five views of it — while the only dimension carrying independent
information was dropped just below the cut. Deduplication now happens before
scoring, and agreement raises confidence rather than score.

**The formula could not be evaluated.** `severity × count × weight` multiplies a
string by an integer, with no severity-to-number map and no rule for aggregating
a mixed-severity dimension. Three defensible readings gave three different
top-fives. It is now `severity × weight` with the mapping published, and count
removed — summing rewarded an agent that split one defect into three findings
over one that stated it precisely.

**Dimension partitioning suppressed a real bug.** The Naming agent found the
file's worst defect — two functions detecting millisecond timestamps by
different, disagreeing rules — and filed it at severity `none` because it was "a
duplication finding, out of this dimension." It survived only because six other
agents also happened to see it. Agents are now told to report out-of-dimension
findings rather than score them away.

**The named validation gate was the wrong one.** The skill required
`make run-tests` before reporting. It changes no code, so the suite's result is
determined before the skill starts; it cost four minutes forty. Worse, it passed
688 tests at 100% branch coverage over a file with five verified wrong outputs —
the gate the skill trusted was the gate that missed everything. It is gone.
`make check` stays, because it earns the "don't duplicate ruff and mypy" rule.

## Why execution is mandatory

The findings from that run were trustworthy for a reason the skill never asked
for: several agents ran the code to prove their claims, one producing
regex-engine root-cause analysis. That was luck — the agent type in use was
`Explore`, specified as locate-only, and it happened to exceed its contract.

Building on agents outperforming their spec is not a design. The skill now
dispatches `general-purpose` agents and requires an execution transcript for
every behavioural claim; anything unproven is labelled UNVERIFIED and barred
from the Critical tier.

## What the rewrite measured

Re-run on the same file, the new version dispatched 4 agents instead of 9 and
discarded none, deduplicated 13 raw findings into 7 defects, and tiered the
target bug Critical. All three returning agents produced execution transcripts
rather than assertions. The out-of-dimension rule earned its place immediately:
the Extraction agent filed its *highest-severity* finding outside its own lens
at `high` — the same class of defect the previous version filed at `none`.

That run exposed three subtler faults, now fixed.

**Weight was being read off the reporting agent.** A dead export belongs to
Abstraction (weight 3), but scored weight 2 because the Conditionals agent
happened to trip over it. Identical defects scored differently depending on who
was dispatched. Weight now comes from the dimension a defect belongs to, whether
or not that dimension ran.

**Removing count from the score removed all resolution.** Seven defects came out
as one 6, five 4s and one 2 — everything below rank one was unordered, and the
skill banned the obvious tiebreak without supplying another. Agreement across
dimensions now breaks ties; it had been computed as "confidence" and then never
used for anything.

**UNVERIFIED was attached to defects rather than claims.** The worst bug in the
file had a proven code-level defect and an unprovable secondary question — do
such inputs actually occur in the bucket? Read literally, the rule demoted it
out of Critical for the unprovable half.

## Why agents must test the code's claims, not just their own

Three agents independently ran the code and all three missed the same defect:
the docstring promises "returns the last one found", and the regex consumes its
own delimiter, so adjacent timestamp segments are invisible and the *first* wins.
It surfaced only when the coordinator checked it.

Proving your own claims finds what you already suspect. Running what the
docstring promises finds what nobody thought to suspect. The dispatch contract
now requires both.

## What earns its keep

The `references/` carve-outs. In the measured run they correctly suppressed four
would-be findings: renaming `timestamp_utils.py` despite matching the `Utils`
grep (six sibling `*_utils.py` files make it convention), primitive `str` and
`float` parameters at a serialization boundary, generic loop variable names, and
a docstring example that turned out correct character-for-character. Detection
patterns without carve-outs produce style opinions; the carve-outs are what make
the output a findings list.

## Usage

```
Use your refactor skill on src/places_signals/helpers/timestamp_utils.py
Use your refactor skill on src/ -- focus on shared abstractions
```

## What it does not do

Generate refactored code, apply fixes, or propose changes beyond what evidence
supports. Documentation rot belongs to `doc-sync`; production-risk review
belongs to the `quality-reviewer` agent.
