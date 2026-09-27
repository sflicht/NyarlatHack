# Seed sweep evidence (#167)

`baseline-v1-seeds-1-100.{json,md}` is the first engine-stage funnel report:
300 games (bard, madman, bard-inherited × seeds 1-100), scripted player,
revision `b037219`.

Reproduce from the repository root on a `CHAOS=1` build:

    python3 scripts/seed_sweep.py --seeds 1-100 --policy baseline-v1 \
      --starts bard,madman,bard-inherited --jobs 3 --out <stem>

The committed report is from revision `b037219`, report digest
`3c0b3e7d…6b8d` (full value in the report header). An earlier revision,
`1c9fba8`, produced byte-identical JSON and Markdown in two independent
passes; that reproducibility check was not repeated at `b037219`.

Limits beyond those in the report:

- Engine stages only. Player notice, attribution and changed decisions are
  human-only (#44) and are not inferred from these numbers.
- Two games end in a harness error in both passes (madman seed 61: a prompt
  the player cannot dismiss; bard-inherited seed 67: an unhandled
  `--More--` message). They are counted, not discarded.
- No Wizard start; the ordinary default start is a Bard.
- The sweep clock (`sweep_clock.c` pins `time()` to 1700000000, and the
  harness sets `TZ=UTC`) is 2023-11-14 22:13 UTC. Every game therefore runs
  at new moon (`phase_of_the_moon()` = 0, "Be careful! New moon tonight.")
  and at night (`night()` true). This is reproducible but biases the
  population.
- #164's per-1000-turn, per-level and budget-over-time views are not included.
