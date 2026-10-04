# Curio replay equivalence and placement RNG (slice 2b)

Tier A evidence: replay of a model-authored curio, and whether the curio's
placement draws from the game's random number generator (RNG).

## What was shown

A recorded curio game replays to identical events and the same final state.
The replay installs the logged source at the logged safe point and never
calls a model or regenerates.

Test: `tests/chaos/test_curio_replay_gameplay.py`, a real game run under
`hermes-heavy` with `NYARLATHACK_GAME_TESTS=1` and the test clock
(`tests/chaos/replay_clock.c`), on the `CHAOS=1` build of this branch.

1. **Record.** A wizard-mode game starts, and its first safe point is
   observed (`safe` 1). `chaos.curio_author.author_curio` then authors a curio
   through the product path: the configured provider `xai-oauth`, a fake
   transport returning a handwritten envelope (no model), and the
   history-grounded prompt with the seeded layer. `curio_author.install`
   publishes it and records `safe: 1` in `install.json`, as the director
   would. A fixed 23-key tape follows:
   - the next safe point (arrival on level 2) admits the curio
     (`pre_admitted`, `admitted`);
   - the fresh level 3 places the whistle (`placed`);
   - eight moves and four searches follow, then the game saves.
2. **Replay.** A fresh game runs with the same clock and binary.
   `chaos.curio_replay.CurioReplayBackend` reads `evidence/`, verifies its
   hash chain, and at `due(1)` installs the logged `source.lua`. During the
   replay `XaiBackend.generate` and `curio_author.author_curio` are patched
   to raise, so any model call or regeneration would fail the test. The same
   tape is sent and the game saves.
3. **Compared** (`equivalence.json`):

   | Artifact | Result |
   |---|---|
   | `run/events.jsonl` | byte-identical (`record/`, `replay/` here) |
   | `curio.lua` and the engine's own `curio-used.lua` | byte-identical; `CurioReplayBackend.verify` cross-checks `curio-used.lua` |
   | `xlogfile` | byte-identical |
   | input tape | identical |
   | final save (355072 bytes) | identical, except the game's process id and raw in-memory pointers |

   On the save, `save_differences` excludes exactly two kinds of bytes:

   - the game's process id (`hackpid`), which dNetHack writes into the save
     header and every level record;
   - 8-byte values that are user-space addresses in both files. dNetHack
     serialises some raw struct pointers, and address-space layout
     randomisation (ASLR) moves them on every run.

   Any other differing byte fails the test, and none remained. The two
   committed save hashes differ only because of these excluded bytes.

## Does placement's `mksobj(WHISTLE)` draw RNG?

**No.** Placement calls `mksobj(WHISTLE, MKOBJ_NOINIT)`. A linked native
probe counts draws with the same oracle as `tests/chaos/native_rng.h`:

- counted `rn2`-family draws, via the globalised `reseed_count` in a copy of
  `src/rnd.o`;
- any raw `random()` call, detected by comparing the next draw.

`rng-probe/probe.out`:

```
mksobj(WHISTLE,MKOBJ_NOINIT) draws=0 raw_random=0     (x5)
full placement draws=0 raw_random=0 creates=1 placed=1 (x3)
```

From the source, `mksobj_core` with `init` false reaches no `rn2` call for a
whistle:

- `init_obj_material` gives a plain tool its base material;
- whistles are not `is_multigen`;
- the `INVISIBLE_OBJECTS` roll sits inside `if (init)`.

The full placement (`chaos_curio_finish`: the square choice, `mksobj` and
`place_object`) draws nothing either. Square selection scans in a fixed order
and does not roll.

**Why it matters for replay:** placement cannot shift the game's random
stream, so a replayed curio leaves every later roll where the recorded game
had it. The existing linked fixture now asserts this
(`tests/chaos/curio_placement.c`: `test_rng_unchanged` around the first
placing generation). The native suite runs that fixture, including its
`--rng-negative-control` and `--raw-rng-negative-control` cases, which must
abort.

## Files

- `equivalence.json`: the test's summary.
- `evidence/`: the recorded curio's run evidence, as `curio_author` writes it:
  - `prompt.json`: the exact instructions and prompt, layer, public-context
    hash and prompt hash;
  - `raw-response.txt`: the exact transport response;
  - `source.lua`: the installed source;
  - `receipt.json`: the outcome, hashes, native validation and transport
    receipt;
  - `install.json`: the logged safe point.
- `record/`, `replay/`: `events.jsonl`, `curio.lua`, `curio-used.lua`,
  `curio-install.json`, `inputs.json`, `manifest.json`, `xlogfile`.
- `rng-probe/`: `probe.c.txt` (C source, kept as text so the upstream hook
  inventory does not scan it as a native path), a probe linked like
  `curio_placement.c` with
  `controlled_rng_objects`, and its output `probe.out`.

## Limits

- One recorded game, with a handwritten curio and the deterministic test
  clock. Equivalence holds for the same binary, nhdat and clock. A real
  model-authored source replays through the same path, because replay only
  ever reads `source.lua`.
- The replay installs at a safe-point index. If a replay passes that index
  before installing, `CurioReplayBackend.due` raises `ReplayDiverged`; it
  never guesses.
- Slice 3 has not wired the director to `curio_author` or `curio_replay`.
  Default ordinary play is unchanged.
