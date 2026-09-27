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

## Recorded-reasons re-run (#177)

`baseline-v1-seeds-1-100-recorded-reasons.{json,md}` is the same sweep (same
policy, seeds, starts and clock) at revision `5b1420a`, which only adds the
engine's recorded rejection row. Report digest `a761389e…93be`. The admission
rule is unchanged, so the stage counts match the baseline (177 published,
5 admitted, 0 delivered); only the loss labels changed from `inferred:` to the
engine's `rejected:` reasons. The Markdown was re-rendered from the committed
JSON after correcting one stale limit line in `scripts/seed_sweep.py`; the JSON
is the sweep's own output.

Across the 153 rejection rows (the other 24 published envelopes were admitted (5) or never reached their safe point (19)): `origin_expired` 140, `origin_superseded` 121,
`level_mismatch` 79, `origin_unbound` 14. No row reports `missed_index` or
`budget`: every envelope was evaluated at its exact `at`, and the budget check
was never reached.
