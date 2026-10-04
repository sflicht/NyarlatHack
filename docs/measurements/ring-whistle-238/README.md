# Paired sweep: C attention (main) vs ring (#238)

Scripted bot, not a player model. Engine stages and felt counts only.

## Revisions and command

- **main arm:** `3b89f6e2a25c7cd363d1e958e7f9ff5bce997163` (origin/main, #237
  merged; C attention effect). Report digests are in `comparison.md`.
- **ring arm:** `29349da082eecb669c79f5555209051c5a35e08e` (feat/ring-whistle).
  `git diff 29349da08 <PR head>` touches only `docs/`.
- Each arm ran from its own `git archive` export, built `make -j2 install
  CHAOS=1` (0 warnings), through `hermes-heavy`:

```
python3 scripts/seed_sweep.py --seeds 1-100 --policy baseline-v2 \
  --starts bard,madman,bard-inherited,bard-default-path,wizard-default-path \
  --jobs 2 --work <scratch> --game-dir <export>/dnethackdir --out <stem>
```

- The export has no `.git`; `seed_sweep.py` records `git rev-parse HEAD`, so
  each export was given a minimal `.git` whose HEAD is the arm's revision.
- `compare.py main.json ring.json > comparison.md` reproduces
  `comparison.md` byte for byte. Run against the #237 probe report twice, it
  reproduces that proposal's "today" figures (6/1, 13/6, 3/0); the main arm
  here gives the same figures.
- `guards.py <ring export> <work dir>` reads every program journal
  (`next_use-journal.jsonl` and `next_use-journal.{2,3}.jsonl`).
- Full per-game reports (16 MB each) are not committed. `paired-summary.json`
  keeps identity, aggregates and per-game outcome, turns, hound, sessions,
  distinct felt sources and program funnel for both arms.

## Gate (part 1 = 2+ distinct felt whispers excluding the hound; part 3 = 2+ felt next-use programs)

| start | main | ring | proposal B bound (old check) | B bound, no program-1 companion check |
|---|---|---|---|---|
| bard-default-path | 6 / 1 | **24 / 16** | 12 / 4 | 23 / 13 |
| bard | 13 / 6 | **34 / 31** | 31 / 19 | 37 / 26 |
| bard-inherited | 3 / 0 | **5 / 3** | 6 / 2 | 11 / 7 |
| madman | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| wizard-default-path | 0 / 0 | 1 / 1 | 1 / 1 | 1 / 1 |

Why ring passes the "upper bounds" on bard-default-path and on part 3: the
estimate held admission at today's and credited each program once. Ring
changes admission:

- program 1 no longer needs a companion (`rejected:no_companion_in_view` 5 →
  0 on bard-default-path, 8 → 0 bard, 18 → 0 bard-inherited);
- deliveries earn the pacing credit the proposal said it did not count, so
  `rejected:budget` falls 16 → 9 on bard-default-path;
- admitted programs: 68 → 106 (bard-default-path), 98 → 137 (bard),
  46 → 75 (bard-inherited).

More admitted programs, each able to ring twice, gives more games with two
felt programs. bard-inherited stays under its no-check bound: the bot dies
early there (91–92 of 100 games), and 23 of its 80 ring uses were guarded,
15 of them for an adjacent hostile.

## Hound admission

Identical in every start: per-seed `haunting` details and visible steps match
in all 500 pairs (bard-default-path 88 accepted / 196 steps;
wizard-default-path 88 / 210; other starts have no hound).

## Ring uses and guards (ring arm; main has none)

| start | delivered | guarded | games rang | by guard |
|---|---|---|---|---|
| bard-default-path | 112 | 21 | 55 | confused 8, peaceful adjacent 7, hostile adjacent 6 |
| bard | 159 | 48 | 60 | peaceful adjacent 25, hostile adjacent 14, confused 9 |
| bard-inherited | 57 | 23 | 36 | hostile adjacent 15, confused 5, low HP 3 |
| wizard-default-path | 3 | 0 | 1 | – |
| madman | 0 | 0 | 0 | – |

Stunned, hallucinating, engulfed and water never fired.

## Side-effects on the bot (main → ring)

| start | deaths | harness errors | total turns | median final turn | seeds with changed outcome |
|---|---|---|---|---|---|
| bard-default-path | 57 → 58 | 0 → 1 | 158058 → 158472 | 1698 → 1667.5 | 22 |
| bard | 52 → 56 | 3 → 2 | 157253 → 153985 | 1822 → 1688.5 | 22 |
| bard-inherited | 92 → 91 | 0 → 1 | 65359 → 61296 | 475 → 488.5 | 2 |
| madman | 100 → 100 | 0 → 0 | equal | equal | 0 |
| wizard-default-path | 80 → 80 | 0 → 0 | 123852 → 124578 | equal | 1 |

Changed seeds are listed in `comparison.md`. Five moves of confusion change
the bot's movement, so its games diverge from the first ring onward.

## Restore rejects (found by this sweep; pre-existing on main)

Three harness errors are the same failure: after `#save`, restore stops with
"Incompatible CHAOS save state; save file preserved." (main bard 10; ring
bard-inherited 26 and bard-default-path 42). An instrumented scratch build
(never committed) located it in both arms (main bard 10 included):
`restore_snapshot`
(`src/chaos_next_use_runtime.c`) refuses a live snapshot whose
`level_token` differs from the restoring level. A broad (C) program survives
level changes by design, so a broad program admitted on one level and saved
on a deeper one cannot be restored. Ring admits more broad programs, so it
hits this more often (1 → 2 games here). Exempting broad programs from that
check restored both ring seeds and played them on. The other two harness
errors (main/ring bard 48 and 75) are a bot screen assertion, identical in
both arms.
