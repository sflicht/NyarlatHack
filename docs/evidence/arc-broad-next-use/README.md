# Broad next-use (C) — evidence

Verification tier: **A** (native next-use state, triggers, delivery,
save/restore, replay). Player-visible delta, new runs only: a next-use program
answers every use of its family (any whistle, tin or magic; any fountain drink)
on any level until it has delivered up to 2 effects, reached 8 callbacks, or
expired. A whistle with no companion in view no longer uses it up. New
telegraphs:

- W: "For a while, your whistles may carry farther than they should."
- F: "For a while, fountain water you drink may not run true."

"Any fountain" means any fountain **drink**. A dip triggers nothing and uses
nothing up: the refresh remap, the only native path that can apply the F
effect, exists only in `drinkfountain`, and AGENTS rule 2 rules out poking
state. Sam chose this on board question q_36d267c9.

The paired sweep is in
[docs/measurements/arc-broad-next-use/](../../measurements/arc-broad-next-use/).

## What changed

- **Envelope v3** (`chaos/next_use_envelope.py`): `next_use_program_v` 3 names
  one family and declares `uses` (1..2). The engine validates it at load.
  Telegraph ids `next-use-v3-W`/`-F` come through `telegraph_extensions`; the
  frozen telegraph block is unchanged.
- **Runtime** (`src/chaos_next_use_runtime.c`, `src/chaos_next_use_safe.c`): a
  broad program answers each use of its family on any level, keeps its
  original `program_expiry` and origin deadline, and ends only between uses:
  after `uses` deliveries, 8 callbacks, or expiry. A whistle suppressed before
  its callback consumes nothing.
- **Magic whistle**: one hook after `use_magic_whistle` in `src/apply.c`,
  registered in `docs/upstream-chaos-hooks.json`. It counts only while a broad
  program is active.
- **Snapshot v7** for broad programs appends `broad_uses`, `delivered` and
  `armed_level_token`. Single-use programs still write v6, byte-identical to
  main. Inconsistent v7 snapshots (uses above the cap, delivered above uses, a
  downgraded version) are refused at import and the game keeps going.
- **Journal**: `chaos/next_use_journal.py` and its C mirror accept broad
  journals with a v3 envelope binding and broad callback/sequence limits; v6
  journals keep the old limits.
- **Reveal**: a broad program reports its telegraph and the engine's delivered
  count.

Unchanged: engine authority, fresh origin per program, terminal before next,
the cap of 3 programs and the budget. No-whisper and CHAOS=0 paths never reach
this code; nothing new reads hidden state.

## Save and record rules

- Old native saves and v6 snapshots restore and play exactly as on main.
- `ordinary-choice.json` v4 (B) restores B's rules exactly: broad off. v3 and
  earlier keep their own rules.
- Fresh ordinary runs write v5: `m2.broad` must equal `enabled`; a mismatch
  fails closed.

Tests: `test_next_use_broad` (17 cases, including save/restore mid-program and
tampered saves and journal headers), `test_launcher_defaults`, `test_reveal`,
`test_next_use_snapshot`, `test_next_use_ordinary` (real launcher game: the
broad program is still open at game end, recorded and replayed byte-identical).

## Ordinary capture

`ordinary/` is a real nonwizard `python3 -m chaos play --ordinary` run on the
default path: no wizard mode, seed, clock or model, and no hand-placed
envelopes. Recipe: whistle (origin), `#pray` (admission), whistle, then rounds
of 8 searches and one whistle. `terminal.txt` shows, in order:

1. "For a while, your whistles may carry farther than they should." (the
   broad W telegraph, at admission);
2. "The whistle's echo sharpens your visible companion's attention." at
   turn 25 (first delivery);
3. the same line at turn 41 (second delivery, the same program).

`run/next_use-felt.jsonl` has two rows, both program_ordinal 1. In the
journal, one earlier whistle reached the callback and was blocked between
admission and the first delivery. The run then saved, restored, searched once
and quit, each with exit 0; the choice record is v5 with `m2.broad` true.

Every attempt (bounds declared before each batch):

- a1, a2: the ordinary start rolled a Troubadour without a whistle; did not
  qualify (not kept).
- a3: search-5 recipe; admitted, 7 callbacks, every decision recorded
  "blocked", nothing felt. Kept as `attempt-a3-search5-unfelt/`.
- b1–b3: step-away recipe; admitted, every decision blocked, nothing felt.
  Cause not established (not kept).
- c1: search-8 recipe; `ordinary/`, above.

Raw files and the drivers are retained in
`~/.hermes/reports/nyarlathack-arc-broad-next-use/`.
