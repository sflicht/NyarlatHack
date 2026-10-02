# Arc metric: distinct felt whispers

Tier B, measurement only. No gameplay, engine, director or contract change;
no player-visible delta. Sam's decision after #229: measure the arc by the
whispers a player feels, not by how many hound steps they see.

## The metric

A **felt event** is the existing public `felt_events` row (#179, #228): a
visible hound step, a next-use W or F notice, a visible door resistance, or
the first `Hungry` in a hunger window. The old figure, "2+ felt events", counts
rows, so one hound walking three visible steps scores 3.

**Distinct felt whispers** counts sources instead, from the same public rows
only (`tests/chaos/sweep_programs.py: distinct_felt`):

- the hound counts at most once per game, at its first visible step;
- each next-use program counts at most once, W or F, at its first felt event;
- each accepted door effect counts at most once (first visible resistance);
- each accepted hunger effect counts at most once (first `Hungry` in it).

The live analyser keys door and hunger rows by the public turn of the accepted
ack that opened the effect. Older reports lack that key, so post hoc door rows
are grouped by the contract's 300-turn duration cap instead. On this sweep both
methods agree on all 500 games.

Every existing field, and the raw "2+ felt events" figure, is unchanged and
reported beside the new one. The v2 report gains `funnel.distinct_felt` per game
and `aggregate_v2[start].distinct_felt` per start. The committed PR 4 ordinary
golden is unchanged; its test now also checks that `distinct_felt` is the only
added key.

## Re-baseline: main, 5 starts x seeds 1-100, baseline-v2

The game sources at the measured head `703ee7e5` are byte-identical to
origin/main `51e8342c` (`src include chaos dat sys win util Makefile`); only
the analyser differs. Build warning-clean. 500 games, sweep exit 0. The two
harness errors (bard seeds 48 and 75) are the same two #229's main side had.
Every game's felt events and outcome match #229's retained main-side sweep
seed for seed, so the baseline reproduces. The full report is
`sweep/baseline-v2-seeds-1-100-main.md`.

| Start | Raw 2+ felt events | 2+ distinct | 2+ distinct, no hound | Distinct per game (0/1/2/3) | Sources: hound / next-use / door / hunger |
|---|---|---|---|---|---|
| bard | 12 | 5 | 5 | 69 / 26 / 5 / 0 | 0 / 17 / 19 / 0 |
| bard-default-path | **69** | **23** | **2** | 20 / 57 / 21 / 2 | 77 / 12 / 16 / 0 |
| bard-inherited | 1 | 0 | 0 | 93 / 7 / 0 / 0 | 0 / 6 / 1 / 0 |
| madman | 0 | 0 | 0 | 95 / 5 / 0 / 0 | 0 / 0 / 0 / 5 |
| wizard-default-path | 63 | 11 | 0 | 21 / 68 / 11 / 0 | 79 / 0 / 11 / 0 |

On bard-default-path, the 23 games with 2+ distinct whispers are: hound + one
next-use program (11), hound + door (10), hound + two door effects (1), and
hound + door + next-use (1). Two of them have two sources besides the hound.

**No game on any start felt two next-use programs.** Across all 500 games,
29 felt next-use rows are attributed to program 1 and none to program 2 or 3.
Six more rows (in six games) carry no public program number, and each of those
games counts them as a single source. A second or third program was *admitted*
in 41 games but *felt* in none (breakdown below).

## Post hoc: #229's retained paired sweep

The retained reports from #229 (`main 44531194e` vs PR `a8d41373`, whose game
sources equal the merged head) were complete: 500 games per side, full
`felt_events`. I re-analysed them with this metric and did not re-run anything
(`posthoc-pr229.json`; door rows grouped by the duration cap, as these reports
predate per-effect keys).

| Start | Main: 2+ distinct / no hound | PR: 2+ distinct / no hound |
|---|---|---|
| bard | 5 / 5 | 5 / 5 |
| bard-default-path | 23 / 2 | 23 / 2 |
| bard-inherited | 0 / 0 | 0 / 0 |
| madman | 0 / 0 | 0 / 0 |
| wizard-default-path | 11 / 0 | 10 / 0 |

Paired seed by seed, only one game differs: wizard-default-path seed 58 drops
from 2 to 1 distinct on the PR side. That game was one of #229's two PR-side
harness timeouts; rerun alone it played identically on both sides (#229
README). Excluding it, **Arc 1 moved the distinct-whisper count in zero of
500 games.**

## What this says about Arc 1

Plainly: Arc 1 barely registers. The recurrence telegraph appeared in 14 of
#229's PR games, but no game ever went on to feel the second program, so the
arc it announces never completes in the sweep. Admission is not the
bottleneck: later programs reach the player and then do nothing felt. Of the 45
admitted program-2/3 instances (41 games), 18 triggered but had no native
effect, 23 never triggered before they completed or expired (14
`program_expired`, 7 `completed`, 2 `origin_expired`; corrected from "21" by
the [diagnosis](../arc-unfelt-diagnosis/)), and 4 were still open at game end.
None was delivered. The old 69/100 figure on bard-default-path was almost
entirely hound steps. Counting sources, it is 23/100. Without the hound
it is 2/100: seed 28 (two door effects) and seed 56 (next-use program 1, then a
door effect). Neither game felt two next-use programs.

## Proposed gate for future arc work (for Sam; not set)

> On bard-default-path seeds 1-100 (baseline-v2), arc work should raise
> games with 2+ distinct felt whispers *excluding the hound* from today's 2/100
> to at least 10/100, with hound admission unchanged from main, and at least 3
> of those games should feel two next-use programs.

Reasoning from the data:

- **Exclude the hound.** It is present in 77 of 100 default-path games and is
  not part of the arc, so any gate that counts it mostly measures the hound.
  The old gate passed at 69 while Arc 1 changed nothing.
- **10 out of 100.** Against a baseline of 2/100, 10/100 is the smallest round
  count that a one-sided Fisher exact test separates from noise (p = 0.017;
  8/100 gives p = 0.050, 6/100 gives p = 0.14). Plain bard already reaches
  5/100 from next-use + door, so 10 is reachable without the hound.
- **Two next-use programs.** That count is 0/500 today. Requiring at least 3
  makes the gate measure recurrence, which is the arc's actual claim, rather
  than unrelated door or hunger effects. The figure 3 is a judgement call: it
  is small enough to reach, and more than one lucky seed.

## Attempts

- Affected-test runs while developing: two failed runs, then a pass. The
  first failed with 12 errors from a variable-name clash in
  `sweep_programs.analyse` (fixed). The second failed with one golden mismatch,
  because the new key was added to the committed PR 4 golden comparison (the
  test now strips and checks it; the golden itself is unchanged).
- Re-baseline attempt 1 (`703ee7e5`, 2026-10-02 02:57-04:22 UTC) played all
  500 games, then crashed writing the report. `seed_sweep.py` records its
  revision with `git rev-parse HEAD`, and the `git archive` export it ran from
  has no `.git`. No report came out of it, and its figures are not used.
- Re-baseline attempt 2 (same head, 04:24-05:46 UTC) ran the sweep script from
  the worktree, which was frozen and checked clean before and after, against
  attempt 1's build of the same export (binary sha256 `79a8fbf1...` recorded
  in the report). Sweep exit 0. These are the figures above.
