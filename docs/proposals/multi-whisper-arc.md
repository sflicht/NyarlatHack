# Proposal: the multi-whisper arc (M2, #164 pacing, #26)

Status: design proposal for Sam. Nothing here is implemented. Tier B, docs only.

Read with #26 (the arc), #164 (pacing, closed by PR #203), #199 (the order of
work: #198, #200, #201, #1, then this) and
[`felt-mutation-1.md`](felt-mutation-1.md), whose "Step M2" section this
proposal expands. Sam chose on 2026-09-30 to take M2 "later, with the arc".

## Terms

- **Default path:** `python3 -m chaos play --ordinary` with no other flags.
  Since #198 it turns on the echo hound and one next-use program; since #1
  (PR #223) it also runs the M1 schedule.
- **M1:** the default whisper schedule from #1. The arrival omen alone at Dlvl 1;
  from the second level-entry safe point, a seeded pick among
  `door_reluctance` (cost 1), `hunger_rate` (3) and `ward_efficacy` (3), each
  with its own engine-owned eligibility.
- **Next-use program:** a sandboxed program the engine admits at a safe point
  and runs on the player's *next use* of a whistle (family W) or fountain
  (family F). It costs 1. Today a game gets at most one.
- **M2:** making next-use repeatable, so a game can have more than one program.
- **Felt consequence:** an on-screen result the sweep can see in public events
  (#179's `first_felt`): a visible hound step; the whistle-attention notice or
  a fountain remap from a next-use program; "The door resists!" while a
  `door_reluctance` effect is active.
- **Pacing (#164):** at full Sanity, capacity is 2, plus 1 per new deepest
  level from DL3 (at most +4), plus 1 per *source* that delivered (at most +2),
  with a ceiling of 12. At most K = 3 is spent per new deepest level.

## 1. Where the default path stands

All numbers come from the committed paired sweep in
[`docs/measurements/door-reluctance-paired-1/`](../measurements/door-reluctance-paired-1/README.md):
seeds 1–100 per start, policy `baseline-v2`, `main` at `d29c4e2a2` against the
#1 branch at `313c0eec5`. The branch is what `main` plays now.

### What each start gets

| start | hound accepted | hound felt | next-use admitted / delivered | door accepted (games) | door felt (games) | first felt: median turn, Dlvl |
|---|---:|---:|---:|---:|---:|---|
| bard-default-path | 88 | 77 | 37 / 10 | 46 | 15 | 15; DL1 in 76 of 80 |
| wizard-default-path | 88 | 79 | 3 / 0 | 46 | 11 | 12; DL1 in all 79 |
| bard | 0 | 0 | 42 / 14 | 59 | 19 | 783; mostly DL2–3 |
| bard-inherited | 0 | 0 | 30 / 5 | 12 | 1 | 320 |
| madman | 0 | 0 | 8 / 0 | 2 | 0 | none felt |

`bard`, `bard-inherited` and `madman` run without the hound (the sweep's
launcher passes `--no-haunt`). Only the two `*-default-path` rows are the
exact default path. Madman took `hunger_rate` instead of door: 37 accepts,
none of them measurable as felt, because the sweep has no hunger kind yet.

### How many games feel 0, 1, 2 or 3+ consequences

Computed from the committed per-game rows, counting each *source* once: the
hound, the next-use program, and `door_reluctance`. The per-game rows give
`haunt_steps`, the next-use felt fields and `door_felt_turn`.

| start | main: 0 / 1 / 2 / 3+ | branch (now): 0 / 1 / 2 / 3+ |
|---|---|---|
| bard-default-path | 23 / 67 / 10 / 0 | 20 / 59 / 20 / 1 |
| wizard-default-path | 21 / 79 / 0 / 0 | 21 / 68 / 11 / 0 |
| bard | 83 / 17 / 0 / 0 | 69 / 26 / 5 / 0 |
| bard-inherited | 94 / 6 / 0 / 0 | 93 / 7 / 0 / 0 |
| madman | 100 / 0 / 0 / 0 | 100 / 0 / 0 / 0 |
| all 500 | 321 / 169 / 10 / 0 | 303 / 160 / 36 / 1 |

Counting *episodes* rather than sources (each separately felt door effect
counts once) moves only one game: bard-default-path becomes 20 / 59 / 19 / 2.
That count needs the kept event logs. They exist for the 149 games that
published a door whisper, and they agree with the committed `door_felt_turn`
in every one of them.

What the rows cannot show:

- Hunger is not counted. The sweep has no felt kind for it.
- For the hound and next-use there is only a per-game flag and the first felt
  turn, not a list of felt events. So "felt per level" and "time between felt
  events" can be computed only for door (from the kept logs), plus the first
  gap after the hound.
- 26 games show a next-use native effect without a public felt signal. They
  are counted as not felt.

### What recurrence looks like today

- **The hound is a DL1 event.** It is first felt at a median turn of 15 (Bard)
  and 12 (Wizard).
- **Door arrives later.** Door is first felt on DL2 in 20 games, DL3 in 24
  and DL4 in 2. The median gap from the door ACK to the first resisted door
  is 30 turns (range 2–189).
- **The gap between the first two felt events is long.** In the 23 games where
  the hound was felt first and door second, door came a median of 716 turns
  later (range 513–1699).
- **Door repeats, but is rarely felt twice.** Door was accepted twice in 30
  games and three times in 3, yet only one game felt two separate door
  effects. The scripted player meets few closed doors.
- **Next-use always ends early, with a lot of game left.** Every admitted
  default-path program terminated. For bard-default-path: 23 completed, 10
  program-expired, 3 origin-expired, 1 level departure. The median game then
  went on for 987 more turns, and 36 of 37 had at least 300 turns left. 85 of
  100 bard-default-path games recorded two or more qualifying whistle or
  fountain actions. A second program has room, and the material to bind to.

## 2. M2: repeatable next-use (the engine limit)

### What has to change

These are survey findings from the current tree (`main` at `5041717f1`).
Line numbers drift, so re-grep before relying on them.

1. **The admission latch.** `src/chaos_next_use_safe.c` has a process-wide
   `static int settled`. `chaos_next_use_safe_try` returns `NOT_OPEN` once it
   is set, and sets it as soon as an envelope is due (even when admission is
   rejected). It is saved as `u.chaos_next_use_attempted` (`include/you.h`),
   written in `src/save.c` and restored through
   `chaos_next_use_safe_restore_attempted`, which accepts only 0 or 1.
   M2 replaces "settled once" with an engine-owned rule for when the *next*
   opportunity opens. The saved value has to carry the number of programs
   settled and the last program id.
2. **One runtime slot.** `src/chaos_next_use_runtime.c` keeps one
   `live_runtime`. `chaos_next_use_runtime_install` refuses while its
   `program_id != 0`. A strictly sequential M2 can keep one slot, provided the
   previous program is terminal and its journal is complete before reset.
   Concurrent programs would need an array of runtimes, an array in the
   snapshot, and interleaved callbacks.
3. **One envelope per program id.** Engine (`src/chaos_next_use_io.c`) and
   director (`chaos/next_use_envelope.py`) both use one fixed file,
   `next_use-envelope.json`. The scheduler (`chaos/next_use_schedule.py`)
   makes one decision per launcher lifetime and stops for good at
   `already_published`. M2 needs per-id names (for example
   `next_use-envelope.<id>.json`), with the engine reading only the id it
   expects next (last id + 1). Then a stale or early envelope can never be
   retimed onto a later program. The scheduler's terminal state becomes per
   program, not per game.
4. **A multi-program journal.** `src/chaos_next_use_journal.c` opens
   `next_use-journal.jsonl` once per game with `O_EXCL`. Its header binds one
   snapshot (program id, source digest). The simplest safe change is one
   journal file per program id. Each stays a complete, independently checked
   chain, and `chaos/next_use_journal.py` reads a list of them. The bounds
   (8 MiB and 4096 records per journal) stay per file.
5. **Replay and restore.** Restore must handle three cases:
   - between programs (program k terminal, k+1 not admitted);
   - mid-program k > 1;
   - at the per-game cap.

   `chaos_start` → `chaos_next_use_safe_resume` → `chaos_next_use_journal_resume`
   has to validate the completed journals of earlier programs as well as the
   open prefix of the current one. The "restore never reopens a settled
   opportunity" rule in
   [`docs/next-use-snapshot.md`](../next-use-snapshot.md) becomes "restore
   never reopens a settled program, and never grants an extra one".
6. **Anti-farming.** Origins (`origin_evidence[2]` in the safe layer, retained
   in `src/chaos_engine.c`) are process-local. Each family holds only its
   newest qualifying notice. A second program must not reuse the origin that
   funded the first. Proposed rule: a new program may bind only an origin
   completed *after* the previous program terminated. Witnessed credit is
   already once per source, so a second program earns no new capacity.
7. **The schedule file.** `next_use-schedule.jsonl` is read with a 32-record
   and 16 KiB bound. Today's bards record a median of about 25 qualifying
   actions per game. PR 1 below must check whether multi-program games can
   exceed the bound, and either raise it or keep only rows since the last
   termination.

### Save-version impact

- **Proposed:** keep the `int chaos_next_use_attempted` field in `struct you`
  so the native layout does not move, and redefine it as "programs settled"
  (0..cap).
- **Proposed:** add `last_program_id` and the cap to the next-use snapshot,
  bumping `CHAOS_NEXT_USE_SNAPSHOT_V` 6 → 7. If PR 1 shows the field must
  live in `u.chaos` instead, it is a native state bump 4 → 5.
- **Either way:** old saves are refused by the structural check and kept, as
  for #164 and #1, never migrated. No state goes into bones.
- **Run records:** `ordinary-choice.json` goes to record v3, carrying the M2
  setting, so restore follows the recorded choice and not today's defaults.

### Options

All three keep cost 1, engine-owned admission, the telegraph, the existing
lifetimes (origin 300 moves, program 100 moves) and the per-level and
lifetime budget. None needs a model call.

- **Option A: strictly sequential, capped (recommended).**
  - A program may open only when the previous one is terminal, the per-game
    cap N is not reached (proposed N = 3), and a fresh origin exists.
  - One runtime slot. The snapshot changes only by the two fields above.
  - Smallest engine change, and the easiest replay story.
- **Option B: one per new deepest level.** Option A, plus at most one program
  per new deepest level.
  - It lines up with pacing's per-level allowance, and level departure already
    terminates a program.
  - It spreads recurrence across levels instead of bunching it. But only 36 of
    100 default games reach DL3, so most games would still get one program.
- **Option C: bounded concurrent (W and F at once).**
  - Two live runtimes, an array snapshot, and journals interleaved by
    sequence.
  - The largest change, with the most new replay states. It is not needed for
    recurrence. Not recommended now.

### Smallest safe PR sequence (Option A)

Each PR is cut from `main`, one behaviour per PR, with gates (CHAOS=0 and
CHAOS=1 warning-clean, fast and native suites, CI) before it opens.

1. **Contract and survey (Tier B, docs and tests only).**
   - Write the next-use policy v3 in `docs/chaos-protocol.md` and
     `docs/next-use-snapshot.md`.
   - Add the cap to `chaos/protocol_contract.json`, regenerated.
   - Measure the schedule-file bound against the sweep's qualifying-action
     counts.
   - Tests: the generator and contract tests.
2. **Engine opportunity rule and save (Tier A).**
   - Replace `settled` with a count plus last id, and read the envelope by
     expected id.
   - Snapshot v7, with old saves rejected.
   - Linked-fixture tests:
     - program 2 is admitted only after program 1 is terminal;
     - the same origin cannot fund two programs;
     - at the cap the result is `NOT_OPEN`;
     - a rejected attempt also counts toward the cap;
     - no new game RNG draws.
   - Real save/restore tests between programs and at the cap.
   - No-whisper equality is unchanged.
3. **Per-program journals and replay (Tier A).**
   - One journal per id, with the Python reader over a list.
   - Tests:
     - two programs replay exactly;
     - a truncated program-2 journal fails closed;
     - restore mid-program 2 validates program 1's complete journal;
     - historical single-journal runs still read.
4. **Director scheduler and record (Tier B).**
   - `NextUseScheduler` decides per program, with record v3, and the sweep
     funnel reports per program.
   - Tests: scheduler unit tests (fresh origin, terminal per program, no
     retiming), record v3 restore, and sweep funnel fixtures.
5. **Evidence (Tier A).**
   - A nonwizard capture with two programs felt.
   - A paired sweep against `main` (Section 5).

## 3. The arc (#26): recurrence, then a reckoning

#26 asks for "a recurring mechanical relationship", then a reckoning that is
"recognition, not merely scale". It also says escalation follows witnessed
episodes, concurrent hauntings stay few, and thematic escalation is not a
budget increase. Every option below uses only reviewed mechanics: the hound,
W and F next-use, and the three M1 mutations. None adds cruelty or model calls.

### What pacing allows (K = 3, ceiling 12)

- **Capacity tops out at 8 at full Sanity.** That is 2 base, +4 descent and
  +2 witnessed. The ceiling of 12 never binds on the default path unless
  Sanity falls.
- **After the hound (2), at most 6 points remain for the rest of the run.**
  They arrive at about +1 per new deepest level from DL3, plus the two
  witnessed credits.
- **Reach is short.** Only 36 of 100 default games reach DL3, and 11–13
  reach DL4.
- **K = 3 almost never binds after DL1.** Capacity is the limit.

So a typical arc has two to four cost-1 beats after the hound. A reckoning has
to be cheap (cost 0 or 1), or it only happens in games that lose Sanity.

### Who owns what

| Part | Engine-owned | Director-chosen |
|---|---|---|
| Admission, price, eligibility, duration bounds, expiry | yes | no |
| Telegraph text | yes, fixed per mutation or program family (plus a recurrence index, if adopted) | no free text |
| Which eligible mutation or family at a safe point | no | seeded pick (M1), or a public-history-weighted pick |
| Recurrence count (programs settled, motif count) | yes, saved | read only, from public events |
| Whether a reckoning is offered | gate is engine-owned (count, level, budget) | whether to publish it |

### Options

- **Arc 1: recurrence made legible (smallest; recommended first).**
  - M2 Option A gives up to three programs.
  - The scheduler prefers the family that was last delivered (seeded, from
    public history).
  - The engine's telegraph for a repeat program carries a fixed recurrence
    line indexed by the saved count, for example "Again, the whistle carries
    farther than it should." This is truthful, because it is engine text about
    an engine fact.
  - The post-mortem reveal (#163) groups episodes by motif.
  - No new mutation and no reckoning yet.
- **Arc 2: one motif across channels (medium).** Arc 1, plus:
  - the M1 pick is weighted by the motif's public history (door for a
    door-heavy player, using the existing `history_choice` backend);
  - the hound may return once on a new deepest level after it was delivered
    (cost 2, so in practice only with descent credit);
  - a cost-0 "reckoning" safe point once a motif has been delivered three
    times: a final telegraphed recurrence of the same motif, and a declared
    refusal through #166's Elder Sign.

  This depends on #166, and on a decision that the reckoning may be free.
- **Arc 3: a saved motif ledger and a branch reckoning (large; later).**
  - An engine-owned ledger (motif id, delivered count, last level) feeds a
    bounded capstone at a branch, Lethe "anchor or relinquish" style from
    #26's comment.
  - It needs #19, #21 and #22's history conditioning, plus its own episode
    retirement contract.
  - Listed for direction only. Not proposed for the next tranche.

## 4. Budget interplay

M2 programs (cost 1) and M1 mutations (door 1, hunger 3, ward 3) draw on the
same capacity, and they already contend in the sweep:

- **Door lost to next-use: 6 games.** On bard-default-path, all 6 `budget`
  rejections of `door_reluctance` came at DL2, in games where the hound (2) and
  a next-use program (1) had already spent 3 against a capacity of 3.
- **Next-use lost to the hound: 7 games** (bard-default-path seeds 16, 60, 67,
  76, 100; wizard-default-path seeds 17, 67, identical on `main`). In each, the
  hound was accepted but took no visible step, so there was no witnessed
  credit and the hound's 2 used the whole capacity.
- **Next-use lost to hunger: 1 game** (madman seed 39). `hunger_rate` (3) took
  the level's whole allowance at the same safe point. See the appendix.
- **Hunger lost to next-use: 1 game** (madman seed 10). The `hunger_rate`
  rejection came after an earlier next-use admission.

With M2, contention grows. Each extra program takes a point that door would
otherwise use, and only about one point arrives per new level. Expect M2 to
trade door admissions for programs one for one, unless arbitration says
otherwise. Within one safe point the engine handles the mailbox whisper before
the next-use envelope (madman seed 39 shows this order).

Ways to arbitrate (Decision 4):

- leave first-come as now;
- let the director skip an M1 pick at a safe point where a program envelope is
  due (director-side, no engine change);
- or alternate by level.

The door rule earns no witnessed credit today (credit sources are the hound,
curios and next-use). Counting a felt door as a source would add at most +1
within the existing cap of 2 (Decision 5).

## 5. Measurement plan

A paired sweep against `main` (same policy, seeds 1–100, all five starts), plus
these new per-game report fields. Each comes from public events only.

- **`felt_events`:** a list of `{turn, dlvl, kind, program}` for every felt
  event, not just the first. Kinds: hound, next_use_W, next_use_F, door, and a
  new `hunger` (the first Hungry status under an active hunger effect).
- **Felt consequences per game:** the 0 / 1 / 2 / 3+ table from Section 1,
  by source and by episode.
- **Felt per level:** a felt-event count per Dlvl.
- **Time between felt events:** median and quartiles of the gaps between
  consecutive felt events. Today's baseline is 716 turns from the hound to the
  first door.
- **Per-program funnel:** published, admitted, delivered and felt for program
  index 1, 2 and 3, with the termination reason.
- **Recurrence:** felt episodes sharing a motif (same family or mutation).
- **Budget contention:** each `budget` rejection, by kind and by what spent
  the capacity, with counts where the capacity or K bound.
- **Guards:**
  - hound acceptance and steps unchanged (88 / 88 on both default paths);
  - no new harness errors beyond the allowlisted pair;
  - save/restore counts match.

Proposed acceptance for M2 (Decision 8): on bard-default-path, games with two
or more felt consequences rise from 21 to at least 35 of 100, and the hound
guard holds.

### Adopted gate for arc work

Adopted by Sam after #231 (2026-10-02). It supersedes the raw-count acceptance
above for arc work, because that count was mostly hound steps. Metric and
baseline: [`docs/measurements/arc-metric-distinct-felt/`](../measurements/arc-metric-distinct-felt/).

> On bard-default-path seeds 1-100 (baseline-v2), games with 2+ distinct felt
> whispers excluding the hound rise from 2/100 to at least 10/100, hound
> admission is unchanged from `main`, and at least 3/100 games feel two
> next-use programs.

Why later programs are not felt today, and the options to meet the gate:
[`docs/measurements/arc-unfelt-diagnosis/`](../measurements/arc-unfelt-diagnosis/).

Option B (recurrence repair) was measured against this gate: 2/100 and 0/100,
hound admission unchanged. It misses both counts because the companion check
moved to the whistle and still suppresses most later programs there:
[`docs/measurements/arc-recurrence-repair/`](../measurements/arc-recurrence-repair/).

## 6. Decisions for Sam

1. **M2 shape.** A, strictly sequential and capped; B, one per new deepest
   level; or C, concurrent W and F. *Recommend A* (B can be added later as one
   extra gate).
2. **Programs per game.** 2, 3, or no cap other than budget. *Recommend 3.*
   36 of 37 admitted default-path programs had at least 300 turns left, but
   budget allows only about one extra point per level.
3. **Fresh-origin rule.** A new program binds only an origin completed after
   the previous program terminated, or any live origin. *Recommend the fresh
   origin.* It stops one whistle from funding two programs.
4. **Arbitration between next-use and M1 at the same safe point.**
   First-come as today; the director skips its M1 pick when a program envelope
   is due; or alternating by level. *Recommend first-come* for the M2 PRs, then
   revisit with the per-kind contention numbers from the paired sweep.
5. **Witnessed credit for a felt M1 mutation.** No, as today; or yes, with
   door as a source within the existing +2 cap. *Recommend no for now.* It
   changes pacing, which should be decided on the M2 sweep, not before.
6. **Arc ambition for the next tranche.** Arc 1, Arc 2 or Arc 3.
   *Recommend Arc 1* with M2. Take Arc 2 after #166 (refusal) lands, and keep
   Arc 3 as direction only.
7. **Save policy for M2.** Refuse and keep old saves (snapshot v7, or state v5
   if the field must move), or write a migration. *Recommend refusal*, as for
   #164 and #1.
8. **M2 acceptance target.** Two or more felt consequences in at least 35 of
   100 bard-default-path games (21 today), with the hound guard. Or a different
   threshold, or no numeric target. *Recommend 35 of 100.*

## Appendix A: madman next-use admission, 10 → 8

The two games are madman seeds 39 and 74. Their run directories are gone. The
branch work directory was cleaned after the sweep, and the kept copies cover
only games that published a door whisper; for madman those are seeds 45 and
47. This appendix therefore uses the committed per-game rows and ACK facts
(`branch-seeds-1-100.json`, `main-seeds-1-100.json`,
`branch-door-facts.json`).

- **Seed 39: budget contention with hunger.**
  - Both sides reach DL3 at turn 686, with start budget 3.
  - On the branch, M1 published `hunger_rate`, accepted at turn 685 (cost 3,
    expiring at 709). The next-use decision at the same safe point (safe 3,
    move 685) was then rejected for `budget`.
  - On `main`, the same program was admitted at move 685.
  - So hunger, not door, took the budget.
- **Seed 74: not budget.**
  - On the branch, the game never recorded a qualifying whistle or fountain
    action (0 against 1 on `main`). No program was published (loss
    `no_qualifying_action`), and no budget refusal is recorded.
  - `hunger_rate` was accepted at turn 684, before `main`'s admission at move
    821. The branch game ended at turn 994 against 886 on `main`. That fits the
    game diverging after the hunger effect, but the rows cannot show the exact
    turn of divergence.
- **Door played no part** in either game.

## Appendix B: sources

- Per-start counts, the 0/1/2/3+ tables and the contention list were computed
  from the committed reports in `docs/measurements/door-reluctance-paired-1/`.
- Door episode counts and the door felt Dlvls came from the 149 kept door
  games' `events.jsonl`. Those logs stay in the session's report directory, not
  in the repository.
- The engine findings in Section 2 are from reading `main` at `5041717f1`. They
  are a survey, not a design review; PR 1 re-checks them.
