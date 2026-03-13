---
title: |
  Vasaloppet 2011--2026:\
  The Changing Pack, Race Conditions,\
  and the Vanishing Medal
author: |
  LC Zürich-Doppelstock\
  \small Analysis of 238,492 race results from vasaloppet.se
date: "2026-03-02"
abstract: |
  We analyse 15 editions of the 90\ km Vasaloppet cross-country ski race
  (2011--2026, excluding the 2021 COVID-restricted elite-only edition).
  Three findings emerge: (1)\ an abrupt structural regime change after COVID,
  with the bottom half of the field materially slower and more fragile while
  the elite are unaffected; (2)\ a conditions-only hardness metric that
  separates race-day difficulty from population effects by using within-era
  z-scores of winner time, upper-quartile normalised times, and fast-skier
  dropout rate; (3)\ a near-perfect within-era correlation ($r = -0.92$)
  between conditions hardness and the fraction of starters earning the
  Vasaloppet medal (finish within $1.5\times$ winner time).
documentclass: extarticle
classoption:
  - twocolumn
  - a4paper
geometry:
  - margin=18mm
  - columnsep=6mm
fontsize: 9pt
header-includes: |
  \usepackage{tgtermes}
  \usepackage[T1]{fontenc}
  \usepackage{booktabs}
  \usepackage{float}
  \usepackage{caption}
  \captionsetup{font=small, labelfont=bf, skip=4pt}
  \usepackage{titlesec}
  \titleformat{\section}{\normalfont\large\bfseries}{\thesection.}{0.5em}{}
  \titleformat{\subsection}{\normalfont\normalsize\bfseries\itshape}{\thesubsection}{0.5em}{}
  \setlength{\parskip}{2pt plus 1pt minus 1pt}
  \setlength{\parindent}{0pt}
  \pagestyle{plain}
---

# A Structural Regime Change

## Something broke

Something broke after COVID---and it wasn't just supply chains and sourdough
habits. When every finisher's time is expressed as a multiple of the winner's
time ($t_\text{norm}$), the shape of the Vasaloppet field changed abruptly
between the 2020 and 2022 editions (Fig.\ 1).

Look at the percentile lines. The top decile barely budged---the elite kept
being elite. But the median drifted upward, and the 90th percentile---the
weekend warriors grinding towards Mora---pulled away like taffy. This is not
a gentle drift over decades. It is a step function.

Table\ 1 puts numbers on it: the top 10% shifted by +0.07 (noise). The
median shifted by +0.30. The 90th percentile by +0.47. The further
down the field you look, the wider the gap. And here's the twist: elite
performance actually *improved*. The average winner crossed in 3:45 in
Era\ 2 versus 4:07 in Era\ 1. The fast skiers got faster. The slow skiers
got much, much slower. Whatever happened during COVID hit the back of the
pack and left the front completely untouched.

| Pctile | Era 1 | Era 2 | Shift |
|:------:|:-----:|:-----:|:-----:|
| P10    | 1.37  | 1.43  | +0.07 |
| P25    | 1.59  | 1.76  | +0.17 |
| P50    | 1.94  | 2.24  | +0.30 |
| P75    | 2.32  | 2.75  | +0.43 |
| P90    | 2.62  | 3.09  | +0.47 |

: Era-average normalised time percentiles. Era 1 = 2011--2020, Era 2 = 2022--2026.

![Structural regime change in the field distribution of $t_\text{norm}$. Dotted lines show era means for P50 and P90. The tail stretches dramatically after 2020 while the top decile barely moves. Horizontal line: $1.5\times$ medal cut-off.](fig_a_regime_change.png)

## This is not your imagination

Claims like "the field changed" are easy to make and hard to pin down. So we
put it to a formal test. For each pair of the 15 race years, we estimated the
full probability density function of $t_\text{norm}$ using kernel density
estimation, then measured how much the two curves overlap---the *overlap
coefficient*, which ranges from 0 (completely different distributions) to 1
(identical). Fig.\ 2 shows the result as a heatmap.

The block structure is unmistakable. Within each era, years look alike:
the average overlap is $0.89 \pm 0.04$ (Table\ 2). Cross the COVID
gap and the overlap drops to $0.77 \pm 0.07$. The difference is
not subtle---a Welch's $t$-test gives $t = 10.6$, $p < 10^{-16}$, and
a permutation test (10,000 resamples) found zero shuffles as extreme as the
observed gap. Cohen's $d = 2.12$: a very large effect. Two-sample
Kolmogorov--Smirnov tests on the raw $t_\text{norm}$ distributions confirm it:
all 50 cross-era pairs are distinguishable at $p < 10^{-17}$.

We are not dealing with one race that got a little harder. We are dealing
with two statistically distinct populations. Everything that follows treats
them as such: **Era\ 1** (2011--2020) and **Era\ 2** (2022--2026).

| Group | Pairs | Overlap | Std |
|:------|:-----:|:-------:|:---:|
| Within Era 1 | 45 | 0.893 | 0.039 |
| Within Era 2 | 10 | 0.876 | 0.037 |
| Cross-era    | 50 | 0.771 | 0.069 |

: Pairwise density overlap statistics. Within-era years share ~89\% of their distribution; cross-era pairs share only ~77\%.

![Pairwise overlap of $t_\text{norm}$ density functions. Each cell shows how much two years' finisher distributions agree (1.0 = identical). The block structure reveals two distinct eras separated by the COVID gap. Most similar: 2011 vs 2013 (0.97). Least similar: 2019 vs 2024 (0.61).](fig_f_similarity_heatmap.png)

## What the DNF data reveals

The overall DNF rate rose from 8.6% (Era\ 1) to 12.9% (Era\ 2), and the
temptation is to blame tougher races. But that number conflates two very
different stories: race-day conditions and the changing composition of who
shows up at the start line.

To tease them apart, we sorted every starter by their time at the Smagan
checkpoint (11\ km) into speed quartiles, then tracked how each group fared
over the remaining 79\ km (Fig.\ 3). The results are revealing:

- **Q1 (fastest quartile):** These are the serious skiers---the ones who
  trained through the summer, own a roller-ski, and have opinions about wax.
  Their DNF rates are comparable across eras, typically 1--4%, spiking to
  5--7% only when the weather truly bites. When *these* skiers abandon the
  race, you know the conditions were genuinely awful.
- **Q4 (slowest quartile):** A different universe. DNF rates jumped from 20%
  (Era\ 1) to 38% (Era\ 2). In 2026, a staggering 60% of Q4 starters did
  not finish---three out of five skiers who passed through Smagan in the
  slowest group never made it to Mora.

The Q4/Q1 DNF ratio averaged $7\times$ in Era\ 1 and $17\times$ in Era\ 2. The
surge in dropouts is overwhelmingly a story about the slowest skiers, not about
the weather getting worse.

![DNF rate by starter speed quartile (assigned at Smagan, 11\ km). Q1 dropout is the conditions signal. Q4 dropout is overwhelmingly structural---driven by the weakened tail of the post-COVID field.](fig_b_dnf_decomposition.png)

## Interpretation

The field that lines up in Berga by after COVID is a fundamentally different
population. The pointy end is intact---arguably sharper than ever. But the
broad base of the pyramid has softened. The back-of-the-pack skiers are
slower, more spread out, and far more likely to climb onto a snowmobile at
Evertsberg.[^presidente]

[^presidente]: One anonymous repeat participant---known to colleagues only as
  *El Presidente*---has lined up for 11 of these 15 editions. His equipment
  failure rate across those races is, by any reasonable standard, statistically
  remarkable---though in fairness, the recent proliferation of the double-pole
  technique has turned the Vasaloppet track into an increasingly dense forest
  of swinging carbon fibre. He has never once abandoned the race. Whether his
  material attrition correlates with our conditions hardness index, the rising
  pole density per square metre of track, or simply an unusually combative
  relationship with Swedish birch remains an open research question---but his
  DNF rate of exactly 0\% across all conditions suggests that stubbornness may
  be an underappreciated confounding variable.

Why? The data can't say for certain. Disrupted training pipelines, a wave of
bucket-list newcomers drawn by post-pandemic marketing, an aging participation
base that lost two years of conditioning---any of these could contribute. But
the signature in the data is unambiguous: this is a *structural* change in who
races, not a change in what the race throws at them.

The practical consequence is important: any analysis that naively uses the DNF
rate or the median finish time as a proxy for "how hard was the race" will be
hopelessly confounded by this shift.

# Measuring Race-Day Conditions

## The problem with naive metrics

If someone tells you "the 2024 Vasaloppet had a 15% DNF rate," your instinct
is to think it was a brutal day. But 2012 had a 3% DNF rate---does that mean
2012 was five times easier? Not necessarily. After the regime change, both the
DNF rate and the median finish time are elevated at baseline, even on a
bluebird day with perfect tracks. Comparing raw numbers across eras is like
comparing batting averages across different ballparks without adjusting for
altitude.

## A conditions-only hardness score

To isolate what Mother Nature actually did from who showed up, we built a
composite hardness score from four components, each standardised as a
**within-era z-score** (so a +1.0 in Era\ 1 and a +1.0 in Era\ 2 both mean
"one standard deviation harder than normal *for that era*"):

1. **Winner time**---pure conditions. The fastest skier in the world doesn't
   get slower because the field behind them changed.
2. **P25 of $t_\text{norm}$**---strong amateurs who train seriously. Their
   normalised times mostly reflect conditions, not population drift.
3. **P50 of $t_\text{norm}$**---the mid-pack. More exposed to structural
   effects, but still informative within an era.
4. **Q1 DNF rate**---the purest conditions signal in the dataset.
   Well-prepared skiers do not quit unless the mountain makes them.

Average the four z-scores and you get a single number (Fig.\ 4). Zero means
average conditions for that era. Positive means harder. Negative means the
blueberry soup flowed freely and the tracks were fast. Table\ 3 ranks all
15 editions.

## Conditions ranking

| Year | Score | Signature |
|:----:|:-----:|:----------|
| 2015 | +1.25 | Hard for all. 6.7% Q1 DNF. |
| 2024 | +0.93 | Brutal mid-pack. |
| 2020 | +0.76 | Broad difficulty. |
| 2019 | +0.69 | Highest Q1 DNF Era 1. |
| 2013 | +0.25 | Moderately hard. |
| 2026 | +0.22 | Paradox (see below). |
| 2011 | -0.01 | Average. |
| 2025 | -0.11 | Average despite 12.5% DNF. |
| 2023 | -0.37 | Easy. |
| 2017 | -0.40 | Easy. |
| 2018 | -0.47 | Easy. Fast winner. |
| 2014 | -0.66 | Easy; DNF all structural. |
| 2016 | -0.66 | Easy. Most medals (23.3%). |
| 2022 | -0.67 | Easiest Era 2 race. |
| 2012 | -0.75 | Easiest overall. |

: Conditions hardness ranking, all 15 editions sorted from hardest to easiest.

![Conditions hardness score. Each bar is the mean of four within-era z-scores. Positive = harder than average for that era. Dashed line: COVID gap.](fig_c_conditions_hardness.png)

## The 2026 paradox

Here is a puzzle: 2026 posted the highest overall DNF in our dataset (21.9%),
yet its conditions score is a modest +0.22. Was it actually hard, or wasn't it?

The Q1 DNF (4.0%) says the conditions were *moderately* tough---nothing like
2015 or 2024. But the Q4 DNF (60.4%) is off the charts. What happened is that
the weakest segment of an already-fragile field crumbled under conditions that
would have been merely inconvenient a decade ago. And because those slow
skiers never finished, the surviving finisher pool was artificially
fast---P25 and P50 of $t_\text{norm}$ actually come in *below* the Era\ 2
average. This is textbook **survivorship bias**: the race looks easy if you
only count the people who made it.

In short, 2026 was a *moderately hard* race that collided with a field
carrying an unusually fragile tail. The headline DNF number is dramatic; the
actual conditions were not.

## Checkpoint dropout patterns

When do skiers quit? In a typical year, roughly 70% of DNFs happen at or
after Evertsberg (47\ km)---deep in the race, when fatigue and cold have
had time to accumulate. But in the hardest years and the most structurally
fragile fields, the dropout curve shifts earlier (Table\ 4). Some skiers
barely make it past the first feed station:

| Year | DNFs < 47 km | Note |
|:----:|:------------:|:-----|
| 2012 | 33% | Normal. |
| 2015 | 33% | Hard but persistent. |
| 2019 | 26% | Late-race attrition. |
| 2025 | 48% | Half quit before halfway. |
| 2026 | 58% | Majority quit early. |
| 2014 | 61% | Weakest knew immediately. |

: Share of DNFs occurring before Evertsberg (47 km), selected years.

# The Vanishing Medal

## The Vasaloppet medal

The *Vasaloppsmedaljen* is one of the most coveted prizes in Swedish amateur
sport. Finish within $1.5\times$ the winner's time---roughly under 6
hours---and you take home the medal. For generations of recreational skiers,
it has been *the* goal: not just finishing, but finishing well enough to prove
you belong.

## Medal yield has collapsed

| Era | Avg medal % | Range |
|:---:|:-----------:|:-----:|
| Era 1 (11--20) | 17.3% | 11.5--23.3% |
| Era 2 (22--26) | 11.2% | 7.3--13.9% |

: Medal yield by era. The threshold is finish within 1.5x winner time.

In Era\ 1, roughly one in six starters earned a medal. In Era\ 2, it is one
in nine (Table\ 5, Fig.\ 6). The medal rate dropped by 6 percentage
points---not because the medal got harder to earn (the threshold is the same),
but because the field around it changed. The $1.5\times$ cut-off is a fixed
line; the field drifted away from it.

## Conditions explain within-era variation

Within Era\ 1, the correlation between conditions hardness and medal yield is
remarkably tight: $r = -0.92$ ($p = 0.0002$) (Fig.\ 5). That means conditions
alone explain 85% of the year-to-year variation in how many skiers take home
the medal. Once you know the weather, you can almost perfectly predict the
medal rate (Table\ 6).

| Year | Cond. | Medal % | Note |
|:----:|:-----:|:-------:|:-----|
| 2016 | -0.66 | 23.3% | Easiest, most medals. |
| 2018 | -0.47 | 21.8% | |
| 2014 | -0.66 | 21.3% | |
| 2020 | +0.76 | 12.9% | |
| 2015 | +1.25 | 11.5% | Hardest, fewest medals. |

: Era 1 extremes: conditions hardness vs medal yield.

Era\ 2 shows the same direction ($r = -0.64$) but with only five data points
the correlation is not statistically significant ($p = 0.24$). Give it a few
more years and it likely will be.

## The double penalty in 2024

If you picked the worst possible year to chase a medal, it was 2024: only
7.3% of starters earned one. Two forces conspired:

1. **Structural:** the Era\ 2 baseline is already lower (~11%), because the
   field is slower relative to the winner.
2. **Conditions:** 2024 was the hardest Era\ 2 race (+0.93), shaving another
   4 percentage points off the already-depressed baseline.

Structure set the floor. Conditions kicked it out from under you.

## 2026: survivorship bias inflates medals

And then there is 2026, which---despite posting the highest DNF rate in our
dataset---produced a medal rate of 13.9%, comfortably *above* the Era\ 2
average. How?

The 22% who dropped out were disproportionately from the slow tail. Strip them
away and the remaining finisher pool skews fast: 17.7% of *finishers* cleared
the $1.5\times$ threshold. The survivors were, in effect, pre-selected for
speed. The race didn't get easier; the people who would have dragged the
average down simply weren't there at the finish line.

![Conditions hardness vs medal yield. Within Era\ 1, conditions explain 85% of medal variance ($r = -0.92$). The two eras occupy distinct bands.](fig_d_medals_scatter.png)

![Medal yield over time. The 6pp drop between eras is structural (dashed lines). Year-to-year variation within each era is conditions-driven.](fig_e_medals_timeseries.png)

# Summary

Three forces shape Vasaloppet results in the modern era, and you need all
three to make sense of what the data is telling you:

1. **Structural regime change (post-COVID).** The bottom half of the field is
   materially slower and more fragile. The top end is unaffected or faster.
   This is a step change, not a gradual trend---something shifted in *who
   races*, and it hasn't shifted back.

2. **Race-day conditions.** The cleanest signal comes from the fastest
   quartile: their times and dropout rates, because they are insulated from
   structural effects. By this measure, the hardest races were 2015, 2024,
   2020, and 2019. The easiest: 2012, 2022, and 2016.

3. **Medals track conditions, not structure.** Within each era, the medal
   rate is almost entirely a function of weather and snow ($r = -0.92$ in
   Era\ 1). The *level* shift---from 17% to 11%---is structural. The
   year-to-year swings are conditions.

The overall DNF rate, the number most commonly cited in post-race commentary,
is a poor proxy for difficulty. It mixes structural fragility (Q4 dropout)
with genuine conditions hardness (Q1 dropout) into a single misleading
number. Several high-DNF years (2014, 2025) had perfectly unremarkable
conditions, while moderate-DNF years (2013, 2019) were genuinely punishing.

Next time someone tells you "this year's Vasaloppet was the hardest ever"
because the DNF rate was high, ask them: hard for *whom*?

---

\small
*Data: 238,492 results from vasaloppet.se, 2011--2026 (15 editions, excluding
2021 COVID elite-only, 325 participants). Checkpoint times: Smagan (11\ km)
through Eldris (81\ km).*
