# #200 options A and C: before and after sweep

Sam's decision (2026-09-29): a next-use program is admitted at the next safe point on whatever level the player is on, and the effect lands on that level (A). A second whistle refreshes the origin even when the earlier one was on another level (C).

## Method

- **Command:** the same one twice, `scripts/seed_sweep.py --seeds 1-100 --policy baseline-v1 --starts bard,madman,bard-inherited --jobs 2`. It uses the default ordinary path with next-use on and the echo hound off, as in `sweep_player.LAUNCHER`.
- **Before:** `origin/main` at `03faaded3`, built with CHAOS=1 (0 warnings) into its own game directory. The report's `revision` field names the checkout the sweep script ran from; the binary is main's (`dnethack_sha256` 679f0518…).
- **After:** branch head `b90ce7ebf` (engine change; the later commit changes only tests and guide text), built with CHAOS=1 (0 warnings), `dnethack_sha256` 0c77b540….
- **Check of the before run:** main's sweep reproduces the committed #196 report (`baseline-v1-seeds-1-100-196-lifetime-300.json`) exactly. Every start has the same stage counts, and all 300 games have the same command count and outcome.
- **Comparison:** `compare.py` counts games reaching each stage and each game's loss reason, and lists per-game transitions.

## Result (games out of 100 per start)

| Start | Envelope published | Admitted | Native effect | Delivered | Games with `level_mismatch` | Games with `no_companion_in_view` | Same play before and after |
|---|---:|---:|---:|---:|---:|---:|---:|
| bard | 86 → 86 | 17 → 47 | 11 → 25 | 6 → 9 | 52 → 0 | 28 → 28 | 98/100 |
| bard-inherited | 75 → 75 | 28 → 32 | 15 → 19 | 5 → 6 | 16 → 0 | 25 → 25 | 99/100 |
| madman | 16 → 16 | 1 → 9 | 0 → 1 | 0 → 1 | 11 → 0 | 0 → 0 | 99/100 |

Across all 300 games: admitted 46 → 88, native effect 26 → 45, delivered 11 → 16.

- **`level_mismatch` is gone:** 79 games before, 0 after.
- **The companion requirement still binds:** the #196 "companion in view" rows are unchanged (28, 25 and 0 games). Every game that was rejected for both reasons is now rejected for the companion alone.
- **Bard, admitted 17 → 47:** this matches the #200 reclassification estimate (at most 50 with A and C together).
- **Play changes only where an effect lands:** 296 of 300 games have the same command count and outcome. The 4 that differ are games where an admitted program now changes a companion's move.

## Where the new admissions end (Bard)

Admitted rose by 30, from 17 to 47:
- 11 games reached the native effect but it was not delivered, and 3 were delivered.
- In 11 games the program expired without a whistle.
- In 5 games the whistle was suppressed (#176).

Among the other games that had `level_mismatch`:
- 17 are now rejected only for `no_companion_in_view`.
- 5 are still rejected for an expired or unbound origin.

The madman start, which rarely stays on one level long enough, goes from 1 admission to 9, with its first delivery.

## Capture: Bard seed 41

This is a real ordinary game with the same commands before and after.

- Before: the program was rejected (`level_mismatch`, `origin_expired`, `origin_superseded`).
- After, from the game's journal and events:
  - The published whistle origin is root 9, on Dlvl 1.
  - A later whistle on Dlvl 1 at move 248 (root 119) refreshes it: C. The admission row records `origin_roots [9]`, `bound_roots [119]`, `bound_moves [248]`.
  - The player descends at turn 326 (`level_leave`, then `level_enter`, then safe point 2).
  - The program is admitted at that safe point on Dlvl 2 (`admission_move 326`, `level_token 100002`): A.
  - The next whistle on Dlvl 2 triggers the companion's move, which is published and delivered. The event log shows `spent 1` at the player's death on turn 669.
- On screen, "The next whistle may call unusual attention." appears once, on Dlvl 2 at T:326.

## Files

On the VPS, in `~/.hermes/reports/nyarlathack-200/`:
- `before/`, `after/`: the reports, sweep logs, revisions, and per-game work directories.
- `before_after.json`: the full comparison.
- `196-vs-main.json`: the reproduction check.
- `compare.py`, `before.sh`, `gates.sh`, `gates2.sh`.
