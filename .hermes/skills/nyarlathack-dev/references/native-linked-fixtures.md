# Native linked fixtures and caller accounting

Linked fixtures compile small C drivers against real engine objects
(`tests/chaos/game_rules.c`, `tests/chaos/haunt_*.c`, etc.). They are a distinct
evidence scope from end-to-end terminal play; label them so.

## Linking

- Link real command, Lua and statistic implementations. Rename `unixmain.o`'s
  `main` with objcopy. Globalize only private object-file copies to expose an
  existing seam; never add runtime test toggles or setters to production.
- GNU ld `--wrap` intercepts only cross-object references. `makemon`→`makemon_full`
  and `deferred_goto`→`goto_level` are same-object: wrap `makemon` /
  `deferred_goto` (or the external command-table entry) instead.
- Wrap to observe arguments/order, then delegate unchanged. Stale health/energy
  maxima can prove native recalculation ran.
- Use `--wrap` only at fault boundaries so failures exercise real admission and
  persistence. Clear fault-wrapper descriptor tracking on `close` (fd numbers are
  reused). Test file `fsync` and directory `fsync` independently.
- Link the same Lua libraries as the game.
- Compile changed upstream translation units off-mode with implicit function
  declarations as errors; a CHAOS-only transitive header can hide a missing no-op.
- Keep the fixture directory stable across iterations; rebuild changed engine
  objects before GREEN.

## Initialization (zero-filled structs are not a valid startup)

- Audit the real startup sequence for every helper you reach; initialize with
  native routines and assert preconditions before gameplay.
- Initialize deity data before `onscary`: even an unprotected target can reach
  `scaryLol` → `gholiness`.
- Real monster creation needs `id_permonst`, race/role and a non-quest dungeon;
  zeroed dungeon/quest state can call absent UI callbacks.
- Combat or monster AI (e.g. the forked haunt trial) needs `init_artifacts()`
  (combat reads `artinstance`) and `vision_init(); vision_reset();` after the map is
  built. Missing either segfaults the child; a SIGSEGV shadow child looks like
  `shadow_failed` with no `dreamlands.json`.
- Objects, gods, player monster data and `init_artifacts` before touching
  `artilist` (runtime-allocated). Object allocation/name lookup needs normal
  game init and a window port.
- Zero-initialized fake monster data is inediate: enable ordinary food flags only
  for fixtures that need hunger admission.
- Wrap `pline` in bare fixtures: there is no terminal.
- Initialize physical fixtures before snapshotting: pre-selection capacity checks
  may refresh artifact weight. Compute the real weight; don't weaken invariance.

## RNG purity and caller accounting

- Reuse `tests/chaos/native_rng.h` / `native_rng.py` and `controlled_rng_objects`:
  they globalize reseed statics in a private `rnd.o` copy. Never replace the RNG.
- Control reseed counters as well as the seed; `check_reseed()` can fetch entropy
  or time between "identical" probes.
- Record both call count and next real draw. A one-sided die can advance the
  counter without consuming a library random value.
- Require a no-draw positive control and deliberate native `rn2()` and raw
  `random()` negative controls through the same oracle. Only paths promised pure
  get purity assertions; native effects may legitimately draw.
- Separate RNG, turn, object-state and output assertions. Bounded repetition
  confirms stability; it is never retry-until-green.
- Capture unchanged-core raw events and RNG measurements before comparing callers.
  Controlled shadow outcomes are caller isolation, not sandbox acceptance; mixed
  links are not fresh-source acceptance.
- Keep protected old core objects read-only until all baseline comparisons finish,
  then release them explicitly in the handoff.

## What to test

- Tag recognition vs. executable ownership: exercise every nonzero tag through the
  real command, including corrupt identities, wrong location and forged membership.
- Save fixtures: wrap the external save-command entry to seed state and the
  external restore entry to assert after native validation. Test feature-bit
  rejection with an otherwise identical version header so struct-size changes
  aren't the only rejection path.
- Aggregate accounting (shops/containers): compare an exempt container against an
  ordinary one with the same topology; include siblings with zero/insufficient/
  ample cash, accepted and declined offers, billed descendants, and wrong-type
  tagged shells (coin/type fast paths bypass traversal). Snapshot the whole exempt
  object around native calls.
- Snapshot integrity vs. semantics: keep a stale digest only for corruption tests;
  recompute digests for semantically invalid fixtures; prove the semantic guard by
  a temporary mutant that bypasses it; restore before final verification.
- Producer/consumer transport: pass real emitted bytes through the unchanged
  consumer; test failed writes at the producer's caller; test transport write
  failure separately from an uninitialized transport.
- Validate a gameplay threshold chosen from a synthetic fixture against real
  ordinary-play outcomes; bare synthetic rooms can mislead.
- Preserve RED/build/GREEN evidence; separate setup/compile failures from
  behavioral RED.
