# Seed sweep measurements (#167)

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

## Rebind re-sweep (#177 option 1)

Same policy, seeds, starts and clock, with the engine rebinding a superseded
envelope to the newest qualifying origin. The origin lifetime was measured at
100 and at 300 monster moves; nothing else differed.

- `baseline-v1-seeds-1-100-rebind-lifetime-100.{json,md}`: revision
  `ce0a988`, lifetime 100. Games delivered 4; admitted 56.
- `baseline-v1-seeds-1-100-rebind-lifetime-300.{json,md}`: revision
  `1e3c7af`, lifetime 300, report digest `a2ee03e4…11de`. Games delivered 9
  (bard 40, 44, 67, 78, 93; bard-inherited 3, 7, 46, 66); admitted 68.

The lifetime-300 comparison was first measured on an unversioned copy of
`a18e498` with only the lifetime constants changed: delivered 9, admitted 68.
The committed 300 report is a fresh run of `1e3c7af`; every game's stage
counts, loss label and outcome match that first measurement. For every admitted game without a delivered effect, the report's
loss label is the engine's recorded reason (`whistle_capture_suppressed`:
not exactly one visible eligible little dog at the triggering whistle;
`program_expired` and `origin_expired`: the 100-move program window or the
bound origin's lifetime ended first; `level_departure`; and
`native_effect_not_delivered`: armed, but the companion's move was not
witnessed). `admitted_trace_incomplete` (7 games in both runs, all ending in the
player's death) means the journal has no terminal record, so delivery is
unknown, not zero. The madman 61 and bard-inherited 67 harness
errors are the same as in the baseline.

## Companion eligibility re-sweep (#196)

`baseline-v1-seeds-1-100-196-lifetime-300.{json,md}` is the same policy,
seeds, starts, clock and origin lifetime (300) at revision `4f0689c09`, after
#196: any visible tame companion with dog data qualifies, the nearest is
picked, and a whistle program is admitted only with one on screen at the safe
point. Report digest `a6814c4b…9da6`. Games delivered 11 (the 9 above plus
bard 60 and bard-inherited 55); admitted 46; armed 26; W capture suppressions
4, all recorded as `none_in_view`; safe-point refusals that include
`no_companion_in_view` in 53 games. This is the fresh baseline for #164. The
comparison with the lifetime-300 report is in
`docs/evidence/companion-eligibility-196/README.md`.
