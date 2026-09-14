# AGENTS.md — working notes for agents (and humans) on NyarlatHack

Read `README.md` first for the vision. This file is about *how we work in this
repository*.

## What this repo is

A fork of dNetHack (dNAO, NetHack 3.4.3 lineage, ~370k lines of K&R-flavoured
C across 119 files in `src/`). Upstream is the `upstream` remote, branch
`compat-3.26.0`. We branched at `a6f0a1c43`. All NyarlatHack work happens on
`main` and feature branches off it.

We intend to keep pulling upstream. **Minimise the diff footprint inside
upstream files.** Prefer:

- new files under `src/chaos_*.c`, `include/chaos*.h`, and the sidecar under
  `chaos/` (Python);
- one-line hook calls at existing seams over restructured functions;
- a build flag (`CHAOS`, default on for our builds) so the engine compiles
  and plays as stock dNetHack when it is off.

## Current milestone

**Milestone 1 — Tier 2.** See the checklist in `README.md`. Tier 3 (embedded
scripting, "the Dreamlands") is *not* to be started, prototyped, or "just
sketched in a branch" until Milestone 1 has a playable build and a passing
replay test. Ideas for it go in `docs/tier3-notes.md`, not in `src/`.

## Vocabulary

Use these words consistently in code, comments, commits and docs.

- **the Crawling Chaos** — the director sidecar (`chaos/`).
- **event** — one JSON-lines record the engine emits about something the
  player did or something that happened to them.
- **whisper** — one validated mutation request from the Chaos to the engine.
- **mutation** — a named, typed, bounded rule change the engine knows how to
  apply. The registry of mutations *is* the API.
- **telegraph** — the in-game signal that precedes a whisper's effect.
  Mandatory.
- **cruelty** — the cost of a whisper; **budget** — how much cruelty the Chaos
  may spend, a function of the player's lost Sanity.
- **safe point** — a moment the engine polls the mailbox: level change,
  prayer, sleep, Sanity threshold.
- **the Dreamlands** — Tier 3's shadow-dungeon verifier. Not yet.

## Architecture rules (non-negotiable)

1. **The engine is deterministic and in charge.** The model chooses; the
   engine executes. No process other than the game writes game state.
2. **Mutations apply through existing engine paths.** Never poke a struct
   from a mutation handler if there is a function the game already uses to do
   that thing. Bounds-check everything at whisper load, not at apply.
3. **Every whisper is logged next to the RNG seed.** `seed + whispers.jsonl`
   must reproduce the run. If a change breaks that property, it is a bug even
   if the game "works".
4. **No whisper without a telegraph.** Reject at load.
5. **No-whisper equals stock.** With the stream on and the mailbox empty, the
   game must behave identically to upstream. The regression test checks this.
6. **The model never sees secrets the player can't.** Prompt context is built
   from the event stream, which records what the player *did*, not the
   dungeon's hidden state. The Chaos should be a malevolent observer, not an
   omniscient one.

## Engine landmarks (where the seams are)

Verified against the current tree; re-grep before relying on line numbers.

- Turn loop: `moveloop()` in `src/allmain.c`.
- Monster decision: `dochug()` / `dochugw()` in `src/monmove.c`.
- Monster creation: `makemon()` → `makemon_full()` → `makemon_core()` in
  `src/makemon.c`.
- Level generation: `src/mklev.c`, `src/mkmaze.c`, special levels via
  `src/sp_lev.c`.
- Prayer: `src/pray.c`.
- Sanity / Insight: `u.usanity`, `u.uinsight` in `include/you.h`;
  `change_uinsight()`; usage in `src/allmain.c` and `src/pray.c`.
- Wards (dNetHack's Elbereth replacement): `src/engrave.c`.
- Death / logging: `src/end.c`, `src/topten.c` (xlogfile).
- Combat: dNAO folds vanilla's `uhitm.c`/`mhitu.c` into `src/xhity.c` /
  `src/xhityhelpers.c`. Grep before assuming vanilla file names.

## Build and run

```
apt install bison flex build-essential libncursesw5-dev pkg-config
make install            # → ./dnethackdir/dnethack
cd dnethackdir && ./dnethack -D -u wizard     # wizard mode
```

`GNUmakefile` is the real build; `sys/unix/Makefile.*` are legacy. Local
overrides go in `local.mk` (git-ignored). AddressSanitizer:
`CFLAGS='-g -fsanitize=address' LDFLAGS=-fsanitize=address`.

Do not regenerate `include/macromagic.h` unless you changed
`util/MacroMagicMarker.py` or `doc/macromagic.txt`.

## Sidecar (`chaos/`)

Python 3.11+, managed with `uv`. Model backends are pluggable behind one
interface; `replay` and `random` backends must always work with no network and
no keys so tests never need a model. Keep prompts in files, not in code.

## Testing

- The engine must build warning-clean under the flags in `GNUmakefile` plus
  whatever we add. New warnings in our files are failures.
- Regression: headless run with the stream on and mailbox empty vs. stock
  build, same seed, identical xlogfile and final map dump.
- Replay: run with a whisper log, then run again with the same seed and log;
  identical outcome.
- Sidecar: unit tests for schema validation, budget arithmetic, and the
  telegraph requirement. Every rejected-whisper path needs a test.

## Git conventions

- Commit identity in this repo is `Xiongmao (雄猫) <xiongmao@lichtens.cloud>`
  for agent commits; do not overwrite with a global identity.
- Conventional commits: `feat(engine):`, `feat(chaos):`, `fix:`, `docs:`,
  `test:`, `build:`, `upstream:` (for merges from dNAO).
- Never force-push `main`. Never commit build outputs (`.gitignore` covers
  dNetHack's; extend it for ours).
- Upstream's `.gitignore` ignores `*.md` and `*.json`; ours un-ignores them.
  Keep that when merging.

## Things that will bite you

- dNAO is 3.4.3-era C with heavy macro use; `include/macromagic.h` is
  generated. Read `doc/macromagic.txt` before touching monster/object flag
  code.
- `makemon.c` is ~15k lines. Hook at `makemon_core()`, not at the wrappers.
- Save files must round-trip any new state you add (`src/save.c`,
  `src/restore.c`). Bones files too — and whispers must *not* ride in bones
  unless the player opted in (out of scope for Milestone 1: just don't save
  them there).
- The game RNG is the only RNG. Anything random in the engine side of a
  mutation must use `rn2()` and friends so replay holds.
- Balance is explicitly not a goal of upstream; do not "fix" role balance in
  passing.
