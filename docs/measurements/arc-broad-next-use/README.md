# Broad next-use (C) — paired measurement

Tier B measurement for the Tier A change in
[docs/evidence/arc-broad-next-use/](../../evidence/arc-broad-next-use/).

## Gate sweep: baseline-v2, 5 starts × seeds 1-100

- **Main side (B):** #233's PR-side sweep at `53acae76`, whose game sources
  are identical to main `1f51bfff`.
- **PR side (C):** `dcd91662`, the game built from a `git archive` export, the
  harness run from the worktree frozen at the same revision.
- Same command, seeds, starts, policy (`baseline-v2`, the gate policy) and
  jobs. Scored by `paired.py` with the committed #231 distinct metric.

`paired.json` holds the full output. Gate start bard-default-path:

| | B | C | Gate |
|---|---|---|---|
| 2+ distinct felt whispers, excluding the hound | 2 | 6 | ≥ 10, not met |
| Hound admission (games accepted) | 88 | 88 | unchanged, met (no seed differs) |
| Games feeling two next-use programs | 0 | 1 | ≥ 3, not met |

Felt programs on the gate start went from 10/0/0 to 16/3/2 (programs 1/2/3);
distinct felt rose in 8 seeds and fell in none. Of 126 later programs C
published on this start, 5 were felt.

Other starts, 2+ distinct excluding the hound (B → C) and two programs felt:
bard 6 → 13 and 3 → 6; bard-inherited 0 → 3 and 0 → 0; madman and
wizard-default-path unchanged at 0. On bard, distinct felt fell in one seed
(24); its harness errors went from 2 to 4.

## Slot hold and attribution

`hold.json` is `broad_hold.py` over every game's retained journal (counts
cross-check against `next_use-felt.jsonl`: 17 felt programs on the gate start,
0 mismatches). On bard-default-path:

- 17 programs had a first delivery; all stayed open afterwards (uses = 2), for
  a median of 40 and a max of 258 moves. 4 reached a second delivery, 9 ended
  by program expiry, 4 by origin expiry.
- In 7 games a fresh origin occurred while a felt program 1 or 2 held the
  slot; in none of them did that stop a later program being published.
- First deliveries: 11 on the first use after admission, 4 after an earlier
  use reached the callback undelivered, 2 after an earlier use never reached
  it (not consumed under C); none on another level, by magic whistle or by
  fountain drink.

`cap1-estimate.json` is an **estimate, not a measurement**, of an effect cap
of 1: each hold becomes a publish chance. Upper bound part 1: 6 → 8, part 3:
1 → 7. Expected at the observed later-program felt rate (5/126): about 6.1 and
1.2. The hold is not why C misses the gate.

## Policy sensitivity: pet-visible-v1 (not the gate)

Same seeds and starts under the `pet-visible-v1` policy, which whistles only when a pet is visibly highlighted on screen. This is a **policy sensitivity, not the gate**. Both sides ran the harness at `dcd91662`, so both report that revision. The main side's game was built from main `1f51bfff` (game sha256s are in the reports directory).

| bard-default-path | main (B) | C |
|---|---|---|
| 2+ distinct felt whispers, excluding the hound | 1 | 4 |
| Hound admission (games accepted) | 85 | 85 (no seed differs) |
| Games feeling two next-use programs | 0 | 0 |

Distinct felt rose in 16 seeds and fell in 3 (21, 39, 82). Other starts: bard 1 → 8 and 0 → 3; bard-inherited 0 → 6 and 0 → 3; madman unchanged; wizard-default-path 0 → 0, with one seed down (51). Hound admission is unchanged on every start. A policy that whistles near a visible pet does not by itself close the gate.

## Files

- `paired.py`, `paired.json` — gate scoring.
- `broad_hold.py`, `hold.json` — slot hold and attribution.
- `cap1-estimate.json` — the cap-1 estimate and the rows it rests on.
- `pet-paired.json` — the sensitivity scoring.
- `sweep/` — both C sweep reports (`.json`, `.md`). The B report is #233's,
  kept in `docs/measurements/arc-recurrence-repair/` history and the reports
  directory.
