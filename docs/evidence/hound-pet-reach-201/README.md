# Echo hound out of the pet's reach (#201)

Tier A evidence for the pull request on #201 (Sam's decision of 2026-09-29:
option A, no fallback).

## The change

The hound's spawn square must now be more than 4 squares (Chebyshev) from
every tame monster on the level; a steed under the player does not count. The
check is one more condition in the existing placement loop in
`src/chaos_haunt.c`, so the shadow trial and live play still use one placement.
When no square qualifies, the tick returns before the trial is marked as
spent, exactly as it already did for a room with no square 3 away: nothing is
spent, written or telegraphed, and a later turn tries again. No new state, no
RNG, no save change.

## Before and after (measured)

Real nonwizard `python3 -m chaos play --ordinary` games on the default path
(hound and next-use on), fresh random maps, driven by the #190 screen driver
(`tests/chaos/haunt_explorer.Player`): pace the start room until the trial is
decided (at most 40 keys), then keep pacing until the haunt ends or 90 keys
pass. A live step is one `haunt_step` event, which the engine emits only when
the player can see the hound. Death attribution follows the game's own
messages. Before: `main` at `ef598188c`. After: this branch at `2c2f1f23d`.
Script: `~/.hermes/reports/nyarlathack-201/baseline.py`; analysis:
`impl/before_after.py` (bootstrap 95% interval on the mean).

| | Before (50 games) | After (50 games) |
|---|---:|---:|
| Hound admitted | 45 | 36 |
| Trial refused | 2 | 1 |
| Still waiting when the driver stopped pacing | 1 | 12 |
| Driver errors | 2 | 1 |
| Live steps, median / mean (95% interval) | 1 / 1.31 (0.98–1.69) | 2 / **2.25** (1.69–2.89) |
| Steps 0 / 1 / 2 / 3+ | 11 / 20 / 7 / 7 | **0** / 17 / 8 / 11 |
| Lived 10+ turns after admission | 2 | 7 |
| Turns from admission to death, median | 3 | 6 |
| Killed by the pet / the player / expired alive | 41 / 3 / 1 | 26 / 9 / 1 |
| Admission turn, median / latest | 6 / 14 | 9 / 23 |

- **No hound dies unseen any more.** Before, 11 of 45 hounds died without one
  visible step; after, none did. Mean visible steps rose by about 70%.
- **The player now kills the hound more often** (9 against 3): it survives long
  enough to reach them.
- **The cost is waiting.** The 12 "still waiting" games had not placed the
  hound when the driver's 40 keys of start-room pacing ran out: the pet stayed
  within 4 squares of every candidate square. Nothing was spent in those
  games; in real play the trial is tried again on every later turn with a
  remembered backtrack. The 25-game scratch run of the same rule (mean 2.90,
  in the first #201 comment) is within noise of this one.

## Capture

Game 36 of the after run, a real nonwizard default-path game (74-square start
room): the hound is admitted on turn 13 (event row) with the telegraph "Something has
learned the rhythm of your footsteps.", follows the player visibly on turns
14–22 (9 `haunt_step` events; it appeared 7 squares from the pet), and is then
killed by the little dog. Game 18 shows 7 visible steps. Both are under
`~/.hermes/reports/nyarlathack-201/impl/capture/` (`terminal.raw`, `run/`,
`xlogfile`).

## Tests

- `tests/chaos/test_haunt_room.py` (linked, real haunt tick and forked trial):
  - `test_pet_near_every_candidate_no_spend`: four rooms where the pet is
    within 4 of every candidate square; five ticks each spend nothing, write
    no files, emit no haunting event, show no telegraph and draw no RNG.
  - `test_pet_moves_off_then_trial_runs_later`: the same 12x6 room; nothing
    happens while the pet is beside the player, then the pet moves to the far
    corner and the next tick places the hound and runs the one trial.
  - `test_start_stairs_with_pet_waits`: the #190 start-stairs rooms with the
    pet beside the stairs, and the 4x3 "cornered" pocket, now wait instead of
    spending the trial.
- `tests/chaos/test_haunt_ordinary.py::test_start_room_first` (real game): in
  the fixed 12-square start room with the pet beside the player, pacing leaves
  nothing spent or written; after leaving for a larger room the trial is
  decided there once, admitted, with one debit of 2.

## Raw data

`~/.hermes/reports/nyarlathack-201/`: `raw/baseline-*.jsonl` (before),
`raw/after-A.jsonl` (after), `impl/before_after.json`, gate logs in
`impl/gates/` (branch head) and `impl/gates2/` (after merging `main`).
