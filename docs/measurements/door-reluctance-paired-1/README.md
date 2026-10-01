# Paired seed sweep for #1 door_reluctance (M1 schedule)

Tier B. The same sweep was run on `main` and on the #1 branch: same policy, seeds and starts. It checks the two acceptance points Sam set for M1:

- the hound's admission on the default path is unchanged from `main`;
- `door_reluctance` is admitted, and felt, from Dlvl 2 on.

## Runs

Each side was built fresh with `make -j2 install CHAOS=1` (0 warnings) and then played:

    python3 scripts/seed_sweep.py --seeds 1-100 --policy baseline-v2 \
      --starts bard,madman,bard-inherited,bard-default-path,wizard-default-path \
      --jobs 2 --work <dir> --out <stem>

Both ran under `hermes-heavy`, one after the other, from the same worktree with a clean tree.

| side | revision | seconds | games | harness errors |
|---|---|---:|---:|---|
| main | `d29c4e2a2` | 4844 | 500 | 2, both allowlisted (bard seeds 48 and 75) |
| branch | `313c0eec5` | 4854 | 500 | 2, the same allowlisted pair |

`scripts/sweep_alert.py check` passed on both reports.

The reports are kept here unchanged:

- `main-seeds-1-100.{json,md}`
- `branch-seeds-1-100.{json,md}`

`branch-door-facts.json` holds one row per branch-side game. `door_collect.py` produced it from the kept work directory's public run files (`events.jsonl`) after the sweep finished. A row records:

- the game's mutation ACKs (turn, status, detail);
- its level-entry turns;
- `door_felt_turn`, the first `door_open` "resisted" notice while an accepted `door_reluctance` effect was active.

## Results (seeds 1–100 per start)

"First felt" is the kind of the earliest felt event in each game, recomputed from the per-game `funnel.first_felt` rows. The branch report's aggregate `by_kind` was produced before `seed_sweep.py` learned the `door` kind (added in this PR), so it leaves door out. The per-game rows are complete.

| start | hound accepted, main / branch | first felt, main | first felt, branch | door accepted (games) | door felt (games) | outcome and last turn identical |
|---|---:|---|---|---:|---:|---:|
| bard-default-path | 88 / 88 | hound 77 | hound 77, door 3 | 46 | 15 | 93 |
| wizard-default-path | 88 / 88 | hound 79 | hound 79 | 46 | 11 | 95 |
| bard | 0 / 0 | W 17 | W 17, door 14 | 59 | 19 | 90 |
| bard-inherited | 0 / 0 | W 6 | W 6, door 1 | 12 | 1 | 100 |
| madman | 0 / 0 | none | none | 2 | 0 | 71 |

"Door felt" counts any resisted notice under the effect, even when another felt kind came earlier.

The v2 baseline report (`docs/measurements/seed-sweep-v2-179/`, revision `9579e3419`) gave 86 for bard-default-path. The `main` side here, at `d29c4e2a2`, gives 88, and the branch matches it exactly.

What the numbers show:

- **The hound is untouched.** On both default-path starts, hound acceptance (88 and 88) and hound steps (196 and 210) are identical on the two sides. Every game where the hound was felt first is still felt first.
- **Door comes only from Dlvl 2.** Across all starts, 165 games accepted a door whisper. The first accept was on Dlvl 2 in 160 of them and Dlvl 3 in 5, and never on Dlvl 1. No mechanical ACK appears before a game's second level entry.
- **The omen stays alone at Dlvl 1.** Its ACK is the only one at the Dlvl 1 arrival safe point.
- **Door is felt.** The hero met a resisting door under the effect in 46 games (15 + 11 + 19 + 1).
- **Madman is the only start that took hunger.** It accepted 37 hunger_rate whispers from the same seeded M1 menu (plus 14 duplicate and 1 budget rejections); no other start accepted any. Madman also has the fewest identical games (71). Why each game diverged was not examined.
- **Next-use admission is unchanged** on four starts (42/42, 37/37, 30/30, 3/3). On madman it went from 10 to 8; that start's games diverge the most, and those two games were not examined.

Rejections, as the engine recorded them in the ACK detail:

- `door_reluctance` "duplicate" (for example 44 in bard): a door whisper arrived while one was already active. No stacking, and it costs nothing.
- "budget": 6 in bard-default-path.
- "ineligible": 1 in wizard-default-path.

## A discarded first branch run

An earlier branch-side run was stopped after about 110 games. Almost every game's offline director had stopped with a `ValueError`. The cause was the measurement, not the code. A side script hard-linked each game's `events.jsonl` to keep it past cleanup. The director's reader refuses any event file whose link count is not 1 (`chaos/director.py`), so it failed closed.

The run above made no links. Door facts were read only after the sweep had finished; no director stopped in any of the 149 games whose logs were kept (every game that published a door whisper), and its harness errors, sync timeouts and save/restore counts match `main` on every start.
