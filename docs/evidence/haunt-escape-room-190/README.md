# Haunt: step around squares the hound cannot use (#190)

Tier A evidence for PR #193. The change is in `chaos_haunt_pick`
(`src/chaos_haunt.c`). When the square the footsteps pack asks for is not a
legal step, the hound used to stay put. Now it takes the legal candidate
nearest to that square. "Not a legal step" covers three cases: another monster
stands on it, it is not plain floor (stairs, doorway, furniture), or the game's
own move list (`mfndpos`) does not offer it. The shadow trial and live play go
through this same code path.

Raw data, scripts and logs are on the VPS in
`~/.hermes/reports/nyarlathack-190/`, with a `SHA256SUMS` file. None of it is
copied here.

## Commit tested

- Gates (builds, fast and native suites) ran at `6921d2b6c`.
- The PR head `8cb63c7dd` adds only a README wording change on top of that.
  This evidence entry is also docs-only. GitHub's Required Quality CI ran on
  the PR head.
- The base is `origin/main` at `337a1929c`.

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
| fast | 1429 | OK | 209 |
| native (`prepare_native_ci.py` + `run_native_tests.py`) | 1429 | OK | 13 |

The native suite includes the stock/empty-mailbox equality, save/restore and
replay tests, and the new tests below. Logs: `gates/fast.log`,
`gates/native-full-suite.log`, `gates/summary.txt`.

## New linked-engine tests

`tests/chaos/test_haunt_room.py` drives `tests/chaos/haunt_room.c`. That
harness links the real engine objects and wraps only `pline`. It runs one of
two things:

- a single real `chaos_haunt_pick` over the real `mfndpos` candidates; or
- the real haunt tick and forked shadow trial, in a lit room built by the test.

Every pick case brackets the pick with the native RNG check
(`test_rng_begin()` / `test_rng_unchanged()`), so the fixture fails if the pick
draws any RNG. The tests are opt-in via `NYARLATHACK_GAME_TESTS=1`.

| test | what it pins |
|---|---|
| `test_pick_steps_around_pet_on_requested_square` | Pet on the requested square: the hound takes the nearest legal square, and ties go to `mfndpos` order (x first). |
| `test_pick_never_steps_next_to_player_when_request_was_not` | The step-around never creates adjacency to the player. |
| `test_pick_stays_put_when_no_step_is_nearer` | Only a candidate strictly nearer the requested square is taken; otherwise the hound stays put. |
| `test_pick_request_for_player_square_stays_put` | A request for the player's own square still never moves the hound. |
| `test_pick_steps_around_start_stairs` | The requested square is the player's starting up staircase: the hound steps around it. |
| `test_pick_steps_around_stairs_on_the_way` | Stairs between the hound and its target: the hound steps around them. |
| `test_pick_doorway_diagonal_stays_illegal` | A diagonal into a doorway is never taken; the hound takes the orthogonal square beside it. |
| `test_pick_doorway_straight_stays_put` | From the square beside a doorway, no candidate is strictly nearer, so the hound stays put. |
| `test_pick_free_request_unchanged` | A legal, free requested square is taken exactly as before. |
| `test_pet_on_hound_target_trial_passes` | Whole trials with the pet on the hound's target (4×4, 5×4, 5×5). On main these rejected with moved 1, blocked 63; now they pass. |
| `test_start_stairs_trial_passes` | Whole trials pacing from the start staircase with the pet beside it (5×4, 6×4) pass. |
| `test_cornered_residual_documented` | The accepted cornered residual (4×3 room, stairs and pet) is pinned as rejected. The fix is tracked in #194. |
| `test_bare_rooms` | A 3×3 room spends nothing and writes neither `haunting-used.lua` nor `dreamlands.json`. 4×3, 6×4 and 12×6 pass. |

`tests/chaos/test_haunt_ordinary.py::test_start_room_first` is a new terminal
test. It paces in the 4×3 replay-clock start room first, then in a larger
room. It records the trial:

    {"accepted": 1, "sandboxed": 1, "steps": 64, "moved": 63, "blocked": 1,
     "contacts": 36, "died": 0, "script_errors": 0, "escaped": 1, "max_damage": 2}

It also checks that there is no second trial and no second charge
(`chaos_admitted=2`, `chaos_spent=2`). This fixed map already passed its trial
on main, so this test shows that start-room pacing works end to end; the
linked tests above are the ones that reproduce the old failure.

## Real-game sweep

Each column is 114 real nonwizard `chaos play --ordinary --haunt` games, with
no clock shim and no model call. Each game paces in its start room until the
one trial is decided, driven by `startroom.py` under `hermes-heavy`.

- **Stuck:** the hound moved at most once and never made contact.
- **Cornered:** the trial's evasive bot never got 3 squares away.
- **Caveat: the maps are unpaired.** Each run drew fresh maps, so the columns
  compare populations, not the same games.

Each cell is trials / pass / stuck / cornered.

| start-room floor squares | main (`337a1929c`) | occupied squares only | widened (PR #193) |
|---|---|---|---|
| ≤12 | 12 / 9 / 2 / 1 | 13 / 11 / 2 / 0 | 9 / 7 / 1 / 1 |
| 13–20 | 21 / 16 / 4 / 1 | 23 / 19 / 4 / 0 | 27 / 22 / 0 / 5 |
| 21–30 | 26 / 23 / 2 / 1 | 20 / 17 / 3 / 0 | 27 / 26 / 1 / 0 |
| 31–45 | 25 / 20 / 4 / 1 | 36 / 34 / 2 / 0 | 25 / 24 / 1 / 0 |
| ≥46 | 29 / 28 / 0 / 1 | 18 / 18 / 0 / 0 | 23 / 23 / 0 / 0 |
| **total** | **113 / 96 / 12 / 5 (15.0% rejected)** | **110 / 99 / 11 / 0 (10.0%)** | **111 / 102 / 3 / 6 (8.1%)** |

Raw rows:

- main: `real-noclock-24.jsonl` and `real-noclock-90.jsonl`
- occupied squares only: `real-after-114.jsonl`
- widened: `real-widen-114.jsonl`

The table comes from `beforeafter.py`.

## Residual after the widening: 9 of 111

Each failed trial was classified by replaying its recorded screen in the
traced harness (`classify.py`, `screen2map.py`). The screens are recorded
after the trial, so pet positions in the replays are approximate.

- **Cornered, 6.** This residual was accepted for #190 and is tracked in
  #194. The hound reaches the bot and asks for the bot's own square, which it
  may never take. The bot walks only plain floor, so stairs, water, furniture,
  doorways and the pet box it into a pocket with no square 3 or more away.
  Replaying the main-branch cornered screens gives the same failing report on
  both builds. The change to 0 and then 6 cornered across the runs is
  therefore not evidence that the widening causes cornering; the maps are
  unpaired.
- **Stuck, 3.** In two, the hound starts where the game offers it at most one
  move and none is strictly nearer (for example, beside a closed door or a
  pool). The third does not stall when replayed from its screen.

## Real capture

Nonwizard `chaos play --ordinary --haunt`, keys chosen from the screen only,
no clock shim, no model call, run under `hermes-heavy`. Files are in
`capture/c2/`: `terminal.raw`, `inputs.txt`, `notes.txt` and the run
directory.

- It paced in its 12-square start room first. The trial report was
  `{"accepted":1,"moved":63,"blocked":1,"contacts":20,"escaped":1}`.
- The telegraph "Something has learned the rhythm of your footsteps." was on
  screen.
- One live `haunt_step` was recorded, and the haunt later expired.
- The script's final phase (dying to reach the reveal) did not finish, so this
  capture has no reveal screen. The reveal is covered by `test_reveal.py` and
  the #165 capture.
- An earlier attempt, `capture/c1-truncated/`, was cut off by a tool timeout
  after its trial passed in a 44-square start room.

## Existing hound-path evidence

`docs/evidence/milestone2-runs/haunt/` predates #190 and is left unchanged. No
test replays it. If it were replayed in a room where the hound's trail crosses
stairs, a doorway or the pet, the hound may no longer take the recorded path.
