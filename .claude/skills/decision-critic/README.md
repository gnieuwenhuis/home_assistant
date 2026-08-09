# Decision Critic

Why this skill is shaped the way it is. The workflow lives in `SKILL.md`.

## The problem

Models agree by default. Ask one whether your architecture is sound and it will
tell you it is well-reasoned. For a decision that is expensive to reverse, that
is worse than no answer, because it feels like confirmation.

## The failure that is easy to miss

Structure alone does not fix sycophancy — it can launder it. A critique that
emits seven claims, marks them all verified, and concludes STAND is agreement
wearing a method's clothes.

But the opposite failure is just as damaging and much less discussed:
**manufactured criticism**. An earlier version of this skill was measured on a
decision that was actually sound. It returned REVISE, and the reviewer, asked to
mark its own objections honestly, scored **four of ten as manufactured** — raised
because the structure expected something in that slot, not because it believed
them. Its own summary: the manufactured items clustered in exactly two places,
the per-item question quota and the reframing pass's fixed sub-question list.

A manufactured objection costs more than a missed one. It teaches the reader to
skim, and the next genuine finding gets skimmed with it.

## What the measurements changed

Two decisions were used, both with known ground truth: one containing a real
flaw, one sound.

**Quotas were removed.** The old decompose step demanded 3-7 claims, 2-5
assumptions, 1-4 constraints and 1-3 judgments. On a fourteen-line function the
Judgments floor of 1 forced a reviewer to reverse-engineer trade-offs the author
never made; the Assumptions floor produced an item that was a restatement of a
claim already listed. There are now no minimums, and an empty class is reported
as a finding about the decision.

**The two overlapping taxonomies became one list.** Claims and Assumptions were
partitioned by *whether the author said it out loud* rather than by what the
statement asserts, so the same defect got recorded twice and verified twice.

**Verification is now empirical.** The old wording confined answers to
"established knowledge, stated constraints, and logical inference." Both
reviewers flagged this as the worst instruction in the skill. One obeyed it and
shipped a mechanical claim at 95% confidence rather than spend three lines in a
REPL; the other ignored it and said so, noting that without execution the
verification section would have been a paraphrase of the author's own reasoning.
Deterministic execution is the opposite of motivated reasoning — the rule banned
the one evidence source that cannot be biased.

The rewrite also asks reviewers to **reproduce the evidence the author cited**.
On the flawed decision that proved the highest-value move available: the reviewer
rebuilt the claimed fifteen tests, reproduced 100% line and branch coverage
exactly, then broke it with one input. Arguing that coverage does not imply
correctness is a lecture; reproducing the author's own number and breaking it is
not arguable.

**Every objection must name the input that triggers it.** This is the load-bearing
addition. On the sound decision it caused the reviewer to drop three objections
it could not attach an input to, and its verdict moved from REVISE to a correct
**Stand** at higher confidence. Its own assessment: "the best thing in this
skill."

**Triggers are tagged OBSERVED or CONSTRUCTIBLE.** Without that split, a reviewer
led its report with a vivid failure whose trigger did not exist in any bucket,
then had to walk the severity back in prose.

The tag deliberately does *not* set severity. The first draft of this rule said a
constructible trigger could never block — which, checked against the flawed test
decision, would have demoted its decisive flaw and produced Stand on a decision
that genuinely needed revising. That flaw's trigger is constructible: it fires
when an upstream producer changes a number format, something that producer had
already done once. So a CONSTRUCTIBLE trigger now carries one sentence on what
would have to happen, and that sentence carries the severity.

**The verdict rests on blocking vs additive**, not on whether a claim was "core."
"Core" was undefined and decided the verdict; one reviewer reached REVISE at 70%
confidence on a technicality of that word and said so.

## What was cut after the rewrite was tested

`HOLDS (inert)` — a verify state for things true but weightless. Both reviewers
identified it as a padding permit with a warning label attached, and one put a
genuinely inert item in it and then called that out as the clearest case of
structure producing content. Weightless checks now get one closing line, not a
row.

The Stand path also got its own opening. The output template assumed a falsifier
existed, so a sound decision forced the reviewer to lead with a hypothetical
break and immediately retract it.

## Usage

```
Use your decision-critic skill on the caching approach in the design doc
```

State the decision as one sentence, or the skill will ask for it.
