# Curio window: preregistered protocol (Tier B)

Committed before any measured game, and before the driver exists. Harness smoke
games run only on seeds 900 and above, which are excluded from every result.

## Question

A human doesn't stop playing while the curio's author works. Before this
change, a curio needed the author's answer to arrive while the player was still
on main-dungeon DL1–2, and it could only be placed on a fresh main DL2–3. After
the change, admission is allowed at depth 1–4 and placement at depth 2–5, in
the main dungeon or the Gnomish Mines. How often does a curio get placed in
ordinary play when the game keeps running during the wait?

## Trees (paired)

- **before**: `origin/main` at 755920a4 (the merge of #256).
- **after**: the committed head of `fix/curio-window` that carries this
  protocol's driver. The engine change is 55a25c2c6.

Each tree is built from a `git archive` export with `make -j2 install CHAOS=1`
(clean environment, `PKG_CONFIG=/usr/bin/pkg-config`). Games run from those
exports. The driver, fake author and analysis come from the after export and are
identical for both trees. The before tree's `tests/chaos` player and harness
files are byte-identical to the after tree's. `chaos/` differs only in
`curio_director.py` docstrings.

## No model

The curio author is a fake backend. It never imports a transport and never
writes an xAI ledger row. Every game:

- returns the committed #247 curio (`docs/evidence/curio-live-capture/attempt-013/run/curio-evidence/raw-response.txt`,
  the "glass reed locket"), unchanged, through the normal curio lane: envelope
  parse, native validator, truth check, publication and engine admission;
- returns it after a wall-clock delay drawn with replacement from the 33
  committed `curio_history` latencies in
  `docs/measurements/model-authoring-pilot/runs/{pilot,smoke}/ledger.jsonl`
  (median 182 s, p90 252 s, max 298 s, as in that README). The draw uses
  `random.Random("curio-window-v1:<seed>")`, so the delay is the same for both
  trees and both paces on a seed.

The game is never paused while the lane waits.

The model hound is off: the fake provider isn't an xAI provider, so the hound is
the default `footsteps.lua`, exactly as in a game without a model. Next-use is at
the `--ordinary` default.

## Play

- A real nonwizard `python3 -m chaos play --ordinary` game per run, under the
  sweep clock (`tests/chaos/sweep_clock.c`, seed per game), human Bard with the
  default pet.
- **Driver:** the #247 curio-capture player (`tests/chaos/curio_capture_player.py`,
  which is baseline-v2 exploration with a 300-turn dwell per level, seen tools
  picked up and inspected). There's one change: it never climbs back from a
  branch staircase. It takes the first `>` it reaches on each level, so it
  enters the Gnomish Mines whenever the Mines staircase is the one it finds
  first.
- The driver's scheduled save/restore at turn 700 is off. Save and restore across
  levels is covered by the Tier A tests.
- **Pace:** after each command the driver sleeps until the game turn counter is
  no further ahead of wall time than the target pace. There are two paces,
  **1 turn/s** and **3 turns/s**. Achieved pace is reported.
- **Stop rules,** whichever comes first:
  - death;
  - turn 1500;
  - the curio is final: expired, rejected or placement failed, or the lane
    failed or ended without a model;
  - 150 turns after placement, or leaving the placement level;
  - depth 7;
  - 30 minutes of wall time;
  - a driver stall (baseline-v2's own bound).
- **Seeds 101–120:** each seed runs four games: before and after at 1 turn/s, and
  before and after at 3 turns/s. Up to 8 games run at once in one hermes-heavy
  slot (2 CPUs). The games mostly sleep. Seeds start in order. If the slot reaches
  about 2 hours, I report only the seeds whose four games all finished, and say
  so.

## Measures (per tree and pace)

From the engine's `curio` events, the curio lane record, and the public status
line:

- **requested:** the lane wrote `requested`; game turn and depth.
- **ready:** the lane wrote `ready` before its deadline; game turn and depth.
- **admitted:** the engine's `curio admitted` event; turn, depth and branch.
- **placed:** the engine's `curio placed` event; turn, depth and branch.
- **expired:** the engine's `curio expired` event; turn and depth.
- **name on screen:** the curio's name ("glass reed locket") appears in the
  terminal output. The driver walks onto seen tools, so this means the player
  walked onto it, picked it up or inspected it.
- Also reported: deaths, stop reasons, the drawn delay, and achieved pace.

Depth comes from the status line's `Dlvl` (dNetHack shows depth). Branch is
"mines" from the first arrival by a branch staircase onward, otherwise "main".
The driver knows this from the game's own "branch staircase up" text, by
looking at the arrival stair, which uses no game time.

The headline is **placed / games** per tree and pace, with paired counts: after
only, before only, both, neither.

## Expected direction (before any game)

1. After ≥ before for placement, at both paces.
2. At 3 turns/s, before places almost nothing: the answer usually arrives after
   the player has left DL2, and the first safe point on main DL3+ expires it.
   After places on most games that survive and request in time.
3. The gap is larger at 3 turns/s than at 1 turn/s.
4. After: admissions mostly at depth 2–4 and placements at depth 3–5. Some are
   in the Mines when the driver takes them.
5. Neither tree should ever place a curio below depth 5 or in Sokoban, or
   place one twice.

Any other result is reported as it is.
