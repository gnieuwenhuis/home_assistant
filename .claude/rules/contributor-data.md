# Contributor Data

Per-contributor signal volumes never enter this repository or anything published
from it. That covers inline comments, docstrings, documentation, commit messages,
PR titles and descriptions, PR and issue comments, and test fixtures.

The repository is public and the contributor agreements are not. A figure that
lets a reader derive how much data a *named* contributor supplies is a disclosure,
whatever file it sits in. Aggregate totals across contributors are not, and are
the right way to say something quantitative here.

## The line: attribution, not counting

**A volume attached to a named contributor is a disclosure. A volume aggregated
across contributors is not.** Totals are how you say something quantitative here.

Not allowed — anything a reader can invert into one contributor's volume:

- Signal or record counts for a source, per run or in total
- Places covered by a source, as a count or as a share of the release
- Score distributions, band counts, or histograms per source
- Ground-truth or label-corpus sizes per source
- Published or suppressed row counts attributable to one source
- Two figures that divide into any of the above

A ratio is still a count when the denominator is knowable. "Source X covers a
quarter of what source Y does" discloses X once Y is known from elsewhere.

## What is fine

- **Aggregate counts across contributors** — total signals ingested, total places
  covered, total rows published or suppressed in a run. Say the total, not the split.
- Thresholds, cost ratios, and other configured values
- Model metrics that carry no volume: AUC, a calibration slope
- Row counts in test fixtures that are invented, not measured
- Statements of shape and direction: "the majority of what this publishes is
  unverifiable", "coverage is the binding constraint"
- Anything about the pipeline's behaviour that does not quantify one contributor

### Two ways an aggregate stops being one

**Subtraction.** A total plus all-but-one of its parts discloses the part left out.
Three per-source figures and a total is four disclosures, not three permitted ones.
The same applies across documents and across time — a total here and a breakdown in
last month's report still subtract.

**A sole contributor.** When one contributor supplies effectively all of a metric,
its "aggregate" is that contributor's number wearing a disguise. Closure signal is
the live example: a pipeline-wide closure count is, in practice, one source's count.
Before publishing a total, ask whether the set it sums over is genuinely plural for
*that* metric — not just plural in the pipeline.

## How to say it instead

Where a total is honest, give the total:

> The run ingested 1,234,567 signals across all contributors. *(invented figure —
> a real one is fine here, since ingestion volume is genuinely plural.)*

Where it is not — because the metric has a sole contributor, or the split is the
point — state the shape and say where the numbers live:

> Selection discards a large share of all closure calls, and the rate swings
> substantially by run. Figures are in the local spec.

Keep the measured values in a spec under `docs/superpowers/specs/`, which is
gitignored, and say so where a reader would otherwise go looking. Reviewers who
need the numbers can ask.

## The hook is a backstop, not the standard

`.claude/hooks/check_contributor_figures.py` blocks a write, and denies a `gh` or
`git commit` invocation, when it sees a contributor name and a volume-shaped
number close together. Its calculus is the inverse of the comment hook's: a missed
match publishes contributor data, so it is deliberately broad and will sometimes
flag a threshold or a sample size. Dismiss a genuine false positive in one line
and carry on.

Its rule of thumb is the same as yours: a number beside a contributor name. So a
figure with no contributor named passes — which for an aggregate is the right answer,
not a gap.

What it cannot see, where the judgment above is what governs:

- A per-source figure whose contributor name is on another line. A table with source
  names in a header row and counts in the rows below is exactly this.
- The subtraction case. A total and its parts each pass alone.
- The sole-contributor case. An un-attributed total looks like an aggregate to a
  regex, and the hook does not know which metrics are genuinely plural.
- A volume spelled out in words. "Roughly a tenth of the release" carries no digits.

Where the hook is silent, the rule still holds.
