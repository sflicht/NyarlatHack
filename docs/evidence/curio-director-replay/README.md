# Director curio lane: engine-authoritative admission and replay (slice 3a)

Tier A evidence. It shows three things:

- the director's curio lane publishes a curio in a real game;
- the engine, not the director, fixes the safe index at which the curio is admitted;
- a replay staged from that engine-logged index reproduces the game.

It also shows that a configured lane whose trigger is never met leaves the game unchanged.

Test: `tests/chaos/test_curio_director_gameplay.py`. It ran as a real game under
`hermes-heavy` with `NYARLATHACK_GAME_TESTS=1` and the test clock
(`tests/chaos/replay_clock.c`), on the `CHAOS=1` build of this branch (build
exit 0, 0 warnings). The slice 2b replay test ran in the same job and still
passes.

## Why no director/engine lock

Whisper replay is deterministic because the engine applies a logged request
only at its logged safe index (`at`). `chaos_protocol.c` defers a future `at`
and rejects one that has passed. The curio now does the same:

- **Live play.** The director publishes `curio.lua` with write-temp, fsync, then
  rename. The engine admits it at the first eligible safe point at which it
  reads it. The engine's `curio`/`pre_admitted` event records that index, and
  `curio-used.lua` holds the bytes it read. `record_admission` writes
  `admission.json` (that index plus the SHA-256 of those bytes) into the
  evidence. The `safe` in `install.json` is what the director observed, and
  it is advisory only.
- **Replay.** `stage_replay` (or `chaos replay --curio-evidence`, or `chaos curio
  replay-stage`) writes the logged source and `curio-safe`, which holds the
  engine's logged index, before the game starts. `chaos_curio_safe` leaves the
  curio untouched while `safe < at`, admits it at `safe == at`, and rejects it
  once the index has passed.

No timing between processes is involved.

## Record and replay (`equivalence.json`)

1. **Record.** A wizard-mode game starts with a fresh lane record
   (`record/curio-lane.json`, which holds the ledger game id and the
   literary-layer seed). At the first observed safe point (`safe` 1) the real
   `CurioLane` runs:
   - `poll()` returns `requested`;
   - authoring runs on the background thread through the product path:
     configured provider `xai-oauth`, a fake transport, no model;
   - the next `poll()` returns `published`.

   The ledger shows exactly one reserved send, under the recorded game id. The
   test forces only `trigger_ready`, so that a short game reaches this path;
   the thresholds are covered offline in `test_curio_director.py`. The 23-key
   tape from slice 2b follows.

   | | safe index |
   |---|---|
   | director observed (`evidence/install.json`, advisory) | 1 |
   | engine admitted (`pre_admitted` event, `evidence/admission.json`) | **2** |

   The publication landed after safe point 1. The engine read it at safe point
   2, on arrival on level 2. Level 3 placed the whistle (`pre_admitted`,
   `admitted`, `placed`).
2. **Replay.** A fresh game, with the same clock and binary. `stage_replay`
   wrote `replay/curio-safe` (`2`) and `curio.lua` before the game started.
   `XaiBackend.generate`, `author_curio` and `build_backend` were patched to
   raise. The source was therefore present at safe point 1, yet the engine
   admitted it only at 2.
3. **Compared:**

   | Artifact | Result |
   |---|---|
   | `events.jsonl` | byte-identical (`record/`, `replay/`) |
   | `curio-used.lua`, `curio.lua` | byte-identical; equal to `evidence/source.lua` |
   | engine admission (index, SHA-256) | equal: `verify_replay` and `CurioReplayBackend.verify_admission` |
   | input tape | identical (23 inputs) |
   | final save (355072 bytes) | identical, except the process id and raw pointers (the same exclusions as in `../curio-grounding-replay/`) |
   | `xlogfile` | identical (empty: both games end by saving, not by death or quit) |

## Configured lane, trigger never met (`untriggered/`)

Two wizard-mode games ran with the same clock and the same 15-key tape:

- `empty`: event stream on, empty mailbox;
- `lane-idle`: a fresh lane record and a real `CurioLane`, polled after every
  key with the engine's latest event. It stays `idle`, since turn < 150.

The two games produced identical terminal output, inputs, `events.jsonl`
(SHA-256 `450e34c9…`) and `xlogfile`. They wrote no `curio.lua` and no curio
events. The only extra file in the run directory is `curio-lane.json`, which
the engine never reads.

Together with the existing stock comparison (`test_gameplay.py`,
`test_stock_inactive_and_on_empty_equal`: stock, inactive and empty-mailbox
games are equal), this extends "no whisper equals stock" to a configured lane
that never fires.

## Not shown here

- No live model call. The live capture is slice 3b.
- Bones: the lane writes only under the run directory. The bones paths are
  covered by the existing native `test_curio_bones*` tests, which pass in the
  full native suite on this branch.
