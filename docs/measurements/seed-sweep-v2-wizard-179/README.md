# Seed sweep baseline-v2: Wizard on the default path (#179)

This is the pre-#1 Wizard baseline. #1's acceptance asks that "a default human Wizard can notice it", and the sweep had no Wizard start, so #1's paired sweep would have had no way to measure it.

## The start

`wizard-default-path` in `tests/chaos/sweep_player.py`:

- options `name:ChaosReview,role:Wiz,race:human,gender:male,align:neutral,pettype:kitten,windowtype:tty,!news,!legacy,time,!splash_screen,!perm_invent,!autopickup` plus the sweep's `,!mail`;
- no inheritance (no `descendant`, no `inherited:`);
- alignment and pet are fixed so the start never depends on a random choice;
- played on the same launcher as `bard-default-path`: the ordinary default (`--ordinary --max-runtime 86400`), so the hound and next-use are on and pacing is at its default.

The policy (`baseline-v2`) and every existing start are unchanged.

## Reproduce

From the repository root, on a `CHAOS=1` build of revision `9579e3419`:

    python3 scripts/seed_sweep.py --seeds 1-100 --policy baseline-v2 \
      --starts wizard-default-path --jobs 2 --out <stem>

The run took 988 s at `--jobs 2` under `hermes-heavy`. Report digest: `7af38248f62d477e42cc539ddd323d1866ebf24e870f65f8470428bdc6a50973` (`baseline-v2-wizard-default-path-seeds-1-100.json` and `.md` here).

## Existing reports stay reproducible

On the same revision, `bard-default-path` under `baseline-v2`, seeds 1–10, was played again and compared with `docs/measurements/seed-sweep-v2-179/baseline-v2-seeds-1-100.json` using `python3 scripts/sweep_alert.py compare`. All 10 per-game results were identical: outcome, commands, final status, funnel, save/restore, exit code and sync timeouts. The run and its report are kept in `~/.hermes/reports/nyarlathack-179-wizard/`.

## Results (seeds 1–100)

Bard-default-path is from the committed v2 report and is shown for comparison only. The two starts differ in role, kit and pet, so the gap is not a measurement of any mutation.

| | wizard-default-path | bard-default-path (v2) |
|---|---:|---:|
| Died / turn limit / depth limit | 81 / 17 / 2 | 57 / 39 / 4 |
| Died before turn 300 | 5 | 0 |
| Median last turn | 1166 | 1665 |
| Reached Dlvl 2 / 3 / 4 | 56 / 26 / 7 | 71 / 35 / 11 |
| First felt (all the hound) | 79, median turn 12 | 76, median turn 15 |
| Hound accepted | 88 | 86 |
| Qualifying history | 22 | 87 |
| Next-use admitted / delivered | 3 / 0 | 37 / 10 |
| Holding a whistle | 2 | 85 |
| Harness errors, nonzero exits, sync timeouts | 0, 0, 0 | 0, 0, 0 |
| Save/restore | 88/88 restored | — |

`python3 scripts/sweep_alert.py check` on the Wizard report: 100 games, no alerts, no allowlisted errors. `sweep_alert.py` needed no change.

## What the scripted player mishandles for a Wizard

These are properties of the fixed policy, recorded here rather than tuned away:

- **No food.** A Wizard's starting kit has no food. 91 of 100 games reached "You don't have anything to eat". Hunger dominates the deaths: 35 "died of starvation" and 26 more killed by a monster "while fainted from lack of food" (61 of 81 deaths). The policy only eats from inventory; it does not eat corpses or look for food.
- **No spells, wands or ranged attacks.** The policy has no cast (`Z`), zap (`z`), fire or throw command. Counted from the recorded inputs, it cast nothing in 100 games, so force bolt and magic missile were never used, and the Wizard fought in melee with a quarterstaff. The policy has no read command either, so its starting spellbooks and scrolls were never read (the only `r` keystrokes are the 118 `#pray` commands).
- **Low HP.** Final maximum HP had median 13 (11 to 36), so melee was riskier than for the Bard.
- **Fountains without a whistle.** A Wizard has no whistle, so v2's `p_fountain_no_whistle` rule walks to every seen fountain (89 quaff attempts). 4 of the 5 deaths before turn 300 were water moccasins, and in each of those games a quaff had released "a stream of snakes" from the fountain first. The fifth was "killed by a potion of paralysis".
- **Next-use barely reached.** With no whistle (found in only 2 games), W programs have almost no qualifying history. Next-use was admitted in 3 games and delivered in none. For #1 this start measures the hound and any registered mutation, not next-use.

No harness error appeared, so nothing in the start needed fixing.

## Limits

- One simple fixed policy. The numbers describe this policy, not human play, and the policy is weaker for a Wizard than for a Bard (above).
- The start fixes one alignment (neutral) and one pet (kitten).
- In-game mail is off (`!mail`): it reads the host mail spool, not the seed.
- The start is not in the `seed-sweep` workflow's `STARTS` yet.
