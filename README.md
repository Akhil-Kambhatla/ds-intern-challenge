# SignalDesk weekly check

A script that reads one week of SignalDesk usage data and answers one question:
**how much of this can you actually believe?**

Run it, read the output, and you will know which numbers are safe to act on,
which ones are lying to you, and what you would need before you could call the
prompt change a win.

---

## The situation

The SignalDesk team changed a prompt on 2026-08-04 and changed a review policy
on 2026-08-07. They have seven days of usage data and want to know whether any
of it went well.

The data does not make that easy. Some rows are not real. Some columns look like
quality signals and are not. And the change happened three days into a seven day
window, which is not much to work with.

---

## What we built, and why it is a script

**We built a repeatable weekly check, not a one-off analysis.**

A notebook answers this week. Next week someone opens it, changes a date, and
quietly re-decides which rows to drop and which numbers to believe. Those
decisions get made differently every time, by whoever is holding the file.

A script makes the decisions once and applies them the same way forever. That is
the whole reason there is arithmetic and statistics in here. The math is not for
show. Each rule replaces a judgment a person would otherwise have to make by eye:

| Judgment a person would make weekly | What the script does instead |
|---|---|
| "This row looks wrong, I'll drop it" | Nine fixed checks, each printing why a row was dropped |
| "Confidence seems fine to me" | Correlates confidence against acceptance, pooled and within group, and reports the disagreement |
| "That looks like an improvement" | Compares the change against the noise band for that sample size |
| "Let's just try harder on quality" | Ranks every workflow by how many accepted outputs a fix would actually add |

Same input, same verdict, every time, with the reasoning printed next to it.

---

## What a clean week would look like, and what this week looks like

| What we check | A week you can trust | This week | |
|---|---|---|---|
| Rows surviving the checks | 41 of 41 | 38 of 41 | fail |
| Duplicate rows | 0 | 2 | fail |
| Arithmetically impossible rows | 0 | 1 | fail |
| Days with all 6 rows present | 7 of 7 | 6 of 7 | fail |
| Confidence agrees with acceptance inside each group | same direction everywhere | reverses in 3 of 6 groups | fail |
| Confidence tracks quality, not traffic | near 0 against volume | 0.84 against volume | fail |
| Minutes saved moves day to day | it varies | barely moves, 2 to 6 percent | fail |
| Worst completion rate | 80 percent or better | 64 percent | fail |
| Change big enough to read | bigger than the noise band | 1.3 points against a band of 8.7 | fail |

Nine checks, nine failures. That is the honest headline, and it is why the
answer to "did the prompt work" is not yes or no but **not yet knowable**.

---

## Could the prompt change have worked?

Yes. It also could have done nothing, or made things slightly worse. The data
cannot separate those three. Here is the gap, using Lead summary:

| | This week's export | What a readable result needs |
|---|---|---|
| Completed runs before the change | 154 | about 3,000 |
| Completed runs after the change | 196 | about 3,000 |
| Days of data on each side | 3 and 4 | about 63 |
| Change in acceptance observed | +1.3 points | +3.0 points |
| Noise band at that sample size | 8.7 points | 2.1 points |
| Can you call it? | No, the change is 7 times smaller than the noise | Yes, comfortably |

The gap is not small. It is a factor of fifteen in data volume. Nothing in the
analysis closes it, which is worth knowing before someone builds a roadmap on
this week's numbers.

---

## The five things worth telling the team

**1. Model confidence is the least trustworthy number in the file.**
Pooled across all rows it appears to track quality closely. Split by source, the
relationship reverses in half the groups. Automated sources simply have both
higher confidence and higher acceptance, so pooling them measures the source, not
the model. Confidence also rises with daily traffic and climbs every day of the
week, which means it is following the calendar.

**2. The prompt change is not measurable yet.**
All three workflows moved less than their own noise. Adjusting for source mix
moves the picture by a tenth of a point, so mix was not hiding anything either.

**3. Minutes saved is close to a fixed number.**
It varies by 2 to 6 percent inside each group across the whole week. Real time
savings would move around more than that. Anything multiplied by it is really
just a volume ranking wearing a disguise.

**4. A third of Feedback clustering runs never produce anything.**
Completion via csv upload is 64 percent. Acceptance measured on finished runs
reads 67 percent and looks normal. Measured on runs started it is 44 percent. The
usual denominator hides every failure.

**5. Reply draft flags were rising before anything changed.**
The flag rate climbs from 12.5 to 16.2 percent over six days, all of it before
the review policy changed. Nobody has explained this one.

---

## The biggest opportunity in the product

Not the prompt. Completion on Feedback clustering via csv upload:

| Workflow and source | Accepted per week now | If completion matched the best in the product | If acceptance did too |
|---|---|---|---|
| Feedback clustering / csv upload | 65 | +20 | +36 |
| Lead summary / manual | 69 | +14 | +26 |
| Reply draft / manual | 41 | +6 | +16 |

The targets are rates already being hit elsewhere inside SignalDesk, so they are
known to be reachable rather than invented.

---

## Run it

pip install -r requirements.txt
python3 weekly_check.py


| Option | Default | What it does |
|---|---|---|
| `--data` | `sample-data/product_usage_events.csv` | Points at a different export |
| `--change-date` | `2026-08-04` | Splits before and after at a different date |
| `--min-effect` | `3.0` | How many points of improvement would be worth acting on |

Plain text to stdout. Nothing written to disk, and the input file is never
touched.

---

## Choices we made, and why

| Choice | Why |
|---|---|
| Report both acceptance denominators | Acceptance on finished runs asks if an output was good. Acceptance on all runs asks if a user got something. The second is the better health number and the gap between them is a finding in itself |
| Quarantine a duplicate group entirely | Nothing in the export says which copy is the real run, so keeping either is a guess |
| Reuse quarantined rows in one place only | A row from a known event is evidence about what a metric means, not about how the product performed. It is excluded from every rate |
| Use notes as a backstop, not a detector | The arithmetic checks work next week when the notes are worded differently. A checker that only reads notes is not a checker |
| Set spike thresholds at 2x and 3x | Chosen, not derived. This week's demo row sits at 2.7x and leaves through the duplicate check instead, which the output says out loud |
| Group metrics into three tiers, not six ranks | The gaps between adjacent ranks are smaller than the scoring can resolve, so the tier is the claim |
| No imputation, upsampling, or resampling | Two values are missing out of 41 rows. Filling them cannot move a rate and would hide the fact they are missing, which is the opposite of the point |

---

## Problems found in the data

| Where | What is wrong |
|---|---|
| 2026-08-05, Lead summary, email | The same row appears twice, at 140 sessions against a normal day near 55, one copy noted as demo traffic |
| 2026-08-07, Reply draft, queue | 8 accepted plus 12 flagged out of 17 completed, which cannot happen. Note says the policy changed mid-day |
| 2026-08-07 | Four rows instead of six. Two source combinations missing |
| 2026-08-02 | `product` in lowercase where every other row says `Product` |
| 2026-08-05 | `median_confidence` holds the text `n/a` |
| 2026-08-01 | `user_rating` is empty |

---

## What we would do next

1. **Split `flagged_for_review` into flags raised by a person and flags raised by
   policy.** No analysis recovers this after a policy change. It needs a schema
   change before the next export.
2. **Instrument the gap between session start and completion**, beginning with
   Feedback clustering via csv upload, where roughly 53 sessions a week end with
   nothing.
3. **Find out where `avg_minutes_saved` comes from.** If it is a fixed number per
   workflow, stop calling it a measurement.
4. **Explain the Reply draft flag climb** using the days before the policy change,
   while that comparison still holds.
5. **Add run and user identifiers to the export**, so sessions stop being confused
   with users and retries become visible.

---

## Terms used above

| Term | Plain meaning |
|---|---|
| Noise band | How much a rate wobbles on its own, given how many runs it was measured from. A change inside the band cannot be told apart from nothing |
| Spearman correlation | Rank both columns and see if the orders agree. +1 is identical, 0 is unrelated, -1 is reversed |
| Pooled versus within group | Whether a pattern holds when everything is thrown together, or still holds inside each group. When they disagree, the pooled version is usually measuring the grouping |
| Mix adjustment | Recomputing both periods as if the split between automated and manual traffic had stayed fixed, so that shift cannot be mistaken for the prompt working |
| Quarantined | Excluded from every calculation, with the reason printed |

---

## Scope

About 40 percent of the file is the text it prints, because a verdict without its
reasoning is not much use to the person reading it. No dashboard, no model, no
stored state. Runs in about a second on pandas, numpy and scipy.
