# Seed sweep funnel: pet-visible-v1, seeds 1-100

Engine stages only, from a scripted player (not an AI and not a human proxy).
Player notice, attribution and changed decisions are not measured (#44).

- Revision: `dcd916621fceab71ea55cf6cbee901cb0ba8baf7`; `dnethack` sha256 `ecfb8593865a3888`
- Policy `pet-visible-v1`: `{"flee_in_trouble": true, "fountain_quaffs_per_level": 2, "max_commands": 8000, "max_dlvl": 5, "max_turns": 2000, "min_prayer_turn": 100, "min_turns_per_level": 300, "no_food_retry_turns": 200, "p_fountain": 0.25, "p_fountain_no_whistle": 1.0, "p_search": 0.05, "p_seek_tool": 0.5, "p_travel_explore": 0.8, "p_whistle": 0.03, "prayer_gap_turns": 1000, "rest_below": 0.67, "rest_command": "20s", "save_restore_turn": 700, "settle_pages": 400, "stall_commands": 200, "travel_retries": 3, "version": 2, "whistle_only_visible_pet": true}`
- Command: `python3 scripts/seed_sweep.py --seeds 1-100 --policy pet-visible-v1 --starts bard,madman,bard-inherited,bard-default-path,wizard-default-path --out <stem>`
- Report digest (sha256 of canonical JSON without this field): `74d61f72bba03029ed8c73ae19a64f4b5d973d63be33dbc6a4850e4d23ae7f0f`

Stages: qualifying history, engine candidate (schedule row), published envelope,
admitted, trigger (Lua callback ran), native effect (W armed or F remapped),
delivered (W witnessed or F remapped).

## bard (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 85, candidate 85, published 85, admitted 0, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 1374, candidate 1351, published 85, admitted 0, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 100/100; delivery unknown (admitted, journal missing/incomplete/invalid): 0
- Loss reasons (first lost stage per game): inferred:origin_superseded_before_safe_point 75, no_qualifying_action 15, inferred:level_changed_before_safe_point 6, inferred:rejected_at_safe_point_other 3, inferred:no_safe_point_before_game_end 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
- First admission move: None
- Outcomes: depth_limit 2, died 57, turn_limit 41
- Last turn: {'n': 100, 'min': 27, 'median': 1759.0, 'max': 2035}; final Dlvl: {'n': 43, 'min': 1, 'median': 2, 'max': 5}
- First felt consequence (#179): 23/100 games; turn {'n': 23, 'min': 428, 'median': 875, 'max': 1782}; Dlvl {'n': 23, 'min': 2, 'median': 2, 'max': 3}; by kind {'hound': 0, 'next_use_W': 0, 'next_use_F': 0, 'door': 23, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.0, 'delivered': 0.0, 'hound_accepted': 0.0}; per level visited {'admitted': 0.0, 'delivered': 0.0, 'hound_accepted': 0.0} (155239 turns, 223 levels)
- Distinct felt whispers (arc metric): 2+ in 1/100 games, 2+ excluding the hound 1/100; raw 2+ felt events 8/100; per game {0: 77, 1: 22, 3: 1}; sources by kind {'hound': 0, 'next_use': 0, 'door': 25, 'hunger': 0}; games by kind {'hound': 0, 'next_use': 0, 'door': 23, 'hunger': 0}
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 119, 'flees': 250, 'rests': 639, 'whistles_found': 0}; games holding a whistle: 85
- Qualifying-action attempts: {'whistling': 1339, 'fountain_drink': 92}
- Save/restore: 92/92 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## bard-default-path (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 85, candidate 85, published 85, admitted 0, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 1250, candidate 1249, published 85, admitted 0, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 100/100; delivery unknown (admitted, journal missing/incomplete/invalid): 0
- Loss reasons (first lost stage per game): inferred:origin_superseded_before_safe_point 73, no_qualifying_action 15, inferred:level_changed_before_safe_point 6, inferred:origin_expired_before_safe_point 3, inferred:no_safe_point_before_game_end 2, inferred:rejected_at_safe_point_other 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
- First admission move: None
- Outcomes: depth_limit 4, died 49, turn_limit 47
- Last turn: {'n': 100, 'min': 62, 'median': 1951.5, 'max': 2023}; final Dlvl: {'n': 51, 'min': 1, 'median': 2, 'max': 5}
- First felt consequence (#179): 73/100 games; turn {'n': 73, 'min': 5, 'median': 15, 'max': 994}; Dlvl {'n': 73, 'min': 1, 'median': 1, 'max': 4}; by kind {'hound': 70, 'next_use_W': 0, 'next_use_F': 0, 'door': 3, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.0, 'delivered': 0.0, 'hound_accepted': 0.515}; per level visited {'admitted': 0.0, 'delivered': 0.0, 'hound_accepted': 0.39} (164920 turns, 218 levels)
- Distinct felt whispers (arc metric): 2+ in 20/100 games, 2+ excluding the hound 1/100; raw 2+ felt events 66/100; per game {0: 27, 1: 53, 2: 20}; sources by kind {'hound': 70, 'next_use': 0, 'door': 23, 'hunger': 0}; games by kind {'hound': 70, 'next_use': 0, 'door': 22, 'hunger': 0}
- Hound: accepted in 85 games, 209 visible steps
- Policy v2 actions: {'prayers': 120, 'flees': 213, 'rests': 681, 'whistles_found': 0}; games holding a whistle: 85
- Qualifying-action attempts: {'whistling': 1213, 'fountain_drink': 102}
- Save/restore: 96/96 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## bard-inherited (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 75, candidate 75, published 75, admitted 0, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 594, candidate 584, published 75, admitted 0, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 100/100; delivery unknown (admitted, journal missing/incomplete/invalid): 0
- Loss reasons (first lost stage per game): inferred:origin_superseded_before_safe_point 49, no_qualifying_action 25, inferred:no_safe_point_before_game_end 17, inferred:rejected_at_safe_point_other 7, inferred:level_changed_before_safe_point 2
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
- First admission move: None
- Outcomes: died 96, turn_limit 4
- Last turn: {'n': 100, 'min': 5, 'median': 505.0, 'max': 2011}; final Dlvl: {'n': 4, 'min': 1, 'median': 1.0, 'max': 2}
- First felt consequence (#179): 4/100 games; turn {'n': 4, 'min': 389, 'median': 446.0, 'max': 772}; Dlvl {'n': 4, 'min': 2, 'median': 2.0, 'max': 3}; by kind {'hound': 0, 'next_use_W': 0, 'next_use_F': 0, 'door': 4, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.0, 'delivered': 0.0, 'hound_accepted': 0.0}; per level visited {'admitted': 0.0, 'delivered': 0.0, 'hound_accepted': 0.0} (61176 turns, 138 levels)
- Distinct felt whispers (arc metric): 2+ in 0/100 games, 2+ excluding the hound 0/100; raw 2+ felt events 4/100; per game {0: 96, 1: 4}; sources by kind {'hound': 0, 'next_use': 0, 'door': 4, 'hunger': 0}; games by kind {'hound': 0, 'next_use': 0, 'door': 4, 'hunger': 0}
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 65, 'flees': 309, 'rests': 627, 'whistles_found': 0}; games holding a whistle: 85
- Qualifying-action attempts: {'whistling': 578, 'fountain_drink': 53}
- Save/restore: 35/35 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## madman (100 games; start Sanity [75], budget [3])

- Games reaching each stage: qualifying_history 21, candidate 21, published 21, admitted 0, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 27, candidate 27, published 21, admitted 0, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 100/100; delivery unknown (admitted, journal missing/incomplete/invalid): 0
- Loss reasons (first lost stage per game): no_qualifying_action 79, inferred:level_changed_before_safe_point 6, inferred:rejected_at_safe_point_other 5, inferred:origin_expired_before_safe_point 4, inferred:origin_superseded_before_safe_point 4, inferred:budget 1, inferred:no_safe_point_before_game_end 1
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
- First admission move: None
- Outcomes: died 100
- Last turn: {'n': 100, 'min': 8, 'median': 1073.5, 'max': 1444}; final Dlvl: None
- First felt consequence (#179): 7/100 games; turn {'n': 7, 'min': 696, 'median': 743, 'max': 793}; Dlvl {'n': 7, 'min': 2, 'median': 3, 'max': 3}; by kind {'hound': 0, 'next_use_W': 0, 'next_use_F': 0, 'door': 0, 'hunger': 7}
- Rates (#164): per 1000 turns {'admitted': 0.0, 'delivered': 0.0, 'hound_accepted': 0.0}; per level visited {'admitted': 0.0, 'delivered': 0.0, 'hound_accepted': 0.0} (101869 turns, 157 levels)
- Distinct felt whispers (arc metric): 2+ in 0/100 games, 2+ excluding the hound 0/100; raw 2+ felt events 0/100; per game {0: 93, 1: 7}; sources by kind {'hound': 0, 'next_use': 0, 'door': 0, 'hunger': 7}; games by kind {'hound': 0, 'next_use': 0, 'door': 0, 'hunger': 7}
- Hound: accepted in 0 games, 0 visible steps
- Policy v2 actions: {'prayers': 99, 'flees': 155, 'rests': 210, 'whistles_found': 1}; games holding a whistle: 1
- Qualifying-action attempts: {'whistling': 0, 'fountain_drink': 73}
- Save/restore: 84/84 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## wizard-default-path (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 27, candidate 27, published 27, admitted 0, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 35, candidate 35, published 27, admitted 0, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 100/100; delivery unknown (admitted, journal missing/incomplete/invalid): 0
- Loss reasons (first lost stage per game): no_qualifying_action 73, inferred:level_changed_before_safe_point 11, inferred:origin_expired_before_safe_point 7, inferred:no_safe_point_before_game_end 4, inferred:rejected_at_safe_point_other 3, inferred:origin_superseded_before_safe_point 2
- W capture suppressions by recorded reason: none
- Safe-point refusals for no companion in view: 0 decisions in 0 games
- First admission move: None
- Outcomes: depth_limit 4, died 75, turn_limit 21
- Last turn: {'n': 100, 'min': 6, 'median': 1161.0, 'max': 2033}; final Dlvl: {'n': 25, 'min': 1, 'median': 2, 'max': 5}
- First felt consequence (#179): 82/100 games; turn {'n': 82, 'min': 5, 'median': 12.0, 'max': 1445}; Dlvl {'n': 82, 'min': 1, 'median': 1.0, 'max': 4}; by kind {'hound': 80, 'next_use_W': 0, 'next_use_F': 0, 'door': 2, 'hunger': 0}
- Rates (#164): per 1000 turns {'admitted': 0.0, 'delivered': 0.0, 'hound_accepted': 0.695}; per level visited {'admitted': 0.0, 'delivered': 0.0, 'hound_accepted': 0.434} (128088 turns, 205 levels)
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
