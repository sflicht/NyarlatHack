# Broad next-use program restores on a deeper level

Tier A evidence: the change alters which saves restore.

## The bug

Since #235, a broad (C, snapshot v7) next-use program survives level changes.
`restore_snapshot` (`src/chaos_next_use_runtime.c`) still applied the
single-use rule to every live snapshot: the program's admission
`level_token` must equal the level being restored. So a broad program
admitted on one level and saved on a deeper one could not be restored. The
game printed "Incompatible CHAOS save state; save file preserved." and
stopped. The paired sweep for #238 found it: main bard seed 10, and ring
bard-inherited 26 and bard-default-path 42.

## The rule

What the same-level check protects. A single-use program ends on level
departure: `chaos_next_use_runtime_boundary` expires it
(`CHAOS_END_LEVEL_DEPARTURE`) as soon as the current level differs from its
`level_token`. A live single-use snapshot on another level therefore cannot
come from play. It is foreign or tampered state, and refusing it keeps one
level's capability from following the player. That stays exactly as it was.

For a broad program:

- the program itself is level-independent: the boundary keeps it alive on a
  new level, so its admission level binds nothing on restore;
- an open W window (`w_runtime == CHAOS_W_RUNTIME_ARMED`) is tied to the level
  it armed on (`armed_level_token`). The boundary ends it on departure, so a
  snapshot whose window is still open for another level also cannot come from
  play. **It stays a refusal**: restoring it would give a companion on the new
  level attention that was bound to the old one. `chaos_next_use_snapshot_validate`
  already requires `armed_level_token` to be nonzero exactly when a window is
  open, so the restore check need not re-derive that.

The change: `restore_level_bound_ok`, `src/chaos_next_use_runtime.c:2568`,
used at `src/chaos_next_use_runtime.c:2612` in place of
`snap.level_token != level_token`. Terminal history is unchanged (it never had
the check). Game token, tamper and digest checks are unchanged and still run
first. The admission `level_token` stays inside the binding digest.

The new rule refuses nothing the old one accepted in reachable play. The only
state it would newly refuse is a broad program restored on its admission level
with a window open for some other level. Reaching that would mean returning to
the admission level without a boundary, and the boundary would have closed the
window.

One edge is unchanged, not fixed (by reading the code; not tested): a hangup save taken between arriving on a
level and the next `chaos_observe` boundary still carries the old level's open
window (or, for single-use, the old level's live program) and is refused, as
before. A normal `#save` is a command, so the boundary at the top of the main
loop has always run first.

## Tests (`tests/chaos/test_next_use_broad.py`, fixture `next_use_broad.c`)

- `test_broad_program_saved_on_a_deeper_level_restores_live` (W and F): admit
  on level 1, deliver one use, descend, save, restore on level 2. The program
  is live (`phase` committed, v7, delivered 1), the journal resumes, and the
  next use delivers (delivered 2, terminated). Wrong run token is still
  refused. These are v7 snapshots, the C-era format; main has no v8. The
  ring v8 case belongs in #238 after it merges main.
- `test_single_use_control_ends_at_the_descent_before_the_save`: the
  single-use control has already ended at the descent; its terminal history
  restores and answers nothing.
- `test_live_snapshot_restored_on_another_level`: a live snapshot restored on
  another level with no boundary in between. Single-use is refused (W, F);
  broad with no open window is restored.
- `test_open_window_snapshot_is_refused_on_another_level`: an open window
  armed on level 1 is refused on level 2 and restores on level 1.
- `test_tampered_broad_snapshot_is_refused`: now also tampers `level_token`
  (digest) and `armed_level_token` (window consistency); both refused.
- `test_replay_holds_across_the_cross_level_restore` (W and F): every
  transition before the save and after the restore replays exactly once into
  the engine's shadow runtime and the duplicate is blocked (W 12 applied,
  F 6, 0 failures).

At 1c5f81a6b (before the replay test existed), reverting only the runtime
change made the deeper-level and the broad another-level tests fail (4
subtests: W and F of each); the other 17 tests passed.

## The real failure (`sweep-seed/`)

Rebuilt `origin/main` (3b89f6e2a, the sweep's main revision) and the fix in
separate exports, same `nhdat` (b7fc1a3a). `scripts/repro-sweep-seed.sh` runs
`scripts/seed_sweep.py --seeds 10-10 --policy baseline-v2 --starts bard`, the
sweep's own command:

- main: `harness_error`, sessions `new` only; terminal shows "Restoring save
  file... Incompatible CHAOS save state; save file preserved." The saved
  header is a v7 broad W program, `level_token` 100002 (DL2), saved on DL3.
- fix: sessions `new`, `restore`; the bot plays on to its death at turn 729.

Ring bard-inherited 26 reproduced on every run, but it needs ring's admission,
so on main the reproducible case is bard 10.

**The save preserved by the old build.** `scripts/restore_preserved.py` takes
the exact save file the sweep's main build preserved (sha256 0e3fe633…,
from the #238 artifacts) with its run directory, and restores it with each
binary under the sweep clock (seed 10):

- main binary: refused again ("Incompatible CHAOS save state");
- fix binary: restores (session `restore`), plays ten more turns to T:712 on
  DL3, and saves again cleanly (exit 0).

## Real nonwizard capture (`capture/`)

`python3 -m chaos play --ordinary`, the default launcher (hound and next-use
on), driven by the sweep bot's public keystrokes. No clock shim (an empty
preload), no wizard mode, no model call. Every attempt is listed:

1. `attempt-turn700-1..3`: the bot's usual save at turn 700. All three saved
   and restored, but every broad program had already ended before the save,
   so none was a cross-level case.
2. `attempt-dlvl-1..8` (`scripts/capture2.py`): save on the first status line
   deeper than a live broad program's admission level. No save happened: in
   each game every broad program had ended before the bot, which stays at
   least 300 turns on a level, went down a level.
3. `attempt-dlvl-fast-11`: the same driver with the bot's per-level minimum
   lowered to 30 turns (`CAPTURE_MIN_TURNS=30`). The first game was the case:
   a broad W program admitted at turn 925 on DL2 (telegraph "For a while, your
   whistles may carry farther than they should."), the bot descended, saved
   on DL3 at turn 1033 ("Be seeing you..."), restored ("Restoring save
   file...", "welcome back"), and played to the 2000-turn limit. The journal
   kept running on DL3 after the restore (144 more transitions) until the
   program ended at turn 1151. No use reached the program's callback before
   it ended (`callback_ordinal` stayed 0), so there was no delivery after the
   restore. Delivery after a cross-level restore is shown by the native test
   above. The batch stopped
   after this success; attempts 12-18 never ran.

These are unseeded games: they show the path in real play, not a
reproducible replay.

## Gates

At a06e54f1f (final engine and author binding; later commits are tests and
docs): CHAOS=0 and CHAOS=1 builds 0 warnings; ruff check/format clean; fast
suite 1627 tests OK (233 skipped); native suite (`prepare_native_ci.py` +
`run_native_tests.py`) 1627 tests OK (13 skipped). This includes the stock
equality and CHAOS-off tests (`test_stock_inactive_and_on_empty_equal`,
`test_invalid_combinations_are_noops`, the replay suites). After the replay
test commit, `test_next_use_broad` 22 tests OK.

`chaos/prompts/next-use-mechanics-sources.json` hashes
`src/chaos_next_use_runtime.c`, so the author guide was rebound to the new
source revision (same bytes, same size; no guide text changed).

## No sweep

Gameplay is unchanged apart from saves that now restore. The change is one
predicate read only by `restore_snapshot`, which runs only when a save is
loaded. It draws no RNG, and admission, budget, effects, the boundary and the
save writer are untouched. A game that never saves is unchanged. A save the old
rule accepted takes the same path, and the new rule refuses nothing the old
one accepted in reachable play. The only behaviour change is that a save the
old build refused now continues.
