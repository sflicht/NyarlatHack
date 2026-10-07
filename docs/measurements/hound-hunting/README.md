# Hounds that hunt: shadow-trial baseline (Tier B)

What it measures: footsteps.lua and the 18 retained #251 pilot sources
(`docs/measurements/hound-free-pilot/run/jobs/*`, the last attempt of each
ready job) through the engine's real shadow trial. The rooms and seeds are
the #251 pilot's: bare 6×4, 12×6 and 20×8, plus the recorded #194 cornered
map, each with native RNG seeds 1, 2 and 3 (12 trials per source).
`measure.py` reuses the pilot's `link`, `shadow` and `reason`.

Instrument: the trial now also reports `min_dist` and `median_dist`. These
are the Chebyshev distance from hound to player after each hound action,
taken as the minimum and the lower median over the steps. They are new fields
in `dreamlands.json`, and the acceptance rule is unchanged. Engine revision:
6cccef24 plus that change, CHAOS=1, 0 warnings.

Files: `baseline/trials.json` (every report), `baseline/table.md`
(per-source medians).

## Findings

- **footsteps** is the only source that reaches the player in every trial:
  `min_dist` is 1 in 12/12, contacts > 0 in 12/12 (median 7.5), max damage
  2, escaped 12/12, moved 54–64.
- **None of the 18 pilot sources reaches the player in every trial.** 16 of
  them never come within 1 square in any trial (`min_dist` ≥ 2 throughout).
  10-madman-00007 and 13-wizard-default-path-00007 reach it in some bare
  rooms only (6 trials each).
- **Movement alone does not separate them.** 16-bard-00007 moves on 64/64
  steps in every room yet never comes closer than 2. It shadows the player at
  distance 2. A "moved at least a fraction of steps" floor would pass it.
- In this harness, "came within 1 square at least once" separates cleanly:
  footsteps passes all 12 trials, and every pilot source fails at least 6.

## Conflict with real play (why the floor is not written yet)

In real ordinary games, footsteps itself often never reaches the player in
the shadow trial. The model-free games for #253 (seeds 1–8 and 12,
`curio-capture-v1` policy, report root
`~/.hermes/reports/nyarlathack-killed`) show this. Footsteps was admitted in
7 games, and all 7 trials had `contacts` 0 (so `min_dist` ≥ 2). In 5 of the
7 it moved only 1–5 of 64 steps (blocked 59–63), mostly because the pet or
the room stood on its trail. Any absolute contact or closeness floor in the
engine would therefore refuse footsteps in most of those games. That breaks
"footsteps must still pass everywhere" and changes no-model play from main.
