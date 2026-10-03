# Seed sweep funnel: pet-visible-v1, seeds 1-100

Engine stages only, from a scripted player (not an AI and not a human proxy).
Player notice, attribution and changed decisions are not measured (#44).

- Revision: `dcd916621fceab71ea55cf6cbee901cb0ba8baf7`; `dnethack` sha256 `b7e0130d2a26eef0`
- Policy `pet-visible-v1`: `{"flee_in_trouble": true, "fountain_quaffs_per_level": 2, "max_commands": 8000, "max_dlvl": 5, "max_turns": 2000, "min_prayer_turn": 100, "min_turns_per_level": 300, "no_food_retry_turns": 200, "p_fountain": 0.25, "p_fountain_no_whistle": 1.0, "p_search": 0.05, "p_seek_tool": 0.5, "p_travel_explore": 0.8, "p_whistle": 0.03, "prayer_gap_turns": 1000, "rest_below": 0.67, "rest_command": "20s", "save_restore_turn": 700, "settle_pages": 400, "stall_commands": 200, "travel_retries": 3, "version": 2, "whistle_only_visible_pet": true}`
- Command: `python3 scripts/seed_sweep.py --seeds 1-100 --policy pet-visible-v1 --starts bard,madman,bard-inherited,bard-default-path,wizard-default-path --out <stem>`
- Report digest (sha256 of canonical JSON without this field): `fe21a03c014b846469f4abadacd10929399d8c78b7d6968a6a5c14ca090cbde8`

Stages: qualifying history, engine candidate (schedule row), published envelope,
admitted, trigger (Lua callback ran), native effect (W armed or F remapped),
delivered (W witnessed or F remapped).

## bard (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 85, candidate 85, published 85, admitted 60, trigger 33, native_effect 33, delivered 20
- Stage totals: qualifying_history 1376, candidate 1353, published 171, admitted 84, trigger 78, native_effect 78, delivered 30
- Zero delivered effects: 72/100; delivery unknown (admitted, journal missing/incomplete/invalid): 10
- Loss reasons (first lost stage per game): rejected:no_companion_in_view 19, admitted_no_trigger:program_expired 17, delivered 15, no_qualifying_action 15, native_effect_not_delivered 13, admitted_trace_missing 11, admitted_no_trigger:origin_expired 3, rejected:origin_expired+origin_unbound+no_companion_in_view 2, admitted_trace_incomplete 1, inferred:no_safe_point_before_game_end 1, rejected:missed_index+origin_expired+origin_superseded 1, rejected:origin_expired 1, rejected:origin_expired+origin_unbound 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 30 decisions in 30 games
- First admission move: {'n': 49, 'min': 303, 'median': 518, 'max': 1125}
- Outcomes: depth_limit 2, died 54, harness_error 1, turn_limit 43
- Last turn: {'n': 100, 'min': 27, 'median': 1794.0, 'max': 2035}; final Dlvl: {'n': 45, 'min': 1, 'median': 2, 'max': 5}
- First felt consequence (#179): 43/100 games; turn {'n': 43, 'min': 316, 'median': 734, 'max': 1403}; Dlvl {'n': 43, 'min': 1, 'median': 2, 'max': 4}; by kind {'hound': 0, 'next_use_W': 25, 'next_use_F': 0, 'door': 18, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.539, 'delivered': 0.193, 'hound_accepted': 0.0}; per level visited {'admitted': 0.378, 'delivered': 0.135, 'hound_accepted': 0.0} (155703 turns, 222 levels)
- Distinct felt whispers (arc metric): 2+ in 8/100 games, 2+ excluding the hound 8/100; raw 2+ felt events 18/100; per game {0: 57, 1: 35, 2: 4, 3: 4}; sources by kind {'hound': 0, 'next_use': 31, 'door': 24, 'hunger': 0}; games by kind {'hound': 0, 'next_use': 26, 'door': 22, 'hunger': 0}
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 120, 'flees': 244, 'rests': 620, 'whistles_found': 0}; games holding a whistle: 85
- Qualifying-action attempts: {'whistling': 1340, 'fountain_drink': 93}
- Save/restore: 91/92 restored; nonzero exits 1; harness errors 1; director sync timeouts 0

## bard-default-path (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 85, candidate 85, published 85, admitted 47, trigger 23, native_effect 23, delivered 13
- Stage totals: qualifying_history 1258, candidate 1257, published 164, admitted 59, trigger 35, native_effect 35, delivered 16
- Zero delivered effects: 84/100; delivery unknown (admitted, journal missing/incomplete/invalid): 5
- Loss reasons (first lost stage per game): rejected:no_companion_in_view 19, admitted_no_trigger:program_expired 16, no_qualifying_action 15, admitted_trace_missing 12, delivered 9, rejected:budget 7, native_effect_not_delivered 6, admitted_no_trigger:origin_expired 4, rejected:origin_expired+origin_unbound 3, inferred:no_safe_point_before_game_end 2, rejected:origin_expired+origin_superseded 2, rejected:origin_expired+origin_unbound+no_companion_in_view 2, rejected:missed_index 1, rejected:origin_expired+no_companion_in_view 1, rejected:origin_expired+origin_superseded+no_companion_in_view 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 33 decisions in 33 games
- First admission move: {'n': 35, 'min': 256, 'median': 429, 'max': 1113}
- Outcomes: depth_limit 4, died 49, turn_limit 47
- Last turn: {'n': 100, 'min': 62, 'median': 1951.5, 'max': 2023}; final Dlvl: {'n': 51, 'min': 1, 'median': 2, 'max': 5}
- First felt consequence (#179): 76/100 games; turn {'n': 76, 'min': 5, 'median': 15.0, 'max': 1082}; Dlvl {'n': 76, 'min': 1, 'median': 1.0, 'max': 4}; by kind {'hound': 70, 'next_use_W': 3, 'next_use_F': 0, 'door': 3, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.355, 'delivered': 0.096, 'hound_accepted': 0.511}; per level visited {'admitted': 0.268, 'delivered': 0.073, 'hound_accepted': 0.386} (166204 turns, 220 levels)
- Distinct felt whispers (arc metric): 2+ in 29/100 games, 2+ excluding the hound 4/100; raw 2+ felt events 69/100; per game {0: 24, 1: 47, 2: 26, 3: 3}; sources by kind {'hound': 70, 'next_use': 18, 'door': 20, 'hunger': 0}; games by kind {'hound': 70, 'next_use': 16, 'door': 20, 'hunger': 0}
- Hound: accepted in 85 games, 209 visible steps
- Policy v2 actions: {'prayers': 120, 'flees': 202, 'rests': 670, 'whistles_found': 0}; games holding a whistle: 85
- Qualifying-action attempts: {'whistling': 1221, 'fountain_drink': 103}
- Save/restore: 96/96 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## bard-inherited (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 75, candidate 75, published 75, admitted 35, trigger 18, native_effect 18, delivered 10
- Stage totals: qualifying_history 606, candidate 596, published 112, admitted 47, trigger 34, native_effect 34, delivered 15
- Zero delivered effects: 80/100; delivery unknown (admitted, journal missing/incomplete/invalid): 10
- Loss reasons (first lost stage per game): no_qualifying_action 25, rejected:no_companion_in_view 21, inferred:no_safe_point_before_game_end 17, admitted_no_trigger:program_expired 12, delivered 9, native_effect_not_delivered 8, admitted_trace_missing 3, admitted_trace_incomplete 2, admitted_no_trigger:origin_expired 1, rejected:missed_index+origin_expired+origin_unbound 1, rejected:origin_expired+origin_unbound+no_companion_in_view 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 25 decisions in 25 games
- First admission move: {'n': 32, 'min': 100, 'median': 325.0, 'max': 1225}
- Outcomes: died 93, harness_error 1, turn_limit 6
- Last turn: {'n': 100, 'min': 5, 'median': 505.0, 'max': 2014}; final Dlvl: {'n': 6, 'min': 1, 'median': 1.0, 'max': 3}
- First felt consequence (#179): 12/100 games; turn {'n': 12, 'min': 211, 'median': 350.5, 'max': 1055}; Dlvl {'n': 12, 'min': 1, 'median': 1.0, 'max': 2}; by kind {'hound': 0, 'next_use_W': 10, 'next_use_F': 0, 'door': 2, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.754, 'delivered': 0.241, 'hound_accepted': 0.0}; per level visited {'admitted': 0.336, 'delivered': 0.107, 'hound_accepted': 0.0} (62320 turns, 140 levels)
- Distinct felt whispers (arc metric): 2+ in 6/100 games, 2+ excluding the hound 6/100; raw 2+ felt events 9/100; per game {0: 88, 1: 6, 2: 3, 3: 2, 4: 1}; sources by kind {'hound': 0, 'next_use': 17, 'door': 5, 'hunger': 0}; games by kind {'hound': 0, 'next_use': 11, 'door': 5, 'hunger': 0}
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 66, 'flees': 339, 'rests': 641, 'whistles_found': 0}; games holding a whistle: 85
- Qualifying-action attempts: {'whistling': 590, 'fountain_drink': 55}
- Save/restore: 34/35 restored; nonzero exits 1; harness errors 1; director sync timeouts 0

## madman (100 games; start Sanity [75], budget [3])

- Games reaching each stage: qualifying_history 21, candidate 21, published 21, admitted 6, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 27, candidate 27, published 23, admitted 6, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 98/100; delivery unknown (admitted, journal missing/incomplete/invalid): 2
- Loss reasons (first lost stage per game): no_qualifying_action 79, rejected:origin_expired+origin_unbound 6, rejected:budget 4, admitted_no_trigger:origin_expired 2, admitted_no_trigger:program_expired 2, admitted_trace_incomplete 2, rejected:origin_expired 2, inferred:no_safe_point_before_game_end 1, rejected:origin_expired+origin_superseded 1, rejected:origin_unbound 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
- First admission move: {'n': 6, 'min': 111, 'median': 260.5, 'max': 455}
- Outcomes: died 100
- Last turn: {'n': 100, 'min': 8, 'median': 1073.5, 'max': 1444}; final Dlvl: None
- First felt consequence (#179): 7/100 games; turn {'n': 7, 'min': 696, 'median': 743, 'max': 793}; Dlvl {'n': 7, 'min': 2, 'median': 3, 'max': 3}; by kind {'hound': 0, 'next_use_W': 0, 'next_use_F': 0, 'door': 0, 'hunger': 7}
- Rates (#164): per 1000 turns {'admitted': 0.059, 'delivered': 0.0, 'hound_accepted': 0.0}; per level visited {'admitted': 0.038, 'delivered': 0.0, 'hound_accepted': 0.0} (101902 turns, 157 levels)
- Distinct felt whispers (arc metric): 2+ in 0/100 games, 2+ excluding the hound 0/100; raw 2+ felt events 0/100; per game {0: 93, 1: 7}; sources by kind {'hound': 0, 'next_use': 0, 'door': 0, 'hunger': 7}; games by kind {'hound': 0, 'next_use': 0, 'door': 0, 'hunger': 7}
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 99, 'flees': 155, 'rests': 210, 'whistles_found': 1}; games holding a whistle: 1
- Qualifying-action attempts: {'whistling': 0, 'fountain_drink': 73}
- Save/restore: 84/84 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## wizard-default-path (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 27, candidate 27, published 27, admitted 7, trigger 2, native_effect 0, delivered 0
- Stage totals: qualifying_history 35, candidate 35, published 30, admitted 7, trigger 4, native_effect 0, delivered 0
- Zero delivered effects: 100/100; delivery unknown (admitted, journal missing/incomplete/invalid): 0
- Loss reasons (first lost stage per game): no_qualifying_action 73, rejected:origin_expired 12, admitted_no_trigger:program_expired 4, inferred:no_safe_point_before_game_end 4, rejected:origin_unbound 2, trigger_no_native_effect 2, admitted_no_trigger:origin_expired 1, rejected:budget 1, rejected:origin_expired+origin_unbound 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
- First admission move: {'n': 7, 'min': 174, 'median': 372, 'max': 675}
- Outcomes: depth_limit 4, died 75, turn_limit 21
- Last turn: {'n': 100, 'min': 6, 'median': 1161.0, 'max': 2033}; final Dlvl: {'n': 25, 'min': 1, 'median': 2, 'max': 5}
- First felt consequence (#179): 82/100 games; turn {'n': 82, 'min': 5, 'median': 12.0, 'max': 1445}; Dlvl {'n': 82, 'min': 1, 'median': 1.0, 'max': 4}; by kind {'hound': 80, 'next_use_W': 0, 'next_use_F': 0, 'door': 2, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.055, 'delivered': 0.0, 'hound_accepted': 0.695}; per level visited {'admitted': 0.034, 'delivered': 0.0, 'hound_accepted': 0.434} (128088 turns, 205 levels)
- Distinct felt whispers (arc metric): 2+ in 16/100 games, 2+ excluding the hound 0/100; raw 2+ felt events 68/100; per game {0: 18, 1: 66, 2: 16}; sources by kind {'hound': 80, 'next_use': 0, 'door': 18, 'hunger': 0}; games by kind {'hound': 80, 'next_use': 0, 'door': 18, 'hunger': 0}
- Hound: accepted in 89 games, 219 visible steps
- Policy v2 actions: {'prayers': 126, 'flees': 219, 'rests': 410, 'whistles_found': 2}; games holding a whistle: 2
- Qualifying-action attempts: {'whistling': 4, 'fountain_drink': 87}
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
