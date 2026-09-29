# Prototype budget pacing (#164)

Tier A evidence for the pull request on #164. **Prototype pacing, not tuned
balance.** Sam decides the numbers (N, K, the witnessed credit, the ceiling);
this entry reports what each one measurably did.

## Where the budget binds today (measured)

- `baseline-v1` without the echo hound: **never.** The committed #196 sweep
  (`docs/evidence/seed-sweep/baseline-v1-seeds-1-100-196-lifetime-300.*`) has no
  `budget` rejection. The launcher runs one next-use program per game (cost 1)
  and Bard Sanity stayed at 100 in 98 of 100 games, so capacity 2 is never used up.
- With `--haunt` (hound cost 2): **always, on dungeon level 1.** The hound is
  accepted at a median of turn 9.5; the earliest next-use admission is move 128
  (median 899). First come, first served, the hound takes the whole full-Sanity
  capacity of 2 before the next-use program's safe point.
- Madman starts at Sanity 75 (capacity 4), so hound plus next-use fit; Madman
  next-use is refused anyway for want of a companion (#196 C3). Inferred from the
  formula and the #196 sweep; Madman was not swept with `--haunt`.

## Configurations

All four are `baseline-v1`, Bard, seeds 1–100, lifetime 300, run under
`hermes-heavy`. B–D add the ordinary launcher's `--haunt` (default hound pack)
through `~/.hermes/reports/nyarlathack-164/haunt_sweep.py`, which changes only
the launcher options.

| | Config | Revision |
|---|---|---|
| A | no hound, policy 2 (the committed #196 sweep, Bard rows) | `4f0689c09` |
| B | `--haunt`, policy 2 (today's rules) | `4f14a6161` (main) |
| C | `--haunt`, pacing on: N=4, K=2, witnessed +1 cap +2, ceiling 12 | `dd20e099c` |
| D | `--haunt`, pacing on, same but K=3 (scratch contract edit, not committed) | `554c3aa01` + `level_cap: 3` |

Pacing is switched on per new game with `NYARLATHACK_PACING=1`.

## Results

| Bard, seeds 1–100 | A | B | C (K=2) | D (K=3) |
|---|---:|---:|---:|---:|
| Games with an end record | 100 | 99 | 99 | 100 |
| Turns | 147,195 | 153,357 | 153,357 | 154,568 |
| Sum of deepest level reached | 227 | 242 | 242 | 243 |
| Hounds accepted | 0 | 85 | 85 | 86 |
| Next-use admitted | 17 | 2 | 2 | 12 |
| Next-use delivered | 6 | 0 | 0 | 5 |
| Next-use refused for `budget` (report loss label) | 0 | 11 | 11 | 1 |
| Admitted per 1000 turns | 0.115 | 0.013 | 0.013 | 0.078 |
| Delivered per 1000 turns | 0.041 | 0 | 0 | 0.032 |
| Admitted per dungeon level reached | 0.075 | 0.008 | 0.008 | 0.049 |
| Delivered per dungeon level reached | 0.026 | 0 | 0 | 0.021 |
| Largest lifetime spend in any game | 1 | 2 | 2 | 3 |

In B and C, seed 67 left no end record (no xlogfile line), so its turns and
depth are missing; its funnel row still counts (it is one of the 11 `budget`
refusals). D completed all 100. Turn and depth totals use games with an end
record; admitted and delivered counts come from the sweep report.

## What each decision point did (measured, paired by seed)

- **K (per-level cap), prototype 2.** With K=2, C is *identical* to B in every
  paired game: after the hound spends 2 on DL1, the level allowance is gone
  until a new deepest level, and next-use programs are proposed on the level
  where their origin was (mostly DL1). Capacity after the hound did grow (64 of
  85 games showed budget 1–2 at a later safe point) but only on deeper levels,
  where no program was pending. With **K=3**, 10 of the 11 budget refusals
  become admissions: 5 delivered, 3 expired unused, 1 left the level, 1 native
  effect not delivered. The one that stays refused (seed 79) is the one game
  where the player had not seen the hound move before the safe point, so there
  was no witnessed credit. K=3 also re-admits hunger (cost 3); ward (4) stays out.
- **Witnessed credit, prototype +1 per delivering source, cap +2.** Under K=3
  it is what frees the point on DL1: descent credit is 0 there, so capacity is
  2 + 1 (the player saw the hound move) = 3, minus the hound's 2. Without it,
  K=3 alone would change nothing on DL1. Inferred from the event rows (budget 1,
  spent 2 at the first next-use safe point in seeds 31, 40, 67, 92, 95).
- **N (descent cap), prototype 4.** No measured effect in this configuration:
  the deepest level in C was 5 (+3), and no admission waited on descent.
- **Ceiling, prototype 12 unchanged.** Never approached: the largest lifetime
  spend was 3.

## Tests

- `tests/chaos/protocol_harness.c` `pacing` case, run by
  `test_protocol.py::test_prototype_pacing`: policy 2 unchanged; over-budget
  fails closed and leaves state untouched; the per-level cap holds with lifetime
  capacity to spare; the descent credit uses the deepest level only (20 rounds
  of stair-bouncing earn nothing and reopen nothing); witnessed credit is once
  per source and capped; capacity never exceeds 12; invalid pacing fields are
  rejected on validation (restore).
- Standing gates at the head: see the PR body.

## Raw data

`~/.hermes/reports/nyarlathack-164/` (with `SHA256SUMS`): `findings.md`,
`comparison.json`, `sweep/` (B), `sweep-pacing/` (C), `sweep-pacing-k3/` (D),
gate logs in `gates3/`.
