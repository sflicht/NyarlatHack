# Generated Curio Implementation Plan

> **For Hermes:** Use subagent-driven-development to implement sequential tasks with specification review followed by correctness/security review. User has approved execution; do not ask again merely to start this plan.

**Goal:** One genuinely model-authored, early-game physical object with bounded Lua inspect/apply behavior, exact-source persistence, and verified native effects.

**Architecture:** A player-owned source/state record binds to one tagged native carrier. A pure Lua interface returns validated data, while C owns admission, placement, uses, native Sanity changes and all object lifecycle decisions. Authoring and bounded editorial notes remain in the Python sidecar, outside the engine's strict request schema.

**Tech stack:** Existing C engine, Lua 5.4, Python 3.11, native linked/terminal fixtures, existing offline GitHub Actions.

**Authorization:** Sam approved the delivered decision PDF in Discord message `1549133159038189651`. Includes rejecting old CHAOS-on saves through an explicit new save discriminator. Preserve the approved limits: one curio/game, source 4096 bytes, name 48 printable ASCII bytes, text 160, owned state 0..255, three uses, Sanity delta -2..2, cruelty cost one. Maximum two new live authoring attempts within the existing shared 20-request/$1 authorization, pinned `gpt-5.6-luna` through `openai-codex`. No live calls before offline acceptance/review gates. Do not reset the ledger.

**Baseline:** `84e2951355cdb68a4f8e959e9ce5907fb4bb7bcd`; hosted baseline 147 passed / one privileged ownership skip. Existing game code must remain stock-equivalent when inactive. Keep all raw replay assertions and the corrected terminal readiness driver.

## Execution rules

Each numbered task is a reviewable unit containing small RED / implement / GREEN steps. Preserve failing evidence, implement the minimum scope, run targeted tests, then get specification and quality passes before checkpointing or starting a dependent task. Parent performs commits/integration and broader runs. Only one writer in the checkout. Never label unrun acceptance requirements complete. If implementation exposes an incompatible requirement, report it rather than weakening the approved contract.

## Task 1 — Pure bounded Lua object interface

Files: extend `include/chaos_lua.h`, `src/chaos_lua.c`; create `tests/chaos/curio_lua_harness.c`, `tests/chaos/test_curio_lua.py`. Preserve the existing movement interface and its tests unchanged.

1. Define the interface in the new test harness before implementation and compile it: expect missing declarations/functions (RED). Then add executable behavior and malicious-output cases, not text-matching source tests.
2. Public interface:
   - `struct chaos_curio_lua_context { int sanity, insight, charges, state; };`
   - `struct chaos_curio_lua_intent { char text[161]; int state, sanity_delta; };`
   - `int chaos_lua_curio_load(const char *source, size_t length, char name[49]);`
   - `int chaos_lua_curio_inspect(const char *source, size_t length, const struct chaos_curio_lua_context *context, char text[161]);`
   - `int chaos_lua_curio_apply(const char *source, size_t length, const struct chaos_curio_lua_context *context, struct chaos_curio_lua_intent *result);`
   Return zero only on success; zero/empty outputs on every failure. Context bounds: Sanity 0..100, Insight 0..1000000, charges 0..3, state 0..255. Engine separately gates depleted use; pure functions must not decrement charges or touch native state.
3. Source returns exactly `{name=string, inspect=function, apply=function}`. Both hooks receive a copied table with exactly `sanity`, `insight`, `charges`, `state`. Inspect returns one nonempty printable ASCII string; apply returns exactly `{text=string, state=integer, sanity_delta=integer}`. Require at least one non-space character in name/text, within approved byte caps. Reject unknown/nonstring/NUL-bearing keys, wrong/missing types, bools/floats for integers, control/non-ASCII text, and out-of-range values. Lua table overwritten assignments are ordinary Lua semantics, not JSON duplicate-key parsing.
4. Share the existing bounded allocator/instruction-hook discipline. Fresh VM each operation; text-only load; no standard libraries or engine capabilities. Source evaluation, hook execution, allocating setup AND output extraction/validation must run protected; memory exhaustion must not panic the host. Do not add libraries or change the old movement schema.
5. A neutral hand-authored test program, not a literary catalogue, exercises conditional text and both positive/negative Sanity intents and different state values. Verify repeated calls cannot retain globals or mutate the C context.
6. Run `PYTHONPATH=tests/chaos:. python3 -m unittest test_curio_lua test_lua -v`, compiler warnings as errors in the new harness, Ruff on Python files, `git diff --check`. Preserve RED/GREEN logs. No game builds, model calls or C gameplay integration in this unit.

## Task 2 — Owned record, tags and save compatibility

Files: create `include/chaos_curio.h`, `src/chaos_curio.c`, `tests/chaos/curio_state.c`, `tests/chaos/test_curio_state.py`; modify `include/you.h`, `include/obj.h`, build source list in `GNUmakefile`, and explicit version handling in `util/makedefs.c` / `src/version.c` as needed after reading actual masks. Update restore validation in `src/restore.c`.

1. Preserve the current executable/data/license as an external pre-curio baseline before native rebuilds; create an old-format save fixture with that real game.
2. Write invalid-state, zero-state, exact-source roundtrip and old-format rejection tests (RED).
3. Add a fixed-size pointer-free record containing version, source length/bytes, canonical name, admission/placement state, owner object ID, charges, owned state and disabled flag. Add an explicit ordinary/generated/inert-remnant object tag. Keep source out of object extras and bones. Use an explicit previously-unused CHAOS version discriminator after checking existing feature masks; preserve stock-off layout/compatibility deliberately.
4. Validate all enum/range/length relationships; do not require the owner to be loaded or in inventory at restore, since it may be on an unloaded level. Failed source admission must not poison saves.
5. Run targeted linked state tests and both build modes. Verify old CHAOS saves reject before reading new layouts, new saves roundtrip, off-mode remains unchanged. Review both stages.

## Task 3 — Exact-source admission and early placement

Files: extend `src/chaos_curio.c`, `include/chaos_curio.h`, `src/chaos_engine.c`, `src/do.c`, `src/mklev.c`; create linked admission/placement tests under `tests/chaos/`.

1. Write budget/no-source/rejected-source/duplicate/late/eligibility tests before hooks.
2. Install candidates as private bounded files through the sidecar; installing is not acceptance. Admit exact source before generation, once per game, with one existing-budget cruelty point and an engine telegraph. Reuse established safe-point/lifecycle conventions without changing exact legacy request indices or adding an implicit retiming path. Log source identity and admission separately from placement/presentation.
3. Save one-shot placement state; capture genuine-newness before discarded-level flags are cleared in `goto_level`. Call placement at the end of eligible generation, after bones refusal. Main dungeon local levels 2/3 only; exclude special/prototype/maze/rogue/restored/rebuilt/bones maps. No model wait inside generation.
4. Deterministically prefer a legal ordinary arrival-stair room cell, then bounded remaining candidates. Exclude traps, objects, monsters, shops and unsuitable terrain. Use native object creation and placement, mark quantity one/nonmerge/tag, bind owner ID. Charge the one-shot opportunity deliberately; never replace destroyed objects or reroll maps. Retire after the early eligibility window closes.
5. Test actual native generation, unavailable placement, restored/discarded levels, source transport loss and unchanged inactive random-call order. Review both stages.

## Task 4 — Inspect, naming and identification

Files: `src/chaos_curio.c`, `include/chaos_curio.h`, native seams in `src/invent.c`, `src/objnam.c`, `src/do_name.c`; linked inspection/naming tests.

1. Tests first: both inventory inspection modes, generated/inert/ordinary names, native-artifact name attacks, user renaming rejection, knowledge isolation and invalid program handling.
2. Recognize tags independently of remaining charges/source validity. Render canonical generated names without `oname`; orphaned remnants get fixed inert names. Intercept generated description before native type knowledge and suppress subsequent carrier encyclopedia lookup. Add a generic Apply menu label, not native whistle wording.
3. Inspect runs pure Lua with copied permitted statistics and state; changes no turn, state, charge or random draw. Preserve native names and global type discovery for ordinary objects. Invalid inspect gives fixed safe output, retaining protective identity; avoid introducing an unapproved mechanical state change on inspection.
4. Run linked and real terminal inspection tests; assert raw physical/state invariance. Review both stages.

## Task 5 — Apply and carrier-specific protections

Files: `src/chaos_curio.c`, `src/apply.c`, `src/invent.c`, `src/shknam.c`, `src/shk.c`, `src/sounds.c`; linked application and carrier exclusion fixtures.

1. RED tests cover valid positive/negative/zero intent, exhausted/disabled/orphan/wrong-ID/wrong-type/wrong-quantity/non-inventory cases, malformed output, failure atomicity, no native wakeup/whistle activation, no sale/billing and Andromalius exclusion.
2. Intercept every tagged object immediately after `doapply` selection, before artifact/native dispatch. Separate handled status from move result. Validate full intent before truthful engine telegraph, charge decrement, owned-state commit and `change_usanity(delta, FALSE)`. Record requested/actual Sanity change. Successful application costs `MOVE_STANDARD`; inert/invalid application costs no turn or charge. Runtime apply failure disables executable behavior but preserves tag.
3. Preserve ordinary physical carrying/dropping/throwing/destruction. Explicitly block native whistle offering use, selling/billing and tagged merging. Do not rely on zero pricing or `no_charge` alone.
4. Test actual hooks, nearby monster wake state, charge conservation and downstream native Sanity behavior rather than claiming an isolated scalar. Review both stages.

## Task 6 — Copy, unload, polymorph and bones lifecycle

Files: `src/chaos_curio.c` and small native seams in `src/mkobj.c`, `src/zap.c`, `src/bones.c`, `src/restore.c` / `src/save.c` if needed. Inspect actual paths before choosing hooks; do not edit unrelated mechanics.

1. RED fixtures: copy/split cannot execute or refill, drop/theft/container/level-unload restore retains the original binding, destruction does not replace, polymorph ends generated identity, bones output and ghostly input become inert even with colliding IDs.
2. Keep placement latch; do not use `dealloc_obj` as proof of destruction because save/unload frees objects. Copies retain an inert protective identity rather than functional whistle behavior. Polymorph replacement does not receive the old program. Demote tags on both bones directions; player-owned source never travels in bones.
3. Run actual native lifecycle fixtures and save/restore terminal tests. Review both stages.

## Task 7 — Offline authoring envelope, installation and continuity

Files: create `chaos/curio.py`, prompt files under `chaos/prompts/curio/`, `scripts/generate_curio.py`, tests under `tests/chaos/`; modify `chaos/__main__.py` and launcher preflight only as necessary for explicit saved-source installation. Reuse `chaos/oauth.py` reservation/receipt helpers without changing its pin or cap.

1. Fake-client RED tests for strict envelope, exact decoded source bytes, duplicate fields, byte caps, preflight-before-inference, fsync failures, exhausted allowance, wrong provider and restore conflicts.
2. Authoring output is exactly a JSON object with `lua_source` and `continuity_note` strings. Preserve raw response and exact decoded source; never repair Lua or let output choose host paths. Notes at most 512 UTF-8 bytes, no controls; at most six prior notes, separately tagged by host-assigned candidate identity/status. Quoted notes never supersede trusted capabilities. Rollback/conflicting evidence fails closed rather than presenting future intentions as current facts.
3. Compose trusted concrete hook contract + shared Gothic layer + one chosen early literary layer + bounded public context/notes. Keep prompts in files. Do not include a completed sample literary implementation. Install saved source without inference; ordinary default play remains offline. Candidate source mismatch on restore rejects instead of overwriting evidence.
4. Verify all budget tests with fake clients. No live request yet. Review both stages.

## Task 8 — Whole-prototype offline acceptance

Create `tests/chaos/test_curio_gameplay.py` using the existing corrected `Game` driver, plus reproducibility evidence and user documentation.

1. Exercise actual inspect/apply paths, ordinary eligible early-floor discovery, no `#setsanity` requirement for admission, both UI modes, depletion, invalid handling, save/restore and transport-independent lifecycle. Retain terminal bytes, events, inputs and exact source/binary/data identities outside the repo until sanitized publication.
2. Run both native builds and the complete offline suite against preserved off-mode baseline. Every approved lifecycle requirement must have passing evidence; no fabricated fixtures presented as model output.
3. Independent specification review, then correctness/security review of the integrated offline implementation. Freeze concrete hook contract after passes. Do not infer whole-dungeon shadow certification from these tests.

## Task 9 — Bounded novel live demonstration and publication

1. Read the current real ledger and verify remaining allowance. Allow at most two NEW attempts in this feature under the existing overall cap; stop on exhaustion/auth failure, no automatic provider fallback.
2. Use the approved Luna OAuth route to author a new object through the frozen interface. Retain exact response/source/notes and usage receipt. Do not hand-edit model code into a passing candidate or add a story-specific engine branch after generation.
3. At least one genuinely model-authored program must pass admission and work in the real game. Compare behavior across contexts with the hand-authored test fixture; source hashes or different names alone do not prove different behavior. Verify actual native effects, owned-state transitions and restore in terminal artifacts.
4. Run final tests/reviews, scan publication diff for secrets, open a pull request, inspect real hosted checks, merge only after success, verify separate main run and remote tree. No live credentials or inference in GitHub Actions.
5. Deliver a rendered human-facing report and working commands/artifacts, clearly separating completed prototype from deferred fountains, companions, mirror enemies, attribute bonuses and quest-stage capabilities.
