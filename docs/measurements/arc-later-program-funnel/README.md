# Later-program funnel — diagnosis

**Tier B, measurement only.** No gameplay, engine, director or contract
change; **player-visible delta: none.** Everything below reads private
journals and two engine probes. It is analysis, not player knowledge.

Every figure is per start, with the gate start `bard-default-path` first.
"Later" means programs 2–3. Gate: part 1 = games with 2+ distinct felt
whispers excluding the hound (target 10); part 3 = games feeling two next-use
programs (target 3).

## Data

The C sweep's per-game journals (dcd91662) were removed by that PR's cleanup,
so the C gate sweep was **re-run at main `3f067b65`** (game sources identical
to dcd91662): baseline-v2, seeds 1–100, five starts, `--jobs 2`, under
`hermes-heavy`. It reproduces C: on bard-default-path, programs 1/2/3
published 87/82/44, admitted 37/25/6, felt 16/3/2; gate part 1 = 6, part 3 = 1;
hound 88. Game for game against the C report, only `bard-00024` differs
(outcome, programs and distinct felt), and it differs between all three runs.

| sweep | report sha256 | game binary sha256 |
|---|---|---|
| plain, 3f067b65 | `eeb5b937…8463` | `721dc482…a391` |
| instrumented twin | `311c9787…12d9` | `1f6174f7…f87d` |

Per-game copies (events, receipts, lifecycle, schedule, whispers, journals,
envelopes, probe logs) are retained outside Git under
`~/.hermes/reports/nyarlathack-arc-later-funnel/runs-plain/` and
`runs-diag/`. B's later-program journals (53acae76) are still under
`~/.hermes/reports/nyarlathack-arc-repair/later-program-journals/`; nothing
below needed them.

### Instrumented twin

Question 1 needs the classifier terms, and questions 2 and 4 need "was a
qualifying companion publicly in view at this whistle". The journals record
neither, so a second sweep ran the same seeds with
[`instrumentation.patch`](instrumentation.patch) applied **only to the
measurement build** (a scratch `git archive` export of 3f067b65; never
committed to `src/`, `include/` or `chaos/`). It adds two `fprintf`s that read
state and draw no RNG:

* `src/dogmove.c`, after the classifier at lines 1258–1260: every term of the
  decision (`whappr`, `extra_attention`, `appr`, `gtyp`, goal square, player
  square, `pre_public`) → `classifier.log`;
* `src/chaos_engine.c`, at the top of `chaos_next_use_whistle_completed`:
  `chaos_next_use_companion_pick()` (the production on-screen + qualifying
  rule, line 611) at every whistle → `whistle-probe.log`.

**Twin check** (`funnel.py`, `twin`): receipts, lifecycle, schedule, whispers,
**events** and last turn byte-identical in **495 of 500 games**. The five that
differ, all in director-side whisper/ack timing, are **excluded from every
probe-derived count** (Q1 blocked reasons, Q2 companion-in-view, Q4):
`bard-00024`, `bard-00069`, `bard-default-path-00001`,
`bard-default-path-00021`, `bard-inherited-00078`. Journals are not compared:
they carry a per-process `run_token` and differ in every pair of runs.

### Aborted runs (disclosed)

None of these contributes a figure.

1. Instrumented sweep, 22 games: killed by a `pkill -f` pattern I ran. Before
   discarding it, its 20 complete games matched the plain run.
2. Both sweeps at ~93 / ~15 games: the worktree was switched off the sweep
   revision between turns while the harness was reading it; both restarted.
3. Instrumented sweep twice more, at under 15 games: stopped by tmux session
   name, once by mistake and once to add the whistle probe.

## 1. "Blocked" callbacks

**Rule working as designed, not a bug.** After the program arms a companion,
the extra-attention window is moves A+5 to A+10
(`src/chaos_next_use_runtime.c:1306-1311`). In that window `dog_move` asks for
a decision (`src/dogmove.c:1241-1253`) and credits the move to the program
only if the classifier holds (`src/dogmove.c:1258-1260`):

```c
manifestation_classifier = whappr == 0 && extra_attention != 0
    && appr != -2 && gtyp == UNDEF && gx == u.ux && gy == u.uy
    && pre_public;
```

If it fails, the observation is finished `CHAOS_OBS_STAGE_BLOCKED`
(`src/dogmove.c:1271-1280`). If it holds but the end-of-move check does not
publish (companion not displaced, not seen after, or presentation not
delivered), `chaos_whistle_witness_finalize` also finishes BLOCKED
(`src/chaos_engine.c:569-578`). Each term keeps the credit to moves only the
program explains:

* `whappr == 0`: no ordinary whistle pull. `whappr` is true for 5 moves after
  any whistle (`src/dogmove.c:1234`, set at `src/apply.c:743`);
* goal `UNDEF` at the player's square: not heading for food or an item
  (`src/dogmove.c:944-961`);
* `pre_public`: the companion was visibly on screen before the move.

A blocked window ends the use, not the program (`src/chaos_next_use_runtime.c:1031-1033`).

**Capture attempts a3 and b1–b3.** Their recipe whistled every 5 moves, so the
next ordinary whistle always landed as the window opened. Re-running the
recipe on the instrumented build:

* a2, a4 (gap 5): all 12 decisions `whappr=1`;
* c2 (gap 8): all 6 `whappr=0`, `gtyp=4` (APPORT, the dog going for an item);
* c1 (gap 8, the PR #235 capture): both `whappr=0`, goal = player, delivered.

**In the sweep**, uses that reached the program's callback, by first failing
term (all failing terms are in `funnel.json`).
"classified_but_move_not_published" means the classifier passed but the
end-of-move check did not publish.

**bard-default-path**

| program | uses reaching callback | delivered | blocked | blocked: first failing term | quiet / other |
|---|---|---|---|---|---|
| 1 | 38 | 16 | 19 | ordinary_whistle_pull_active 7, goal_apport 6, classified_but_move_not_published 3, goal_not_player_square 2, not_publicly_visible_before_move 1 | F:fountain_native_19_30 2, W:no_decision_in_window 1 |
| 2 | 11 | 3 | 8 | classified_but_move_not_published 2, goal_apport 2, goal_not_player_square 2, not_publicly_visible_before_move 1, ordinary_whistle_pull_active 1 | — |
| 3 | 9 | 2 | 6 | ordinary_whistle_pull_active 2, classified_but_move_not_published 1, goal_apport 1, goal_cadaver 1, not_publicly_visible_before_move 1 | W:no_decision_in_window 1 |

**bard**

| program | uses reaching callback | delivered | blocked | blocked: first failing term | quiet / other |
|---|---|---|---|---|---|
| 1 | 42 | 23 | 16 | classified_but_move_not_published 8, goal_apport 3, not_publicly_visible_before_move 3, goal_not_player_square 1, ordinary_whistle_pull_active 1 | W:no_decision_in_window 3 |
| 2 | 23 | 11 | 12 | ordinary_whistle_pull_active 6, not_publicly_visible_before_move 3, classified_but_move_not_published 2, goal_not_player_square 1 | — |
| 3 | 5 | 2 | 3 | classified_but_move_not_published 1, goal_not_player_square 1, ordinary_whistle_pull_active 1 | — |

**bard-inherited**

| program | uses reaching callback | delivered | blocked | blocked: first failing term | quiet / other |
|---|---|---|---|---|---|
| 1 | 25 | 7 | 16 | classified_but_move_not_published 5, goal_not_player_square 5, goal_apport 2, ordinary_whistle_pull_active 2, goal_cadaver 1, not_publicly_visible_before_move 1 | W:no_decision_in_window 2 |
| 2 | 10 | 5 | 5 | not_publicly_visible_before_move 2, classified_but_move_not_published 1, goal_apport 1, goal_not_player_square 1 | — |
| 3 | 0 |  |  |  |  |

**madman**

| program | uses reaching callback | delivered | blocked | blocked: first failing term | quiet / other |
|---|---|---|---|---|---|
| 1 | 1 | 0 | 0 | — | F:fountain_native_19_30 1 |
| 2 | 0 |  |  |  |  |
| 3 | 0 |  |  |  |  |

**wizard-default-path**

| program | uses reaching callback | delivered | blocked | blocked: first failing term | quiet / other |
|---|---|---|---|---|---|
| 1 | 0 |  |  |  |  |
| 2 | 0 |  |  |  |  |
| 3 | 0 |  |  |  |  |

## 2. Origin expiry

The origin deadline is set at admission as the origin's move plus
`CHAOS_NEXT_USE_ORIGIN_LIFETIME` = 300
(`src/chaos_next_use_safe.c:795-799`, `include/chaos_next_use_safe.h:11`). The
program's own lifetime is the envelope ttl, 300 moves from **admission** for a
later program (`chaos/next_use_envelope.py:42-51`,
`src/chaos_next_use_admission.c:116`). Both deadlines are 300 moves, but the
origin clock started earlier, at the origin whistle. So for a later program
the origin deadline always comes first, by the origin's age at admission. It
is checked before program expiry (`src/chaos_next_use_runtime.c:926-934`).

| start | later programs ended at origin expiry | moves admission → origin expiry (min / median / max) | origin age at admission (min / median / max) | whistle uses in window (in N programs) | of those, companion in view (in N programs) | fountain drinks in window (in N programs) | programs with ≥ 1 callback |
|---|---|---|---|---|---|---|---|
| bard-default-path | 23 | 38 / 255 / 297 | 4 / 46 / 263 | 51 in 19 | 21 in 8 | 4 in 2 | 8 |
| bard | 43 | 14 / 219 / 294 | 7 / 82 / 287 | 112 in 34 | 21 in 12 | 7 in 6 | 12 |
| bard-inherited | 10 | 7 / 268.0 / 300 | 1 / 33.0 / 294 | 12 in 6 | 6 in 4 | 3 in 2 | 4 |
| madman | 0 |  |  |  |  |  |  |
| wizard-default-path | 2 | 244 / 262.0 / 280 | 21 / 39.0 / 57 | 6 in 2 | 0 in 0 | 2 in 1 | 0 |

bard-default-path, each of the 23 (companion in view at each whistle:
Y = a qualifying companion on screen, n = none):

| seed | program | origin move | admitted | origin deadline | program expiry | moves admitted → origin expiry | whistles | companion in view at each | fountain drinks | callback outcomes |
|---|---|---|---|---|---|---|---|---|---|---|
| 4 | 3 | 781 | 808 | 1081 | 1108 | 274 | 0 | — | 0 | — |
| 7 | 3 | 1152 | 1180 | 1452 | 1480 | 273 | 9 | YnnnYYYnn | 0 | blocked, delivered, blocked, no_decision_in_window |
| 12 | 2 | 595 | 635 | 895 | 935 | 261 | 3 | nnn | 0 | — |
| 22 | 2 | 650 | 696 | 950 | 996 | 255 | 1 | n | 0 | — |
| 25 | 2 | 610 | 640 | 910 | 940 | 271 | 3 | nYY | 0 | blocked, blocked |
| 27 | 2 | 875 | 913 | 1175 | 1213 | 263 | 5 | YnYYY | 0 | blocked, blocked |
| 32 | 2 | 261 | 427 | 561 | 727 | 135 | 1 | n | 0 | — |
| 56 | 3 | 858 | 907 | 1158 | 1207 | 252 | 1 | Y | 2 | blocked |
| 64 | 2 | 1080 | 1107 | 1380 | 1407 | 274 | 3 | nYY | 0 | blocked, blocked |
| 65 | 2 | 1250 | 1362 | 1550 | 1662 | 189 | 1 | n | 0 | — |
| 70 | 3 | 673 | 677 | 973 | 977 | 297 | 2 | nn | 0 | — |
| 72 | 2 | 824 | 859 | 1124 | 1159 | 266 | 3 | nYn | 0 | delivered |
| 72 | 3 | 1194 | 1220 | 1494 | 1520 | 275 | 6 | YYYYYY | 0 | delivered, blocked, blocked, blocked |
| 77 | 2 | 906 | 970 | 1206 | 1270 | 237 | 2 | nn | 0 | — |
| 81 | 2 | 1195 | 1372 | 1495 | 1672 | 124 | 0 | — | 0 | — |
| 85 | 2 | 175 | 336 | 475 | 636 | 140 | 2 | nn | 0 | — |
| 89 | 2 | 625 | 636 | 925 | 936 | 290 | 1 | n | 0 | — |
| 90 | 2 | 573 | 624 | 873 | 924 | 250 | 1 | n | 0 | — |
| 90 | 3 | 970 | 1021 | 1270 | 1321 | 250 | 2 | nn | 0 | — |
| 91 | 2 | 1639 | 1902 | 1939 | 2202 | 38 | 0 | — | 0 | — |
| 95 | 2 | 623 | 633 | 923 | 933 | 291 | 2 | Yn | 0 | blocked |
| 96 | 2 | 539 | 666 | 839 | 966 | 174 | 0 | — | 2 | — |
| 99 | 2 | 1081 | 1237 | 1381 | 1537 | 145 | 3 | nnn | 0 | — |

Only **2 of 23** had a companion-in-view whistle between the origin deadline
and their own expiry (seeds 7 and 64). Most of the 23 had no use that could
deliver: 15 had no whistle with a companion in view at all in their window.

## 3. Budget refusals

The engine refuses when cost > `chaos_budget()`
(`src/chaos_next_use_admission.c:103-105`). `chaos_budget()`
(`src/chaos_protocol.c:214-228`) is base 2 + lost Sanity / 10, plus #164
pacing credits (descent, witnessed) under a per-level cap, minus spent. Every
event row logs it (`src/chaos_io.c:61`). The counterfactual is admission at
`chaos_budget() + k`.

| start | later refusals for budget | budget the only reason | lost Sanity (value: count) | cruelty spent (value: count) | spent by source (points) | engine budget available (value: count) | admitted at +1 | admitted at +2 | Sanity-only bound: +1 / +2 |
|---|---|---|---|---|---|---|---|---|---|
| bard-default-path | 38 | 38 | 0: 38 | 2: 6, 3: 18, 4: 12, 5: 2 | hound 75, next_use_program 23, ordinary_whisper 26 | 0: 38 | 38 | 38 | 6 / 24 |
| bard | 9 | 9 | 0: 9 | 2: 7, 3: 1, 4: 1 | next_use_program 10, ordinary_whisper 11 | 0: 9 | 9 | 9 | 7 / 8 |
| bard-inherited | 3 | 3 | 0: 3 | 2: 3 | next_use_program 3, ordinary_whisper 3 | 0: 3 | 3 | 3 | 3 / 3 |
| madman | 0 | 0 | — | — | — | — | 0 | 0 | 0 / 0 |
| wizard-default-path | 1 | 1 | 0: 1 | 2: 1 | next_use_program 1, ordinary_whisper 1 | 0: 1 | 1 | 1 | 1 / 1 |

On bard-default-path, every refusal had lost Sanity 0 and engine budget 0.
**The hound's 2 points spent the whole Sanity base in 37 of 38.** That's why
all 38 are admitted at +1. The Sanity-only column ignores pacing credits; it
is a bound, not the engine rule. **Admission is not the same as being felt.**
Of the later programs already admitted on this start, 5 of 31 were felt.

| seed | program | move | lost Sanity | Sanity budget (2 + lost/10) | spent | spent by source | engine budget available | cost | admitted at +1 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 2 | 1007 | 0 | 2 | 3 | hound 2, next_use_program 1 | 0 | 1 | yes |
| 4 | 2 | 490 | 0 | 2 | 3 | hound 2, ordinary_whisper 1 | 0 | 1 | yes |
| 5 | 2 | 721 | 0 | 2 | 4 | hound 2, next_use_program 1, ordinary_whisper 1 | 0 | 1 | yes |
| 5 | 3 | 1033 | 0 | 2 | 4 | hound 2, next_use_program 1, ordinary_whisper 1 | 0 | 1 | yes |
| 6 | 2 | 1147 | 0 | 2 | 2 | hound 2 | 0 | 1 | yes |
| 8 | 2 | 839 | 0 | 2 | 4 | hound 2, next_use_program 1, ordinary_whisper 1 | 0 | 1 | yes |
| 8 | 3 | 1851 | 0 | 2 | 4 | hound 2, next_use_program 1, ordinary_whisper 1 | 0 | 1 | yes |
| 9 | 2 | 610 | 0 | 2 | 3 | hound 2, ordinary_whisper 1 | 0 | 1 | yes |
| 10 | 2 | 979 | 0 | 2 | 2 | hound 2 | 0 | 1 | yes |
| 15 | 2 | 604 | 0 | 2 | 3 | hound 3 | 0 | 1 | yes |
| 16 | 2 | 1090 | 0 | 2 | 2 | hound 2 | 0 | 1 | yes |
| 22 | 3 | 1133 | 0 | 2 | 5 | hound 2, next_use_program 1, ordinary_whisper 2 | 0 | 1 | yes |
| 25 | 3 | 1933 | 0 | 2 | 5 | hound 2, next_use_program 2, ordinary_whisper 1 | 0 | 1 | yes |
| 28 | 2 | 484 | 0 | 2 | 3 | hound 2, ordinary_whisper 1 | 0 | 1 | yes |
| 34 | 2 | 1273 | 0 | 2 | 3 | hound 2, ordinary_whisper 1 | 0 | 1 | yes |
| 36 | 2 | 561 | 0 | 2 | 2 | hound 2 | 0 | 1 | yes |
| 37 | 2 | 787 | 0 | 2 | 3 | hound 2, next_use_program 1 | 0 | 1 | yes |
| 37 | 3 | 1794 | 0 | 2 | 3 | hound 2, next_use_program 1 | 0 | 1 | yes |
| 38 | 2 | 1067 | 0 | 2 | 3 | hound 2, ordinary_whisper 1 | 0 | 1 | yes |
| 39 | 2 | 962 | 0 | 2 | 3 | hound 2, next_use_program 1 | 0 | 1 | yes |
| 42 | 2 | 583 | 0 | 2 | 3 | hound 2, ordinary_whisper 1 | 0 | 1 | yes |
| 45 | 2 | 826 | 0 | 2 | 2 | hound 2 | 0 | 1 | yes |
| 47 | 2 | 1157 | 0 | 2 | 3 | hound 2, ordinary_whisper 1 | 0 | 1 | yes |
| 52 | 2 | 1332 | 0 | 2 | 3 | hound 2, next_use_program 1 | 0 | 1 | yes |
| 56 | 2 | 850 | 0 | 2 | 4 | hound 2, next_use_program 1, ordinary_whisper 1 | 0 | 1 | yes |
| 57 | 2 | 819 | 0 | 2 | 2 | next_use_program 1, ordinary_whisper 1 | 0 | 1 | yes |
| 58 | 2 | 1001 | 0 | 2 | 3 | hound 2, ordinary_whisper 1 | 0 | 1 | yes |
| 63 | 2 | 797 | 0 | 2 | 4 | hound 2, next_use_program 1, ordinary_whisper 1 | 0 | 1 | yes |
| 63 | 3 | 1901 | 0 | 2 | 4 | hound 2, next_use_program 1, ordinary_whisper 1 | 0 | 1 | yes |
| 64 | 3 | 1474 | 0 | 2 | 4 | hound 2, next_use_program 1, ordinary_whisper 1 | 0 | 1 | yes |
| 69 | 2 | 595 | 0 | 2 | 3 | hound 2, ordinary_whisper 1 | 0 | 1 | yes |
| 70 | 2 | 603 | 0 | 2 | 3 | hound 2, ordinary_whisper 1 | 0 | 1 | yes |
| 88 | 2 | 628 | 0 | 2 | 4 | hound 2, next_use_program 1, ordinary_whisper 1 | 0 | 1 | yes |
| 88 | 3 | 798 | 0 | 2 | 4 | hound 2, next_use_program 1, ordinary_whisper 1 | 0 | 1 | yes |
| 89 | 3 | 1736 | 0 | 2 | 4 | hound 2, next_use_program 1, ordinary_whisper 1 | 0 | 1 | yes |
| 94 | 2 | 893 | 0 | 2 | 3 | hound 2, next_use_program 1 | 0 | 1 | yes |
| 96 | 3 | 925 | 0 | 2 | 4 | hound 2, next_use_program 1, ordinary_whisper 1 | 0 | 1 | yes |
| 97 | 2 | 1043 | 0 | 2 | 3 | hound 2, next_use_program 1 | 0 | 1 | yes |

## 4. Program 1 refused for no companion

A later whistle within what would have been the program's 100-move lifetime
(`include/chaos_next_use.h:130`), with `chaos_next_use_companion_pick()`
non-null. This is the upper bound on what checking at the whistle would admit.
Excluded twin games count as no.

| start | program-1 refusals, no companion in view | games | games with a later whistle in the 100-move lifetime and a qualifying companion in view |
|---|---|---|---|
| bard-default-path | 40 | 40 | 6 |
| bard | 37 | 37 | 5 |
| bard-inherited | 31 | 31 | 11 |
| madman | 1 | 1 | 0 |
| wizard-default-path | 0 | 0 | 0 |

## 5. Levers

Measured counts first, then a **separately labelled estimate** of the gate
effect (`estimate.py`). Estimate assumptions:

* A lever adds at most one newly felt program per game.
* Part 1 gains a game only where it had exactly 1 distinct felt whisper;
  part 3 gains only where exactly 1 program was felt.
* Each newly admitted or rescued program is felt with probability p, taken
  from this start:
  * budget: later felt / later admitted;
  * program-1 check: program-1 felt / admitted;
  * origin: later delivered callbacks / later callbacks;
  * blocked callbacks: p = 1, an upper bound that also discards the
    attribution rule above.

**bard-default-path** (gate now: part 1 6 of 10, part 3 1 of 3)

| lever | measured: programs affected | estimate: part 1 gain | estimate: part 3 gain | p |
|---|---|---|---|---|
| budget +1 | 38 of 38 refused later programs admitted (33 games) | 1.5 | 0.6 | 0.161 |
| program-1 whistle-time check (upper bound) | 6 games of 40 refused | 0.0 | 0.4 | 0.432 |
| blocked callbacks (upper bound) | 5 later programs blocked, never delivered (33 blocked callbacks, all programs) | 1.0 | 3.0 | 1 |
| origin deadline | 2 of 23 origin-expired programs had a companion-in-view whistle after the deadline | 0.2 | 0.2 | 0.25 |

**bard** (gate now: part 1 13 of 10, part 3 6 of 3)

| lever | measured: programs affected | estimate: part 1 gain | estimate: part 3 gain | p |
|---|---|---|---|---|
| budget +1 | 9 of 9 refused later programs admitted (9 games) | 0.9 | 0.2 | 0.232 |
| program-1 whistle-time check (upper bound) | 5 games of 37 refused | 0.0 | 0.0 | 0.548 |
| blocked callbacks (upper bound) | 8 later programs blocked, never delivered (31 blocked callbacks, all programs) | 2.0 | 4.0 | 1 |
| origin deadline | 5 of 43 origin-expired programs had a companion-in-view whistle after the deadline | 0.9 | 0.9 | 0.464 |

**bard-inherited** (gate now: part 1 3 of 10, part 3 0 of 3)

| lever | measured: programs affected | estimate: part 1 gain | estimate: part 3 gain | p |
|---|---|---|---|---|
| budget +1 | 3 of 3 refused later programs admitted (2 games) | 0.3 | 0.0 | 0.312 |
| program-1 whistle-time check (upper bound) | 11 games of 31 refused | 0.5 | 0.5 | 0.233 |
| blocked callbacks (upper bound) | 2 later programs blocked, never delivered (21 blocked callbacks, all programs) | 2.0 | 1.0 | 1 |
| origin deadline | 3 of 10 origin-expired programs had a companion-in-view whistle after the deadline | 1.0 | 1.0 | 0.5 |

**Ranked by measured count on bard-default-path:**

1. budget, 38 programs (+1 admits all of them);
2. program-1 whistle-time check, 6 games;
3. blocked callbacks, 5 programs;
4. origin deadline, 2 programs.

**Recommendation: none.** No single lever can reach the gate. Part 1 needs +4
on bard-default-path. The largest estimate is budget +1 at about 1.5, and even
the p = 1 upper bound for blocked callbacks gives +1. Blocked callbacks would
lift part 3 to about 4, but only by crediting moves the ordinary whistle or an
item explains, which is exactly what the classifier exists to prevent. The
measured bottleneck sits after admission: whistles that land with a qualifying
companion visible and not already pulled. Of the 51 whistles inside the 23
origin-expired windows, 21 had a companion in view, and they fell in only 8
programs.

## Reproduce

```
# per-game copies or a sweep --work dir; from the repository root
python3 docs/measurements/arc-later-program-funnel/funnel.py PLAIN_RUNS DIAG_RUNS > funnel.json
python3 docs/measurements/arc-later-program-funnel/estimate.py funnel.json SWEEP_REPORT.json PLAIN_RUNS DIAG_RUNS > estimate.json
python3 docs/measurements/arc-later-program-funnel/tables.py funnel.json estimate.json
```

`funnel.json` and `estimate.json` here are those outputs. The sweep reports'
markdown summaries are in [`sweep/`](sweep/).
