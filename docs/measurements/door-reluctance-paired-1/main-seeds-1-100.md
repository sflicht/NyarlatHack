# Seed sweep funnel: baseline-v2, seeds 1-100

Engine stages only, from a scripted player (not an AI and not a human proxy).
Player notice, attribution and changed decisions are not measured (#44).

- Revision: `d29c4e2a25fcb91bd8baed1495c1e46f2b1df9c7`; `dnethack` sha256 `4da83fe3df074cdc`
- Policy `baseline-v2`: `{"flee_in_trouble": true, "fountain_quaffs_per_level": 2, "max_commands": 8000, "max_dlvl": 5, "max_turns": 2000, "min_prayer_turn": 100, "min_turns_per_level": 300, "no_food_retry_turns": 200, "p_fountain": 0.25, "p_fountain_no_whistle": 1.0, "p_search": 0.05, "p_seek_tool": 0.5, "p_travel_explore": 0.8, "p_whistle": 0.03, "prayer_gap_turns": 1000, "rest_below": 0.67, "rest_command": "20s", "save_restore_turn": 700, "settle_pages": 400, "stall_commands": 200, "travel_retries": 3, "version": 2}`
- Command: `python3 scripts/seed_sweep.py --seeds 1-100 --policy baseline-v2 --starts bard,madman,bard-inherited,bard-default-path,wizard-default-path --out <stem>`
- Report digest (sha256 of canonical JSON without this field): `e0423deea2ca959fa5199eb025b23c5341ccf9e89c51443eeb1e0efdb18ece6e`

Stages: qualifying history, engine candidate (schedule row), published envelope,
admitted, trigger (Lua callback ran), native effect (W armed or F remapped),
delivered (W witnessed or F remapped).

## bard (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 88, candidate 88, published 88, admitted 42, trigger 22, native_effect 22, delivered 14
- Stage totals: qualifying_history 1781, candidate 1715, published 88, admitted 42, trigger 22, native_effect 22, delivered 14
- Zero delivered effects: 85/100; delivery unknown (admitted, journal missing/incomplete/invalid): 1
- Loss reasons (first lost stage per game): rejected:no_companion_in_view 35, delivered 14, no_qualifying_action 12, admitted_no_trigger:program_expired 8, native_effect_not_delivered 8, admitted_no_trigger:whistle_capture_suppressed 5, admitted_no_trigger:level_departure 3, admitted_no_trigger:origin_expired 3, inferred:no_safe_point_before_game_end 3, rejected:origin_expired+origin_unbound 3, rejected:origin_expired 2, rejected:origin_expired+origin_unbound+no_companion_in_view 2, admitted_trace_incomplete 1, rejected:origin_expired+origin_superseded 1
- W capture suppressions by recorded reason: none_in_view 5
- Safe-point refusals for no companion in view: 37 decisions in 37 games
- First admission move: {'n': 42, 'min': 118, 'median': 431.0, 'max': 1134}
- Outcomes: depth_limit 2, died 55, harness_error 2, turn_limit 41
- Last turn: {'n': 100, 'min': 19, 'median': 1843.0, 'max': 2039}; final Dlvl: {'n': 45, 'min': 1, 'median': 2, 'max': 5}
- First felt consequence (#179): 17/100 games; turn {'n': 17, 'min': 200, 'median': 699, 'max': 1145}; Dlvl {'n': 17, 'min': 1, 'median': 2, 'max': 2}; by kind {'hound': 0, 'next_use_W': 17, 'next_use_F': 0}
- Rates (#164): per 1000 turns {'admitted': 0.267, 'delivered': 0.089, 'hound_accepted': 0.0}; per level visited {'admitted': 0.195, 'delivered': 0.065, 'hound_accepted': 0.0} (157054 turns, 215 levels)
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 115, 'flees': 244, 'rests': 699, 'whistles_found': 1}; games holding a whistle: 86
- Qualifying-action attempts: {'whistling': 1748, 'fountain_drink': 93}
- Save/restore: 91/91 restored; nonzero exits 0; harness errors 2; director sync timeouts 0

## bard-default-path (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 87, candidate 87, published 87, admitted 37, trigger 23, native_effect 22, delivered 10
- Stage totals: qualifying_history 1884, candidate 1809, published 87, admitted 37, trigger 23, native_effect 22, delivered 10
- Zero delivered effects: 90/100; delivery unknown (admitted, journal missing/incomplete/invalid): 0
- Loss reasons (first lost stage per game): rejected:no_companion_in_view 38, no_qualifying_action 13, native_effect_not_delivered 12, admitted_no_trigger:program_expired 10, delivered 10, rejected:budget 5, rejected:origin_expired+origin_unbound 4, admitted_no_trigger:origin_expired 2, rejected:origin_expired+origin_unbound+no_companion_in_view 2, admitted_no_trigger:level_departure 1, admitted_no_trigger:whistle_capture_suppressed 1, rejected:origin_expired 1, trigger_no_native_effect 1
- W capture suppressions by recorded reason: none_in_view 1
- Safe-point refusals for no companion in view: 40 decisions in 40 games
- First admission move: {'n': 37, 'min': 26, 'median': 460, 'max': 1221}
- Outcomes: depth_limit 4, died 59, turn_limit 37
- Last turn: {'n': 100, 'min': 507, 'median': 1651.0, 'max': 2033}; final Dlvl: {'n': 41, 'min': 1, 'median': 2, 'max': 5}
- First felt consequence (#179): 77/100 games; turn {'n': 77, 'min': 5, 'median': 15, 'max': 311}; Dlvl {'n': 77, 'min': 1, 'median': 1, 'max': 2}; by kind {'hound': 77, 'next_use_W': 0, 'next_use_F': 0}
- Rates (#164): per 1000 turns {'admitted': 0.236, 'delivered': 0.064, 'hound_accepted': 0.561}; per level visited {'admitted': 0.169, 'delivered': 0.046, 'hound_accepted': 0.402} (156850 turns, 219 levels)
- Hound: accepted in 88 games, 196 visible steps
- Policy v2 actions: {'prayers': 111, 'flees': 196, 'rests': 596, 'whistles_found': 0}; games holding a whistle: 85
- Qualifying-action attempts: {'whistling': 1862, 'fountain_drink': 84}
- Save/restore: 96/96 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## bard-inherited (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 75, candidate 75, published 75, admitted 30, trigger 15, native_effect 15, delivered 5
- Stage totals: qualifying_history 660, candidate 659, published 75, admitted 30, trigger 15, native_effect 15, delivered 5
- Zero delivered effects: 95/100; delivery unknown (admitted, journal missing/incomplete/invalid): 0
- Loss reasons (first lost stage per game): rejected:no_companion_in_view 30, no_qualifying_action 25, inferred:no_safe_point_before_game_end 12, native_effect_not_delivered 10, admitted_no_trigger:program_expired 6, admitted_no_trigger:whistle_capture_suppressed 6, delivered 5, admitted_no_trigger:level_departure 3, rejected:origin_expired 1, rejected:origin_expired+no_companion_in_view 1, rejected:origin_expired+origin_superseded 1
- W capture suppressions by recorded reason: none_in_view 6
- Safe-point refusals for no companion in view: 31 decisions in 31 games
- First admission move: {'n': 30, 'min': 100, 'median': 287.0, 'max': 1311}
- Outcomes: depth_limit 1, died 92, turn_limit 7
- Last turn: {'n': 100, 'min': 5, 'median': 475.0, 'max': 2014}; final Dlvl: {'n': 8, 'min': 1, 'median': 1.0, 'max': 5}
- First felt consequence (#179): 6/100 games; turn {'n': 6, 'min': 115, 'median': 366.0, 'max': 1198}; Dlvl {'n': 6, 'min': 1, 'median': 1.0, 'max': 2}; by kind {'hound': 0, 'next_use_W': 6, 'next_use_F': 0}
- Rates (#164): per 1000 turns {'admitted': 0.457, 'delivered': 0.076, 'hound_accepted': 0.0}; per level visited {'admitted': 0.236, 'delivered': 0.039, 'hound_accepted': 0.0} (65649 turns, 127 levels)
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 85, 'flees': 506, 'rests': 947, 'whistles_found': 0}; games holding a whistle: 85
- Qualifying-action attempts: {'whistling': 646, 'fountain_drink': 43}
- Save/restore: 41/41 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## madman (100 games; start Sanity [75], budget [3])

- Games reaching each stage: qualifying_history 19, candidate 19, published 19, admitted 10, trigger 1, native_effect 0, delivered 0
- Stage totals: qualifying_history 26, candidate 26, published 19, admitted 10, trigger 1, native_effect 0, delivered 0
- Zero delivered effects: 97/100; delivery unknown (admitted, journal missing/incomplete/invalid): 3
- Loss reasons (first lost stage per game): no_qualifying_action 81, admitted_no_trigger:program_expired 5, rejected:origin_expired+origin_unbound 4, admitted_trace_incomplete 3, rejected:origin_expired 3, admitted_no_trigger:origin_expired 1, inferred:no_safe_point_before_game_end 1, rejected:origin_expired+origin_unbound+no_companion_in_view 1, trigger_no_native_effect 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 1 decisions in 1 games
- First admission move: {'n': 10, 'min': 111, 'median': 335.5, 'max': 821}
- Outcomes: died 100
- Last turn: {'n': 100, 'min': 8, 'median': 1142.5, 'max': 1439}; final Dlvl: None
- First felt consequence (#179): 0/100 games; turn None; Dlvl None; by kind {'hound': 0, 'next_use_W': 0, 'next_use_F': 0}
- Rates (#164): per 1000 turns {'admitted': 0.1, 'delivered': 0.0, 'hound_accepted': 0.0}; per level visited {'admitted': 0.063, 'delivered': 0.0, 'hound_accepted': 0.0} (99525 turns, 158 levels)
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 101, 'flees': 249, 'rests': 185, 'whistles_found': 2}; games holding a whistle: 2
- Qualifying-action attempts: {'whistling': 3, 'fountain_drink': 67}
- Save/restore: 72/72 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## wizard-default-path (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 22, candidate 22, published 22, admitted 3, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 46, candidate 46, published 22, admitted 3, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 100/100; delivery unknown (admitted, journal missing/incomplete/invalid): 0
- Loss reasons (first lost stage per game): no_qualifying_action 78, rejected:origin_expired 11, inferred:no_safe_point_before_game_end 4, admitted_no_trigger:program_expired 2, rejected:budget 2, admitted_no_trigger:level_departure 1, rejected:origin_expired+origin_unbound 1, rejected:origin_unbound 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
- First admission move: {'n': 3, 'min': 292, 'median': 616, 'max': 680}
- Outcomes: depth_limit 2, died 81, turn_limit 17
- Last turn: {'n': 100, 'min': 6, 'median': 1165.5, 'max': 2029}; final Dlvl: {'n': 19, 'min': 1, 'median': 2, 'max': 5}
- First felt consequence (#179): 79/100 games; turn {'n': 79, 'min': 5, 'median': 12, 'max': 1754}; Dlvl {'n': 79, 'min': 1, 'median': 1, 'max': 1}; by kind {'hound': 79, 'next_use_W': 0, 'next_use_F': 0}
- Rates (#164): per 1000 turns {'admitted': 0.024, 'delivered': 0.0, 'hound_accepted': 0.713}; per level visited {'admitted': 0.016, 'delivered': 0.0, 'hound_accepted': 0.466} (123380 turns, 189 levels)
- Hound: accepted in 88 games, 210 visible steps
- Policy v2 actions: {'prayers': 118, 'flees': 158, 'rests': 366, 'whistles_found': 2}; games holding a whistle: 2
- Qualifying-action attempts: {'whistling': 21, 'fountain_drink': 89}
- Save/restore: 88/88 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## Limits

- One simple fixed policy. Numbers describe this policy, not human play.
- `rejected:` loss reasons are the engine's recorded decision row (every failing
  check, #177). Reasons marked `inferred:` are guesses from public event timing
  (`turn`, not monstermoves), used only where the engine wrote no decision row.
- `whistle_capture_suppressed`: admitted, but at the first whistle no qualifying
  companion was in view, so the engine skipped the callback (by design, #196).
  The recorded reason says whether none was in view, only ineligible ones were,
  or the chosen one stopped qualifying before capture.
- A single one-shot next-use program per game (the launcher's current design).
- The inherited start fixes one artifact (Vampire Killer); others are untested.
- In-game mail is off (`!mail`): it reads the host mail spool, not the seed.
