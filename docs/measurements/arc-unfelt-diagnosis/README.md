# Why later next-use programs are never felt (diagnosis)

Tier B, docs only. No engine, director, sweep-tool or contract change, no new
sweep or capture, no player-visible delta. Everything here is post-run analysis
of #231's retained main sweep plus a reading of the code at origin/main
`8eef504b`.

## Sources, and what is missing

- The retained #231 main-sweep JSON report (5 starts x seeds 1-100,
  baseline-v2, `report_sha256` `671a0bb9...`; file sha256 `7979c5dd...`). Its
  rendered form is committed as
  [`../arc-metric-distinct-felt/sweep/`](../arc-metric-distinct-felt/sweep/).
- **The per-game run directories (journals, `events.jsonl`) are gone.** They
  were removed in #231's cleanup. So there is no per-use timing, no admission
  move for later programs, and no record of which family (W or F) a later
  program had. What remains per program is: published, admitted, trigger count,
  native-effect count, delivered, felt, and termination reason. Per game it also
  has whistle and drink counts, game length, outcome, levels and felt events.
  Where a claim below depends on what is missing, it says so.
- [`attribute.py`](attribute.py) turns the report into
  [`attribution.json`](attribution.json): one row per admitted later program
  with its binding, the later-program publication funnel, and the projections in
  the options section. Usage: `python3 attribute.py <report.json>`. It runs no
  game.

**Correction to #231's README.** It said "21 never triggered (14
`program_expired`, 7 `completed`, 2 `origin_expired`)". Those parts sum to 23,
and 18 + 23 + 4 = 45. The right figure is 23. This PR corrects that line.

## Attribution of the 45 admitted-but-unfelt later programs

45 programs (index 2 or 3) were admitted in 41 games: bard 22,
bard-default-path 12, bard-inherited 11. None was felt.

| Binding that stopped it | n | bard | default-path | inherited | Kind |
|---|---:|---:|---:|---:|---|
| Triggered; the callback was **authored `quiet`** and consumed the slot | 18 | 12 | 2 | 4 | game fact (default director) |
| Whistled, but **no qualifying companion** (W capture suppressed before the callback) | 7 | 0 | 5 | 2 | game fact (C3) |
| **100-move program expiry** with no qualifying use | 14 | 9 | 2 | 3 | rule = game fact; whether the player used it = policy |
| **300-move origin deadline** with no qualifying use | 2 | 1 | 1 | 0 | same |
| **Open at game end** (2 deaths before turn 400; 2 at the 2,000-turn cap) | 4 | 0 | 2 | 2 | policy (survival, turn cap) |
| Level departure | 0 | | | | |
| Origin eviction | 0 | | | | |
| Whistle-type exclusion (magic whistle) | 0 | | | | none of the 41 games found any whistle |

### The decisive one: programs 2 and 3 are always `quiet` on the default path

The sweep passes no `--seed`, so the director seed is 0. A default
`python3 -m chaos play --ordinary` run gets the same seed. `NextUseScheduler`
picks program *k* with `RandomHistoryBackend(seed + k - 1)`
(`chaos/next_use_schedule.py`). For the one origin row it publishes on, the
menu is `[quiet, effect]`, in `_FAMILIES` order (`chaos/next_use_history.py`).
`random.Random(0).choice` of two items picks index 1 (`effect`), while
`Random(1)` and `Random(2)` pick index 0 (`quiet`). So with no `--seed`:

- program 1 is always the effect: 59 of 60 program-1 triggers had a native
  effect;
- programs 2 and 3 are always `quiet`: 0 of 18 triggers had one, and the Arc 1
  ordinary capture's program 2 (`docs/measurements/arc1-recurrence/`) is
  `quiet` too.

Under `quiet`, the engine records the intent, consumes the slot
(`CHAOS_SLOT_*_CONSUMED_QUIET`) and completes the program. The player saw the
recurrence telegraph ("Again, the whistle carries farther than it should."), and
then nothing happened. **Under today's default no later program can be felt,
whatever the player does.** Every other binding in the table only decides
whether a quiet callback runs. This is not a sweep-player artefact. It is what
the default path does.

### W needs a companion, at the whistle and at admission

The 7 `completed` programs with no trigger are W programs suppressed at the
whistle. A program completes without an intent row only through
`W_CAPTURE_SUPPRESSED`: `chaos_next_use_whistle_completed` asks
`chaos_next_use_companion_pick` before the callback runs. The recorded reason
(none in view, or not eligible) was in the deleted journals; the report's
`w_suppressions` field reads program 1's journal only.

Further up the funnel, the same C3 rule decides more. On bard-default-path, the 200 later-program slots break down as:

| Later-program slot (bard-default-path) | n |
|---|---:|
| not published (program 1 still open, or the game ended first) | 69 |
| published, no admission decision before the game ended | 53 |
| rejected: no companion in view at the safe point (C3) | 48 |
| rejected: budget | 17 |
| rejected: origin/index | 1 |
| admitted | 12 |

C3 at admission rejects four times as many later programs as are admitted.

### Expiry and re-use: what the sweep player contributes

In the 16 expiries, the player whistled 0.6-2.2 times per 100 turns over the
game (median 1.25). That is the baseline-v2 policy: `p_whistle = 0.03` per
step, and at most 2 drinks per fountain level. At each game's own average rate,
about 4.8 of the 16 programs would see no whistle in 100 moves by chance. The
other 11 or so fell in quieter stretches; why can't be checked without the
journals. Also unknown without them is how many of the 16 were F programs: 10
of the 16 games never drank from a fountain, so those programs were W.

**Separating the two plainly:**

- **Game facts.** Recurrence programs are authored quiet on the default path
  (18 programs directly, and every other later program had it latent). W needs
  a companion in view at the whistle (7) and at admission (48 rejections on the
  default path). Programs live 100 moves and origins 300.
- **Sweep-policy limits.** The whistle rate decides whether a use falls inside
  the 100-move window (16 programs; about 5 explained by rate alone). The
  2,000-turn cap and early deaths leave 4 open. The policy also suppresses
  publication: 122 default-path later slots never reach a decision before the
  game ends.
- **Net effect on the gate today: the policy contributes nothing.** If the sweep
  player re-used the whistle at once every time, the 20 expired or open programs
  would run a quiet callback and still not be felt.

## Adopted gate and how far today is from it

The adopted gate is in [`../../proposals/multi-whisper-arc.md`](../../proposals/multi-whisper-arc.md#adopted-gate-for-arc-work).
On bard-default-path, games with 2+ distinct felt whispers excluding the hound
must rise from 2/100 to at least 10/100, and at least 3/100 games must feel two
next-use programs. Today the second figure is 0/100. On bard-default-path only
5 games admit two programs at all, and if every admitted program were felt, 10
games would reach 2+ non-hound. Even a perfect fix to what happens after
admission therefore lands exactly on the threshold, so admission has to grow
too.

## Options (projections)

The projections replay each game's own recorded rates. They are not
measurements, and the gate is measured only by a sweep on the implementing PR.
The model, all from this sweep:

- a W use finds a companion with probability 0.83 (program 1: 60 triggers vs 12
  suppressions);
- an armed effect is witnessed with probability 0.49 (29 felt of 59 native);
- whistles arrive as a Poisson process at the game's average rate;
- door and hunger sources are kept as observed.

Columns: bard-default-path at the observed whistle rate, then at half that rate
(sensitivity to the sweep player), then plain bard. Each cell gives games with
2+ non-hound distinct / games with two felt next-use programs, per 100.

| Option | default-path | default-path, half rate | bard |
|---|---:|---:|---:|
| today (model reproduces observed) | 2.0 / 0.0 | 2.0 / 0.0 | 4.0 / 0.0 |
| **1** measurement/policy only | 2.6 / 0.4 | 2.6 / 0.4 | 6.0 / 2.7 |
| 2a effect authoring only | 2.0 / 0.0 | 2.0 / 0.0 | 4.5 / 3.0 |
| **2** recurrence repair, later life 300 | 8.0 / 3.4 | 7.1 / 2.8 | 14.8 / 7.8 |
| 2 with later life 100 | 6.3 / 2.3 | 4.8 / 1.4 | 12.2 / 6.1 |
| 3 Sam's idea as worded, life 100 | 3.8 / 0.0 | 3.0 / 0.0 | 6.0 / 0.0 |
| 3 Sam's idea as worded, life 300 | 5.3 / 0.0 | 4.3 / 0.0 | 7.4 / 0.0 |
| 3 + effect authoring, life 300 | 7.6 / 3.2 | 5.9 / 2.1 | 14.0 / 8.2 |
| **3+** Sam's idea + recurrence repair, life 100 | 9.9 / 5.1 | 6.3 / 2.3 | 17.5 / 10.5 |
| **3+** Sam's idea + recurrence repair, life 300 | **18.1 / 12.6** | **12.8 / 7.6** | 28.5 / 22.2 |
| 3+ life 300, recurrence effect 50/50 | 13.6 / 8.0 | 9.1 / 4.1 | 22.1 / 13.8 |

Gate: at least 10 / 3. "Life" is how many moves a program stays open.

### Option 1: measurement and policy only

- **What:**
  - the sweep passes a per-game director seed (for example, the game seed), so
    the director's choice varies across games;
  - a baseline-v3 policy whistles after it sees a next-use telegraph, while a
    companion is in view, inside the window. The telegraph is public, so this
    is public-only.
  - Where: `tests/chaos/sweep_player.py`, `scripts/seed_sweep.py`.
- **Rules:** none touched; no game change.
- **Effect:** 2.6 / 0.4. Even perfect re-use mostly runs quiet callbacks. A
  varied seed makes about half the later programs effects, but only 12
  default-path later programs are admitted.
- **Risk:** it measures a different director than the one players get with no
  `--seed`. Meeting the gate this way would not be a game fact. It does not
  meet the gate.

### Option 2: recurrence repair (three targeted fixes)

- **What:**
  - (a) **Director:** for programs 2-3, narrow the menu to the effect op, as
    Arc 1's family preference narrows the family (`chaos/next_use_schedule.py`).
    A recurrence telegraph then always precedes a real effect.
  - (b) **Engine:** C3 is checked only at the use, not at admission, for
    programs 2-3 (`src/chaos_next_use_safe.c`, the `no_companion_in_view` bit).
    The whistle-time check stays.
  - (c) **Engine:** later programs live 300 moves, matching the origin
    deadline (`program_expiry` in `src/chaos_next_use_admission.c`).
- **Rules:**
  - Engine authority is kept: the engine still admits, debits and checks the
    companion at use.
  - Telegraph: the "Again, ..." line becomes true. Today it precedes a
    guaranteed quiet.
  - No retiming: the expiry change is a constant written at admission, not a
    move of an existing effect.
  - Public-only and no-whisper-equals-stock are unaffected.
- **Save/replay:**
  - `program_expiry` is already stored per admission, so old saves keep their
    100;
  - the admission reason set changes, so journals and contract fixtures change.
    That is Tier A.
- **Effect:** 8.0 / 3.4. It meets the two-programs clause narrowly and the
  10/100 clause not quite. Fix (a) alone does nothing on the default path:
  only 2 admitted later programs triggered there.
- **Risk:**
  - it falls short of 10 in projection;
  - admitting without a companion means more W programs end suppressed at the
    use;
  - a fixed effect op for recurrences removes director choice for programs 2-3.

### Option 3: Sam's idea, one program covers every whistle and fountain use

Strongest coherent form: an admitted program fires on every use of any whistle
(tin or magic) and any fountain until it expires. It survives level changes,
with one callback per use. The data first, then what it requires.

**Data.**

- As worded, with the director unchanged, it scores 5.3 / 0.0. Programs 2-3
  are authored quiet, and a quiet program stays quiet on every use.
- It also does not add distinct programs. The gate counts programs, so many
  felt uses of program 1 count once.
- Its real gain is on program 1: an armed-but-unwitnessed effect (half of all
  program-1 effects) gets more tries.
- Combined with Option 2 (3+), it is the only option that clears both clauses
  with margin: 18.1 / 12.6. It still clears them at half the whistle rate:
  12.8 / 7.6.

**What it requires.**

- **Triggers:**
  - accept `MAGIC_WHISTLE`, which today has no next-use hook: a one-line hook
    in `src/apply.c`'s `MAGIC_WHISTLE` case, registered in
    `docs/upstream-chaos-hooks.json`;
  - decide what "attention" means for a magic whistle, which already
    teleports pets to you.
- **Slots:** replace the one-shot per-family slot (pending → consumed) with a
  per-family use counter. The author already emits `uses_per_family=1`
  (`chaos/next_use_author.py`); it becomes a bounded N. A quiet use should no
  longer end the program.
- **Bindings removed:**
  - `level_departure` no longer terminates. The runtime's `level_token` check
    goes, and the W armed window stays per level, because it binds a
    companion `m_id`;
  - the origin funds admission only. The 300-move origin deadline and
    eviction stop binding after admission.
- **Save/replay and journal:**
  - the runtime snapshot gains the use counter and loses the level binding,
    so `CHAOS_NEXT_USE_SNAPSHOT_V` is bumped and restore converts old
    snapshots;
  - journals carry several intent and effect rows per program, so the
    analyser's per-program counts and the replay capture records (already one
    per use root) need fixtures for repeats;
  - restores across a level change need a save-across-levels native test.
    Tier A throughout.
- **Telegraph:** "The next whistle may call unusual attention." promises one
  use. Multi-use needs new truthful text, for example "Whistles may call
  unusual attention for a while.", and the same for the recurrence lines. That
  is a contract change, regenerated with `scripts/generate_protocol_contract.py`.
- **No retiming:** each effect still happens at its own use; holding a program
  open longer is not retiming.
- **Engine authority:** the engine still admits and validates every use, and
  the callback decides each use.
- **Cap and budget:**
  - a program still costs 1, but is worth up to N uses. Consider cost 2.
  - #164 pacing counts a delivering *source* once, so repeats do not inflate
    capacity.
  - Because the scheduler publishes program *k*+1 only after program *k*
    terminates, longer-lived programs push programs 2-3 later. The median
    default-path game admits program 1 at move 460 and ends at turn 1,698, so
    there is usually room. Still, this makes the two-programs projection for 3+
    optimistic.
- **Risks:**
  - the largest change of the three: snapshot, journal, contract and telegraph;
  - multi-use pressure on a companion that can't be seen (W stays suppressed
    without one);
  - the magic-whistle semantics need a design of their own.

## Recommendation

Option 3+ (Sam's idea built on the recurrence repair), in two PRs: Option 2
first, since it is small and can be measured on its own, then the multi-use
program. The data favour it for these reasons:

- No option meets the gate without fixing the quiet recurrences and C3 at
  admission. That is Option 2, a prerequisite either way.
- Option 2 alone projects just short (8.0 / 3.4).
- Sam's multi-use program adds enough tries to clear both clauses with margin,
  even if the sweep player whistles half as often.

Option 1 is not enough: the sweep player is not the main limit.
