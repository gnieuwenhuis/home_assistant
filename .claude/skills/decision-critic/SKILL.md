---
name: decision-critic
description: Use when you have chosen an approach but are not confident in it, before committing to a design decision that is expensive to reverse
---

# Decision Critic

Stress-tests a decision before it is committed to. Models agree by default;
this makes disagreement structural rather than optional.

The report is worth reading only if every objection in it is real. **A
manufactured objection costs more than a missed one** — it teaches the reader
to skim, and the next genuine finding gets skimmed too.

## The decision under review

State it as one explicit sentence, taken from the design at hand. If none has
been stated, ask for it before going further.

That sentence fixes what "verify" applies to. It does not fence off what you
may read — the surrounding design, the code, and the repo are all fair game,
and usually necessary.

## 1. List what it rests on

One list. Every statement the decision needs to be true, whether or not the
author said it out loud. Stable IDs (D1, D2, …) carried through the whole pass.

Tag each: **[V]** settleable by evidence · **[J]** a value trade-off ·
**[C]** a fixed limit.

Mark each **load-bearing** or not — load-bearing means the decision's own
sentence fails if this is false. A statement the surrounding *reasoning* leans
on can break without the decision breaking; that is an additive finding, not a
contradiction, and the verdict table below is what resolves it.

Extract as many as the decision actually contains. **There is no minimum.** A
decision resting on three things rests on three things; say so rather than
inventing a fourth. If two entries describe the same mechanism from different
angles, record it once and note that you merged them.

Merging keeps the *list* clean; it does not bury the finding. When one of the
merged angles is a sentence the author actually wrote, quote that sentence in the
opening — their own false premise is the most persuasive thing you can hand back.

## 2. Verify

For each [V] item: ask what would have to be true for it to be false, then
answer that.

**Settle it by running something whenever you can.** Execute the code, check
the file, compute the number, list the bucket. Quote the command and its real
output. A one-line result is stronger than a paragraph of reasoning and cannot
be motivated by what you hope to find.

**Reproduce the evidence the author cited.** When the reasoning leans on
something — the tests pass, coverage is 100%, the benchmark shows X — rebuild
that and find what it fails to constrain. Breaking the author's own stated
grounds for confidence is stronger than attacking the mechanism, because it is
unarguable and it addresses the reason they actually believe the decision.

Where you cannot execute, reason it through — but never by assuming the
decision is right, or wrong, and working backward to suit.

Mark each **HOLDS** · **BREAKS** · **UNSETTLED**. A HOLDS that carries weight is
a result — it is usually the best material for the case *for* the decision, so
carry it into the challenge rather than discarding it. Only something true that
changes nothing either way goes in a single closing line ("also checked, no
bearing: …").

Where a statement is about what someone else will do next — a producer, a
consumer, a team — it is UNSETTLED unless you can bound it. Quantify the exposure
if you can and say what you bounded; do not promote a guess to BREAKS.

[J] and [C] items are not verified. Carry them into the challenge; a value
trade-off is argued with, not checked. A constraint may hold at one granularity
and be negotiable at another — "we cannot import that package" can be true of
the package and false of the one function you need from it. Say which.

## 3. Challenge

**Every objection names the concrete input that triggers it** — the specific
value, config, sequence, or event. No trigger, no objection: drop it silently.
This is the rule that keeps the report worth reading.

Tag each trigger:

- **OBSERVED** — it exists in the system now. Cite it: the folder, the row, the
  config line. Go and look; do not assume.
- **CONSTRUCTIBLE** — a valid input that has not occurred. Add one sentence on
  what would have to happen for it to occur.

That sentence decides the severity, not the tag: is this a path the system will
plausibly take, or one that needs someone to act against their own interest?
Write it in the item so the ranking is auditable instead of a matter of tone.

Do not reach for the phrasing of an example to inherit its severity — say what
would actually have to happen here, in this system, and let a reader disagree
with it.

Build the strongest case against the decision, drawing on whatever BREAKS or is
UNSETTLED. Then build the strongest case *for* it. An argument whose other side
you cannot state is advocacy, not critique.

Then question the problem rather than the solution: is this the real problem or
a symptom of one, and is there a simpler statement of it? Answer where you have
something. A heading with nothing under it is padding — leave it out.

## 4. Verdict

Label every BREAKS item by what the fix does to the decision *sentence*:

- **blocking** — the sentence itself has to change.
- **additive** — the sentence stands and you put a guard around it.
- **adjacent** — a real defect the sentence neither causes nor fixes. Report it
  in its own short section and keep it out of the verdict. Do not file it as
  additive to give it somewhere to live.

Apply that test rather than asking whether a fix is technically an addition;
almost any defect is "additively" fixable if a preprocessing step is allowed.

| Verdict | When |
|---|---|
| **Escalate** | A blocking item touches safety, security, or compliance; or a load-bearing item is UNSETTLED and cannot be cheaply settled; or the problem itself is misdiagnosed |
| **Revise** | A blocking item whose trigger is credible on the account you wrote for it |
| **Stand** | No blocking items — or the only blocking item's trigger needs someone to act against their own interest, in which case say so and file it as a follow-up |

The severity sentence has to be able to change the verdict, or it is decoration.
A blocking item with an implausible trigger does not force Revise.

"Stand" with additive findings is the common, healthy outcome for a sound
decision. Reaching for Revise to look rigorous is the failure this skill exists
to prevent, in the same way sycophancy is.

## Output

Open in the first ten lines, so a reader who stops there still has the finding:

- **Revise or Escalate** — the verdict, the single strongest falsifier, and the
  strongest premise that survived. A Revise that does not say what held up is
  advocacy; state it in one line even when the news is bad.
- **Stand** — the verdict, the strongest premise that *survived*, and the
  evidence that survived it. Then the falsifier you went looking for and did not
  find. Do not open a Stand with a hypothetical break and walk it back.

Then:

1. **Blocking and additive items**, each with its trigger and its
   OBSERVED/CONSTRUCTIBLE tag.
2. **One next action per distinct fix.** Two unrelated fixes get two actions.
3. **Per-item verification, as an appendix** — but **evidence that changed the
   verdict belongs in the body**, next to the item it settles. The appendix is
   for checks that confirm what the body already claims.

Scale the report to the decision. A one-screen decision gets a three-row table
and a three-line appendix. Structure that outweighs the finding is the same
mistake as an objection with no trigger.

## Common mistakes

| Mistake | Fix |
|---|---|
| An objection with no triggering input | Drop it. It is padding wearing a critique's clothes |
| A CONSTRUCTIBLE trigger with no account of how it would arise | Add the sentence. That sentence is what justifies the severity |
| Filling a category because it looked thin | There are no minimums. An empty class is a finding: say the decision weighs nothing |
| Reasoning about behaviour you could have executed | Run it and quote the output |
| Taking the author's "tests pass, 100% coverage" at face value | Rebuild it and find what it fails to constrain |
| The same mechanism recorded twice under two labels | Merge, and say you merged |
| Resting the verdict on whether a claim was "core" | Blocking vs additive, by whether the decision sentence must change |
| Only building the case against | Steel-man both sides, or you are advocating |
| Opening a Stand with a break you then walk back | Lead with what survived and the evidence for it |
| Burying the verdict-changing evidence in the appendix | It goes in the body, beside the item it settles |
