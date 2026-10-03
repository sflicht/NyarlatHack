# Proposal: a whistle effect the player feels without the companion classifier

Status: design proposal for Sam. **Nothing here is implemented.** Tier B, docs
only; player-visible delta: none.

Read with #236 (the funnel diagnosis that found the bottleneck), #235 (C,
broad next-use) and #231 (the `distinct_felt` metric). The measurements behind
every count below are in
[`docs/measurements/felt-whistle-estimate/`](../measurements/felt-whistle-estimate/README.md).

## Terms

- **W program:** a next-use program whose operation is the whistle family.
  It is triggered by a valid whistle: a tin whistle, or a magic whistle while
  a broad program runs (`src/chaos_engine.c:657-661`).
- **Callback:** the program's Lua decision at a valid whistle. It returns an
  *intent*: `quiet`, `delay`, `whistle_attention` or `fountain_refresh`
  (`src/chaos_next_use.c:712-726`).
- **Classifier:** the test at `src/dogmove.c:1258-1260` that credits a
  companion's move to `whistle_attention`. It requires:
  - no ordinary whistle pull active;
  - the companion's goal is the player rather than an item;
  - the companion was publicly visible before the move.
- **Felt:** a public consequence the sweep records as a `felt_events` row.
- **Gate:** part 1 = games with 2+ distinct felt whispers excluding the hound
  (target 10); part 3 = games feeling two next-use programs (target 3). On
  bard-default-path today: **6 and 1**.

## The problem

#236 measured the bottleneck: the W effect counts only when the companion's
next moves pass the classifier. On bard-default-path, 58 uses reached a
callback and **21 delivered**. Most failures were the ordinary whistle pull or
the dog heading for an item. Each guard is right: it keeps the credit to moves
only the program explains. So the fix is not to loosen the classifier. It is
an effect the player can feel and attribute **with no companion in the loop**.

## Candidates

All three keep today's trigger, price (cost = operation count, 1;
`src/chaos_next_use.c:665`), telegraph-at-admission rule and lifetimes. All
use the existing whistle hook. Each would be a new callback intent beside
`whistle_attention`.

### A. "Call": the visible companion is drawn to the player's side

- **What the player sees:** "Your whistle carries farther than it should;
  your dog comes running." The companion's glyph jumps to a square next to
  the player.
- **Mechanism:**
  - `mnexto()` (`src/mon.c:7035`), the same call the magic whistle makes
    (`src/apply.c:776`).
  - It places the companion with `enexto()`, whose one random choice is
    `rn2()` (`src/teleport.c:384`).
  - The target is `chaos_next_use_companion_pick()` (`src/chaos_engine.c:611`):
    on screen only, nearest, no RNG.
  - Bounds: one companion, one move, only if it is not already adjacent.
- **Cost and budget:** 1, as today. It changes no admission, so the 38
  budget refusals of later programs stay refused.
- **Interactions:**
  - hound: none;
  - door reluctance: none;
  - hunger: none;
  - companion: pulls it out of whatever it was doing, such as a fight or
    eating.
- **Failure modes and fairness:** it is a *boon* (it is the magic whistle's
  effect), so it barely reads as the Chaos. It still needs a visible
  companion, the very condition being escaped.
- **Measured:** the companion is usually already beside the player when the
  player whistles. On bard-default-path A's precondition held on **8 of 109**
  valid whistles inside admitted programs' windows, in 8 programs.
- **Telegraphs:** the existing W lines stay honest ("the whistle carries
  farther", "may call unusual attention"): the whistle does carry and call.

### B. "Ring": the whistle's note goes on ringing in the player's head (recommended)

- **What the player sees:**
  1. "Your whistle's note goes on ringing inside your head."
  2. The status line gains **Conf** (`src/botl.c:87`).
  3. For a few moves, movement occasionally goes astray, the native confusion
     rule (`src/hack.c:1140`).
  4. It ends with the native "You feel less confused now."
     (`src/timeout.c:931-933`).
- **Mechanism:**
  - `make_confused(HConfusion + N, FALSE)` (`src/potion.c:67`), the function
    potions, traps and spells already use. No struct is touched.
  - N is an engine constant, **5 moves**, bounded 3..5 if Sam wants it to be
    a parameter.
  - Applying it draws **no random number**. Later confused steps use the
    native `rn2(5)` (`src/hack.c:1140`), which replays from seed plus
    whispers.
- **Guards** are all public, all evaluated at the whistle, and none chooses
  the outcome from hidden state. Any failing guard makes the use quiet
  (nothing applied, nothing charged beyond admission):
  - not already confused, stunned or hallucinating (status line);
  - not engulfed;
  - HP above a third of max HP (status line);
  - no visible hostile monster adjacent (`canspotmon`, `distmin` ≤ 1);
  - no visible peaceful monster adjacent: confusion skips the "Really
    attack?" prompt (`src/xhityhelpers.c:246`);
  - no remembered water or lava glyph adjacent (`glyph_at`,
    `src/display.c:1937`): the player's **map memory**, not `is_pool()`
    on terrain the player may not have seen.
- **Cost and budget:** 1, as today; admission is unchanged.
  - The budget stays binding for later programs: the hound's 2 points use up
    the base in 37 of 38 refusals (#236).
  - One indirect gain: each delivery credits pacing's witnessed source
    (`chaos_pacing_delivered`, `src/chaos_next_use_runtime.c:1432-1433`).
    More deliveries bring that +1 (cap 2) earlier, which makes later
    admissions easier. The estimate below does not count it.
- **Interactions:**
  - **hound:** the adjacent-hostile guard refuses while the hound is next to
    the player.
  - **door reluctance:** confusion disables autoopen (`src/hack.c:696`) for
    those few moves. Fewer door attempts means slightly fewer chances for
    "The door resists!".
  - **hunger:** none.
  - **companion:** none. It is not involved; today's `whistle_attention`
    stays available as a separate intent.
- **Failure modes and fairness:**
  - Confusion changes what a scroll does. A player who reads one in those 5
    moves gets the confused effect, a well-known NetHack rule, flagged by
    **Conf** on the status line.
  - A ranged attacker the guards don't cover could make a stray step costly.
  - The message, the status flag and the telegraph make the cause plain; the
    short duration bounds the cost.
- **Measured:** on bard-default-path B's precondition held on **102 of 109**
  valid whistles, in **41 of 64** probed admitted programs. That compares
  with 21 delivered of 58 today. The water/lava and peaceful guards are not
  in the probe, so these counts are upper bounds on them.
- **Telegraphs:** the existing W lines are **not** honest for B. "Carries
  farther" and "call unusual attention" promise the opposite of a note that
  stays in the player's head. B needs new text (below).

### C. "Carry": the whistle wakes sleepers four times as far away

- **What the player sees:** "Your whistle carries farther than it should."
  Sleeping monsters the player can see stir.
- **Mechanism:** `wake_nearto(u.ux, u.uy, 4 * u.ulevel * 20)`
  (`src/mon.c:7470`). The ordinary whistle's radius is `u.ulevel * 20`
  (`src/mon.c:7446`). No RNG.
- **Cost and budget:** 1, as today.
- **Interactions:**
  - hound: none (it is awake);
  - door reluctance: none;
  - hunger: none;
  - companion: none.
- **Failure modes and fairness:** real cruelty (more awake enemies) that is
  usually invisible. When it isn't felt, the player cannot attribute it.
- **Measured:** **0** of 4,289 probed whistles had a visible sleeping monster
  in the extended band; 17 had only unseen ones. It is never felt, so it is
  rejected.
- **Telegraphs:** the existing lines would stay honest.

### Comparison

| | A call | B ring | C carry |
|---|---|---|---|
| needs a companion | yes (visible) | no | no |
| bard-default-path: whistles meeting the precondition / programs | 8 / 8 | 102 / 41 | 0 / 0 |
| existing telegraphs honest | yes | no, new text | yes |
| new RNG draw at apply | `rn2` in `enexto` | none | none |
| reads as the Chaos | weakly (a boon) | yes | yes, but unseen |

## How "felt" is defined (B)

- **Public notice.** B's message is printed under a new observation
  operation, `whistle_ring` (contract observation id 5), fact `ringing`
  (id 13). It uses the projection `completed_notice_by_operation`, as
  `whistle_attention` does, with `allow_blocked: false`. The notice is
  published only if it reached the screen.
- **Effect row.** The journal effect row is a new
  `CHAOS_EFFECT_W_RING_DELIVERED` carrying the whistle's public root, so the
  sweep attributes it by `(family W, root)` exactly as today
  (`tests/chaos/sweep_programs.py:93-131`).
- **The felt row.** It has the existing shape and kind:
  `{"turn": T, "dlvl": D, "kind": "next_use_W", "program": k}`.
  - It comes from one new branch in `program_metrics`:
    `op == "whistle_ring" and fact == "ringing"` →
    `add(turn, "next_use_W", effects_by_root.get((1, root)))`.
  - `distinct_felt` keys it as `("next_use", k)`, at most once per program,
    W or F (`tests/chaos/sweep_programs.py:189-190`).
  - `DISTINCT_KINDS` and every existing kind's counting are unchanged.

## Measured estimate

Full tables, method and per-start figures:
[measurement README](../measurements/felt-whistle-estimate/README.md).

**How the counts were made:**
- The probe was a read-only `fprintf` patch, applied to a scratch build from
  a `git archive` export of `8d2c8df3`, never to the session worktree.
- Its twin check matched #236's plain runs in 495 of 500 games. The five that
  differ are excluded.
- Counts are whistles meeting each precondition inside admitted programs'
  windows, per start and per program ordinal.

bard-default-path (programs 1 / 2 / 3):

| | admitted (probed) | today: delivered of reached callback | A uses / programs | B uses / programs | C |
|---|---|---|---|---|---|
| program 1 | 37 (36) | 16 of 38 | 5 / 5 | 57 / 23 | 0 |
| program 2 | 25 (23) | 3 of 11 | 2 / 2 | 35 / 15 | 0 |
| program 3 | 6 (5) | 2 of 9 | 1 / 1 | 10 / 3 | 0 |

**Gate estimate (not a measurement):**

| start | today part 1 / part 3 | A | B | C |
|---|---|---|---|---|
| bard-default-path | 6 / 1 | 6 / 1 | **12 / 4** | 6 / 1 |
| bard | 13 / 6 | 14 / 8 | 31 / 19 | 13 / 6 |
| bard-inherited | 3 / 0 | 5 / 1 | 6 / 2 | 3 / 0 |

**Assumptions:**
- Every admitted program with one precondition use becomes felt, once.
  - On bard-default-path every recorded callback intent was an effect, never
    `quiet`.
- Admission is unchanged.
- The rest of the game is held fixed, although a confused player plays
  differently afterwards.
- Unprobed guards would refuse some uses.

So B's figures are an **upper bound**. They clear both parts of the gate on
bard-default-path with a margin of 2 and 1; A and C do not move it.

If program 1 also dropped the companion admission check (#196 C3), which a
companion-free effect does not need, the 38 refused program-1 publishes would
be admitted. 29 of them had a whistle meeting B's precondition within 100
moves. The looser upper bound is then 23 / 13. That is a separate decision
(question 3).

## Recommendation: B, "ring"

### Telegraph text (new)

| where | identifier / contract id | text |
|---|---|---|
| first program (v2) | `next-use-v2-Wr` | "The next whistle may ring on after you stop." |
| recurrence | `next-use-again-Wr`, telegraph extension **9** | "Again, a whistle may ring on after you stop." |
| broad program (v3/v4) | `next-use-v4-Wr`, telegraph extension **10** | "For a while, your whistles may ring on after you stop." |

Ids 5 and 7 stay as they are, for `whistle_attention` programs.

### Validated at load

- The envelope names its W effect. `next_use_program_v` 4 is v3 plus one key,
  `"w_effect"`: `"attention"` or `"ring"`.
- `schema_envelope` (`src/chaos_next_use.c:624-687`) rejects any other value,
  and pins the telegraph identifier to the effect. So a ring program can only
  load with a ring telegraph.
- The runtime rejects a callback intent that does not match the loaded
  effect. It uses the existing wrong-family path
  (`src/chaos_next_use_runtime.c:1164-1171`), so no program can switch effect
  mid-run.
- Bounds are engine-owned: N = 5 moves (`CHAOS_NEXT_USE_RING_MOVES`), and
  `BROAD_USES` = 2 as today.

### Implementation outline

- **Hook:** none new. B reuses `chaos_next_use_whistle_completed`, already
  called from `src/apply.c:12264` and `src/apply.c:12272` and registered in
  `docs/upstream-chaos-hooks.json`. With CHAOS=0 it is `((void)0)`
  (`include/chaos.h:113`). No upstream file changes.
- **Engine** (`src/chaos_engine.c`, the whistle callback):
  1. When the runtime returns a pending ring, evaluate the public guards.
  2. Arm the `whistle_ring` observation and print the message.
  3. Call `make_confused(HConfusion + CHAOS_NEXT_USE_RING_MOVES, FALSE)`.
  4. Report delivered or guarded to the runtime.
- **Runtime** (`src/chaos_next_use_runtime.c`):
  - intent `CHAOS_NEXT_USE_INTENT_WHISTLE_RING`;
  - effect rows `W_RING_DELIVERED` and `W_RING_GUARDED` (with a guard
    reason);
  - pacing credit on delivery, as at lines 1432-1433;
  - a broad program counts deliveries toward `BROAD_USES`.
- **Parsers:**
  - `src/chaos_lua.c:448-458` (the intent op);
  - `src/chaos_next_use.c` (`schema_intent`, `schema_envelope` v4,
    `chaos_next_use_player_warning`);
  - `src/chaos_reveal.c:690-697` (end-of-game reveal line).
- **Contract** (`chaos/protocol_contract.json`, then the generator, which
  rewrites `include/chaos_protocol.h` and `chaos/_protocol_contract.py`):
  - telegraph extensions 9 and 10;
  - observation operation 5 and fact 13.
- **Director:**
  - `chaos/next_use_compose.py:9-19` (op menu);
  - `next_use_history.py`;
  - `next_use_envelope.py` (v4, `w_effect`);
  - `next_use_journal.py:319` (names);
  - `next_use_author.py`;
  - `chaos/prompts/next-use-mechanics.txt` and its pinned sources JSON.
- **Measurement:** the felt branch in `tests/chaos/sweep_programs.py`.

### Saves and replay

- The runtime gains `w_effect`, so the next-use snapshot version goes 7 → 8
  (`include/chaos_next_use_runtime.h:279-280`). Versions 6 and 7 still
  restore, as attention programs.
- Confusion itself is `HConfusion` in `struct you`, which is already saved
  whole (`src/save.c:335`).
- Nothing new goes into bones.
- Replay: seed plus whispers plus the envelope reproduce the run, since the
  apply draws no RNG.

### Tests (write the failing oracle first)

- **Linked native fixtures:**
  - a ring program at a valid whistle gives Conf for exactly 5 moves, the
    message, a published notice and the effect row;
  - each guard (confused, stunned, hallucinating, engulfed, low HP, adjacent
    visible hostile, adjacent visible peaceful, remembered water or lava)
    gives no confusion, a guarded row, and **RNG accounting identical** to
    the no-program control;
  - an unseen hostile or unseen water does not block, as the guards read only
    public state.
- **Schema:**
  - v4 rejects an unknown `w_effect`;
  - a ring effect with an attention telegraph (and the reverse) is rejected;
  - a mismatched intent ends the program as an invalid callback;
  - every rejected path has a test.
- **Save/restore:**
  - mid-confusion, and mid-program between uses;
  - a v7 snapshot restores as an attention program.
- **Stock:** CHAOS=0 build, and no-whisper equality, unchanged.
- **Sweep:** `distinct_felt` unit test for the new felt branch, with old
  kinds unchanged.

### Tier A acceptance evidence it would need

- Both CHAOS=1 and CHAOS=0 builds warning-clean.
- Fast and native suites complete, run under tmux into retained logs.
- A real Unix save/restore round trip, and an exact replay.
- A real nonwizard `python3 -m chaos play --ordinary` capture showing, in
  order:
  1. the ring telegraph at admission;
  2. the whistle;
  3. "Your whistle's note goes on ringing inside your head.";
  4. **Conf** on the status line;
  5. "You feel less confused now.".
- A fresh baseline-v2 seeds 1–100 sweep giving the gate figures per start, as
  a measured check of this proposal's estimate.
- An entry under `docs/evidence/`.

## Questions for Sam

1. **B as the new W effect?** And for which programs: all W programs, or
   programs 2–3 only (where `whistle_attention` delivered 5 of 31), keeping
   attention for program 1?
2. **Duration:** a fixed engine constant of 5 moves, or a load-validated
   parameter 3..5 in the envelope?
3. **Program 1's companion admission check** (#196 C3): drop it for ring
   programs, since the effect no longer needs a companion?
4. **A guarded use:** should it consume a broad program's use, or leave it
   waiting for the next whistle, as C does for a use suppressed before the
   callback (`src/chaos_next_use_runtime.c:1254-1260`)?
