# SignalDesk weekly check

## The problem

The SignalDesk team changed a prompt on 2026-08-04 and changed a review policy on 2026-08-07. They have one week of usage data and want to know whether anything improved.

The export makes that hard to answer. It holds 41 rows across seven days. A few of those rows are not real runs. Several of the columns look like quality signals but measure something else. And the prompt change landed three days into a seven day window, so there is very little data on either side of it.

## Why it needs working

The risk is not that the team gets no answer. The risk is that they get a confident wrong one.

Model confidence rose after the prompt change. Read on its own, that looks like evidence the change worked, and it is the kind of number that ends up in a summary for leadership. If the team acts on it, they roll out a change that has not been shown to do anything, and they spend the next quarter maintaining it.

There is also a smaller, repeating cost. Somebody has to look at this export every week and decide by eye which rows to ignore and which numbers to believe. Those decisions get made a little differently each time, by whoever happens to be holding the file, and the reasoning behind them is not written down anywhere.

## The proposed solution

A command line script that reads the export and reports what can and cannot be concluded from it, using simple arithmetic and basic statistics.

The aim is narrow: use straightforward math to surface information the raw table hides, and to make the same judgment the same way every week.

Two reasons for that approach.

**Arithmetic finds problems that eyes miss.** One row this week has 8 accepted outputs plus 12 flagged out of 17 completed runs. That total cannot happen, and it identifies the row as broken without needing anyone to read its note or know what happened that day.

**Statistics answers a question the raw numbers cannot.** Acceptance for Lead summary rose 1.3 points after the prompt change. Whether that is a real improvement depends entirely on how many runs it was measured from, and that requires a calculation rather than an opinion.

Every rule in the script replaces a judgment a person would otherwise make from memory:

| Judgment made by eye each week | What the script does instead |
|---|---|
| "This row looks wrong, I will drop it" | Nine fixed checks, each printing the row and the reason |
| "Confidence looks reasonable" | Measures whether confidence agrees with acceptance, overall and inside each group |
| "That looks like an improvement" | Compares the change against how much that rate wobbles at this sample size |
| "Quality needs work" | Estimates how many more accepted outputs each possible fix would produce |

## What it does

Four sections, in order.

1. **Data trust report.** Runs nine checks. Five remove a row from the analysis, four keep it and note it. The checks are arithmetic and structural, so they still work next week when the notes column is worded differently. Reading the notes for keywords happens last, as a backstop.
2. **Metric trust ranking.** Scores the six metrics on how complete they are, where they come from, whether a rise in them has one clear meaning, whether they agree with an independent signal, and whether they move at all. The order is computed from the data rather than written in.
3. **Weekly health summary.** Shows every rate split by source, with both acceptance denominators side by side.
4. **Targets.** Compares before and after the prompt change with source mix held fixed, states how large a change would have to be before this much data could detect it, and estimates which fix would add the most accepted outputs.

## What the output looks like

Plain text. A trimmed extract:

```
  [2] accepted + flagged > completed: 1 row(s)
      line  40  2026-08-07  Reply draft   queue   accepted 8 + flagged 12 > completed 17

  Workflow / source                  sess  cmpl  acpt  compl%   acc/cmpl   acc/sess
  Feedback clustering / csv upload    149    96    65   64.4%      67.7%      43.6%

  Lead summary
    acceptance 77.3% -> 78.6%, observed change +1.3 points
    noise band +/- 8.7 points at 95 percent, observed change sits INSIDE it
    a 3 point change needs about 63 days at 49 completed/day
```

## How to read it

The output is arranged so the reader can stop early. Section 1 says how much of the export survived. If very little did, the rest matters less.

Three things to look at:

**Rows kept.** 38 of 41 this week. Rows are removed for stated reasons, not because they look odd.

**Whether a change sits inside its noise band.** Every rate moves around on its own depending on how many runs it came from. The band is the size of that movement. A change inside the band cannot be separated from nothing having happened. This week all three workflows sit inside their bands.

**Where the two acceptance rates disagree.** Acceptance measured on finished runs asks whether an output was good. Acceptance measured on all runs asks whether a user who started got something usable. A large gap between them means runs are failing before they produce anything, and the first number is hiding it.

## What this week's data shows

**Model confidence does not track quality here.** Across all rows, confidence and acceptance move together, with a rank correlation of 0.71. Split the rows by workflow and source and the relationship reverses in three of six groups. Automated sources have both higher confidence and higher acceptance, so the combined figure reflects the source rather than the model. Confidence also correlates with daily session volume at 0.84 and rises on every day of the week, which points to it following traffic and the calendar.

**The prompt change cannot be evaluated with this data.** Acceptance moved +1.3 points for Lead summary, +0.2 for Reply draft, and -1.1 for Feedback clustering, against noise bands of 8.7, 8.4 and 16.9 points. Holding source mix fixed changes the picture by about a tenth of a point, so mix was not concealing an effect either.

**Minutes saved barely varies.** Within each workflow and source it moves 2 to 6 percent across the whole week. A measured time saving would move more than that. Any figure built by multiplying it is close to a volume count.

**A third of Feedback clustering runs end without an output.** Completion via csv upload is 64.4 percent. Acceptance on finished runs is 67.7 percent, which looks similar to the other workflows. Acceptance on all runs started is 43.6 percent.

**Reply draft flags rose before either change.** The flag rate per finished output goes from 12.5 to 16.2 percent over six days, ending before the review policy changed. The export contains nothing that explains it.

## What an improved result would look like

The comparison below is what the script would print if the underlying problems were fixed. Each line explains what the number means and why it matters.

| Check | This week | A week that supports a decision | What the difference signifies |
|---|---|---|---|
| Rows kept | 38 of 41 | 41 of 41 | Duplicates and impossible rows mean the export pipeline needs fixing, not just the analysis |
| Confidence agreement inside each group | reverses in 3 of 6 | same direction in all groups | If it reversed nowhere, confidence could be used for routing. It cannot be used that way now |
| Confidence against session volume | 0.84 | near 0 | A quality signal should not rise because traffic rose |
| Minutes saved variation | 2 to 6 percent | varies with the work done | Would show the field is measured rather than assigned |
| Lowest completion rate | 64.4 percent | 80 percent or above | Roughly 53 sessions a week currently end with nothing to accept |
| Observed change against noise band | 1.3 against 8.7 | change larger than the band | Only then can a prompt change be called either way |
| Days of clean data each side | 3 and 4 | about 63 for a 3 point change | The gap is a factor of about fifteen in volume, and no analysis closes it |

## Does this add impact

**Quantitatively, in a limited way.** The script estimates what closing the gap on each workflow would add, using rates already achieved elsewhere inside SignalDesk rather than invented targets.

| Workflow and source | Accepted outputs per week now | If completion matched the best rate in the product | If acceptance matched it too |
|---|---|---|---|
| Feedback clustering / csv upload | 65 | +20 | +36 |
| Lead summary / manual | 69 | +14 | +26 |
| Reply draft / manual | 41 | +6 | +16 |

These are upper bounds. They assume one group can reach a rate another group reaches, and different inputs may not allow that. They are useful for ordering the work, not for forecasting.

**Qualitatively, in a narrower and more certain way.** The output prevents one specific wrong decision: reporting the prompt change as a success on the strength of a confidence increase. It also converts "we are not sure" into a number the team can plan around, which is 63 days of data for Lead summary at current volume. That tells them the honest option for the low volume workflows is to read a sample of outputs by hand rather than wait for rates to become readable.

## Choices made, and why

| Choice | Reason |
|---|---|
| Both acceptance denominators are reported | They answer different questions, and the gap between them is itself a finding |
| A duplicate group is removed entirely | Nothing in the export identifies which copy is the real run, so keeping either would be a guess |
| Notes are read last, as a backstop | The arithmetic checks keep working when next week's notes are worded differently |
| Rows removed from the analysis are reused in one place | A row tied to a known event says something about what a metric means, though nothing about how the product performed. It is excluded from every rate |
| Spike thresholds set at 2x and 3x | Chosen, not derived from the data. This week's demo row sits at 2.7x and is removed by the duplicate check instead, which the output states |
| Metrics grouped into three tiers rather than ranked one to six | The gaps between neighbouring ranks are smaller than the scoring can distinguish |
| No imputation or resampling | Two values are missing out of 41 rows. Filling them cannot change any rate and would remove the record that they were missing |

## Problems found in the data

| Where | What is wrong |
|---|---|
| 2026-08-05, Lead summary, email | The same row appears twice, at 140 sessions against a normal day near 55. One copy is noted as demo account traffic |
| 2026-08-07, Reply draft, queue | 8 accepted plus 12 flagged out of 17 completed. The note says the review policy changed mid-day |
| 2026-08-07 | Four rows instead of six. Two source combinations are absent |
| 2026-08-02 | `product` in lowercase where every other row has `Product` |
| 2026-08-05 | `median_confidence` holds the text `n/a` |
| 2026-08-01 | One `user_rating` is empty |

## What to do next

1. Split `flagged_for_review` into flags raised by a person and flags raised by policy. Once a policy has changed, no analysis can separate them after the fact. This needs a schema change before the next export.
2. Instrument what happens between session start and completion, starting with Feedback clustering via csv upload.
3. Establish where `avg_minutes_saved` comes from. If it is a fixed value per workflow, it should not be presented as a measurement.
4. Look into the Reply draft flag increase using the days before the policy change, while that comparison still holds.
5. Add run and user identifiers to the export, so sessions can be told apart from users and retries become visible.

## Run it

```
pip install -r requirements.txt
python3 weekly_check.py
```

| Option | Default | Effect |
|---|---|---|
| `--data` | `sample-data/product_usage_events.csv` | Reads a different export |
| `--change-date` | `2026-08-04` | Splits before and after at a different date |
| `--min-effect` | `3.0` | Sets how many points of improvement would be worth acting on |

Output is plain text on stdout. Nothing is written to disk and the input file is not modified.

## Terms used above

| Term | Meaning |
|---|---|
| Noise band | How much a rate moves on its own, given the number of runs behind it. A change inside the band cannot be told apart from no change |
| Rank correlation | Rank the rows by two columns and see whether the orders agree. +1 is identical, 0 is unrelated, -1 is reversed |
| Overall against within group | Whether a pattern holds when all rows are combined, and whether it still holds inside each group. When the two disagree, the combined figure is usually reflecting the grouping |
| Source mix held fixed | Recomputing both periods as though the split between automated and manual traffic had not moved, so that shift cannot be mistaken for the prompt working |

## Scope

The data is `sample-data/product_usage_events.csv`, provided with the challenge. About 40 percent of the script is the text it prints, since a verdict without its reasoning is hard to act on. There is no dashboard, no model and no stored state. It runs in about a second on pandas, numpy and scipy.
