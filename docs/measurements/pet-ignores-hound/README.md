# Pets never attack the echo hound: real-play before/after (Tier B)

Sam's decision (2026-10-08, about 11:22Z): "Pets won't attack it". The change
makes tame monsters never target, hold a grudge against, or return an attack
on the admitted echo hound. The player can still kill it, and it still gives
up after about 60 turns. This measurement checks what that does in real play.

## Protocol (written and committed before any game was run)

- **Games:** 50 real nonwizard `python3 -m chaos play --ordinary` games per
  tree (#198 defaults: hound and next-use on), each on a fresh random map.
- **Trees:** `main` at 8715309f against this branch's head. Both are git
  archive exports, each built with `make -j2 install CHAOS=1` (clean env).
  The games alternate between trees (main 0, head 0, main 1, ...) under
  hermes-heavy.
- **No model:** no `NYARLATHACK_AUTHOR_*` settings, so the hound is
  `footsteps.lua` and there is no hound lane. `measure.py` refuses to start
  if any author setting is present and records whether a hound lane appeared.
- **Driver:** the #190 screen driver (`tests/chaos/haunt_explorer.Player`),
  exactly as #201's `baseline.py`. It paces the start room until the trial is
  decided (at most 40 keys). If the hound is admitted, it keeps pacing until
  the haunt expires, the hound is killed, or 90 keys pass.
- **Measures** (per admitted hound; `analyze.py`, #201's attribution):
  - admitted;
  - killed by the pet / by the player / expired alive (and alive at end);
  - live steps (`haunt_step` events, which the engine emits only when the
    player can see the hound): median, mean with a bootstrap 95% interval,
    and the distribution;
  - lived 10+ turns after admission.

## Expected direction (stated before running)

- **Primary:** killed by the pet falls from most admitted hounds on main (26 of
  36 in #201's after run) to **0** on the head. Any pet kill on the head is a
  path this change left open and will be reported as such.
- **Secondary:** mean live steps and "lived 10+ turns" rise on the head, and
  "expired alive" and "killed by the player" rise with them.
- **Unchanged (no direction expected):** admitted count and admission turn.
  Placement is untouched, so differences there are noise.
- The pet may still stand in the hound's path, and the driver stops at 90
  keys, so a hound that is still alive then counts as "alive at end", not
  "expired alive".

## Results

- **Run:** 2026-10-08, 11:58Z to 12:00Z, under hermes-heavy. Trees: main
  8715309f and head 807c7b79. The head tree is the engine change plus this
  preregistered protocol; later commits change only tests and this directory.
- **Per-game data:** `games.jsonl`, including each game's per-key top-line
  messages that mention the echo hound, the dog or a corpse (every message
  `analyze.py` reads). `python3 analyze.py games.jsonl` reproduces
  `summary.json` byte for byte.
- **No model:** no hound lane appeared in any of the 100 games.

| | main 8715309f | head 807c7b79 |
|---|---|---|
| games (driver errors) | 50 (0) | 50 (1) |
| admitted | 44 | 35 |
| undecided in 40 keys / rejected | 6 / 0 | 13 / 1 |
| **killed by the pet** | **36** | **0** |
| killed by the player | 6 | 31 |
| killed, unattributed | 2 | 0 |
| expired alive | 0 | 4 |
| lived 10+ turns after admission | 8 | 27 |
| life after admission, median (turns) | 5 | 17 |
| live steps, median | 2 | 3 |
| live steps, mean (bootstrap 95%) | 2.82 (2.32 to 3.43) | 3.00 (2.31 to 3.80) |
| pet hits the hound (top-line messages) | 14 | 0 |
| the hound bites the pet | 5 | 38 |

Live steps, distribution (number of admitted hounds; 10+ pooled):

| steps | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10+ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| main | 0 | 9 | 17 | 8 | 3 | 3 | 1 | 1 | 1 | 1 | 0 |
| head | 5 | 4 | 7 | 5 | 6 | 5 | 2 | 0 | 0 | 0 | 1 |

### Against the stated expectations

- **Primary, as expected:** the pet killed 36 of 44 admitted hounds on main
  and 0 of 35 on the head. It never hit the hound on the head, although the
  hound bit the pet 38 times.
- **Secondary, mixed:** the hound now lives much longer (10+ turns in 27 of 35
  hounds against 8 of 44; median life 17 turns against 5). Most hounds now die
  to the player (31), and 4 expired alive. But **live steps barely moved**
  (mean 2.82 to 3.00; the intervals overlap almost entirely), and 5 head
  hounds were seen to step 0 times. `haunt_step` counts only the hound's
  following moves that the player can see. Once the pet stops killing it, the
  hound mostly spends its turns fighting the pet or the player beside it, which
  are not steps. So "lives longer" did not become "is seen hunting longer".
- **Admission, not expected to move, but it did:** 44 against 35 (Fisher
  exact two-sided p = 0.048). The change cannot act before admission: the
  predicate is false while no hunt is active and inside the shadow trial.
  Each game draws a fresh random map, and the head draw had more small start
  rooms (7 of 49 with 12 squares or fewer, against 3 of 50). #201's rule makes
  the trial wait in a start room where every square is within 4 of the pet.
  All 13 undecided head games were still waiting in the start room at the
  driver's 40-key limit. The best reading is map-draw noise, but this design,
  with unpaired maps, cannot prove that.

### Post-run corrections (disclosed)

- `analyze.py` first scored "the little dog eats a jackal corpse named echo
  hound" as a pet kill even when the player had killed the hound the turn
  before. That moved 6 head games and 1 main game from "player" to "pet". The
  rule now counts a corpse-eating message as a pet kill only when the player
  did not kill the hound. The uncorrected output said 6 pet kills on the head;
  all 6 had "You kill echo hound" on the previous turn.
- `measure.py`'s raw-stream hit counters read 0 for every game: the terminal
  stream splits those messages with cursor moves. The table's hit counts come
  from the per-key top-line messages in the trace instead.

## Run 2: the two-way truce (preregistered before any game was run)

Sam's decision (2026-10-08, about 14:51Z): "Two-way truce". The admitted
echo hound now never attacks a tame monster either (the steed included), so
its turns should go into following the player's trail.

- **Question:** what does the reverse truce add on top of run 1's head?
- **Trees:** `prev` = 9a608714 (the run-1 change, as reviewed) against `head`
  = the commit that adds this section (the reverse truce plus this
  protocol). Same protocol as run 1: 50 games per tree, alternating, git
  archive exports built with `make -j2`, hermes-heavy, no author settings.
  Raw results go to `games-run2.jsonl`, the summary to `summary-run2.json`.
- **Expected direction:**
  - live steps rise (mean and median) on `head`;
  - the hound biting the pet falls to 0 on `head` (from 38 in run 1);
  - pet kills stay 0 on both trees.
  - No direction expected for admission (placement is untouched).
- **Also reported:** main 8715309f (run 1) against `head` (run 2). That
  comparison is made **across separate runs**, so map draws and host load
  differ, and is labelled as such.
- **Added measure:** the per-hound median number of turns from admission to
  the first live step.
