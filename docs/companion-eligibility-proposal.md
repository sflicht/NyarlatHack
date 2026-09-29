# Proposal: which companion a next-use whistle may bind

## Decided (Sam, 2026-09-28)

Sam decided on 2026-09-28. Issue #196 is the implementation contract, and the
pull request that fixes it implements these four choices. Where they differ
from this proposal's recommendation, the decision wins.

- **A2, which companions qualify.** Any visible tame companion with dog data
  (`MX_EDOG`), not only the little dog. Every other guard stays: not the
  steed or rider, not leashed, not summoned, not an exploder, not under
  Conflict or berserk.
- **C3, no qualifying companion in view at the safe point.** The program is
  not admitted, and nothing is charged. Only what is on screen counts. The
  decision row records the new reason `no_companion_in_view`.
- **C0 at the whistle.** If no qualifying companion is in view when the player
  whistles, the program is still suppressed with no refund. Sam did not
  choose C1, so the program does not wait.
- **B1, several in view.** The companion nearest the player wins, by squared
  distance. A tie goes to the top row, then the leftmost column. Monster list
  order, `m_id` and random numbers never decide.
- **Recorded reasons: yes.** The `W_CAPTURE_SUPPRESSED` effect row records why
  the capture was suppressed.

The rest of this document is the design record as written before the
decision.

Status before the decision: **design proposal only.** The sections below
describe options, not the implementation. See "Decisions for Sam" at the end.

## Terms used here

- **Next-use program (W):** an admitted whisper that waits for the player's next
  ordinary whistle, then gives one tame companion extra attention toward the
  player for a few moves. `docs/next-use-whistle.md` is the contract.
- **Admission:** the engine accepts the program at a safe point, charges the
  budget (cost 1 for W only), and shows the telegraph. The program then lives
  for 100 monster moves (its time to live, TTL).
- **Capture:** at the first valid whistle after admission, the engine binds the
  program to one companion. If it cannot, it **suppresses** the program: the W
  slot is consumed, nothing happens in the game, and the journal records
  `whistle_capture_suppressed`. The budget is not refunded.
- **Delivered:** the bound companion's move was witnessed and the public
  message was shown.
- **#182 sweep:** the committed seed sweep
  `docs/evidence/seed-sweep/baseline-v1-seeds-1-100-rebind-lifetime-300.json`
  (revision `1e3c7af`, origin lifetime 300). It has 300 scripted games: starts
  `bard`, `madman` and `bard-inherited`, seeds 1–100.

## Problem

In the #182 sweep, 68 games admitted a program and 9 delivered it. Of the 59
admitted but undelivered, **30** lost it to `whistle_capture_suppressed`: 9 of
them `bard` games and 21 `bard-inherited`. That is the largest single loss
after admission.

## How eligibility is decided today

This is from reading the code on `main` (`337a1929c`).

1. `src/apply.c` (`case WHISTLE`, about line 12267) calls
   `chaos_next_use_whistle_completed(obj, root)` after every tin whistle.
2. `chaos_next_use_whistle_completed` (`src/chaos_engine.c`, about lines
   542–610) goes through these steps:
   - It checks that the whistle is ordinary, identified, a single item and not
     an artifact.
   - It calls `chaos_next_use_action_preflight` (`src/chaos_next_use_runtime.c`
     about line 954). This passes only if a program is committed and its W slot
     is still `PENDING`.
   - It counts **candidates**: every monster on the level that the player can
     see, not dead, whose on-screen glyph is a *little dog*
     (`chaos_presentation_snapshot(x, y, PM_LITTLE_DOG, 0)`, in
     `src/chaos_presentation.c`). Nothing is counted while the player is
     hallucinating or swallowed.
   - If there is **exactly one** candidate, it re-checks that monster: still a
     `PM_LITTLE_DOG`, tame, with dog data (`MX_EDOG`), not steed or rider, not
     leashed, not summoned, not an exploder, no Conflict, not berserk, and its
     `m_id` unique. If those pass, it calls `chaos_next_use_capture_whistle`,
     which arms the slot on that `m_id`.
   - Otherwise, **zero or several** candidates, or the re-check fails, it calls
     `chaos_next_use_whistle_unavailable`. That function
     (`runtime_whistle_unavailable_impl`, about line 1113) sets the slot to
     `CONSUMED_SUPPRESSED`, appends the `W_CAPTURE_SUPPRESSED` effect row and
     ends the program.
3. The little-dog requirement is repeated in `chaos_whistle_witness_finalize`
   (`src/chaos_engine.c` about line 512) and in `dog_move`'s public check
   (`src/dogmove.c` about line 1240). Any change to which companions qualify
   must change all three places together.

Two consequences follow:

- The **first** valid whistle after admission decides the program. A whistle
  with no little dog in view ends it, even with 99 moves of TTL left.
- The rule names a **monster type**, not "your pet". A starting little dog
  that grows into a *dog* stops qualifying.

## What the #182 data shows

The committed report records only the loss label, so I re-ran the 30
suppressed games (same seeds, starts, policy and clock) on `main` with a
scratch diagnostic build. The diagnostic was not committed; the patch is
`diag-eligibility-v2.patch` in the report directory below. It appends one
JSON line per valid whistle listing:

- the number of visible little-dog glyphs;
- every tame monster on the level: type, whether it is seen, distance,
  leashed, summoned, steed.

It draws no RNG and writes only to the run directory. All 30 games
reproduced `whistle_capture_suppressed`. All runs went through `hermes-heavy`.

**Measured, at the whistle that suppressed the program:**

| what the engine saw | games |
|---|---|
| a tame companion in view, but not a little dog (12 grown *dogs*, 1 iguana) | 13 |
| a tame companion on the level, out of sight | 9 |
| no tame monster on the level (pet dead or left on another level) | 8 |
| **several** visible little dogs | **0** |
| hallucinating or swallowed | 0 |

Across all 455 valid whistles in these 30 games, a visible little dog was
present at 171 and absent at 284.

**Counterfactuals** use the same records, looking only at whistles inside the
program's 100-move TTL. Until the capture decision, the suppressed path draws
no RNG and changes no game state, so the game up to each later whistle is the
same as it would have been under the alternative. These count **captures**,
not deliveries. After a capture the dog's move must still be witnessed, and
the #182 sweep already lost 9 games at that stage (`native_effect_not_delivered`).

| rule | games of 30 that would capture |
|---|---|
| wait for a later whistle in the TTL; little dog only | 3 |
| accept the little dog's growth line (little dog, dog, large dog), first whistle only | 12 |
| growth line, and wait for a later whistle in the TTL | 15 |
| any visible tame companion with dog data, first whistle only | 13 |
| any visible tame companion, and wait | 16 |

The remaining 14 or so are the "out of sight" and "no tame monster" games.
Nothing at whistle time recovers them. Only not charging for them would
help.

Caveats:

- This is the scripted `baseline-v1` player: it whistles with probability 0.03
  per step, and all 21 `bard-inherited` games end in death.
- It is one sweep with a new-moon night clock (see the seed-sweep README).
- The re-run was at `337a1929c`, not `1e3c7af`. It reproduced every
  suppression label, but other fields were not compared.

## Options

### A. Which companions qualify

- **A0 (today).** A visible `PM_LITTLE_DOG` only.
- **A1. The little dog's growth line.** `PM_LITTLE_DOG`, `PM_DOG`,
  `PM_LARGE_DOG`, with every other guard unchanged. Measured: 12 of 30
  captured at the first whistle. The in-game message already says "your
  visible companion", so no telegraph or message text needs to change. The
  presentation check (`chaos_presentation_snapshot`) would test "the glyph is
  one of these three types" instead of one type.
- **A2. Any visible tame companion with dog data.** Measured: 13 of 30, one
  more than A1 (an iguana). This widens the program beyond what
  `docs/next-use-whistle.md` and the pack describe ("companion attention" on
  a dog), and the native move it relies on (`dog_goal` with extra attention)
  was only validated on little dogs.

### B. Several qualifying companions in view

Measured: **0** of 30, under A0, A1 or A2. So there is no evidence for this
case either way.

- **B0 (today).** Suppress.
- **B1. Deterministic pick.** Choose the nearest to the player (squared
  distance), breaking ties by screen position: top row first, then leftmost.
  Everything in this rule is on screen, and it draws no RNG. It would not use
  `m_id` or the order of the monster list, which the player cannot see.
- **B2. Don't consume the slot; wait for a whistle with exactly one in view.**
  Same mechanism as C1 below.

### C. No qualifying companion in view

- **C0 (today).** Suppress on the first valid whistle. The slot is consumed and
  the charge stands.
- **C1. Wait.** A whistle with no qualifying companion leaves the W slot
  `PENDING`. The next whistle inside the TTL gets another capture attempt. If
  the TTL runs out, the program ends as `program_expired`, an existing end
  reason, with no refund. Measured: +3 of 30 on its own, and 15 instead of 12
  when combined with A1.
- **C2. Refund on suppression.** Give back the 1 point. This conflicts with
  the standing rule that expiry is not a refund (#164). It also lets the
  director re-admit indefinitely at no cost, because the refund depends on a
  hidden-to-the-director condition, so the charge no longer paces anything.
- **C3. Don't admit without a visible qualifying companion.** Add a check at
  the safe point, before charging. It would use only what is on screen. It is
  **unmeasured**: I did not record visibility at admission. Admission came 4
  to 91 moves before the suppressing whistle in these games, so visibility at
  the safe point is a weak predictor of visibility at the whistle. It also
  adds a new admission rejection reason, which touches the receipt and the
  generated protocol contract. That makes it the largest change.

## How each option meets the rules

| rule | A1 / A2 | B1 | C1 | C2 | C3 |
|---|---|---|---|---|---|
| deterministic, no new RNG | yes: the same `dog_goal` extra-attention path, more types | yes: distance plus screen order | yes | yes | yes |
| no hidden information | yes: on-screen glyph and `canseemon` | yes: no `m_id` or list order | yes | yes | yes, if it uses on-screen visibility only |
| telegraph first | unchanged: it fires at admission | unchanged | unchanged, but the effect may come later inside the TTL (already allowed) | unchanged | no telegraph when not admitted |
| no whisper equals stock | yes: runs only with a committed program | yes | yes | yes | yes |
| expiry is not a refund | kept | kept | kept | **broken** | kept (nothing is charged) |

## Save and replay

- **A1, A2, B1.** No save field. The runtime already stores `armed_m_id`, and
  the type check is re-evaluated from native monster state. The snapshot
  version does not change. Replay: the same seed and journal give the same
  capture. The journal records only the `m_id`, which is unchanged.
- **C1.** No save field: `slot_w = PENDING` is already saved and restored.
  The journal changes meaning without changing format. Today a
  `W_UNAVAILABLE` replay record ends the program. Under C1 a non-final
  whistle would write no record, and the program would end by the existing
  `program_expired` path. The replay tests that pin
  `CHAOS_REPLAY_W_UNAVAILABLE` on the first whistle (the replay case is in
  `src/chaos_next_use_runtime.c` about line 1741; the tests are
  `tests/chaos/next_use_admit.c`, `tests/chaos/sweep_funnel.py` and
  `tests/chaos/test_seed_sweep.py`)
  would need to be updated and listed in the PR, not quietly re-baselined.
- **C2.** No new field, but restore rules say restore "cannot refund spend"
  (`docs/next-use-snapshot.md`), so the budget contract changes.
- **C3.** A new admission rejection reason in `chaos_next_use_safe.c`'s reason
  list and in the generated protocol contract. Old journals stay valid.

## Recommendation

- **A1 + C1, and keep B0.**
  - A1 fixes the largest measured class: a starting pet that grew into a dog.
    It needs no new wording and has the same native move.
  - C1 stops one unlucky whistle from ending a program that still has most of
    its TTL left. It needs no budget change and no save change.
  - Together they captured 15 of the 30 measured games, against 0 today.
  - Keep B0, suppressing when several qualify. There were no such cases, and
    a rule for them can wait for evidence.
- **Record the reason for each suppression** in the existing
  `W_CAPTURE_SUPPRESSED` effect row: none in view, wrong type, several, or the
  re-check failed. The next sweep can then report these classes directly,
  without a scratch build. This follows the same pattern as #177's recorded
  rejection reasons.
- **Do not choose C2.** It breaks the no-refund rule and the pacing.
- Treat **C3** as a separate question, if at all, after measuring visibility at
  admission.

The roughly 17 games whose pet was out of sight or gone at every whistle stay
suppressed under this recommendation. I propose accepting that: those players
had no companion to be watched.

## What the fresh sweep for #164 should measure afterwards

Run the same `baseline-v1` sweep: seeds 1–100, the three starts, lifetime 300,
under `hermes-heavy`. It should report:

- admitted, captured and delivered games, and the loss labels, compared
  against the committed lifetime-300 report;
- suppressions split by the new recorded reason. This checks the 13 / 9 / 8 /
  0 split above on the full population, not just the re-run 30;
- for C1, how many programs capture on a later whistle, and how many end
  `program_expired` after waiting;
- delivered per 1000 turns and per dungeon level, which #164 needs.

The remaining sweep biases should be listed in that report: the scripted
whistle rate, early deaths in `bard-inherited`, and the new-moon night clock.

## Raw data

On the VPS, in `~/.hermes/reports/nyarlathack-companion/`:

- `r30-v1/`, `r30-v2/`: the per-game sweep reports and diagnostic JSON lines;
- `diag-eligibility*.patch`: the scratch diagnostic, not committed;
- `rerun30.sh`, `an2.py`, `an30.py`, `cf30.py`: the re-run and analysis
  scripts;
- `an2-output.txt`, `an30-output.txt`: the analysis output.

## Decisions for Sam

1. **Which companions qualify:** A0 (today), **A1 growth line (recommended)**,
   or A2 any tame companion.
2. **No qualifying companion in view:** C0 (today), **C1 wait within the TTL
   (recommended)**, C2 refund, or C3 don't admit (measure first).
3. **Several in view:** **B0 keep suppressing (recommended; no measured
   cases)**, B1 nearest with screen-order tie-break, or B2 wait.
4. Should the implementation also record the suppression reason in the effect
   row? (Recommended.)
