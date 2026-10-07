# Pressure floor: pre-registered rule (written before any new generation)

Decision: Sam, 2026-10-07 about 11:39Z, "Make hounds hunt (Recommended)"
(proposal §8 item 4). Placement: the host pre-check only (orchestrator, option A).
The in-game shadow trial's acceptance rule is unchanged.

## The rule

`chaos.hound_author.HoundValidator.validate(source)` admits a source only if
all of the following hold:

1. **Grid (unchanged).** Every one of the 120 grid calls to the engine's own
   `chaos_lua_step` returns a valid intent, and at least one of them moves.
2. **Rehearsal, in each of three bare lit rooms** (6×4 with the player at
   offset 2,1; 12×6 at 5,3; 20×8 at 10,4). There are 64 steps against the
   shadow trial's evasive player, and the hound is placed and moved by the
   engine's rules. The source must pass all three rooms:
   - no script error on any step;
   - **moves on at least 16 of 64 steps (25 %)**;
   - **comes within 1 square of the player (Chebyshev) at least once**;
   - the player gets at least 3 squares away at some step after the 9th
     (the engine's escape rule).

The engine's shadow trial still applies its own bounds in the real room:
64 steps, moved > 0, escaped, no script errors, max damage ≤ 4, no death.
Damage and death are not modelled in the host rehearsal.

A source that fails the rule is `native_rejected`. The hound lane then
regenerates once, inside the same 480 s lane-clock deadline. If the second
source also fails, or time runs out, the lane publishes footsteps.lua.

## The rehearsal is the engine's trial, offline

The rehearsal reproduces `chaos_haunt.c` `trial()` in Python (the bot step,
the trail, hound placement, `chaos_haunt_pick`'s legality and #190
nearer-candidate fallback), calling the engine's `chaos_lua_step` for every
decision. In bare rooms the engine trial draws no RNG that affects positions.
`fidelity.py` compares it with the engine's own reports
(`baseline/trials.json`, produced with `instrument.patch` applied).
**57 of 57 rehearsals match exactly** on moved, contacts, min_dist,
median_dist and escaped (`fidelity.json`).

## Verdicts on the existing sources (`preregistered-verdicts.json`)

| Source | Verdict |
|---|---|
| footsteps.lua | **pass** in all three rooms (moved 64, contacts 12 / 3 / 3, min distance 1) |
| 16-bard-00007 | **fail, never_closes** (moves 64/64 but stays 2 squares away in every room) |
| 15-wizard-default-path-00041, 17-bard-00023, 19-bard-default-path-00023 | fail, barely_moves |
| 10-madman-00007, 13-wizard-default-path-00007 | fail, never_closes in one room (they close in the other two) |
| the other 12 #251 sources | fail, never_closes in all three rooms |

So 0 of the 18 #251 sources pass, and footsteps passes. Under this rule, the
old pilot's end-to-end rate of hunting hounds is 0 of 20.

## What this does not claim

The rehearsal rooms are bare. In real start rooms the pet and furniture often
stand on the trail. In the model-free #253 games, footsteps was admitted 7
times and never made contact in the in-game trial. The floor says the
program *hunts when it can*, not that it will reach the player in a given
game.
