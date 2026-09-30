# Proposal: one mutation a default game can feel (#1)

Status: design proposal for Sam. Nothing here is implemented. Tier B, docs only.

Read with #1 (the goal and its constraints), #26 (the arc), #164 (pacing) and
#199 (the order of work: #198, #200, #201, then #1, then the multi-whisper arc).

## Terms

- **Default path:** `python3 -m chaos play --ordinary` with no other flags. Since
  #198 it turns on the echo hound and one next-use program.
- **Registered mutation:** an engine-owned rule change in the protocol registry
  (`chaos/protocol_contract.json`), such as `hunger_rate`. The director only
  names it; the engine prices, telegraphs, admits, applies and expires it.
- **Ordinary whisper channel:** the mailbox request path for registered
  mutations (`whispers.jsonl`). It is separate from next-use programs.
- **Safe point:** a moment where the engine may admit a whisper. In ordinary
  play today these are the session start and each `level_enter`.
- **Pacing:** #164's budget (on by default). A full-Sanity character has 2 base
  points, +1 per new deepest level from DL3 (at most +4), +1 per delivering
  source (at most +2), at most 3 spent per new deepest level, ceiling 12.
- **first_felt:** the sweep's turn and kind of the first on-screen consequence
  (#179). Today it knows three kinds: a visible hound step, the whistle
  attention notice, a fountain remap.

## Where the default path stands

From the committed v2 sweep (`docs/measurements/seed-sweep-v2-179/`,
bard-default-path, seeds 1–100):

- Something is felt in 76/100 games, always the hound, median turn 15, at DL1.
- The next-use program is admitted in 37 and delivered in 10.
- The ordinary whisper channel admits exactly one whisper in all 100 games: the
  cosmetic arrival omen (`ambient`, cost 0) at safe point 1.
- Games reach DL2 in 71, DL3 in 35 (median turn 708) and DL4 in 11.

Nothing after the first level is a registered mutation. Two things cause
that, and both matter more than the choice of mutation:

1. **The default path never asks for one.** `chaos play` defaults to
   `--backend pack --pack ambient`, which is a `ScheduleBackend` holding one
   request (id 1, safe point 1). After it is accepted the director has
   nothing more to send. The seeded `RandomBackend`, which picks from the
   eligible registry at every safe point, exists but is opt-in.
2. **No registered mechanical mutation is eligible at full Sanity.**
   `ward_efficacy` needs Sanity ≤ 80 and `hunger_rate` needs Sanity ≤ 90. The
   sweep's Bard stays at Sanity 100 in every game, as a healthy early
   character does. Both also cost 3, which is a whole level's allowance.

## Budget arithmetic on the default path

The hound is admitted in 86/100 games and costs 2 at DL1. Then:

| Where | Capacity (full Sanity) | Spent | Available | Fits |
|---|---|---|---|---|
| DL1 after the hound | 2 (+1 once a hound step is seen) | 2 | 0–1 | cost 1 at most |
| DL2 (new deepest) | 2 + witnessed (≤ 2) | 2 | 0–2 | cost 1; cost 2 only with two credits |
| DL3 | + descent 1 | | about 1–3 | cost 1 or 2 |
| each deeper new level | + descent 1 (to DL6) | | about +1 per level | cost 1 per level |

The next-use program also costs 1 and competes for the same points. So **only
a cost-1 mutation can recur level after level** at full Sanity. A cost-2
mutation appears from about DL3, in roughly a third of games. A cost-3
mutation fits at most once, and seldom.

## Options

All options keep #1's contract: an engine-owned price, telegraph, duration cap
and eligibility, applied through an existing engine path; no model text, no
hidden-state disclosure, no immediate damage, no raw stat writes, no stacking
or refresh, and lifetime cruelty still engine-owned.

Common to all options: a new kind grows `enum chaos_kind` and
`struct chaos_state.effects[]`, so the saved state changes size. Under the
existing migration policy that is a **native state version bump (3 → 4)**:
old saves are rejected by the structural check and preserved, not migrated.
No state goes into bones, as today. With CHAOS=0 the hook compiles to the
stock expression. With an empty mailbox nothing is admitted, the rule query
returns the base value, and play is stock; the existing no-whisper equality
tests cover this. Replay reads admitted effects from the saved state, as for
the ward and hunger effects.

### Option A: `door_reluctance`: closed doors resist more often (recommended)

- **Engine path:** `doopen_indir` in `src/lock.c` opens a closed door when
  `rnl(20) < (STR + DEX + CON) / 3`. One `chaos_rule` hook halves the
  right-hand side while the effect is active. The `rnl(20)` call is made
  either way, so there is **no new random draw**, only a different threshold.
  Nothing is poked: the door's own state changes only through the native
  "The door opens." and "The door resists!" branches. Locked doors, kicking,
  unlocking tools and monsters are unaffected.
- **Telegraph:** "The doors of this place seem to lean against you."
- **Cost:** 1. Duration: 1..300 turns (the current 50-turn cap is too short to
  meet many doors; a larger cap is part of the decision).
- **Eligibility:** conscious and living; no active door effect; no Sanity
  gate, so a healthy character qualifies. `verysmall` forms already cannot
  open doors natively and are unaffected.
- **Why it is noticeable:** every early level has closed doors, and autoopen
  makes each one a move the player takes. At Luck 0, `rnl(20)` is uniform on
  0..19, so a character with STR + DEX + CON = 33 opens a door on 11 tries
  in 20; halved, on 5 in 20, about four tries per door. "The door resists!" repeating, right after the telegraph, needs no
  wards and no `#setsanity`.
- **Measurement:** the door result is not an observation today. It needs one
  public observation (operation `door_open`, stage `completed`, fact `opened`
  or `resisted`), following #21's pattern, and a first_felt kind `door`
  counted on the first `resisted` while the effect is active. Rough size: an
  admission at DL2 in about 50/100 default games (the 71 that reach DL2, times
  the share with a point left after the hound). Felt in perhaps half of those,
  because the scripted player meets fewer closed doors than a human. Recurring
  at DL3 in about 25/100.

### Option B: `burden`: carrying capacity shrinks

- **Engine path:** `weight_cap()` in `src/hack.c`. One `chaos_rule` hook
  scales the final capacity by 3/4. Encumbrance is recomputed by the native
  code, which prints "You are burdened" and shows it on the status line. No
  stat is written; Strength and Constitution are unchanged.
- **Telegraph:** "Your pack drags at you like a second shadow."
- **Cost:** 1. Duration: 1..300 turns.
- **Eligibility:** not riding (a steed's capacity is used then); no active
  burden effect; no Sanity gate.
- **Why it is noticeable:** only if the player is already near capacity. A
  low-Strength Wizard often is; a lightly loaded Bard often is not. It is
  certain to show on the status line when it bites, but it does not always
  bite.
- **Risk:** Stressed and worse limit fighting and fleeing. That is indirect
  but real harm, so the scale should stay mild.
- **Measurement:** the status line is public, and the sweep already parses it.
  first_felt kind `burden` on a status change to Burdened or worse while the
  effect is active. Rough size: felt in 10–20/100, mostly by Wizards; the
  Bard sweep will undercount it.

### Option C: reprice and ungate `hunger_rate` (no new mutation)

- **Engine path:** unchanged (`gethungry` in `src/eat.c`, doubled ordinary
  food consumption).
- **Telegraph:** unchanged ("An unnatural hunger coils in your stomach.").
- **Cost:** 3 → 1. Sanity gate ≤ 90 → none. Duration cap 50 → about 500:
  at 50 turns the doubling costs 50 nutrition, which nobody notices.
- **Eligibility:** unchanged apart from Sanity: ordinary food metabolism only
  (Inediate, clockwork and Incantifier forms stay excluded).
- **Why it is noticeable:** "Hungry" arrives several hundred turns early. It is
  slow and easy to attribute to ordinary play.
- **Save:** no new kind, so no state version bump. This is the smallest
  change, but it does not meet #1's "one new named mutation" acceptance line.
- **Measurement:** first_felt kind `hunger` on the first Hungry status seen
  while the effect is active. Rough size: 30–40/100, late in the level.

## Smallest step to more than one whisper per default game

Two separate limits exist.

1. **Ordinary whisper channel (a launcher default, not the engine).** The
   engine already admits many requests per game, one per safe point, at most
   two active effects and one of each kind, within the budget. What stops
   it on the default path is the single-request `ScheduleBackend`.
   - **Step M1 (recommended):** on `--ordinary`, use the existing seeded
     `RandomBackend` instead of the ambient pack, restricted to the arrival
     omen plus the new mutation. Record the choice in `ordinary-choice.json`
     (record v2), so restore follows the recorded choice and never today's
     defaults, exactly as #198 does for the hound. No engine change, no model
     call, no new save field. Safe points come only at level entry, so this
     yields at most one whisper per new level, which is the recurrence #1 asks
     for.
2. **Next-use programs (an engine limit).** `src/chaos_next_use_safe.c` keeps
   a process-wide `settled` flag, saved as `attempted`. After the first
   envelope is evaluated, no other is considered for the life of the game.
   The launcher's `NextUseScheduler` stops at `already_published`, and the
   envelope has one fixed file name (`next_use-envelope.json`).
   - **Step M2:** let a new program open after the previous one has
     terminated. That needs a saved last-program id in place of the
     `attempted` flag, one envelope file per program id, a journal that holds
     several programs, and replay and restore tests for each. It is a save
     version change and a multi-PR series. It belongs with #164 and #26's
     multi-whisper arc, not with #1.

M1 plus option A is the smallest change that gives a default game a
registered mutation it can feel, and lets it recur on later levels.

## Decisions for Sam

1. Which mutation: A (door reluctance, recommended), B (burden) or C
   (reprice hunger; does not meet #1's acceptance as written).
2. Whether the default path switches to the seeded `RandomBackend` (M1), and
   whether its menu should also include `hunger_rate` and `ward_efficacy`.
3. The duration cap for the new mutation (the registry caps effects at 50
   turns; this proposal suggests 300).
4. Whether next-use should become repeatable (M2) now, or stay with the
   multi-whisper arc after #1.

## Not decided here

The expected sizes above are estimates from the v2 sweep's level reach and
budget, not measurements. The first real numbers come from the #1
implementation PR's paired sweep.
