# Ring whistle effect (#238)

Tier A evidence: the change adds saved state (next-use snapshot v8), a new
native effect (confusion through `make_confused`), and new admission rules
(ring programs skip the companion admission check).

Design: [`docs/proposals/felt-whistle-effect.md`](../../proposals/felt-whistle-effect.md),
option B ("ring"). Sam's decisions on #237: build ring, default-on for new runs.
- **Q1:** in a ring run, every W program is a ring program.
- **Q3:** ring programs drop program 1's companion admission check.
- **Q4:** a use is guarded: when a public guard holds, nothing happens and the
  program keeps waiting.
- **Telegraphs (q_af7157b1):** option A.

## What changed

- **Contract.** Telegraph rows 9–11, added to the existing rows.
  - Row 11, "For a while, your whistles may ring on after you stop.", is shown
    on every ring program.
  - Row 10, "Again, a whistle may ring on after you stop.", is the recurrence
    line for programs 2–3, once an earlier program has rung.
  - Row 9, "The next whistle may ring on after you stop.", is registered for a
    future single-use ring program and shown by none today.
- **Envelope v4.** It adds `w_effect: "ring"` and the telegraph
  `next-use-v4-Wr`, plus the intent op `whistle_ring`.
  - The intent must match the program's loaded effect. A mismatch ends the
    program as an invalid callback, so no program can switch effect mid-run.
  - v2 and v3 envelopes are read exactly as before.
- **Runtime.** A ring program is a broad program (C) with a W effect.
  - **Delivered use:** recorded as a `RING_DELIVERED` row in the RANG slot. It
    counts toward the cap of 2 and credits pacing.
  - **Guarded use:** recorded as a `RING_GUARDED` row that names the guard. It
    spends no cap and the program keeps waiting. Its callback still counts
    toward the 8-callback bound, so the program stays finite.
- **Engine** (`src/chaos_engine.c`, no upstream file changed).
  - At the whistle, ring programs skip the companion pick.
  - After the callback, the guards are read from public state only, in order:
    1. Confusion, Stun, Hallucination;
    2. engulfed;
    3. HP at or below a third of max;
    4. an adjacent hostile the player can spot;
    5. an adjacent peaceful the player can spot;
    6. water or lava in the remembered map next to the player.
  - With no guard holding: "Your whistle's note goes on ringing inside your
    head." and `make_confused(HConfusion + 5, FALSE)`. The confusion ends with
    the native "You feel less confused now."
  - No RNG is drawn.
- **Saves.** Snapshot v8 is v7 plus `w_effect`.
  - The effect is bound into the snapshot's binding hash (`|w=ring`).
  - Versions 6 and 7 are written and read byte-for-byte as before.
  - Confusion itself is `HConfusion` in `struct you`, which is already saved.
  - Nothing new goes into bones.
- **Felt.** A ring program counts as felt once it has rung. It writes the
  existing `next_use-felt.jsonl` row.
- **Director.** Choice record v6 adds `m2.ring`. A v5 record restores with
  ring off, so C's rules stay exact.
- **Reveal.** The end-of-game reveal gains ring wording for the telegraph,
  effect, outcome and recurrence lines.

## Tests

All runs went through `hermes-heavy`, with suites under tmux into retained
logs.

- **Builds.** CHAOS=1 (`make install`) and CHAOS=0: 0 warnings each.
- **Fast suite.** OK: 1623 tests, 233 skipped.
- **Native next-use suite** (`NYARLATHACK_GAME_TESTS=1`, `test_next_use*.py`):
  OK.
- **Hosted Quality CI** (full native suite): green on cc7c0833a.
- **Linked ring fixture** (`tests/chaos/test_next_use_ring.py`, 20 tests):
  - the cap of 2;
  - each of the 8 guards (held, nothing delivered, program waiting);
  - guarded, rang, guarded, rang (guarded uses spend no cap);
  - guarded uses ending at the callback bound;
  - out-of-range guard, wrong root, or a second answer to one use: refused;
  - an intent that doesn't match its effect, both ways: ends the program;
  - level change and expiry;
  - save/restore: v8 stays ring, C's v7 stays v7;
  - a tampered effect, version or bound: refused;
  - the journal reader accepts ring journals and records each guard;
  - envelopes: W rows become v4 ring programs, F rows and C runs are
    unchanged, and ring without broad is refused.
- **Telegraph mapping**
  (`test_next_use_safe.py::test_ring_telegraph_mapping_option_a`). Three real
  ring envelopes are admitted through the safe layer, for four patterns:
  none rang, program 1 rang, program 2 rang, all rang. Expected lines:
  `[[11], [11], [11]]`, `[[11], [10, 11], [10, 11]]`,
  `[[11], [11], [10, 11]]` and `[[11], [10, 11], [10, 11]]`.
  `next_use_safe.c felt_checks` pins the text of rows 9–11.
- **Real Unix save/restore and exact replay**
  (`test_next_use_ordinary.py::test_starting_whistle_admits_once_through_the_launcher`,
  native, nonwizard, through the launcher).
  - The prefix rings at the second whistle, then saves, and the process exits.
  - The record and replay runs each restore their own private copy of the save.
  - They end with byte-identical events, journal, envelope, owner, receipt,
    felt, schedule and observer files and xlogfile.
  - The binding hash, including `|w=ring`, is recomputed independently.
- **Sweep metrics** (`test_sweep_programs.py`). A delivered ring is felt at
  its whistle's public notice. A guarded ring is not felt, and neither is an
  attention program's plain whistle. The effect codes match the engine header.

## Real nonwizard play

`python3 -m chaos play --ordinary` with no next-use flags, so ring came from
the defaults. Public keys only: inventory, apply the tin whistle, `#pray`,
apply it again, search until the confusion ends, quit, answer the reveal. No
clock shim, no wizard mode, no model call. The driver and raw terminal stream
are retained outside the repository
(`~/.hermes/reports/nyarlathack-ring-238/capture/`, with SHA256SUMS).

In order:
1. Choice record v6 (`m2.ring: true`); the envelope is v4 (`next-use-v4-Wr`,
   `uses: 2`).
2. At the prayer: "For a while, your whistles may ring on after you stop."
3. "You produce a high whistling sound.--More--Your whistle's note goes on
   ringing inside your head."
4. `Conf` on the status line.
5. "You feel less confused now."
6. The reveal: "Delivered: yes, 1 time; the note rang on in your head and
   confused you."

No companion attention line appeared. The felt record names program 1,
family W. The game never reached a second program, so the "Again" line was not
seen in real play; the mapping test covers it.

## Paired sweep

Main `3b89f6e2` vs ring `29349da08`, baseline-v2 seeds 1–100, five starts;
full tables in [`docs/measurements/ring-whistle-238/`](../../measurements/ring-whistle-238/README.md).

- Gate (part 1 / part 3), main → ring: bard-default-path 6/1 → 24/16, bard
  13/6 → 34/31, bard-inherited 3/0 → 5/3, wizard-default-path 0/0 → 1/1,
  madman 0/0 → 0/0.
- Hound admission identical in all 500 seed pairs.
- Ring uses delivered / guarded: 331 / 92; guards that fired: peaceful
  adjacent 32, hostile adjacent 35, confused 22, low HP 3.
- Restore rejects of a broad program saved on a deeper level than it was
  admitted on: 1 game on main, 2 on ring. Pre-existing (#235); see the
  measurement README.

## Player-visible delta

In new ordinary games, a whistle in a W program no longer depends on a visible
companion. It can make the note ring on in the player's head: a message plus 5
moves of confusion, at most twice per program. Before it rings, the game checks
the player's visible situation (confused, stunned, hallucinating, engulfed, low
HP, a monster next to them, water or lava next to them); if any applies, the
whistle does nothing extra and the program keeps waiting.
