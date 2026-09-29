# Companion eligibility for the next-use whistle (#196)

Tier A evidence for the pull request that fixes #196. Sam's decisions on the
design proposal (#195) were:

- **A2:** any visible tame companion with dog data (`MX_EDOG`) qualifies.
- **B1:** with several in view, the nearest wins.
- **C3:** a program with a whistle (W) operation is admitted only if a
  qualifying companion is on screen at the safe point.
- **C0** at the whistle itself: unchanged.
- The suppression reason is recorded.

Terms used here:

- **Safe point:** one of the moments the engine may admit a published
  next-use program (level entry, prayer, sleep, the sanity threshold).
- **Admitted:** the program passed every check and the budget was charged.
- **Armed:** at the first whistle after admission the engine bound a
  companion (effect outcome 1).
- **Delivered:** the companion's extra-attention move was shown on the map
  and the player saw "The whistle's echo sharpens your visible companion's
  attention." (effect outcome 3).
- **Suppressed:** admitted, but no qualifying companion was in view at that
  first whistle, so nothing was armed (effect outcome 2).

Raw data, scripts and logs are on the VPS in
`~/.hermes/reports/nyarlathack-196/`, with a `SHA256SUMS` file. Only the two
sweep report files are copied into `docs/measurements/seed-sweep/`, as for earlier
sweeps; none of the raw data is copied.

## Commit tested

- The gates (builds, fast and native suites), the sweep and the capture all ran
  at `4f0689c09`.
- Commits after it add only this entry, the sweep report and the PR text.
- The base is `origin/main` at `931e574e6`, which includes #193.

## Builds

Both builds ran under `hermes-heavy` with `make -j2 install`.

| build | exit | warnings |
|---|---|---|
| `CHAOS=0` | 0 | 0 |
| `CHAOS=1` | 0 | 0 |

Logs: `gates/build-chaos0.log`, `gates/build-chaos1.log`.

## Suites

Both suites ran under tmux into log files.

| suite | tests | result | skipped |
|---|---|---|---|
| fast | 1444 | OK | 218 |
| native (`prepare_native_ci.py` + `run_native_tests.py`) | 1444 | OK | 13 |

The native suite includes the stock-equality, save/restore and replay tests.
Logs: `gates/fast.log`, `gates/native-full-suite.log`, `gates/summary.txt`.

The first native run, at `f167c95e3`, had 2 failures, both in the haunt
first-come-first-served fixture. That fixture's map holds no monsters, so C3
now refuses its whistle program before the budget is compared. Its fix is
listed under "Changed expectations" below.

## New linked tests

All of these link the real engine objects and are opt-in with
`NYARLATHACK_GAME_TESTS=1`.

| test | what it pins |
|---|---|
| `test_next_use_dogmove.py::test_extra_attention_on_other_companion_types` | The extra-attention move on a dog, a large dog, a kitten, a housecat and a pony, as well as the little dog. In each case the companion stays tame and peaceful, ends nearer the player, and the move is published on the map. |
| `test_next_use_dogmove.py::test_pick_nearest_wins` | B1: of several qualifying companions in view, the nearest to the player by squared distance is picked. |
| `test_next_use_dogmove.py::test_pick_tie_top_row_then_leftmost` | B1 ties: the top row wins, then the leftmost column. |
| `test_next_use_dogmove.py::test_pick_ignores_list_order_and_m_id` | Reversing the monster list and swapping `m_id` values does not change the pick. |
| `test_next_use_dogmove.py::test_pick_draws_no_rng` | The pick draws no RNG: the fixture compares the reseed counter before and after. |
| `test_next_use_dogmove.py::test_pick_reports_why_none_qualified` | No companion in view → `none_in_view`. Only a non-qualifying tame monster in view (for example a leashed one) → `not_eligible`. |
| `test_next_use_safe.py` (C3 cases) | No companion in view: rejected with `no_companion_in_view`, nothing charged, no telegraph, reason in the receipt. One in view: admitted exactly as before. A program with only a fountain (F) operation never consults the check. |
| `test_next_use_journal_w.py` (suppression cases) | Each recorded reason round-trips through the journal, and the old path with no recorded reason is byte-identical. A journal whose transition reason and effect-row reason disagree is rejected. |
| `test_haunt_lifecycle.py::test_no_companion_in_view_refuses_w_before_budget` | The production check on an empty map refuses the whistle program before any budget is taken or any telegraph is shown. |
| `test_seed_sweep.py` (suppression cases) | The sweep funnel reports suppressions by recorded reason, and journals written before #196 report `unrecorded`. |

None of the new companion types misbehaved in these tests. There were no
hostile turns, no stuck moves, no crashes, and no move the player could not
see.

## Changed expectations

- `tests/chaos/haunt_lifecycle.c` (`fcfs`): the fixture now binds a test
  companion that is always in view. That keeps the two existing budget-order
  tests about budget order; their expected receipts and spends are unchanged.
  A third order, `no-companion`, runs the real check.
- `chaos/prompts/next-use-mechanics-sources.json`: the pinned hashes of
  `src/chaos_engine.c`, `src/chaos_next_use_runtime.c`,
  `src/chaos_next_use_safe.c` and `src/dogmove.c` are rebound. The guide text
  describes neither the companion rule nor the admission reasons, so it
  needed no change.
- `docs/upstream-chaos-hooks.json`: the `dog_move` hook line's signature
  changes from `PM_LITTLE_DOG` to `mtmp->mtyp`. It is still one line.
- `docs/next-use-whistle.md`, `docs/next-use-ordinary.md`, and the Limits text
  in `scripts/seed_sweep.py` now say "qualifying companion" where they said
  "little dog" or "exactly one".
- The telegraph and delivery message texts were already species-neutral and
  are unchanged.
- The protocol contract was regenerated with
  `scripts/generate_protocol_contract.py`. There is no diff, because admission
  reason names are not part of the generated contract.

## Fresh sweep (also the #164 baseline)

The fresh sweep is `docs/measurements/seed-sweep/baseline-v1-seeds-1-100-196-lifetime-300.{json,md}`:

- Policy `baseline-v1`, seeds 1–100, starts bard, madman and bard-inherited.
- Origin lifetime 300, sweep clock unchanged, under `hermes-heavy`, at
  `4f0689c09`.
- Report digest `a6814c4b…9da6`.

It is compared with the committed
`baseline-v1-seeds-1-100-rebind-lifetime-300` report at `1e3c7af`. The seeds
are the same, so the games are paired, and every game ended the same way
(death, turn limit and so on) in both runs.

| games reaching the stage | before (`1e3c7af`) | after (`4f0689c09`) |
|---|---|---|
| published | 177 | 177 |
| admitted | 68 | 46 |
| armed (native effect) | 18 | 26 |
| delivered | 9 | 11 |

- **Suppressed at the whistle:** 30 before, 4 after. All 4 are recorded
  `none_in_view`: bard 57, and bard-inherited 39, 78 and 79. In each, a
  companion was in view at the safe point but had left view by the whistle.
  No suppression was recorded as `not_eligible` or `recheck_failed`.
- **Refused by C3:** 53 safe-point decisions in 53 games (bard 28,
  bard-inherited 25, madman 0).
  - 22 of these games were refused for `no_companion_in_view` alone.
  - The other 31 were already refused for other reasons, and the new reason
    is simply added to the recorded list.
  - The madman start has no companion and was never admitted before either.
- **Newly delivered:** bard 60 and bard-inherited 55. Every game delivered
  before is still delivered.

Where each changed game went, before → after (238 games unchanged):

| before | after | games |
|---|---|---|
| refused, other reasons | refused, reasons now include `no_companion_in_view` | 31 |
| suppressed | refused by C3 at the safe point | 17 |
| suppressed | armed, not delivered | 7 |
| suppressed | delivered | 2 |
| program or origin expired after admission | refused by C3 | 3 |
| armed, not delivered | refused by C3 | 1 |
| admitted, journal incomplete | refused by C3 | 1 |

What this shows, and what it does not:

- **Measured:** C3 turns most suppressions into refusals at the safe point, so
  the budget is no longer charged, and the telegraph is no longer shown, for
  programs that could not bind a companion. A2 lets 9 former suppressions
  arm. In the pre-#196 diagnostic rerun of these same games
  (`~/.hermes/reports/nyarlathack-companion/r30-v2/`), the companion in view at
  the first whistle was a grown dog in 8 and an iguana in 1 (bard-inherited
  56); none was a little dog. That rerun used the old admission rule, so the
  whistle it saw may differ from the one that armed here. The iguana is a
  companion type not covered by the linked native tests; its game armed and
  ended unwitnessed, like the other undelivered cases.
- **Measured:** armed-but-undelivered rose from 9 to 15. The 7 new cases all
  end with the effect row "ended, no witness" (outcome 5), the same ending
  the existing undelivered cases have: the companion was armed but its move
  was not shown within the window. Nothing in these games suggests a companion
  misbehaving, but the sweep records only the ending, not the move itself.
  This conversion from armed to delivered is a natural next measurement for
  #164.
- **Not measured:** player notice or attribution (#44). The scripted player
  is not a human proxy.
- The harness errors (madman 61, bard-inherited 67) are the same two as in
  every earlier sweep.

Raw per-game artifacts: `sweep/work/` (199 MB), `sweep/sweep.log`,
`sweep/revision.txt` and `sweep/tree-status.txt`. The tree was clean when the
sweep ran.

## Real captures

Each capture is a nonwizard `chaos play --ordinary --next-use` game: keys
chosen from the screen only, no clock shim, no model call, run under
`hermes-heavy` at `4f0689c09`. The script is `capture/play.py`.

- **`capture/c2/`**, the passing capture:
  - A dog was on screen at the start, at the safe point and at the whistle.
  - The receipt shows the W origin rebound (published 8, bound 12).
  - The telegraph "The next whistle may call unusual attention." was shown.
  - The journal records "armed" (outcome 1), then "witnessed" (outcome 3), on
    the same `m_id`.
  - "The whistle's echo sharpens your visible companion's attention." was on
    screen.
  - The post-mortem reveal prompt was answered.
- **`capture/c1/`**, the same recipe in another game: admitted with the dog in
  view and armed, but the dog stayed next to the player, so the program ended
  unwitnessed (outcome 5). For c2 the script was changed to step away before
  searching.
- Both captures used the starting little dog. The new companion types are
  covered by the linked native tests above, not by a real capture: reaching a
  grown dog or a pony in scripted play needs a long game. The sweep's 7 newly
  armed games are real-play evidence that the wider rule arms in ordinary
  games.
