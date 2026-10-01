# Schedule-file bound against qualifying actions (M2, PR 1)

Tier B. No new games were played. This reads the reports already committed
for #1's paired sweep (`docs/measurements/door-reluctance-paired-1/`, seeds
1–100 on five starts, `main` at `d29c4e2a2` and the #1 branch at `313c0eec5`).
It answers one question for the next-use program policy v3
([protocol](../../chaos-protocol.md#next-use-program-policy-v3-m2-contract-engine-pending)):
does `next_use-schedule.jsonl`'s bound of 32 rows starve a second program of
fresh origins?

Each qualifying whistle or fountain notice appends one row to the schedule
file. The engine refuses a row once 32 are there. In the sweep's per-game
funnel, `qualifying_history` counts the rows the engine tried to write, and
`candidate` counts the rows actually written. In all 1,000 games,
`candidate == min(qualifying_history, 32)`.

    python3 docs/measurements/next-use-schedule-bound-m2/schedule_bound.py

regenerates `schedule-bound.json` from the committed files.

## Rows per game (branch side)

| start | median | 90th percentile | max | games over 32 |
|---|---:|---:|---:|---:|
| bard-default-path | 19 | 34 | 54 | 11 |
| wizard-default-path | 0 | 1 | 12 | 0 |
| bard | 18 | 33 | 44 | 11 |
| bard-inherited | 5 | 15 | 33 | 1 |
| madman | 0 | 1 | 4 | 0 |

No game wanted more than 54 rows. `main`'s figures are in `schedule-bound.json`;
its games over 32 differ from the branch's by at most one per start.

## Does the bound cost a second program its origin?

The per-game reports count rows but do not give their turns. Turns come from
the 149 branch games whose run logs were kept (every game that published a
door whisper). `qualifying-turns.json` holds, for each of them, the turns of
its qualifying notices (the same filter `tests/chaos/sweep_funnel.py` uses;
148 of 149 match the committed count exactly), its first admission move and
its last turn.

A row is *fresh* for program 2 if it completed after program 1 must have
terminated: admission plus the 100-move program lifetime. Program 1 often ends
sooner, which only adds fresh rows, so this undercounts.

- 44 kept games admitted a first program.
- 3 of them have no fresh row at all, with or without the bound.
- In 7 the bound trims fresh rows, but each keeps at least 8 (bard seeds 41,
  57, 60, 93, 99; bard-default-path seeds 27, 57).
- In none does the bound leave fewer than 2 fresh rows where an unbounded file
  would have 2 or more.
- The 32nd row lands at turn 1,123 or later in every game that fills the file.

So policy v3 keeps the bound and the first 32 rows. A game that fills the file
has already had about 1,100 turns of origins to bind. With a cap of 3
programs, the bound would matter only for a third program in a long game.
That is worth re-measuring in the M2 paired sweep, not changing now.

## Limits

- Turns cover only the 149 kept games, a biased subset (those with a door
  whisper). The row counts cover all 1,000.
- Freshness here is by turn. The engine's rule is by event sequence, which is
  stricter only within a single turn.
