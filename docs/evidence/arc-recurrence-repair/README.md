# Recurrence repair (B) — evidence

Verification tier: **A** (admission, program lifetime, Lua context range).
Player-visible delta: after "Again, the whistle carries farther than it
should." the next whistle near a companion now does something. Program 2 and
3 always author an effect, are no longer refused at admission for a missing
companion, and stay armed for 300 moves instead of 100. Program 1 is unchanged.

Sam chose option B of the [unfelt diagnosis](../../measurements/arc-unfelt-diagnosis/)
on 2026-10-02. The paired sweep is in
[docs/measurements/arc-recurrence-repair/](../../measurements/arc-recurrence-repair/).

## What changed

- **Director** (`chaos/next_use_schedule.py`): with the repair on, the menu for
  program 2 or 3 omits the `quiet` row, so the seeded choice
  (`RandomHistoryBackend(seed + k - 1)`) picks among effect rows. Program 1's
  menu and choice are unchanged. The envelope's `ttl` is 100 for program 1 and
  300 for repaired later programs (`chaos.next_use_envelope.program_lifetime`).
- **Engine** (`src/chaos_next_use*.c`): the envelope `ttl` is validated
  against the ordinal: program 1 must declare 100; programs 2-3 may declare 100
  (pre-repair) or 300 (repaired). Admission sets
  `program_expiry = admission_move + ttl`. A program with `ttl` 300 skips the
  #196 C3 admission check (`no_companion_in_view`); the whistle-time check and
  its recorded suppression are unchanged. The Lua context `age` range is
  0..299 (it was 0..99); program 1 still never sees an age above 99 because
  it ends at 100.
- **Snapshot import** accepts a closed or active program whose lifetime is 100
  (any ordinal) or 300 (ordinal 2-3 only), and rejects any other value.

Unchanged: engine authority (the engine still validates source, budget,
families and origins), the telegraph wording and timing, no retiming, fresh
origin, terminal before next, the cap of 3 and the budget. No new state is
read; no-whisper and CHAOS=0 paths do not reach this code.

## Save and record rules

The envelope's existing `ttl` field carries the rule, and the admitted
`program_expiry` is already saved. Nothing in the save layout changed:
native state stays **5**, next-use snapshot stays **v6**. This is not
refuse-and-keep; there is nothing to refuse.

- **Old native saves** restore and continue unchanged. Every program they
  admitted has a 100-move lifetime, which import still accepts for any
  ordinal; a pre-repair program 2 keeps its 100 moves.
- **`ordinary-choice.json` v3** (written before this PR): restore keeps the
  pre-repair director. Later programs keep the seeded quiet-or-effect choice
  and publish `ttl` 100, so the engine keeps the admission companion check and
  the 100-move lifetime for them. An old game therefore plays exactly as on
  main.
- **v4** (fresh ordinary runs): `m2` gains `repair`, which must equal
  `enabled`. Restore follows it.
- **No record** (before #198): explicit flags only, no later programs; unchanged.

Tests: `test_launcher_defaults` (v4 fresh, v3 restore follows the old director,
invalid `repair` fails closed), `test_next_use_multi_schedule` (repair authors
the effect with `ttl` 300 for programs 2-3; without it seeds 1 and 2 still
author quiet with `ttl` 100), `test_next_use_safe` (repaired later program
admits without a companion in view; a pre-repair later program is still
rejected `no_companion_in_view`; mismatched `ttl`/ordinal rejected),
`test_next_use_snapshot` (lifetime/ordinal validation on import), and the
native linked series (`next_use_safe.c`, `next_use_journal_native.c`).

## Gates

Run on the PR head under `hermes-heavy` and tmux, logs retained in
`~/.hermes/reports/nyarlathack-arc-repair/`: CHAOS=0 and CHAOS=1 builds with
0 warnings each, then the fast suite and the native suite. Counts and the
exact head are in the PR body. The first native run (on `53acae76`) failed two
tests that still assumed the old rules: the linked native series expired
program 2 at 100 moves, and an ordinary-restore test expected record v3. Both
were updated to the new rules; no test was removed or skipped.

## Ordinary capture

`ordinary/` is a real nonwizard `python3 -m chaos play --ordinary` run on the
default path: no wizard mode, seed, clock or model, and no hand-placed
envelopes. The recipe is #229's: whistle, `#pray`, whistle, then search until
program 1 closes; whistle, `#pray`, whistle, then search until program 2
closes. The transcript (`terminal.txt`) shows, in order:

1. "The next whistle may call unusual attention." (program 1's telegraph);
2. "The whistle's echo sharpens your visible companion's attention."
   (program 1 felt, turn 9);
3. "Again, the whistle carries farther than it should." then "The next
   whistle may call unusual attention." (program 2 admitted, turn 15);
4. "The whistle's echo sharpens your visible companion's attention."
   (program 2 felt, turn 23).

`next_use-felt.jsonl` has one row each for program_ordinal 1 and 2. Program
2's envelope declares `ttl` 300; the choice record is v4 with
`m2.repair` true.

Every attempt:

- a1: `attempt-a1-program-1-unfelt/`. Program 1 completed without being felt,
  so no "Again" line followed (the recurrence line needs an earlier felt
  program). Program 2 was admitted and felt. It is kept as a second witness
  that a repaired program 2 reaches the player, but it does not show the
  "Again" sequence.
- a2: `ordinary/`, above.

Both exited 0 on save and quit. The PTY preload, decoding and path
normalisation are as in #229 (`docs/measurements/arc1-recurrence/`); raw
files and the driver are retained in `~/.hermes/reports/nyarlathack-arc-repair/`.
