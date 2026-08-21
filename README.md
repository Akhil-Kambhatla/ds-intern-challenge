# SignalDesk weekly check

A command line script that reads one week of SignalDesk usage data and tells you
which numbers in it you should not trust, before you use them to make a call.

## Who this is for

The product teammate who owns SignalDesk and has to decide whether the prompt
change on 2026-08-04 worked. It is meant to be run once a week against a fresh
export.

## Run it
pip install -r requirements.txt
python3 weekly_check.py

Options:
python3 weekly_check.py --data sample-data/product_usage_events.csv
python3 weekly_check.py --change-date 2026-08-04
python3 weekly_check.py --min-effect 3.0

Output is plain text on stdout. Nothing is written to disk and the input file is
never modified.

## Data

`sample-data/product_usage_events.csv`, provided with the challenge. 41 rows
covering 2026-08-01 to 2026-08-07. One row is one day, one team, one workflow,
one source, across three workflows with two sources each.

## What it prints

1. **Data trust report.** Nine checks. Five quarantine a row and exclude it from
   everything downstream. Four flag a row and keep it. The arithmetic and
   structure checks run first and stand alone, so they still work next week when
   the notes column is worded differently. The keyword scan of the notes is a
   backstop and the output says so.
2. **Metric trust ranking.** Six metrics scored on completeness, provenance,
   direction clarity, agreement with an independent signal, and whether they move
   at all. The ranking is computed rather than written in, and the evidence
   behind it is printed underneath.
3. **Weekly health summary.** Every rate shown split by source, never pooled on
   its own, with both acceptance denominators side by side.
4. **Targets.** A mix adjusted before and after comparison, how big a change
   would have to be before this volume of data could see it, which field has the
   most room to move, and a pre-registered threshold per workflow.

## What it found

**Model confidence is the metric to trust least.** Across all clean rows, confidence
and acceptance agree strongly, with a Spearman correlation of 0.71. Split the
rows by workflow and source and the relationship reverses in three of the six
groups. Automated sources carry both higher confidence and higher acceptance, so
the pooled figure is measuring the source, not the model. Confidence also rises
with session volume at 0.84, and rises monotonically across the week in nearly
every group, which means it is tracking the calendar.

**The prompt change cannot be called yet.** Acceptance moved 1.3 points for Lead
summary, 0.2 for Reply draft, and down 1.1 for Feedback clustering. Every one of
those sits inside its own noise band of 8.7, 8.4 and 16.9 points. Adjusting for
source mix moves the picture by a tenth of a point. At a three point minimum
effect, confirming a change would need roughly 63, 45 and 172 days of clean data
per period at current volume. The team gave it three days before and four after.

**Minutes saved is closer to an assumption than a measurement.** Within each
workflow and source, its coefficient of variation is between 0.02 and 0.06. It
barely moves. Anything that multiplies by it is really just re-ranking by volume.

**A third of Feedback clustering runs never produce an output.** Completion for
csv upload is 64.4%. Acceptance measured against completed runs reads 67.7%,
which looks close to the other workflows. Measured against runs started it is
43.6%. Same data, different question, and the usual denominator hides the failures.

**Reply draft flags were climbing before the policy change.** The flag rate per
completed output runs 12.5%, 13.1%, 14.1% across the three days before the new
prompt, and reaches 16.2% by 08-06, all of it before the review policy changed on
08-07. Nothing in the packet explains it.

## Assumptions and judgment calls

- **Acceptance denominator.** Both are printed. Acceptance over completed runs
  answers whether a finished output was good. Acceptance over sessions answers
  whether a user who started got something usable. The second is the better
  product health number and the script says why.
- **Sessions is excluded from the metric ranking**, because it is the exposure
  denominator rather than an outcome.
- **Quarantined rows are used in one place only.** They are excluded from every
  rate, and retained for scoring how clearly a metric can be interpreted, since a
  row tied to a known event is evidence about a metric's meaning rather than
  about performance.
- **The 2x and 3x spike boundaries are chosen, not derived.** This week's demo
  row sits at 2.7x and leaves the analysis through the duplicate check instead.
- **The scoring weights in the ranking are mine.** The gaps between adjacent
  ranks are smaller than the scheme can resolve, so the output groups the metrics
  into three tiers and states that the tier is the claim.
- **No imputation, upsampling, or resampling.** Two values are missing out of 41
  rows. Filling them would not move any rate and would hide the fact that they
  are missing, which is the opposite of what a trust report is for. A sensitivity
  line reports the headline rate with and without the flagged rows instead.

## Issues found in the data

- The same Lead summary row appears twice on 2026-08-05, at 140 sessions against
  a normal day near 55, with one copy noted as demo account traffic.
- The Reply draft row on 2026-08-07 has 8 accepted plus 12 flagged out of 17
  completed, which is arithmetically impossible, and its note says the review
  policy changed mid-day.
- 2026-08-07 has four rows instead of six. Two source combinations are absent.
- `product` appears in lowercase on 2026-08-02 while every other row uses
  `Product`.
- `median_confidence` holds the text `n/a` on 2026-08-05.
- One `user_rating` is empty on 2026-08-01.

## What I would do next

1. **Split `flagged_for_review` into flags raised by a person and flags raised by
   policy.** No amount of analysis recovers this after a policy change. It needs
   a schema change before the next export.
2. **Instrument what happens between session start and completion**, starting
   with Feedback clustering via csv upload, where roughly 53 sessions a week end
   with nothing.
3. **Find out where `avg_minutes_saved` comes from.** If it is a fixed number per
   workflow, stop reporting it as a measurement.
4. **Explain the Reply draft flag climb** using the days before the policy change,
   while that comparison is still valid.
5. **Add a run identifier and a user identifier to the export**, so sessions can
   be separated from users and retries become visible.

## Scope

Around 40% of the file is the explanatory text it prints, since a trust report
that states a verdict without its reasoning is not much use. There is no
dashboard, no model, and no stored state. It runs in about a second on pandas,
numpy and scipy.
