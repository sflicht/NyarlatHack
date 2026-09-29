# Seed sweep funnel: baseline-v1, seeds 1-100

Engine stages only, from a scripted player (not an AI and not a human proxy).
Player notice, attribution and changed decisions are not measured (#44).

- Revision: `1e3c7af0e561802c7920c54a8467009678032911`; `dnethack` sha256 `754c9ee9ce43236e`
- Policy `baseline-v1`: `{"fountain_quaffs_per_level": 2, "max_commands": 8000, "max_dlvl": 5, "max_turns": 2000, "min_turns_per_level": 300, "no_food_retry_turns": 200, "p_fountain": 0.25, "p_search": 0.05, "p_travel_explore": 0.8, "p_whistle": 0.03, "prayer_gap_turns": 1000, "save_restore_turn": 700, "stall_commands": 200}`
- Command: `python3 scripts/seed_sweep.py --seeds 1-100 --policy baseline-v1 --starts bard,madman,bard-inherited --out <stem>`
- Report digest (sha256 of canonical JSON without this field): `a2ee03e4fa75d0649f0eb397e4c410de89904ba81a705ea2f3246ba2965411de`

Stages: qualifying history, engine candidate (schedule row), published envelope,
admitted, trigger (Lua callback ran), native effect (W armed or F remapped),
delivered (W witnessed or F remapped).

## bard (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 86, candidate 86, published 86, admitted 26, trigger 9, native_effect 9, delivered 5
- Stage totals: qualifying_history 1982, candidate 1794, published 86, admitted 26, trigger 9, native_effect 9, delivered 5
- Zero delivered effects: 95/100; delivery unknown (admitted, journal missing/incomplete/invalid): 0
- Loss reasons (first lost stage per game): rejected:level_mismatch+origin_expired+origin_superseded 27, rejected:level_mismatch+origin_superseded 18, no_qualifying_action 14, admitted_no_trigger:whistle_capture_suppressed 9, admitted_no_trigger:program_expired 5, delivered 5, rejected:origin_expired+origin_unbound 5, native_effect_not_delivered 4, inferred:no_safe_point_before_game_end 3, rejected:level_mismatch+origin_expired 3, admitted_no_trigger:level_departure 2, rejected:level_mismatch 2, rejected:level_mismatch+origin_expired+origin_unbound 2, admitted_no_trigger:origin_expired 1
- First admission move: {'n': 26, 'min': 128, 'median': 904.0, 'max': 1101}
- Outcomes: depth_limit 2, died 61, stalled 3, turn_limit 34
- Last turn: {'n': 100, 'min': 9, 'median': 1599.5, 'max': 2043}; final Dlvl: {'n': 39, 'min': 1, 'median': 2, 'max': 5}
- Qualifying-action attempts: {'whistling': 1955, 'fountain_drink': 104}
- Save/restore: 87/87 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## bard-inherited (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 75, candidate 75, published 75, admitted 41, trigger 9, native_effect 9, delivered 4
- Stage totals: qualifying_history 788, candidate 772, published 75, admitted 41, trigger 9, native_effect 9, delivered 4
- Zero delivered effects: 90/100; delivery unknown (admitted, journal missing/incomplete/invalid): 6
- Loss reasons (first lost stage per game): no_qualifying_action 25, admitted_no_trigger:whistle_capture_suppressed 21, inferred:no_safe_point_before_game_end 16, rejected:level_mismatch+origin_expired+origin_superseded 8, admitted_trace_incomplete 6, rejected:level_mismatch+origin_superseded 6, native_effect_not_delivered 5, delivered 4, admitted_no_trigger:program_expired 3, admitted_no_trigger:level_departure 2, rejected:level_mismatch 1, rejected:level_mismatch+origin_expired+origin_unbound 1, rejected:origin_expired 1, rejected:origin_expired+origin_unbound 1
- First admission move: {'n': 41, 'min': 14, 'median': 185, 'max': 1290}
- Outcomes: died 93, harness_error 1, turn_limit 6
- Last turn: {'n': 100, 'min': 4, 'median': 402.5, 'max': 2009}; final Dlvl: {'n': 7, 'min': 1, 'median': 1, 'max': 2}
- Qualifying-action attempts: {'whistling': 777, 'fountain_drink': 49}
- Save/restore: 25/25 restored; nonzero exits 0; harness errors 1; director sync timeouts 0

## madman (100 games; start Sanity [75], budget [4])

- Games reaching each stage: qualifying_history 16, candidate 16, published 16, admitted 1, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 17, candidate 17, published 16, admitted 1, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 99/100; delivery unknown (admitted, journal missing/incomplete/invalid): 1
- Loss reasons (first lost stage per game): no_qualifying_action 84, rejected:level_mismatch 8, rejected:origin_expired+origin_unbound 3, rejected:level_mismatch+origin_expired 2, admitted_trace_incomplete 1, rejected:level_mismatch+origin_expired+origin_unbound 1, rejected:origin_unbound 1
- First admission move: {'n': 1, 'min': 8, 'median': 8, 'max': 8}
- Outcomes: died 96, harness_error 1, stalled 3
- Last turn: {'n': 100, 'min': 9, 'median': 1181.0, 'max': 1453}; final Dlvl: {'n': 4, 'min': 1, 'median': 1.0, 'max': 3}
- Qualifying-action attempts: {'whistling': 0, 'fountain_drink': 81}
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
