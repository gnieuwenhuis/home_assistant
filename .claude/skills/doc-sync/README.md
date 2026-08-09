# Doc Sync

Why this skill is shaped the way it is.

## The paradigm it used to serve

doc-sync was imported from a configuration built around a different idea: a
CLAUDE.md in every directory, each one a tabular navigation index with "What"
and "When to read" columns, so an LLM could traverse the tree without loading
it. README.md was defined as the complement — invisible knowledge only.

This repository does not work that way and does not want to. Run against
`src/`, `dags/`, and `conf/`, the old skill created **31 CLAUDE.md files**. That
is 31 files auto-injected into context whenever anything beneath them is read,
to replace what `Glob` and `Grep` already do for free.

The skill now forbids that outright. One CLAUDE.md, at the root, as a project
instruction file.

## Why "invisible knowledge only" was dropped as a universal rule

The old convention said: for each sentence, ask whether a developer could learn
it by reading the source; if yes, delete it. Applied to this repo's eight
READMEs, that rule removes roughly 85% of the root operator manual, 90% of
`pipelines/inference/README.md`, and 85% of `docs/contributor_bucket_access/`.
It deletes the Airflow test sequence — where every individual command is in a
Makefile but the ordering is not — and the output-schema table that downstream
consumers read instead of the node implementation.

The rule is sound for a design doc under `src/`. It is wrong for an operator
manual. Genre now follows depth, which is what the repo actually does.

## What replaced coverage as the driver

The old skill was driven by a coverage target: every directory gets an index.
The new one is driven by **boundaries** — a README exists where a different
tool, runtime, or audience begins. Empirically that predicts where READMEs
actually live here better than "invisible knowledge is present" does, and it
makes absence the default rather than a gap to be filled.

The dominant real failure is not missing docs. It is rot: line-number citations
that are all now wrong, node names for nodes that no longer exist, and
documented commands that fail because they predate per-source pipeline
registration. The skill hunts those.

## The fabrication problem, measured

A second pass measured what the skill causes an agent to *write*, by having it
document two directories and then grade every factual claim it produced.

Mechanism claims — what the code does — verified at **78%**. Reason claims — why
it is that way — verified at **15%**, and once claims verified only as "a
docstring says this" were stripped out, at **2 of 13**.

The cause was structural, not carelessness. The skill required a rejected
alternative in every `src/` design doc, stated in the same breath that such
content "is the part no reader can recover from the code", listed inventing it as
the top mistake — and never named a source. Under a timebox that is a machine for
producing plausible fiction. One claim, "which every caller (Makefile, DAG,
ad-hoc run) had to compute identically", the reviewer described as "effectively
invented"; it existed because the template demanded a rejected alternative and
nothing told it where to get one.

The fix is the sourcing ladder — ADRs, `git log -S`, the PR, an attributed
docstring, or ask — plus explicit permission to record that no rationale exists.
Re-measured, the reviewer invented nothing: it ran `git log -S` across three
classes, read ADR-004 in full, wrote "there is no rejected alternative on record"
twice, and added a negative citation warning that ADR-004's filename looks like
the rationale for the credential chain but its contents are not.

## Two smaller failures the same measurement exposed

**Unverified connectives.** Sentences whose halves are both true, joined by a
"because" / "so that" / "instead" asserting a link nobody established. One
reviewer's summary: "the fabrication is entirely in the connective", and it "reads
as the most insightful part of the document." Every causal connective is now
itself a claim to be checked.

**Scope words.** Every fabrication observed reached past the file the author had
open — "the only place", "no other caller", "written by X instead". The first
version of the rule listed noun phrases, and a reviewer then shipped three
adverbial ones, noting they "read as hedges rather than scope claims while
writing." The rule now names the small words: `only`, `never`, `all`, `instead`.

## Division of labor

Split by scope, not by problem type. An earlier draft split it as "is the
statement true?" (incoherence) versus "should the file exist?" (doc-sync);
testing showed that boundary is unworkable, because most README rot — a node
name that no longer resolves, a command that fails — is a factual claim. An
agent auditing a README would have had to defer the majority of what it found.

doc-sync owns READMEs and the root CLAUDE.md, and every defect in them.
`incoherence` sweeps everything else and resolves interactively.

## Example usage

```
Use your doc-sync skill to audit documentation across this repository
Use your doc-sync skill on src/places_signals/pipelines/
```
