# Seed sweep baseline-v2 (#179)

Sam's decision (2026-09-29): sweep v2. The policy is `baseline-v2` in `tests/chaos/sweep_player.py`; its rules and the reasons for them are in the PR.

Reproduce from the repository root on a `CHAOS=1` build:

    python3 scripts/seed_sweep.py --seeds 1-100 --policy baseline-v2 \
      --starts bard,madman,bard-inherited,bard-default-path --jobs 2 --out <stem>

`bard-default-path` is played on the ordinary default launcher (`--ordinary`, with the hound and next-use on and pacing at its default). The other three starts use the baseline launcher, as v1 does. The report records the launcher for each start.

## baseline-v1 stays reproducible

The same branch head played `baseline-v1` (300 games) as well. Its report matches the #200 "after" report, which was made on the same engine, game for game:
- 300 of 300 games have identical commands, outcome, final status and funnel;
- the aggregate is equal.

The branch v1 report digest is `c996c467137ad6692d3b8428537eb8aba8b8eb05b1190ce159c4243cf9ecc80c`. The committed #196 report (`docs/evidence/seed-sweep/baseline-v1-seeds-1-100-196-lifetime-300.json`) differs from current main only in the madman's recorded `start_budget` (4 then, 3 now), because #164 (merged after it) made pacing the default. Commands, outcomes and stage counts are identical.

## Results (seeds 1–100)

Report digest `fa61c7b66a830b94a0a39c9e36ec89e2bec3a1659a80284eb308170090ad066f`.

| Start | Died (v1 → v2) | Died before turn 300 | Median last turn | Admitted | Delivered | Harness errors |
|---|---:|---:|---:|---:|---:|---:|
| bard | 61 → 55 | 6 → 3 | 1615 → 1843 | 47 → 42 | 9 → 14 | 0 → 2 |
| bard-inherited | 93 → 92 | 39 → 31 | 402 → 475 | 32 → 30 | 6 → 5 | 1 → 0 |
| madman | 96 → 100 | 6 → 10 | 1187 → 1142 | 9 → 10 | 1 → 0 | 1 → 0 |
| bard-default-path (new) | 57 | 0 | 1665 | 37 | 10 | 0 |

Death causes (from each game's xlogfile):
- bard-inherited: v1 {'monster_other': 76, 'while_praying': 11, 'hunger': 6}, v2 {'monster_other': 85, 'hunger': 7}.
- madman: v1 {'hunger': 78, 'monster_other': 7, 'while_praying': 11}, v2 {'hunger': 71, 'while_praying': 14, 'monster_other': 15}.

**First felt consequence (#179)**

| Start | Games with a felt consequence | By kind | Turn (min / median / max) | Dlvl (median, max) |
|---|---:|---|---|---|
| bard | 17/100 | next_use_W 17 | 200 / 699 / 1145 | 2, 2 |
| bard-inherited | 6/100 | next_use_W 6 | 115 / 366 / 1198 | 1, 2 |
| madman | 0/100 | none | — | — |
| bard-default-path | 76/100 | hound 76 | 5 / 15 / 311 | 1, 2 |

**Rates (#164)**

| Start | Admitted per 1000 turns | Delivered per 1000 turns | Hound accepted per 1000 turns | Per level visited (adm / del / hound) |
|---|---:|---:|---:|---|
| bard | 0.267 | 0.089 | 0.0 | 0.195 / 0.065 / 0.0 |
| bard-inherited | 0.457 | 0.076 | 0.0 | 0.236 / 0.039 / 0.0 |
| madman | 0.1 | 0.0 | 0.0 | 0.063 / 0.0 / 0.0 |
| bard-default-path | 0.234 | 0.063 | 0.545 | 0.171 / 0.046 / 0.396 |

**What this says against Sam's goals**

- **Inherited Bard dying early: not fixed.** Deaths before turn 300 fell only from 39 to 31, and total deaths from 93 to 92. Deaths while praying went from 11 to 0, but monster deaths rose from 76 to 85. So prayer at the game's own trouble line works; the flee and rest rules do not save this character. The policy flees 506 times and rests 947 times and still loses in melee.
- **Madman whistle: essentially not achieved.** The seeking rule found a whistle in only 2 of 100 games (3 whistle attempts, 10 admissions, 0 deliveries). Tool glyphs on Dlvl 1–2 are rare, and the madman starves first (71 hunger deaths). He dies in all 100 games.
- **Default-path start: works.** The hound was accepted in 86 games and gave the first felt consequence in 76, at a median of turn 15 on Dlvl 1. Next-use still got 37 admissions and 10 deliveries alongside the hound.
- **Plain Bard:** deliveries rose from 9 to 14, and there were no stalls (2 in v1). The first felt consequence (a whistle notice) came in 17 games, at a median of turn 699.
- **Harness errors:** v1's two (madman 61, bard-inherited 67) are gone. v2 has two new ones, bard seeds 48 and 75. Both are an unhandled `"I don't know you." "Please follow me."` message, apparently a speech a monster makes, that the v1 settle loop also does not handle. They are counted, not discarded.

## Files

- `baseline-v2-seeds-1-100.json`, `.md`: the v2 report.
- The v1 reproduction run, per-game directories, `summary.json` and `deaths.json` are kept under `~/.hermes/reports/nyarlathack-179/`.

## Limits

- Engine stages only, from a scripted player. Player notice, attribution and changed decisions are human-only (#44).
- The sweep clock is still a new-moon night (see `docs/evidence/seed-sweep/README.md`).
- No Wizard start.

