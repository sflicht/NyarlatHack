# Seed sweep funnel: baseline-v1, seeds 1-100

Engine stages only, from a scripted player (not an AI and not a human proxy).
Player notice, attribution and changed decisions are not measured (#44).

- Revision: `5b1420a93e521eb9fa8aa8378084fd0773a3d581`; `dnethack` sha256 `157189db7998c1a1`
- Policy `baseline-v1`: `{"fountain_quaffs_per_level": 2, "max_commands": 8000, "max_dlvl": 5, "max_turns": 2000, "min_turns_per_level": 300, "no_food_retry_turns": 200, "p_fountain": 0.25, "p_search": 0.05, "p_travel_explore": 0.8, "p_whistle": 0.03, "prayer_gap_turns": 1000, "save_restore_turn": 700, "stall_commands": 200}`
- Command: `python3 scripts/seed_sweep.py --seeds 1-100 --policy baseline-v1 --starts bard,madman,bard-inherited --out <stem>`
- Report digest (sha256 of canonical JSON without this field): `a761389ea07c1f5f3f1f0759daf7a2174660cb7c41cb418b7e67a3b3d27793be`

Stages: qualifying history, engine candidate (schedule row), published envelope,
admitted, trigger (Lua callback ran), native effect (W armed or F remapped),
delivered (W witnessed or F remapped).

## bard (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 86, candidate 86, published 86, admitted 0, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 1979, candidate 1791, published 86, admitted 0, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 100/100; delivery unknown (admitted, journal missing/incomplete/invalid): 0
- Loss reasons (first lost stage per game): inferred:no_safe_point_before_game_end 3, no_qualifying_action 14, rejected:level_mismatch+origin_expired 5, rejected:level_mismatch+origin_expired+origin_superseded 44, rejected:level_mismatch+origin_expired+origin_unbound 2, rejected:level_mismatch+origin_superseded 1, rejected:origin_expired+origin_superseded 25, rejected:origin_expired+origin_unbound 5, rejected:origin_superseded 1
- First admission move: None
- Outcomes: depth_limit 2, died 62, stalled 3, turn_limit 33
- Last turn: {'max': 2043, 'median': 1599.5, 'min': 9, 'n': 100}; final Dlvl: {'max': 5, 'median': 2.0, 'min': 1, 'n': 38}
- Qualifying-action attempts: {'fountain_drink': 104, 'whistling': 1952}
- Save/restore: 87/87 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## bard-inherited (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 75, candidate 75, published 75, admitted 4, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 787, candidate 772, published 75, admitted 4, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 98/100; delivery unknown (admitted, journal missing/incomplete/invalid): 2
- Loss reasons (first lost stage per game): admitted_no_trigger:origin_expired 1, admitted_no_trigger:whistle_capture_suppressed 1, admitted_trace_incomplete 2, inferred:no_safe_point_before_game_end 16, no_qualifying_action 25, rejected:level_mismatch+origin_expired 1, rejected:level_mismatch+origin_expired+origin_superseded 14, rejected:level_mismatch+origin_expired+origin_unbound 1, rejected:origin_expired 2, rejected:origin_expired+origin_superseded 27, rejected:origin_expired+origin_unbound 1, rejected:origin_superseded 9
- First admission move: {'max': 118, 'median': 34.0, 'min': 14, 'n': 4}
- Outcomes: died 93, harness_error 1, turn_limit 6
- Last turn: {'max': 2009, 'median': 402.5, 'min': 4, 'n': 100}; final Dlvl: {'max': 2, 'median': 1, 'min': 1, 'n': 7}
- Qualifying-action attempts: {'fountain_drink': 49, 'whistling': 776}
- Save/restore: 25/25 restored; nonzero exits 0; harness errors 1; director sync timeouts 0

## madman (100 games; start Sanity [75], budget [4])

- Games reaching each stage: qualifying_history 16, candidate 16, published 16, admitted 1, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 17, candidate 17, published 16, admitted 1, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 99/100; delivery unknown (admitted, journal missing/incomplete/invalid): 1
- Loss reasons (first lost stage per game): admitted_trace_incomplete 1, no_qualifying_action 84, rejected:level_mismatch 2, rejected:level_mismatch+origin_expired 8, rejected:level_mismatch+origin_expired+origin_unbound 1, rejected:origin_expired+origin_unbound 4
- First admission move: {'max': 8, 'median': 8, 'min': 8, 'n': 1}
- Outcomes: died 96, harness_error 1, stalled 3
- Last turn: {'max': 1453, 'median': 1181.0, 'min': 9, 'n': 100}; final Dlvl: {'max': 3, 'median': 1.0, 'min': 1, 'n': 4}
- Qualifying-action attempts: {'fountain_drink': 81, 'whistling': 0}
- Save/restore: 84/84 restored; nonzero exits 0; harness errors 1; director sync timeouts 0

## Limits

- One simple fixed policy. Numbers describe this policy, not human play.
- `rejected:` loss reasons are the engine's recorded decision row (every failing
  check, #177). Reasons marked `inferred:` are guesses from public event timing
  (`turn`, not monstermoves), used only where the engine wrote no decision row.
- `whistle_capture_suppressed`: admitted, but the engine skipped the callback
  because there was not exactly one eligible target (by design).
- A single one-shot next-use program per game (the launcher's current design).
- The inherited start fixes one artifact (Vampire Killer); others are untested.
- In-game mail is off (`!mail`): it reads the host mail spool, not the seed.
