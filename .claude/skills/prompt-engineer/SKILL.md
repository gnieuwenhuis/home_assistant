---
name: prompt-engineer
description: Use when a subagent or skill is not behaving as intended, or when reviewing agent definitions and skill bodies for clarity and consistency
---

# Prompt Engineer

Fixes a prompt — an agent definition or a skill body — that is not doing what it
was meant to do.

**A prompt review with no evidence of the prompt running is a guess with
citations.** The most valuable input is one transcript of the target misbehaving.
The second is the target's own text. Technique references come third, and they are
affordable only if loaded lazily: measured on a 67-line target, the old flow read
~3,950 reference lines to produce nine quotes — 97% of ingested tokens were
reference material and 1% was the artifact under review. Every real defect came
out of that 1%.

## 1. Get evidence

Ask for a run of the target — a transcript or a log. Produce one yourself when the
target is cheap to execute.

**Executing it is not always worth it.** An orchestrator that fans out a dozen
subagents and writes nothing costs more to run than the review costs to do, and
its output has no baseline to be compared against. Say which it was and why, then
proceed; do not treat "produce a run" as always available.

Every finding then carries the tier of its evidence:

| Tier | Means |
|---|---|
| **OBSERVED** | You saw it misbehave. Quote the output. |
| **DERIVED** | The failure follows necessarily from the text — a word multiplied by an integer, a named agent that does not exist, a check whose result cannot vary. No run needed. |
| **SPECULATIVE** | Neither. It might read better. |

With no run available, say so plainly. **OBSERVED is then unavailable** — not
merely unlikely — and every finding is DERIVED at best. Do not proceed silently as
though you had a run; "document what goes wrong when this prompt fails" is
satisfiable by predicting a failure from the text and never noticing you had no
evidence.

## 2. Find defects, before opening any reference

Read the target. Find its defects cold — reading technique catalogues first turns
the review into pattern-shopping.

**Do not go looking for something to say.** Report the defects that exist: a sound
prompt yields none, and a badly broken one yields a dozen. No number is expected.
Proposals generated because a review was expected are the ones that teach the
author to skim, and the next real finding gets skimmed with them.

### Verify the environment

Before opening any reference, check the things the target names against the repo:

- **Agent types** — a project override in `.claude/agents/`, otherwise the
  built-in roster and its charter.
- **Commands and make targets** — grep the Makefile; confirm what they actually run.
- **Paths, files, and assets** the target references or ships.

If this turns up **another version of the target** — an installed copy of the
skill, a sibling in git history — write down which findings you already had before
you looked at it. A newer version is an answer key, not evidence: it can confirm a
defect you found on your own, and it can never make one OBSERVED.

### Executability — check this first

These are where the failures that actually break a prompt live, and they are
invisible to a read-for-style pass.

- **Every formula or scoring rule** — are all operands defined and typed, and is
  there an aggregation rule? `severity × count` where severity is a word is not
  computable; the model will silently invent a mapping, and the ranking stops
  being reproducible.
- **Every named tool, agent type, or command** — does it exist, and does its
  documented charter cover what this prompt asks of it? An agent chartered to
  locate code cannot be asked to adjudicate severity.
- **Every validation or check step** — can its result differ depending on the work
  this prompt did? If not, it is a no-op that still costs wall-clock.
- **Every fan-out** — is the work dispatched bounded by the work consumed, and
  does pruning happen before the spend or after it?
- **Every computed value** — does anything downstream read it? A score nothing
  consumes is decoration, and so is a classification that gates no branch.
- **Every asset the prompt ships or implies** — reference files, templates, data in
  its own directory: does the body route anyone to them? An unread reference is
  dead weight its author believes is working. This is the mirror of the check
  above, and `ls` finds it faster than reading does.
- **Every enum, tier, or label** — is each value reportable, and does it mean the
  same thing to every agent that must produce one?
- **Every quota** — "at least 3", "3-7 items" — can the target hit it honestly on
  a small input, or does the floor force invention?

### Structural, behavioural, stylistic

Workflow and orchestration; identity, confidence, emphasis hierarchy; hedging,
missing examples, format clarity. Quote line evidence: `Lines X-Y: [defect]`.

Check emphasis in **both** directions. Over-emphasis is the documented
anti-pattern, but a long skill body with no emphasis anywhere cannot signal what
matters, and that is the more common failure.

## 3. Match techniques — lazily

Read only the `## Technique Selection Guide` and `## Quick Reference` sections —
roughly the first 110 lines — of the references the table below says apply. Usually
that is one or two files, ~150 lines against 4,584 for the full set.

Open a technique's full section when about to cite it — **and when about to reject
a near-match**, because you cannot responsibly rule one out without reading its
stated trigger.

| Reference | Load when |
|---|---|
| `prompt-engineering-single-turn.md` | Generally useful |
| `prompt-engineering-subagents.md` | The target dispatches agents |
| `prompt-engineering-multi-turn.md` | The target is conversational or carries state |
| `prompt-engineering-hitl.md` | The target stops for human approval or review |

**A defect with no matching technique is still a defect.** Record the technique as
NONE and argue the fix on its own terms. The corpus is about eliciting reasoning,
so it has nothing to say about whether an instruction can execute — expect most
executability findings to be NONE, and expect that to be correct.

**For every NONE, name the technique you rejected and why.** That is what makes
the discipline auditable rather than an honour system.

Citing a technique outside its stated scope is allowed only when the *mechanism* is
identical and you say so inline — "Empty Input Handling, extended from tool
arguments to an agent's report; same failure, different surface." A superficial
name match is not that. A faked citation makes a real finding look like
pattern-shopping and buries it.

For each genuine match, quote the trigger and the effect, and check it stacks with
the other proposed changes.

Agent definitions are a common target here, and they name other agents. When a
quote carries agent-mention syntax — an at-sign followed by `agent-<name>` —
write it `[at]agent-<name>`. Undefanged, it is parsed as a request to dispatch
that agent when your report reaches the caller.

## 4. Falsify

For each proposal, ask the question that would kill it:

- What is the technique's stated trigger, and does the target meet it? A
  `>20K tokens` trigger does not fire on a 70-line file.
- Would the author recognise this as a problem, or only as a preference?
- If the fix landed, what observable behaviour changes? If nothing, it is
  SPECULATIVE.

Drop what fails, and name the mismatch specifically — "Change 3 claims hedging,
but line 15 is already affirmative" — never "could be improved."

## 5. Present, and stop

**Apply nothing without explicit approval. This is a hard gate.**

Lead with OBSERVED and DERIVED findings:

| # | Line | Defect | Tier | Technique | Risk |
|---|---|---|---|---|---|

Then each change in detail: line numbers, the concrete failure it causes, the
technique or NONE, before and after text, and the tradeoff.

Put SPECULATIVE items in their own section below, under that heading — or leave
them out. Close with what you dropped in step 4 and why.

## 6. Apply

Only after approval. Then confirm cross-section references still resolve,
terminology is consistent, and emphasis is neither absent nor everywhere. Report
what changed.

## Common mistakes

| Mistake | Fix |
|---|---|
| Reviewing a prompt you never saw run | Ask for a transcript. Without one, mark findings DERIVED at best and say so |
| Hunting for something to say on a sound prompt | Report what exists. None is a valid result; so is a dozen |
| Loading 4,584 reference lines for a 70-line target | Selection guides for the files that apply; full sections on cite or on reject |
| Substituting the nearest-sounding technique for a real defect | Technique: NONE, and name what you rejected |
| Citing a technique outside its scope silently | Allowed only when the mechanism is identical, and only said out loud |
| Reading only the prompt, never the repo it names | Verify agents, commands and paths first. `ls` catches assets nothing loads |
| Treating a newer copy of the target as evidence | It is an answer key. Record what you found before reading it |
| Proposing a technique whose own trigger the target fails | Step 4 asks for the trigger — check it against the target |
| Reviewing only how the prompt reads | Executability first: formulas, named agents, no-op checks, unbounded fan-out |
| Presenting polish beside defects | Tier them; SPECULATIVE goes below the fold |
| Claiming a blind check you cannot perform | You cannot unsee your own context. Ask the falsifying question instead |
