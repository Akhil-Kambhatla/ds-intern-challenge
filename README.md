# SignalDesk weekly check

## The problem

The SignalDesk team changed a prompt on 2026-08-04 and a review policy on
2026-08-07. They have one week of usage data, 41 rows across seven days, and want
to know whether anything improved.

The export makes that hard. Some rows are not real runs. Some columns look like
quality signals but measure something else. And the prompt change landed three
days into a seven day window.

## Why it matters

Model confidence rose after the prompt change. On its own that reads as evidence
the change worked, and it is the sort of number that ends up in a summary for
leadership. Acting on it means rolling out a change that has not been shown to do
anything.

There is a smaller repeating cost too. Someone has to look at this export every
week and decide by eye which rows to ignore and which numbers to believe. Those
decisions come out differently each time and the reasoning is not written down.

## The approach

A command line script that uses simple arithmetic and basic statistics to surface
what the raw table hides, and to make the same judgment the same way every week.

Arithmetic finds problems that reading cannot. One row this week has 8 accepted
outputs plus 12 flagged out of 17 completed runs, which is impossible, and that
identifies it as broken without anyone knowing what happened that day.

Statistics answers a question the raw numbers cannot. Acceptance for Lead summary
rose 1.3 points after the change. Whether that means anything depends on how many
runs it came from, and that is a calculation rather than an opinion.

Each rule in the script replaces a judgment someone would otherwise make from
memory:

| Judgment made by eye each week | What the script does instead |
|---|---|
| "This row looks wrong, I will drop it" | Nine fixed checks, each printing the row and the reason |
| "Confidence looks reasonable" | Tests whether confidence agrees with acceptance, overall and inside each group |
| "That looks like an improvement" | Compares the change against how much that rate moves on its own |
| "Quality needs work" | Estimates how many more accepted outputs each possible fix would add |

## What it prints

The default run is a short summary aimed at someone with two minutes:

```
SIGNALDESK WEEKLY CHECK          2026-08-01 to 2026-08-07          38 of 41 rows used

VERDICT
  The change on 2026-08-04 cannot be called either way: all 3 workflows moved less than their own
  margin of error.
  Do not report the median_confidence rise as evidence the change worked: it disagrees with
  acceptance in 3 of 6 groups and tracks traffic, not quality.

DID THE PROMPT CHANGE WORK
  workflow              acceptance             change    margin    readable
  Lead summary          77.3% -> 78.6%         +1.3pt     8.7pt          no
  Reply draft           76.8% -> 77.0%         +0.2pt     8.4pt          no
  Feedback clustering   66.7% -> 65.6%         -1.1pt    16.9pt          no
  Clean days per period needed at a 3.0 point minimum effect: 63, 45, 172, in the row order above.
  This export holds 3 days before 2026-08-04 and 4 after.

WHICH NUMBERS TO USE
  use            accepted_output, completed
  use with care  flagged_for_review, its direction is unclear on the rows tied to a known event
  do not use     avg_minutes_saved, user_rating, median_confidence

BIGGEST OPPORTUNITY, AND IT IS NOT THE PROMPT
  Feedback clustering / csv upload completes 64.4% of sessions: about 53 a week end with nothing.
  Acceptance on completed runs reads 67.7% and hides them. On sessions started it is 43.6%.
  Lifting completion to the best rate in the product adds about 20 accepted outputs a week.

EXPORT PROBLEMS TO RAISE WITH THE DATA OWNER
  2026-08-05  Lead summary / email              the same row was exported twice
  2026-08-05  Lead summary / email              the same row was exported twice
  2026-08-07  Reply draft / queue               accepted plus flagged exceed completed runs
  4 more issues flagged and kept: team 'product' on 2026-08-02; median_confidence holds 'n/a' on
  2026-08-05; user_rating empty on 2026-08-01; 2026-08-07 has 4 of 6 rows.

DO THIS WEEK
  1. Ask the export owner to account for the 3 dropped rows, starting with the one where the same
  row was exported twice.
  2. Do not report the +1.3 point move on Lead summary as a result. Re-run once 63 days of clean
  post-change data exist.
  3. Before any median_confidence threshold reaches routing, hand check a sample of high confidence
  rejected outputs.
  4. Instrument session start to completion for Feedback clustering / csv upload, where about 53
  sessions a week end with nothing.

  Run with --detail for the checks, correlations and full health summary behind this.
```

`--detail` prints that same summary followed by the working behind it: the nine
data checks with every row they caught, the metric ranking with its correlations,
the health summary split by source, and the target calculations.

## How to read it

Three things carry most of the meaning.

**Rows used.** 38 of 41 this week. Rows are dropped for stated reasons, never
because they look odd.

**Margin.** Every rate moves around on its own depending on how many runs it came
from. The margin is the size of that movement. A change smaller than the margin
cannot be separated from nothing having happened.

**The two acceptance rates.** Acceptance on finished runs asks whether an output
was good. Acceptance on all runs asks whether a user who started got something
usable. A large gap means runs are failing before they produce anything and the
first number is hiding it.

## What this week's data shows

**Confidence does not track quality here.** Across all rows, confidence and
acceptance move together at 0.71. Split by workflow and source, the relationship
reverses in three of six groups. Automated sources carry both higher confidence
and higher acceptance, so the combined figure reflects the source rather than the
model. Confidence also moves with daily volume at 0.84 and rises on every day of
the week.

**The prompt change cannot be evaluated with this data.** All three workflows
moved less than their own margin. Holding the source mix fixed changes the
picture by about a tenth of a point, so mix was not concealing an effect.

**Minutes saved barely varies.** It moves 2 to 6 percent within each group across
the whole week, which suggests a value assigned per workflow rather than measured.

**A third of Feedback clustering runs end without an output.** Completion via csv
upload is 64.4 percent. Acceptance on finished runs is 67.7 percent and looks
normal. On all runs started it is 43.6 percent.

**Reply draft flags rose before either change.** The flag rate goes from 12.5 to
16.2 percent over six days, ending before the review policy changed. Nothing in
the export explains it.

## Choices made, and why

| Choice | Reason |
|---|---|
| Both acceptance denominators reported | They answer different questions, and the gap between them is itself a finding |
| A duplicate group is dropped entirely | Nothing identifies which copy is the real run, so keeping either would be a guess |
| Notes read last, as a backstop | The arithmetic checks keep working when next week's notes are worded differently |
| Dropped rows reused in one place | A row tied to a known event says something about what a metric means, though nothing about how the product performed. It is excluded from every rate |
| Spike thresholds at 2x and 3x | Chosen, not derived. This week's demo row sits at 2.7x and is dropped by the duplicate check instead |
| Metrics grouped into three tiers, not ranked one to six | The gaps between neighbouring ranks are smaller than the scoring can distinguish |
| No imputation or resampling | Two values are missing out of 41 rows. Filling them cannot change any rate and would remove the record that they were missing |

## Problems found in the export

| Where | What is wrong |
|---|---|
| 2026-08-05, Lead summary, email | The same row appears twice, at 140 sessions against a normal day near 55. One copy is noted as demo traffic |
| 2026-08-07, Reply draft, queue | 8 accepted plus 12 flagged out of 17 completed. The note says the policy changed mid-day |
| 2026-08-07 | Four rows instead of six |
| 2026-08-02 | `product` in lowercase where every other row has `Product` |
| 2026-08-05 | `median_confidence` holds the text `n/a` |
| 2026-08-01 | One `user_rating` is empty |

## What to do next

1. Split `flagged_for_review` into flags raised by a person and flags raised by
   policy. Once a policy has changed, no analysis separates them after the fact.
   This needs a schema change before the next export.
2. Instrument what happens between session start and completion, starting with
   Feedback clustering via csv upload.
3. Establish where `avg_minutes_saved` comes from. If it is assigned per workflow
   it should not be presented as a measurement.
4. Look into the Reply draft flag increase using the days before the policy
   change, while that comparison still holds.
5. Add run and user identifiers to the export, so sessions can be told apart from
   users and retries become visible.

## Run it

```
pip install -r requirements.txt
python3 weekly_check.py
python3 weekly_check.py --detail
```

| Option | Default | Effect |
|---|---|---|
| `--detail` | off | Prints the working behind the summary |
| `--data` | `sample-data/product_usage_events.csv` | Reads a different export |
| `--change-date` | `2026-08-04` | Splits before and after at a different date |
| `--min-effect` | `3.0` | Sets how many points of improvement would be worth acting on |

Output is plain text on stdout. Nothing is written to disk and the input file is
not modified.

## Terms used above

| Term | Meaning |
|---|---|
| Margin | How much a rate moves on its own, given the number of runs behind it. A change inside the margin cannot be told apart from no change |
| Rank correlation | Rank the rows by two columns and see whether the orders agree. +1 is identical, 0 is unrelated, -1 is reversed |
| Overall against within group | Whether a pattern holds when all rows are combined, and whether it still holds inside each group. When the two disagree, the combined figure is usually reflecting the grouping |
| Source mix held fixed | Recomputing both periods as though the split between automated and manual traffic had not moved, so that shift cannot be mistaken for the prompt working |

## Scope

The data is `sample-data/product_usage_events.csv`, provided with the challenge.
No dashboard, no model, no stored state. Runs in about a second on pandas, numpy
and scipy.
