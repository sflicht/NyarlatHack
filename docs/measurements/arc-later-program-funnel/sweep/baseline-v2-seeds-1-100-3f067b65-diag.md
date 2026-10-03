# Seed sweep funnel: baseline-v2, seeds 1-100

Engine stages only, from a scripted player (not an AI and not a human proxy).
Player notice, attribution and changed decisions are not measured (#44).

- Revision: `3f067b65f1325b507069e2253bfbdf120747ed06`; `dnethack` sha256 `1f6174f7c211d2bd`
- Policy `baseline-v2`: `{"flee_in_trouble": true, "fountain_quaffs_per_level": 2, "max_commands": 8000, "max_dlvl": 5, "max_turns": 2000, "min_prayer_turn": 100, "min_turns_per_level": 300, "no_food_retry_turns": 200, "p_fountain": 0.25, "p_fountain_no_whistle": 1.0, "p_search": 0.05, "p_seek_tool": 0.5, "p_travel_explore": 0.8, "p_whistle": 0.03, "prayer_gap_turns": 1000, "rest_below": 0.67, "rest_command": "20s", "save_restore_turn": 700, "settle_pages": 400, "stall_commands": 200, "travel_retries": 3, "version": 2}`
- Command: `python3 scripts/seed_sweep.py --seeds 1-100 --policy baseline-v2 --starts bard,madman,bard-inherited,bard-default-path,wizard-default-path --out <stem>`
- Report digest (sha256 of canonical JSON without this field): `82b3ff23ed27d9f23d0beb232f68a5462c90d5a87b3bafccc077930017ab29e8`

Stages: qualifying history, engine candidate (schedule row), published envelope,
admitted, trigger (Lua callback ran), native effect (W armed or F remapped),
delivered (W witnessed or F remapped).

## bard (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 88, candidate 88, published 88, admitted 69, trigger 29, native_effect 29, delivered 21
- Stage totals: qualifying_history 1779, candidate 1716, published 210, admitted 98, trigger 70, native_effect 70, delivered 36
- Zero delivered effects: 71/100; delivery unknown (admitted, journal missing/incomplete/invalid): 10
- Loss reasons (first lost stage per game): admitted_trace_missing 27, delivered 18, admitted_no_trigger:program_expired 15, no_qualifying_action 12, rejected:no_companion_in_view 8, native_effect_not_delivered 5, admitted_no_trigger:origin_expired 3, inferred:no_safe_point_before_game_end 3, rejected:origin_expired 2, rejected:origin_expired+origin_unbound 2, admitted_trace_incomplete 1, rejected:budget 1, rejected:missed_index 1, rejected:origin_expired+origin_superseded 1, rejected:origin_expired+origin_unbound+no_companion_in_view 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 37 decisions in 37 games
- First admission move: {'n': 42, 'min': 118, 'median': 431.0, 'max': 1134}
- Outcomes: depth_limit 4, died 52, harness_error 3, turn_limit 41
- Last turn: {'n': 100, 'min': 19, 'median': 1822.0, 'max': 2039}; final Dlvl: {'n': 47, 'min': 1, 'median': 2, 'max': 5}
- First felt consequence (#179): 36/100 games; turn {'n': 36, 'min': 200, 'median': 746.5, 'max': 1927}; Dlvl {'n': 36, 'min': 1, 'median': 2.0, 'max': 3}; by kind {'hound': 0, 'next_use_W': 24, 'next_use_F': 0, 'door': 12, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.623, 'delivered': 0.229, 'hound_accepted': 0.0}; per level visited {'admitted': 0.452, 'delivered': 0.166, 'hound_accepted': 0.0} (157247 turns, 217 levels)
- Distinct felt whispers (arc metric): 2+ in 13/100 games, 2+ excluding the hound 13/100; raw 2+ felt events 24/100; per game {0: 64, 1: 23, 2: 9, 3: 2, 4: 2}; sources by kind {'hound': 0, 'next_use': 36, 'door': 19, 'hunger': 0}; games by kind {'hound': 0, 'next_use': 24, 'door': 19, 'hunger': 0}
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 115, 'flees': 219, 'rests': 703, 'whistles_found': 1}; games holding a whistle: 86
- Qualifying-action attempts: {'whistling': 1746, 'fountain_drink': 93}
- Save/restore: 90/91 restored; nonzero exits 1; harness errors 3; director sync timeouts 0

## bard-default-path (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 87, candidate 87, published 87, admitted 59, trigger 28, native_effect 27, delivered 16
- Stage totals: qualifying_history 1889, candidate 1814, published 213, admitted 68, trigger 58, native_effect 56, delivered 21
- Zero delivered effects: 78/100; delivery unknown (admitted, journal missing/incomplete/invalid): 7
- Loss reasons (first lost stage per game): admitted_trace_missing 22, rejected:budget 16, delivered 13, no_qualifying_action 13, admitted_no_trigger:program_expired 12, native_effect_not_delivered 9, rejected:no_companion_in_view 5, admitted_no_trigger:origin_expired 2, rejected:missed_index 2, rejected:origin_expired+origin_superseded 2, rejected:origin_expired+origin_unbound 2, rejected:origin_expired+origin_unbound+no_companion_in_view 1, trigger_no_native_effect 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 40 decisions in 40 games
- First admission move: {'n': 37, 'min': 26, 'median': 460, 'max': 1221}
- Outcomes: depth_limit 4, died 57, turn_limit 39
- Last turn: {'n': 100, 'min': 507, 'median': 1698.0, 'max': 2033}; final Dlvl: {'n': 43, 'min': 1, 'median': 2, 'max': 5}
- First felt consequence (#179): 82/100 games; turn {'n': 82, 'min': 5, 'median': 15.0, 'max': 1255}; Dlvl {'n': 82, 'min': 1, 'median': 1.0, 'max': 3}; by kind {'hound': 77, 'next_use_W': 2, 'next_use_F': 0, 'door': 3, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.43, 'delivered': 0.133, 'hound_accepted': 0.557}; per level visited {'admitted': 0.308, 'delivered': 0.095, 'hound_accepted': 0.398} (158058 turns, 221 levels)
- Distinct felt whispers (arc metric): 2+ in 28/100 games, 2+ excluding the hound 6/100; raw 2+ felt events 71/100; per game {0: 18, 1: 54, 2: 23, 3: 4, 4: 1}; sources by kind {'hound': 77, 'next_use': 23, 'door': 16, 'hunger': 0}; games by kind {'hound': 77, 'next_use': 17, 'door': 15, 'hunger': 0}
- Hound: accepted in 88 games, 196 visible steps
- Policy v2 actions: {'prayers': 113, 'flees': 239, 'rests': 644, 'whistles_found': 0}; games holding a whistle: 85
- Qualifying-action attempts: {'whistling': 1866, 'fountain_drink': 90}
- Save/restore: 96/96 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## bard-inherited (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 75, candidate 75, published 75, admitted 40, trigger 22, native_effect 22, delivered 11
- Stage totals: qualifying_history 674, candidate 673, published 139, admitted 46, trigger 35, native_effect 35, delivered 12
- Zero delivered effects: 82/100; delivery unknown (admitted, journal missing/incomplete/invalid): 7
- Loss reasons (first lost stage per game): no_qualifying_action 25, rejected:no_companion_in_view 18, inferred:no_safe_point_before_game_end 12, admitted_no_trigger:program_expired 10, admitted_trace_missing 10, native_effect_not_delivered 10, delivered 7, admitted_trace_incomplete 3, rejected:origin_expired+origin_superseded 3, rejected:origin_expired 2
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 31 decisions in 31 games
- First admission move: {'n': 30, 'min': 100, 'median': 287.0, 'max': 1311}
- Outcomes: depth_limit 1, died 92, turn_limit 7
- Last turn: {'n': 100, 'min': 5, 'median': 475.0, 'max': 2014}; final Dlvl: {'n': 8, 'min': 1, 'median': 1.0, 'max': 5}
- First felt consequence (#179): 14/100 games; turn {'n': 14, 'min': 115, 'median': 398.5, 'max': 1198}; Dlvl {'n': 14, 'min': 1, 'median': 1.5, 'max': 2}; by kind {'hound': 0, 'next_use_W': 13, 'next_use_F': 0, 'door': 1, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.704, 'delivered': 0.184, 'hound_accepted': 0.0}; per level visited {'admitted': 0.362, 'delivered': 0.094, 'hound_accepted': 0.0} (65359 turns, 127 levels)
- Distinct felt whispers (arc metric): 2+ in 3/100 games, 2+ excluding the hound 3/100; raw 2+ felt events 5/100; per game {0: 86, 1: 11, 2: 3}; sources by kind {'hound': 0, 'next_use': 16, 'door': 1, 'hunger': 0}; games by kind {'hound': 0, 'next_use': 13, 'door': 1, 'hunger': 0}
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 85, 'flees': 476, 'rests': 911, 'whistles_found': 0}; games holding a whistle: 85
- Qualifying-action attempts: {'whistling': 660, 'fountain_drink': 43}
- Save/restore: 41/41 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## madman (100 games; start Sanity [75], budget [3])

- Games reaching each stage: qualifying_history 18, candidate 18, published 18, admitted 8, trigger 1, native_effect 0, delivered 0
- Stage totals: qualifying_history 26, candidate 26, published 21, admitted 8, trigger 1, native_effect 0, delivered 0
- Zero delivered effects: 98/100; delivery unknown (admitted, journal missing/incomplete/invalid): 2
- Loss reasons (first lost stage per game): no_qualifying_action 82, admitted_no_trigger:program_expired 4, rejected:origin_expired+origin_unbound 4, rejected:origin_expired 3, admitted_trace_incomplete 2, admitted_no_trigger:origin_expired 1, inferred:no_safe_point_before_game_end 1, rejected:budget 1, rejected:origin_expired+origin_unbound+no_companion_in_view 1, trigger_no_native_effect 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 1 decisions in 1 games
- First admission move: {'n': 8, 'min': 111, 'median': 325.0, 'max': 347}
- Outcomes: died 100
- Last turn: {'n': 100, 'min': 8, 'median': 1105.0, 'max': 1423}; final Dlvl: None
- First felt consequence (#179): 5/100 games; turn {'n': 5, 'min': 703, 'median': 716, 'max': 771}; Dlvl {'n': 5, 'min': 3, 'median': 3, 'max': 3}; by kind {'hound': 0, 'next_use_W': 0, 'next_use_F': 0, 'door': 0, 'hunger': 5}
- Rates (#164): per 1000 turns {'admitted': 0.081, 'delivered': 0.0, 'hound_accepted': 0.0}; per level visited {'admitted': 0.051, 'delivered': 0.0, 'hound_accepted': 0.0} (98242 turns, 156 levels)
- Distinct felt whispers (arc metric): 2+ in 0/100 games, 2+ excluding the hound 0/100; raw 2+ felt events 0/100; per game {0: 95, 1: 5}; sources by kind {'hound': 0, 'next_use': 0, 'door': 0, 'hunger': 5}; games by kind {'hound': 0, 'next_use': 0, 'door': 0, 'hunger': 5}
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 101, 'flees': 224, 'rests': 177, 'whistles_found': 2}; games holding a whistle: 2
- Qualifying-action attempts: {'whistling': 4, 'fountain_drink': 66}
- Save/restore: 72/72 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## wizard-default-path (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 21, candidate 21, published 21, admitted 4, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 36, candidate 36, published 26, admitted 5, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 100/100; delivery unknown (admitted, journal missing/incomplete/invalid): 0
- Loss reasons (first lost stage per game): no_qualifying_action 79, rejected:origin_expired 10, inferred:no_safe_point_before_game_end 3, admitted_no_trigger:program_expired 2, rejected:budget 2, admitted_no_trigger:origin_expired 1, admitted_trace_missing 1, rejected:origin_expired+origin_unbound 1, rejected:origin_unbound 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
- First admission move: {'n': 3, 'min': 292, 'median': 616, 'max': 680}
- Outcomes: depth_limit 2, died 80, turn_limit 18
- Last turn: {'n': 100, 'min': 6, 'median': 1169.0, 'max': 2029}; final Dlvl: {'n': 20, 'min': 1, 'median': 2.0, 'max': 5}
- First felt consequence (#179): 79/100 games; turn {'n': 79, 'min': 5, 'median': 12, 'max': 1754}; Dlvl {'n': 79, 'min': 1, 'median': 1, 'max': 1}; by kind {'hound': 79, 'next_use_W': 0, 'next_use_F': 0, 'door': 0, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.04, 'delivered': 0.0, 'hound_accepted': 0.711}; per level visited {'admitted': 0.026, 'delivered': 0.0, 'hound_accepted': 0.466} (123852 turns, 189 levels)
- Distinct felt whispers (arc metric): 2+ in 11/100 games, 2+ excluding the hound 0/100; raw 2+ felt events 63/100; per game {0: 21, 1: 68, 2: 11}; sources by kind {'hound': 79, 'next_use': 0, 'door': 11, 'hunger': 0}; games by kind {'hound': 79, 'next_use': 0, 'door': 11, 'hunger': 0}
- Hound: accepted in 88 games, 210 visible steps
- Policy v2 actions: {'prayers': 118, 'flees': 142, 'rests': 361, 'whistles_found': 2}; games holding a whistle: 2
- Qualifying-action attempts: {'whistling': 13, 'fountain_drink': 89}
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
- Sequential M2 next-use, cap 3; each publication is final, not an admission.
- The inherited start fixes one artifact (Vampire Killer); others are untested.
- In-game mail is off (`!mail`): it reads the host mail spool, not the seed.
