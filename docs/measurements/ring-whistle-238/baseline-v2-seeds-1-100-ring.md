# Seed sweep funnel: baseline-v2, seeds 1-100

Engine stages only, from a scripted player (not an AI and not a human proxy).
Player notice, attribution and changed decisions are not measured (#44).

- Revision: `29349da082eecb669c79f5555209051c5a35e08e`; `dnethack` sha256 `f1d02df7a059d2f1`
- Policy `baseline-v2`: `{"flee_in_trouble": true, "fountain_quaffs_per_level": 2, "max_commands": 8000, "max_dlvl": 5, "max_turns": 2000, "min_prayer_turn": 100, "min_turns_per_level": 300, "no_food_retry_turns": 200, "p_fountain": 0.25, "p_fountain_no_whistle": 1.0, "p_search": 0.05, "p_seek_tool": 0.5, "p_travel_explore": 0.8, "p_whistle": 0.03, "prayer_gap_turns": 1000, "rest_below": 0.67, "rest_command": "20s", "save_restore_turn": 700, "settle_pages": 400, "stall_commands": 200, "travel_retries": 3, "version": 2}`
- Command: `python3 scripts/seed_sweep.py --seeds 1-100 --policy baseline-v2 --starts bard,madman,bard-inherited,bard-default-path,wizard-default-path --out <stem>`
- Report digest (sha256 of canonical JSON without this field): `b1ae7d636db5875419c4f7ef31d7c28fd2171214fbf6e64a591ff07804cf94d7`

Stages: qualifying history, engine candidate (schedule row), published envelope,
admitted, trigger (Lua callback ran), native effect (W armed or F remapped),
delivered (W witnessed or F remapped).

## bard (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 88, candidate 88, published 88, admitted 79, trigger 61, native_effect 60, delivered 60
- Stage totals: qualifying_history 1787, candidate 1723, published 216, admitted 137, trigger 207, native_effect 159, delivered 159
- Zero delivered effects: 38/100; delivery unknown (admitted, journal missing/incomplete/invalid): 7
- Loss reasons (first lost stage per game): delivered 53, admitted_no_trigger:program_expired 19, no_qualifying_action 12, admitted_no_trigger:origin_expired 3, inferred:no_safe_point_before_game_end 3, rejected:origin_expired+origin_unbound 3, admitted_trace_missing 2, rejected:origin_expired 2, admitted_trace_incomplete 1, rejected:origin_expired+origin_superseded 1, trigger_no_native_effect 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
- First admission move: {'n': 77, 'min': 43, 'median': 404, 'max': 1182}
- Outcomes: depth_limit 4, died 56, harness_error 2, turn_limit 38
- Last turn: {'n': 100, 'min': 19, 'median': 1688.5, 'max': 2023}; final Dlvl: {'n': 44, 'min': 1, 'median': 2.0, 'max': 5}
- First felt consequence (#179): 61/100 games; turn {'n': 61, 'min': 126, 'median': 500, 'max': 1922}; Dlvl {'n': 61, 'min': 1, 'median': 2, 'max': 3}; by kind {'hound': 0, 'next_use_W': 58, 'next_use_F': 0, 'door': 3, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.89, 'delivered': 1.033, 'hound_accepted': 0.0}; per level visited {'admitted': 0.623, 'delivered': 0.723, 'hound_accepted': 0.0} (153985 turns, 220 levels)
- Distinct felt whispers (arc metric): 2+ in 34/100 games, 2+ excluding the hound 34/100; raw 2+ felt events 45/100; per game {0: 39, 1: 27, 2: 20, 3: 9, 4: 5}; sources by kind {'hound': 0, 'next_use': 98, 'door': 16, 'hunger': 0}; games by kind {'hound': 0, 'next_use': 60, 'door': 16, 'hunger': 0}
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 114, 'flees': 293, 'rests': 867, 'whistles_found': 1}; games holding a whistle: 86
- Qualifying-action attempts: {'whistling': 1754, 'fountain_drink': 91}
- Save/restore: 91/91 restored; nonzero exits 0; harness errors 2; director sync timeouts 0

## bard-default-path (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 87, candidate 87, published 87, admitted 75, trigger 57, native_effect 55, delivered 55
- Stage totals: qualifying_history 1875, candidate 1807, published 213, admitted 106, trigger 135, native_effect 112, delivered 112
- Zero delivered effects: 44/100; delivery unknown (admitted, journal missing/incomplete/invalid): 4
- Loss reasons (first lost stage per game): delivered 47, admitted_no_trigger:program_expired 18, no_qualifying_action 13, rejected:budget 9, admitted_trace_missing 5, admitted_no_trigger:origin_expired 3, rejected:origin_expired+origin_unbound 3, trigger_no_native_effect 2
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
- First admission move: {'n': 70, 'min': 26, 'median': 400.5, 'max': 1221}
- Outcomes: depth_limit 1, died 58, harness_error 1, turn_limit 40
- Last turn: {'n': 100, 'min': 425, 'median': 1667.5, 'max': 2031}; final Dlvl: {'n': 41, 'min': 1, 'median': 2, 'max': 5}
- First felt consequence (#179): 88/100 games; turn {'n': 88, 'min': 5, 'median': 16.0, 'max': 1273}; Dlvl {'n': 88, 'min': 1, 'median': 1.0, 'max': 3}; by kind {'hound': 77, 'next_use_W': 9, 'next_use_F': 0, 'door': 2, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.669, 'delivered': 0.707, 'hound_accepted': 0.555}; per level visited {'admitted': 0.477, 'delivered': 0.505, 'hound_accepted': 0.396} (158472 turns, 222 levels)
- Distinct felt whispers (arc metric): 2+ in 55/100 games, 2+ excluding the hound 24/100; raw 2+ felt events 79/100; per game {0: 12, 1: 33, 2: 34, 3: 16, 4: 5}; sources by kind {'hound': 77, 'next_use': 73, 'door': 19, 'hunger': 0}; games by kind {'hound': 77, 'next_use': 55, 'door': 19, 'hunger': 0}
- Hound: accepted in 88 games, 196 visible steps
- Policy v2 actions: {'prayers': 119, 'flees': 204, 'rests': 588, 'whistles_found': 0}; games holding a whistle: 85
- Qualifying-action attempts: {'whistling': 1846, 'fountain_drink': 87}
- Save/restore: 95/96 restored; nonzero exits 1; harness errors 1; director sync timeouts 0

## bard-inherited (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 75, candidate 75, published 75, admitted 61, trigger 44, native_effect 36, delivered 36
- Stage totals: qualifying_history 676, candidate 675, published 130, admitted 75, trigger 80, native_effect 57, delivered 57
- Zero delivered effects: 57/100; delivery unknown (admitted, journal missing/incomplete/invalid): 10
- Loss reasons (first lost stage per game): delivered 34, no_qualifying_action 25, admitted_no_trigger:program_expired 17, inferred:no_safe_point_before_game_end 12, admitted_trace_incomplete 5, trigger_no_native_effect 4, admitted_trace_missing 1, rejected:origin_expired 1, rejected:origin_expired+origin_superseded 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
- First admission move: {'n': 60, 'min': 53, 'median': 239.5, 'max': 1311}
- Outcomes: depth_limit 1, died 91, harness_error 1, turn_limit 7
- Last turn: {'n': 100, 'min': 5, 'median': 488.5, 'max': 2023}; final Dlvl: {'n': 8, 'min': 1, 'median': 1.0, 'max': 5}
- First felt consequence (#179): 37/100 games; turn {'n': 37, 'min': 110, 'median': 347, 'max': 1402}; Dlvl {'n': 37, 'min': 1, 'median': 1, 'max': 2}; by kind {'hound': 0, 'next_use_W': 36, 'next_use_F': 0, 'door': 1, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 1.224, 'delivered': 0.93, 'hound_accepted': 0.0}; per level visited {'admitted': 0.577, 'delivered': 0.438, 'hound_accepted': 0.0} (61296 turns, 130 levels)
- Distinct felt whispers (arc metric): 2+ in 5/100 games, 2+ excluding the hound 5/100; raw 2+ felt events 19/100; per game {0: 63, 1: 32, 2: 5}; sources by kind {'hound': 0, 'next_use': 39, 'door': 3, 'hunger': 0}; games by kind {'hound': 0, 'next_use': 36, 'door': 3, 'hunger': 0}
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 82, 'flees': 353, 'rests': 676, 'whistles_found': 0}; games holding a whistle: 85
- Qualifying-action attempts: {'whistling': 661, 'fountain_drink': 43}
- Save/restore: 31/32 restored; nonzero exits 1; harness errors 1; director sync timeouts 0

## madman (100 games; start Sanity [75], budget [3])

- Games reaching each stage: qualifying_history 18, candidate 18, published 18, admitted 8, trigger 1, native_effect 0, delivered 0
- Stage totals: qualifying_history 26, candidate 26, published 21, admitted 8, trigger 1, native_effect 0, delivered 0
- Zero delivered effects: 98/100; delivery unknown (admitted, journal missing/incomplete/invalid): 2
- Loss reasons (first lost stage per game): no_qualifying_action 82, rejected:origin_expired+origin_unbound 5, admitted_no_trigger:program_expired 4, rejected:origin_expired 3, admitted_trace_incomplete 2, admitted_no_trigger:origin_expired 1, inferred:no_safe_point_before_game_end 1, rejected:budget 1, trigger_no_native_effect 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
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

- Games reaching each stage: qualifying_history 21, candidate 21, published 21, admitted 4, trigger 1, native_effect 1, delivered 1
- Stage totals: qualifying_history 34, candidate 34, published 26, admitted 5, trigger 3, native_effect 3, delivered 3
- Zero delivered effects: 99/100; delivery unknown (admitted, journal missing/incomplete/invalid): 0
- Loss reasons (first lost stage per game): no_qualifying_action 79, rejected:origin_expired 10, inferred:no_safe_point_before_game_end 3, admitted_no_trigger:program_expired 2, rejected:budget 2, admitted_no_trigger:origin_expired 1, admitted_trace_missing 1, rejected:origin_expired+origin_unbound 1, rejected:origin_unbound 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
- First admission move: {'n': 3, 'min': 292, 'median': 616, 'max': 680}
- Outcomes: depth_limit 1, died 80, turn_limit 19
- Last turn: {'n': 100, 'min': 6, 'median': 1169.0, 'max': 2029}; final Dlvl: {'n': 20, 'min': 1, 'median': 2.0, 'max': 5}
- First felt consequence (#179): 79/100 games; turn {'n': 79, 'min': 5, 'median': 12, 'max': 1754}; Dlvl {'n': 79, 'min': 1, 'median': 1, 'max': 1}; by kind {'hound': 79, 'next_use_W': 0, 'next_use_F': 0, 'door': 0, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.04, 'delivered': 0.024, 'hound_accepted': 0.706}; per level visited {'admitted': 0.026, 'delivered': 0.016, 'hound_accepted': 0.466} (124578 turns, 189 levels)
- Distinct felt whispers (arc metric): 2+ in 11/100 games, 2+ excluding the hound 1/100; raw 2+ felt events 63/100; per game {0: 21, 1: 68, 2: 10, 3: 1}; sources by kind {'hound': 79, 'next_use': 2, 'door': 10, 'hunger': 0}; games by kind {'hound': 79, 'next_use': 1, 'door': 10, 'hunger': 0}
- Hound: accepted in 88 games, 210 visible steps
- Policy v2 actions: {'prayers': 119, 'flees': 143, 'rests': 366, 'whistles_found': 2}; games holding a whistle: 2
- Qualifying-action attempts: {'whistling': 11, 'fountain_drink': 87}
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
