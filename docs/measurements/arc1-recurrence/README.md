# Arc 1 recurrence (PR 5): ordinary capture and paired sweep

Verification tier B. The engine change is presentation only: a fixed
recurrence line is shown just before an admitted program's own telegraph.
Admission, budget, RNG draws, save layout, effects and replay are unchanged.
The scheduler preference only reorders choices among origins that are ready at
the same safe point, using public `next_use-felt.jsonl` rows.

## Wording and when it fires

Contract `telegraph_extensions` ids 5 and 6 (the frozen block is byte-identical):

- W: "Again, the whistle carries farther than it should."
- F: "Again, the fountain's water may not run true."

The engine shows it at admission of program k >= 2 for each family in the
envelope that an earlier, closed program of this game delivered to the player
(a witnessed W, or an F drink that changed). It comes before the program's
own telegraph and therefore before any effect. It names no hidden state. The
fact it reports is one the player already saw.

## Ordinary capture

`ordinary/` is a real nonwizard `python3 -m chaos play --ordinary` run on
revision `a8d4137381dc48cce193f611c232c56902269e30`. It uses the default path
with haunt, M1 and next-use on. No model, wizard, seed or clock override,
hand-placed envelope, or policy retry was used. The recipe is the same as #228:
apply the tin whistle, pray, apply; wait for program 1's terminal receipt;
apply, pray, apply; save, restore, search, quit.

Program 1 (W) was admitted, then witnessed at turn 9 (public felt row) and
completed. Program 2 (W) was published from a fresh origin after terminal
receipt 20. At the turn-15 prayer the transcript reads:

    You begin praying to Pan.--More--Again, the whistle carries farther than it should.--More--The next whistle may call unusual attention.

Program 2 then stayed quiet and completed. `run/reveal.json` groups both
programs under `Motif: the whistle, 2 programs, felt 1 time.` and shows the
Recurrence line on program 2 only. Save and quit returned 0, and the v3 M2
choice survived restore.

### Every attempt

- a1: never started. `hermes-heavy` deferred it (exit 75, both slots held by
  the two sweeps), and no game process ran.
- a2: `attempt-a2-harness-error/`. This start rolled a wooden flute, not a tin
  whistle (see the retained inventory). The bounded recipe aborted with no
  qualifying action and no envelope.
- a3: `ordinary/`, the capture described above.

## Paired sweep

Main is a frozen `git archive` of `44531194e`; the PR is `a8d41373` (the
engine and scheduler are byte-identical at the later head). Each side has its
own CHAOS=1 build (0 warnings) and uses the committed `baseline-v2` policy,
seeds 1-100, starts bard, madman, bard-inherited, bard-default-path and
wizard-default-path, with `--jobs 2`. Both sides use the same seeds and starts.
The full JSON reports (about 16 MB each) are retained off-repo. Their per-start
markdown is in `sweep/`, and the paired numbers are in `sweep/paired.json`.
Report SHA-256: main `29e5be459403a3ecd8e6f51f2c2c6e3c4d2b17e102e15aef1b883e0c06522cbd`, PR `c4fad4587862feb2100d34ef3c816651b9b43581a18cace2fb187594d2a151f8`.

Cells are main / PR:

| start | 2+ felt | 1+ felt | felt events | hound games | hound steps | admitted | delivered | harness errors |
|---|---|---|---|---|---|---|---|---|
| bard | 12 / 12 | 31 / 31 | 49 / 49 | 0 / 0 | 0 / 0 | 64 / 64 | 14 / 14 | 2 / 2 |
| bard-default-path | 69 / 69 | 80 / 80 | 237 / 237 | 88 / 88 | 196 / 196 | 50 / 50 | 10 / 10 | 0 / 0 |
| bard-inherited | 1 / 1 | 7 / 7 | 8 / 8 | 0 / 0 | 0 / 0 | 41 / 41 | 5 / 5 | 0 / 0 |
| madman | 0 / 0 | 5 / 5 | 5 / 5 | 0 / 0 | 0 / 0 | 8 / 8 | 0 / 0 | 0 / 0 |
| wizard-default-path | 63 / 63 | 79 / 79 | 230 / 227 | 88 / 88 | 210 / 210 | 3 / 3 | 0 / 0 | 0 / 2 |

### Gate

- 2+ felt on PR bard-default-path: **69/100** (threshold 35). **Pass.**
- Hound admission: identical per seed on every start (88/88 on both default
  paths). **Pass.**

To be plain: this gate does not measure Arc 1. Main already scores 69/100,
and the PR moves no felt count on any bard-default-path seed. Of the 69, 62
reach 2 only with at least one visible hound step (bard-default-path felt
events: 196 hound, 29 door, 12 next-use W), and the hound was unchanged. On this policy the
felt-family preference changed **zero** published envelope families out of 500
games. The policy rarely has two families ready at the same safe point after a
felt program. The recurrence line is presentation only.

What did change: the recurrence line appeared in 14 PR games (19 times, all
W) and in 0 main games. Each of those games had an earlier felt W program.

### Harness errors

bard seeds 48 and 75 hit the same known shopkeeper harness assertion on both
sides. wizard-default-path seeds 57 and 58 hit terminal-readiness timeouts on
the PR side only. Rerun alone on each frozen build (`--jobs 1`), both seeds
finished `died` on both sides with identical felt counts (0 and 9). That points
to a load-dependent harness timeout, not a game difference. The rerun counts
are recorded in `paired.json`; the table above keeps the raw sweep numbers.
That accounts for the PR's wizard-default-path total of 227 versus 230.
