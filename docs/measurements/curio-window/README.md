# Curio window: before vs after, paced real play (Tier B)

The protocol is in [PREREGISTERED.md](PREREGISTERED.md). It was committed in
19f280179, before the driver (6276ce951), the analysis (99c2c7988) and any
measured game. No model was called and no xAI ledger row was written. Every
game's curio receipt records provider `fake`, and no game wrote a ledger file
(`analyze.py` checks both).

- **Trees:** before is 755920a4, after is 6276ce951. Both are `git archive`
  exports built with `make -j2 install CHAOS=1`.
- **Fake author:** returns the committed #247 glass reed locket after a delay
  drawn from the 33 committed `curio_history` latencies in
  `docs/measurements/model-authoring-pilot/runs/{pilot,smoke}/ledger.jsonl`.
  The draw is seeded per seed. This run's draws ranged from 76 to 298 s.
- **Play:** the game never pauses while the author waits. Achieved pace was
  1.0 and 3.0 turns/s, as targeted.
- **Size:** seeds 101–114, four games each, 56 games. One hermes-heavy slot
  ran for 6,157 s. The start budget was reached before seed 115, so seeds
  115–120 never ran.

## Results

From `summary.json`. `python3 analyze.py results.jsonl summary.json`
reproduces it.

| per 14 games | before, 1 t/s | after, 1 t/s | before, 3 t/s | after, 3 t/s |
|---|---|---|---|---|
| requested | 14 | 14 | 14 | 14 |
| ready in time | 14 | 14 | 12 | 13 |
| admitted | 10 | 12 | 7 | 10 |
| **placed** | **2** | **2** | **0** | **1** |
| expired | 2 | 0 | 3 | 0 |
| name on screen | 2 | 2 | 0 | 1 |
| entered the Mines | 1 | 2 | 1 | 2 |
| died | 2 | 3 | 3 | 4 |

- **Where it was admitted, after:** main 1 ×8, main 2 ×2, main 3 ×1, Mines 4 ×1
  at 1 t/s; main 1 ×6, main 2 ×1, main 3 ×2, Mines 4 ×1 at 3 t/s.
- **Where it was placed:** before at 1 t/s, main 2 and main 3; after at 1 t/s,
  the same two; after at 3 t/s, main 4.
- **Where it expired (before only):** main 3, each time.
- **Paired placement (same seed and map):** at 1 t/s, both trees placed on 2
  seeds and neither on 12. At 3 t/s, only after placed, on 1 seed (103), and
  neither placed on 13.
- **Anomalies:** none. No curio was placed twice, below depth 5, or in Sokoban.

## What this shows, and what it doesn't

- **Expiry is gone in the window that matters.** On main the curio expired on
  arrival at main DL3 in 5 of 28 games (seeds 101, 103 and 108; 101 and 108 at
  both paces). On the same seeds and maps, after expired none. It admitted
  instead: at main 3 (seeds 103 at 3 t/s and 108) or Mines 4 (seed 101). On seed
  103 at 3 t/s it then placed on the fresh main DL4: before expired at turn 681,
  after placed at turn about 1,025, and the player saw the locket.
- **Placement barely moved, and n is too small to say more.** It went from 2 to
  2 at 1 t/s and from 0 to 1 at 3 t/s. The direction matches the preregistration
  (after ≥ before, with a larger gap at 3 t/s), but one paired seed is not
  evidence of a rate.
- **The driver is the bottleneck.** The #247 capture player never left DL1 in 8
  of 14 seeds (102, 104, 105, 106, 107, 109, 112, 113): it runs out its
  1,500-turn cap or dies there. It reached depth 3 or deeper on only 4 seeds. A
  curio admitted on DL1 can only be placed on a later fresh level, so on those
  seeds neither tree could place one. The same driver produced the #247
  capture, which descended because of its seed.
- **The other losses:**
  - Seed 110 requested on Mines 3 and died there.
  - Seed 101 (after) admitted on Mines 4 and then died.
  - Seed 108 (after) admitted on main 3 and hit the turn cap before reaching a
    new level.
  - Seeds 113 and 114 at 3 t/s became ready on DL1 with no later safe point
    before the cap or death.
- **Mines:** the driver entered the Mines on seed 110 in both trees, arriving
  at Mines 3 at turn 665. It requested there and died before the next safe
  point. It also entered on seed 101, after only: before stopped at its main DL3
  expiry, while after went on to Mines 4 and admitted there (turn 986), then
  died. No Mines placement was observed; Tier A covers it
  (`tests/chaos/test_curio_window_gameplay.py`).

A sweep with a driver that descends at a human-like rate is the open follow-up.
For example, it would take the first `>` after a fixed number of turns rather
than after exploring.

## Files

- `PREREGISTERED.md`: the protocol and expected direction.
- `fake_chaos.py`: `python3 -m chaos`, with the curio author replaced by the
  fake.
- `measure.py`: one paced game.
- `run.py`: the paired runner.
- `analyze.py`: the summary.
- `results.jsonl`: one row per game, including curio events and lane steps with
  turn, depth and branch, the depth timeline, the drawn delay, the receipt, and
  achieved pace.
- `summary.json`: the output of `analyze.py`.
