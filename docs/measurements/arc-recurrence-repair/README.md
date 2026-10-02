# Recurrence repair (B): paired sweep

Measurement for the recurrence repair (Tier A; evidence in
[docs/evidence/arc-recurrence-repair/](../../evidence/arc-recurrence-repair/)).
Gate and metric: [multi-whisper-arc.md](../../proposals/multi-whisper-arc.md),
[arc-metric-distinct-felt](../arc-metric-distinct-felt/). Projection being
tested: [arc-unfelt-diagnosis](../arc-unfelt-diagnosis/) option B, which
projected 8.0 and 3.4 on bard-default-path.

## Result

bard-default-path, seeds 1-100, the adopted gate:

| Gate part | main | PR | Target | Met |
|---|---|---|---|---|
| Games with 2+ distinct felt whispers, excluding the hound | 2 | 2 | ≥ 10 | no |
| Hound admission (games with an accepted hound) | 88 | 88 | unchanged | yes, no seed differs |
| Games feeling two next-use programs | 0 | 0 | ≥ 3 | no |

**B does not meet either count.** The projection (8.0 / 3.4) was wrong. Hound
admission and hound steps (196) are identical seed for seed, so the repair does
not touch the hound.

## Why the projection missed

The repair works as specified: every later program now authors its effect,
none is rejected for `no_companion_in_view` at admission, and later programs
live 300 moves. On bard-default-path, admitted later programs went from 12 to
30. The companion requirement did not go away, though; it moved to the
whistle. Final state of the 30 admitted later programs, read from each
program's own journal (`later-programs.json`):

| Ending | Programs |
|---|---|
| Whistled with no qualifying companion in view: suppressed (`CHAOS_W_SUPPRESSED_NONE_IN_VIEW`) | 17 |
| Never used before the 300-move expiry | 4 |
| Still open when the game ended | 5 |
| Armed: the attention went out | 4 |

None of the 4 armed programs was felt: the public record has no W notice for
them (`delivered` 0). The diagnosis replayed recorded whistle rates and treated
any whistle inside the lifetime as felt, so it ignored the companion check
that now runs at the whistle. On this sweep policy, a qualifying companion is
usually not in view when the bot whistles for a later program. Main rejected 48
later programs at admission for `no_companion_in_view`. Here they are admitted,
and the same requirement suppresses most of them at the whistle. (Main's
per-game journals are gone, so the programs cannot be matched one for one.)

Admission rejections for later programs are now budget (28 + 13), missed safe
index (2 + 1) and expired or superseded origins (2 + 1). Program 1's
published, admitted, felt and termination counts are identical between the
sides, as intended.

Other starts (not gated): bard, which plays without the default path,
improved from 0 to **3** games feeling two programs, and 2+ distinct from 5 to
6. bard-inherited, madman and wizard-default-path are unchanged on the gate
metrics. No seed on any start lost a distinct felt whisper except one
bard-inherited seed (one up, one down; see `paired.json`).

## What this means for C

C (one program covers every whistle and fountain use until it expires) is the
change that could help here: a suppressed whistle would no longer consume the
program. The diagnosis's "C on top of B" projection used the same flawed
assumption about companions, so its 18.1 / 12.6 should not be relied on.

## Method

- **PR side:** `53acae76` (this branch before the docs and test-only commits;
  game sources identical to the PR head). Built warning-clean from a
  `git archive` export; 500 games, sweep exit 0, worktree clean and unchanged
  before and after. `scripts/seed_sweep.py --seeds 1-100 --policy baseline-v2
  --starts bard,madman,bard-inherited,bard-default-path,wizard-default-path
  --jobs 2`, under `hermes-heavy`.
- **Main side:** #231's retained re-baseline at `703ee7e5`, whose game sources
  are byte-identical to main (#231's README). It used the same command, seeds,
  starts, policy and jobs. Report SHA-256 `671a0bb9…`; the PR report is
  `ebce9dd4…`. Both are in `paired.json`.
- **Scoring:** `paired.py MAIN.json PR.json` scores both reports with the
  committed #231 metric (`sweep_programs.distinct_felt`) and writes
  `paired.json`. Harness errors are the same two bard seeds (48, 75) on both
  sides.
- `later-programs.json` reads the final W/F slot of each admitted later
  program's journal on the PR side. The per-game journals behind it are
  retained outside the repo (`~/.hermes/reports/nyarlathack-arc-repair/`); the
  sweep work tree was cleaned.

Limits: one bot policy, which never moves toward its pet before whistling.
Real players may keep the companion in view far more often. This sweep
measures the policy, not players.
