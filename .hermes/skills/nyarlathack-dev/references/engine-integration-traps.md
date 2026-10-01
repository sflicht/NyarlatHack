# Engine integration traps

Read `AGENTS.md` "Engine landmarks" and "Things that will bite you" first; this
adds traps found while hooking dNAO. Re-grep before trusting any function name.

## Authority

- Engine is authoritative: exact-source admission, fresh bounded Lua per decision,
  copied inputs, typed outputs, no pointers or unrestricted libraries exposed.
  Generated Lua proposes bounded intent/state; fresh-call locals are not
  persistent state. Broader model context never grants new Lua operations.
- Validate schema, budget, schedule, dynamic eligibility, dedup, and every
  family-bound origin before telegraph, debit or installation. Fixed telegraphs
  precede effects.
- Logical game/program/target/level identity is not transport-directory identity.
  Transport dirs, VM state, descriptors and presentation caches are not saved-game
  identity.
- Maintain admitted-effect history and expiry without a healthy transport; gate
  new admission, not lifecycle maintenance, on transport.
- Admit only player-known observations; match status-display semantics. Don't call
  identification/hallucination renderers or draw RNG to build context. Don't expose
  invisible creature movement in director events.

## Objects and monsters

- Treat every real object/monster as mechanically active until audited.
  Peacefulness doesn't prevent blocking, Conflict attacks or death rewards.
- Don't pass generated names through `oname()` without checking artifact
  transformation. Cover naming wrappers too: corpse helpers bypass ordinary names
  and singular formatters may normalize quantity; validate identity first.
- A hardened carrier needs unconditional tagged dispatch even when disabled,
  depleted or orphaned; never fall through to the carrier's native use.
- Check copy/split IDs, polymorph, merging, naming/identification, shop billing
  (zero price doesn't prevent billing) and carrier offerings.
- `dealloc_obj()` is not destruction: save/unload free objects too. Trace every
  deallocator caller; children may be freed before parent pointers clear, and
  monster extras before inventory. Retire at an explicit destruction seam.
- Never hold object pointers across level unload; re-find by ID through all chains
  (containers, buried, migrating, magic chests, monster inventories).
- Imported object tags need inert demotion; keep program source out of bones.
- Prove command preconditions at the real command entry; earlier movement or
  teleport may already perform the action.

## Save state

- Chaos state lives in the player save, not level/bones data. Test active and
  pending requests through real save/restore, cross-layout rejection, version
  rejection, target/level mismatch, no duplicate admission/spend.
- Audit save-version discrimination explicitly when adding fields; packed sizes
  can overlap. Check the earlier `uptodate` native-header refusal too: adding
  player bytes may hit that branch before the CHAOS state validator. Prove it
  preserves the file and does not offer deletion.
- When changing `struct chaos_state`, update ctypes mirrors, the native layout
  reporter's current-layout fixture, and version assertions together. Leave
  historical frozen fixtures and shared-metadata checks unchanged.
- Keep fixture ledger storage alive for callbacks after admission: use the
  game owner or static storage, never an admission helper's automatic local.
  An ASan stack-use-after-return probe distinguishes this from a timeout flake.
- Keep rejected-attempt authority in a carrier that exists without a runtime
  snapshot. Test native save/restore both after rejection and after terminal
  journal closure; label any fixture-initialized cap state explicitly.
- Snapshot version bumps must update the pinned version in
  `tests/chaos/test_next_use_unix_save.py` (it reads the `NUS1` header word).
- Trace `bwrite`/`mread` compression and error semantics. Preflight before
  `create_savefile`, stage restore before publication, keep originals on
  incompatibility. An error marker after truncating a save is not preservation.
- In legacy non-ZEROCOMP IO, `bufoff` may leave the descriptor registered;
  `bclose` releases it.
- Clear rejected source bytes and their persisted length so a rejected candidate
  can't poison the next save.
- Derive snapshot invariants from per-family transitions (pending beside consumed
  is valid). Preserve claimed/witnessed state, context counts, callback-family bits,
  next sequence, terminal marker, identity binding. Verify continuation runs its
  remaining effect: "no second debit" also passes when the program was lost.
- Never invent a witness/consumed state when migrating an incomplete historical
  schema; reject it.
- Test trusted identity at restore and turn boundaries; birthday alone isn't
  unique across same-second starts. Identity must not draw gameplay RNG.
- A `chaos_start` path runs on both new game and restore: guard against reseeding
  restored state.

## Level generation, RNG, sanity

- Capture genuine first-generation status before discarded-level flags clear;
  `mklev()` can rebuild a visited level. Exclude bones/scripted/revisits
  deliberately.
- Preserve inactive RNG call order. `mkfeature()` placement can fail; promoted
  fountain/sink calls affect puddles. An attempt cap is not a feature count.
- Hunger: the ordinary food seam is in `gethungry()`; don't multiply ring/energy
  costs. Non-food metabolism must not block ambient or ward mutations.
- Use native Sanity helpers, accounting for glyph and max HP/energy effects.

## Presentation

- Include `chaos.h` after `wintty.h` declarations when adding a seam to a stock
  file. CHAOS=0 no-op macros otherwise expand in the TTY function declarations;
  always compile both configurations rather than trusting the enabled build.

- `dog_move` alone doesn't publish the new cell; `m_move` does `newsym` on the
  moving path (`mmoved == 1`). A fixture bypassing it can falsely certify a glyph;
  mirror the real seam.
- Fake monster glyphs are not a safe cosmetic overlay: annotation, inspection and
  hidden-portal highlighting leak information.
- Harmless echoes go into message history without changing the top line or
  prompting; ordinary `pline` can steal a key via an extra `--More--`. Echoes must
  come from actual shadow events, with identical-input on/off comparisons.
- A message receipt or earlier redraw is not a bound map publication.

## Shadow trials and hooks

- Fork shadow execution only from the single-threaded game; close inherited fds,
  restrict syscalls, bound memory/time, reap, reject incomplete reports. Call a
  partial actor simulation a targeted trial; it proves no universal safety.
- Put selected-action begin/end at narrow dispatch cases; retain zero/stale-root
  guards. Capture tone/wording conditions once; keep short-circuit RNG conditions
  verbatim.
- New upstream seams: add narrow justified rows to the hook inventory
  (`docs/upstream-chaos-hooks.md`, `scripts/check_upstream_hooks.py`); never
  auto-accept diagnostics or update historical goldens.
