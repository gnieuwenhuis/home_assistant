# Prompt Engineer

Why this skill is shaped the way it is. The workflow lives in `SKILL.md`.

Prompts are code. They have bugs, edge cases, and failure modes — and unlike code,
nothing compiles them, so a formula that multiplies a word by an integer ships and
runs and quietly invents its own answer.

## The failure the old version documented and accepted

Its README said:

> "When you tell an LLM 'find problems and opportunities for optimization', it will
> find problems. That is what you asked it to do. Some may not be real issues. I
> recommend invoking the skill multiple times."

That diagnosis was correct and the remedy was not. Repeated invocation re-runs the
same instruction against the same text and produces the same class of noise;
nothing accumulates and nothing is falsified. Worse, a technique-shaped proposal
that recurs on three runs looks like consensus when it is only a stable
instruction — it launders systematic bias into apparent agreement.

The noise also was not inherent to asking a model to find problems. It was ordered.
One line did most of it:

> "Scan proactively even where Assess found nothing: no examples suggests
> Contrastive Examples or Few-Shot; a task needing reasoning suggests Plan-and-Solve
> or RE2; a long prompt suggests Document Positioning."

Measured, that line generated four proposals and zero survivors. The reviewer's
verdict on defending them to the target's author: *"No — not one."* Document
Positioning has a stated trigger of >20K tokens and was being proposed against a
67-line file. Plan-and-Solve was being proposed against a document that already is
a numbered plan. The Refine step then killed all four — so one instruction
manufactured noise, another filtered it, and both were paid for.

## What measurement changed

Two runs over the same 67-line target, one per version.

**Reference loading was the largest single cost, and almost pure waste.** The old
flow read ~3,950 lines of reference to produce **nine quoted lines**: 97% of
ingested tokens were reference material and about 1% was the artifact under review.
`prompt-engineering-multi-turn.md` — 1,177 lines, mandatory whenever any structural
finding existed — yielded zero citations. Every real defect came out of the 1%.
Loading only the `Technique Selection Guide` and `Quick Reference` heads, and
opening a full section only on cite or on reject, brought that to **297 of 4,584
lines (6.5%)** with a better result.

**Nothing required evidence that the prompt had ever run.** The closest instruction
was "document what goes wrong when this prompt fails" — and *document* is satisfied
by predicting a failure from the text. The reviewer's summary: *"I gathered zero
behavioral evidence. Nothing in the skill required me to, and nothing in it would
have caught that I hadn't. The entire skill is a closed loop over two text
artifacts."* Findings now carry an evidence tier, and OBSERVED is unavailable
without a run.

**The format presupposed a technique for every defect.** "For each opportunity:
find the matching technique, quote its trigger condition" has no exit. The most
important finding in the baseline run — a scoring formula that cannot be computed —
had no match anywhere in 3,950 lines, because the corpus is about eliciting
reasoning rather than about whether an instruction can execute. That left two
options: fake a citation, or break the format. The reviewer broke the format and
said so; a less scrupulous run fakes it, and the faked citation makes a real defect
look like technique-shopping. `NONE` is now a first-class answer, and 7 of 11
findings in the reworked run used it.

**The skill had no lens for the defects that matter.** Its levels were Structural,
Behavioural, Stylistic; its anti-pattern audit was three fixed stylistic patterns.
A prompt could pass every check it performs while containing an uncomputable
formula, an agent asked to do what its charter excludes, and a four-minute
validation step whose result cannot vary. The executability pass exists for that
class, and in testing **all seven of its checks fired** on a single 66-line target.

## What testing the rework found

Six defects were measured empirically in the target before either run. The reworked
version found **all six**, plus five more — including 546 lines of detection
thresholds shipped in a `references/` directory that the skill body never tells
anyone to read. That one came from `ls`, not from the checklist, so the checklist
gained an eighth item: an asset nothing loads is the mirror of a value nothing
consumes.

Three smaller corrections came out of the same run. "Open a section only when about
to cite it" made responsibly *rejecting* a near-match unlicensed. "A prompt with
three defects has three" anchored a number and made a reviewer second-guess a
correct list of ten. And the skill demanded charter checks on named agents while
never saying where charters live — or what to do on finding a newer copy of the
target in the same repo, which is an answer key rather than evidence.

## A note on testing this skill

The first baseline run of this skill was invalid, and the reviewer caught it rather
than the author: the six ground-truth defects had been listed in its own task
prompt, so its "blind" pass was not blind to the answer key. It refused to claim
the 6/6. Score a prompt reviewer by handing it the target and nothing else.

## Usage

```
Use your prompt engineer skill on .claude/agents/developer.md
Use your prompt engineer skill on .claude/skills/refactor/SKILL.md
```

Bring a transcript of the thing misbehaving if you have one. It is worth more than
everything else the skill reads.
