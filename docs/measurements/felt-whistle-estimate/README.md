# Felt-whistle estimate

**Tier B, measurement only.** No gameplay, engine, director or contract
change; **player-visible delta: none.** This supports
[`docs/proposals/felt-whistle-effect.md`](../../proposals/felt-whistle-effect.md).
Everything here reads private journals and one engine probe. It is analysis,
not player knowledge, and none of it reaches the director.

## Data

- **Plain runs:** #236's retained per-game copies of the C gate sweep re-run
  at `3f067b65` (baseline-v2, seeds 1–100, five starts, `--jobs 2`), under
  `~/.hermes/reports/nyarlathack-arc-later-funnel/runs-plain/`. The report is
  `docs/measurements/arc-later-program-funnel/sweep/`.
- **Probe runs:** a new instrumented twin of the same sweep. Game and harness
  both ran from a `git archive` export of `8d2c8df3`, never from the session
  worktree, under `hermes-heavy`. `git diff 3f067b65 8d2c8df3` is empty for
  `src/`, `include/`, `win/`, `dat/`, `util/`, `sys/`, `chaos/`, `tests/`,
  `scripts/` and `GNUmakefile`, so the two revisions play identically. Per-game
  copies are under `~/.hermes/reports/nyarlathack-felt-whistle/runs-probe/`.

| sweep | report sha256 | game binary sha256 |
|---|---|---|
| plain, 3f067b65 (#236) | `eeb5b937…8463` | `721dc482…a391` |
| probe, 8d2c8df3 + patch | `88fd7681…44c0` | `e83aa56b…23a3` |

### The probe

[`felt-probe.patch`](felt-probe.patch) is applied **only to the measurement
build**; it is never committed to `src/`, `include/` or `chaos/`. It adds one
block at the top of `chaos_next_use_whistle_completed`
(`src/chaos_engine.c:644`), which runs after every completed whistle. The
block reads state, draws no random numbers, and writes one line to
`felt-probe.log`, keyed by the action's public root:

- the trigger fields of `src/chaos_engine.c:657-661` (object type, `known`,
  quantity, artifact, in inventory, broad program active);
- `chaos_next_use_companion_pick()`: a qualifying companion on screen, and
  its squared distance to the player;
- the player's public status: confused, stunned, hallucinating, blind,
  engulfed, HP and max HP, and a count of visible hostile monsters adjacent;
- sleeping, non-tame monsters in the band that a 4× whistle radius would
  newly reach, split by whether the player can see them.

### Twin check

`felt_estimate.py` reuses #236's `twin_match`. Receipts, lifecycle, schedule,
whispers, events and last turn are byte-identical in **495 of 500 games**.
The five that differ are **excluded from every probe-derived count**: their
programs still count as admitted, and their gate figures are counted as today:
`bard-00024`, `bard-00069`, `bard-default-path-00021`,
`bard-default-path-00072` and `bard-inherited-00078`. Journals are not
compared: they carry a per-process `run_token`.

### Today's gate, reconstructed

The script rebuilds today's gate from the plain report before it estimates
anything. Part 1 matches the report's `games_2plus_excluding_hound` on all
five starts (6, 13, 3, 0, 0).

## Method

A program's **window** runs from admission to the earliest of three points:
origin expiry (`src/chaos_next_use_runtime.c:926-934`), program expiry, and
the game's last turn. Today's early ends (a broad program's second delivery,
an invalid callback) are not applied, because a new effect changes them.

A **valid whistle** is one that today's trigger accepts
(`src/chaos_engine.c:657-661`). Each candidate's precondition is evaluated on
the probe line for that whistle. Every precondition is public state.

- **A, call:** a qualifying companion is on screen and not adjacent (squared
  distance > 2), so moving it beside the player is visible.
- **B, ring:** the player is not already confused, is not hallucinating or
  engulfed, has no visible hostile adjacent, and has HP above a third. The
  proposal's water/lava and peaceful-neighbour guards are **not probed**, so
  B's counts are an upper bound on those.
- **C, carry:** a visible sleeping monster lies in the extended wake band.

## Results

Uses are valid whistles meeting the precondition; programs are admitted
programs with at least one such use. Today's figures are #236's: uses that
reached the program's callback, and how many delivered (21 of 58 on
bard-default-path).

<!-- T1 -->
| start | program | admitted (probed) | today: delivered of reached callback | valid whistles in window | A call: uses / programs | B ring: uses / programs | C carry: uses / programs | reference: companion in view, uses / programs |
|---|---|---|---|---|---|---|---|---|
| bard-default-path | 1 | 37 (36) | 16 of 38 | 57 | 5 / 5 | 57 / 23 | 0 / 0 | 52 / 21 |
| bard-default-path | 2 | 25 (23) | 3 of 11 | 38 | 2 / 2 | 35 / 15 | 0 / 0 | 13 / 5 |
| bard-default-path | 3 | 6 (5) | 2 of 9 | 14 | 1 / 1 | 10 / 3 | 0 / 0 | 5 / 2 |
| bard | 1 | 42 (40) | 23 of 42 | 62 | 15 / 11 | 61 / 28 | 0 / 0 | 48 / 23 |
| bard | 2 | 42 (41) | 11 of 23 | 122 | 9 / 3 | 114 / 32 | 0 / 0 | 29 / 13 |
| bard | 3 | 14 (14) | 2 of 5 | 30 | 3 / 3 | 29 / 11 | 0 / 0 | 10 / 3 |
| bard-inherited | 1 | 30 (29) | 7 of 25 | 45 | 5 / 5 | 37 / 18 | 0 / 0 | 28 / 17 |
| bard-inherited | 2 | 16 (16) | 5 of 10 | 26 | 2 / 2 | 25 / 9 | 0 / 0 | 13 / 6 |
| madman | 1 | 8 (8) | 0 of 1 | 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| wizard-default-path | 1 | 3 (3) | 0 of 0 | 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| wizard-default-path | 2 | 1 (1) | 0 of 0 | 3 | 0 / 0 | 3 / 1 | 0 / 0 | 0 / 0 |
| wizard-default-path | 3 | 1 (1) | 0 of 0 | 3 | 0 / 0 | 3 / 1 | 0 / 0 | 0 / 0 |

On bard-default-path, all programs together: **B's precondition holds on 102
of 109 valid whistles, in 41 of 64 probed admitted programs.** That compares
with 21 delivered of 58 that reached the callback today. A holds on 8 whistles
in 8 programs. C holds on none: across all 4,289 probed whistles no visible
sleeping monster was in the extended band (17 whistles had only unseen ones).

Program 1 refused at admission for no companion in view, and nothing else
(#196 C3). An effect that needs no companion would not need that check.
Counted: refusals with a valid tin whistle meeting the precondition within the
100 moves that program 1 would have lived (`include/chaos_next_use.h:130`).

<!-- T2 -->
| start | program 1 refused, no companion only | probed | A precondition met | B precondition met | C precondition met |
|---|---|---|---|---|---|
| bard-default-path | 38 | 38 | 2 | 29 | 0 |
| bard | 35 | 35 | 1 | 24 | 0 |
| bard-inherited | 30 | 30 | 2 | 16 | 0 |
| madman | 0 | 0 | 0 | 0 | 0 |
| wizard-default-path | 0 | 0 | 0 | 0 | 0 |

## Gate estimate (not a measurement)

Gate: part 1 = games with 2+ distinct felt whispers excluding the hound
(target 10); part 3 = games feeling two next-use programs (target 3).

Assumptions:

1. Each admitted program with at least one precondition use becomes felt,
   once. The effect has no classifier: when its guards pass it delivers, and
   its message is the felt row. This is an **upper bound**:
   - program 1 may still author `quiet`, while programs 2–3 always author
     the effect (`chaos/next_use_schedule.py:380-384`);
   - the unprobed B guards may refuse some uses.
2. A newly felt program adds one distinct source to part 1, and one program
   to part 3, only where today's report does not already credit it.
3. The rest of the game is held fixed. That is false in detail: a confused
   player moves differently afterwards. The estimate ignores that divergence.
4. Admission is held at today's (budget unchanged). The last column also
   admits the program-1 refusals counted above, without rechecking origin or
   budget: a looser upper bound.

<!-- T3 -->
| start | today: part 1 / part 3 | A estimate | B estimate | C estimate | B upper bound, program 1 without the companion admission check | twin games excluded (counted as today) |
|---|---|---|---|---|---|---|
| bard-default-path | 6 / 1 | 6 / 1 | 12 / 4 | 6 / 1 | 23 / 13 | 2 |
| bard | 13 / 6 | 14 / 8 | 31 / 19 | 13 / 6 | 37 / 26 | 2 |
| bard-inherited | 3 / 0 | 5 / 1 | 6 / 2 | 3 / 0 | 11 / 7 | 1 |
| madman | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 0 |
| wizard-default-path | 0 / 0 | 0 / 0 | 1 / 1 | 0 / 0 | 1 / 1 | 0 |

## Reproduce

```
# from the repository root
python3 docs/measurements/felt-whistle-estimate/felt_estimate.py \
    PLAIN_RUNS PROBE_RUNS PLAIN_SWEEP_REPORT.json > felt-estimate.json
python3 docs/measurements/felt-whistle-estimate/tables.py felt-estimate.json
```

`felt_estimate.py` imports #236's `funnel.py` for the journal reader and the
twin check. The committed [`felt-estimate.json`](felt-estimate.json) is its
output on the runs above.

**Probe sweep recipe:**

1. `git archive 8d2c8df3` into a scratch directory.
2. Apply `felt-probe.patch`.
3. Build: `make -j2 install CHAOS=1 CC=/usr/bin/cc` (0 warnings).
4. From the export, run `scripts/seed_sweep.py --seeds 1-100 --policy
   baseline-v2 --starts bard,madman,bard-inherited,bard-default-path,wizard-default-path
   --jobs 2` with `NYARLATHACK_KEEP_ARTIFACTS=1`.

The probe sweep's summary is
[`baseline-v2-seeds-1-100-8d2c8df3-felt-probe.md`](baseline-v2-seeds-1-100-8d2c8df3-felt-probe.md).
