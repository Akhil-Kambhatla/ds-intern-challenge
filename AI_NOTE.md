# AI note

I used AI deliberately throughout this.

## Where it was used

- **Reading the domain packet.** I had Claude summarise the workflows, the metric
  definitions and the caveats, then argue about which caveats actually mattered
  for this dataset rather than in general.
- **Exploring the data.** The first pass over the CSV was mine to direct and the
  model's to execute: dtypes, duplicates, arithmetic invariants, rates by group.
- **Choosing the angle.** I considered a weekly health check, a before and after
  comparison, a workflow comparison, and a trust checker. I picked the trust
  checker fused with a weekly summary, because the file is mostly a mess by
  design and a comparison built on it would have inherited the mess.
- **Writing the script.** weekly_check.py was written by Claude Code from a
  detailed prompt I wrote, and then revised through one round of corrections.

## What I decided or corrected myself

- **I asked whether upsampling, imputation, or weighted sampling would surface
  more signal, and concluded they would not.** With 41 rows, no label, and seven
  time points, all three would add information that is not in the file. The two
  missing values cannot move a rate, and filling them would erase the one thing
  worth reporting about them. I replaced that idea with a sensitivity check that
  reports the headline rate with and without the questionable rows.
- **I decided the analysis should compute what an improvement would have to look
  like rather than search for a cut where the prompt change looks good.** That
  reframe produced the most useful part of the artifact: the noise bands, the
  days of data required, and the pre-registered thresholds.
- **A review pass over the first working version caught a real error.** The
  pre-registered thresholds had been built by adding the current noise band to
  the current rate, producing bars near 86% and claiming eight days would settle
  it, while the detectability block in the same output said 62 days. Two numbers
  from one script contradicting each other. The fix was to make the minimum
  effect a business input and derive the data requirement from it.
- **I tempered a claim the model was happy to leave standing.** The correlation
  between confidence and sessions comes out at exactly 1.00 in four of six
  groups, which sounds decisive and is not: both columns rise monotonically over
  seven consecutive days, so with six points a perfect rank correlation is easy.
  The output now says so.
- **I checked the script's own verification claims by rerunning it.** A model
  reporting that its own output is correct is not evidence that it is.

## What helped and what did not

Most useful: fast domain digestion, and having something to argue with while
deciding what not to build.

Least useful: the model's first instinct on the thresholds was internally
inconsistent and read as authoritative. Fluent output is not checked output, and
the contradiction was only visible by holding two sections of the same report
side by side.
