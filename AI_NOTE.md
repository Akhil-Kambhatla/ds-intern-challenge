# AI note

I used AI throughout this, and I directed it rather than accepting what it
produced.

## Where I used it

Reading the domain packet and arguing about which caveats mattered for this
dataset rather than in general. Running the first pass over the CSV. Weighing
four possible angles before I picked one. Writing weekly_check.py from a detailed
prompt I wrote, then revising it across two rounds of corrections.

## What I decided or corrected

**I ruled out upsampling, imputation and weighted sampling.** I asked whether any
of them would surface more signal. With 41 rows, no label and seven time points,
all three add information that is not in the file. Two values are missing and
neither can move a rate, so filling them would only erase the record that they
were missing. I used a sensitivity check instead, which reports the headline rate
with and without the questionable rows.

**I changed the question.** My first instinct was to look for a way to show the
prompt change had worked. Trying enough cuts of a small dataset will eventually
produce a positive one, so I switched to computing what an improvement would have
to look like: the margin at this sample size, the data required to read a three
point change, and a threshold set before the next export arrives.

**The first working version contradicted itself.** It built the pre-registered
thresholds by adding the current margin to the current rate, giving bars near 86
percent and claiming eight days would settle it, while the detectability block in
the same output said 62 days. That was caught in review before submission. The
fix was to take the minimum effect worth acting on as an input and derive the
data requirement from it.

**I tempered a claim the model was content to leave standing.** The correlation
between confidence and sessions is exactly 1.00 in four of six groups. That
sounds decisive and is not: both columns rise on every one of seven consecutive
days, so with six points a perfect rank correlation is easy to hit. The output
now says so.

**I reran the script rather than trusting its report.** A model stating that its
own output is correct is not evidence that it is.

## What helped and what did not

Most useful: getting to a working understanding of an unfamiliar domain quickly,
and having something to argue with while deciding what not to build.

Least useful: fluent output reads as correct. The threshold contradiction was
only visible by holding two sections of the same report side by side, and nothing
in the writing signalled that one of them was wrong.
