# Seed sweep funnel: baseline-v1, seeds 1-100

Engine stages only, from a scripted player (not an AI and not a human proxy).
Player notice, attribution and changed decisions are not measured (#44).

- Revision: `1c9fba80231f3957e8f58fd10e2bd96f9eb9ba42`; `dnethack` sha256 `789bf481d4496ab5`
- Policy `baseline-v1`: `{"fountain_quaffs_per_level": 2, "max_commands": 8000, "max_dlvl": 5, "max_turns": 2000, "min_turns_per_level": 300, "no_food_retry_turns": 200, "p_fountain": 0.25, "p_search": 0.05, "p_travel_explore": 0.8, "p_whistle": 0.03, "prayer_gap_turns": 1000, "save_restore_turn": 700, "stall_commands": 200}`
- Command: `python3 scripts/seed_sweep.py --seeds 1-100 --policy baseline-v1 --starts bard,madman,bard-inherited --out <stem>`
- Report digest (sha256 of canonical JSON without this field): `d863471ba5d4a66f480542711cff0568739fbe42bf92b9f1cfe888aac42ba2b3`

Stages: qualifying history, engine candidate (schedule row), published envelope,
admitted, trigger (Lua callback ran), native effect (W armed or F remapped),
delivered (W witnessed or F remapped).

## bard (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 86, candidate 86, published 86, admitted 0, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 1979, candidate 1791, published 86, admitted 0, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 100/100
- Loss reasons (first lost stage per game): level_changed_before_safe_point 52, origin_expired_before_safe_point 30, no_qualifying_action 14, no_safe_point_before_game_end 3, rejected_at_safe_point_other 1
- First admission move: None
- Outcomes: depth_limit 2, died 62, stalled 3, turn_limit 33
- Last turn: {'n': 100, 'min': 9, 'median': 1599.5, 'max': 2043}; final Dlvl: {'n': 38, 'min': 1, 'median': 2.0, 'max': 5}
- Qualifying-action attempts: {'whistling': 1952, 'fountain_drink': 104}
- Save/restore: 87/87 restored; nonzero exits 0; harness errors 0; director sync timeouts 0

## bard-inherited (100 games; start Sanity [100], budget [2])

- Games reaching each stage: qualifying_history 75, candidate 75, published 75, admitted 4, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 787, candidate 772, published 75, admitted 4, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 100/100
- Loss reasons (first lost stage per game): origin_expired_before_safe_point 30, no_qualifying_action 25, level_changed_before_safe_point 16, no_safe_point_before_game_end 16, rejected_at_safe_point_other 9, admitted_no_trigger:game_ended 2, admitted_no_trigger:completed 1, admitted_no_trigger:origin_expired 1
- First admission move: {'n': 4, 'min': 14, 'median': 34.0, 'max': 118}
- Outcomes: died 93, harness_error 1, turn_limit 6
- Last turn: {'n': 100, 'min': 4, 'median': 402.5, 'max': 2009}; final Dlvl: {'n': 7, 'min': 1, 'median': 1, 'max': 2}
- Qualifying-action attempts: {'whistling': 776, 'fountain_drink': 49}
- Save/restore: 25/25 restored; nonzero exits 0; harness errors 1; director sync timeouts 0

## madman (100 games; start Sanity [75], budget [4])

- Games reaching each stage: qualifying_history 16, candidate 16, published 16, admitted 1, trigger 0, native_effect 0, delivered 0
- Stage totals: qualifying_history 17, candidate 17, published 16, admitted 1, trigger 0, native_effect 0, delivered 0
- Zero delivered effects: 100/100
- Loss reasons (first lost stage per game): no_qualifying_action 84, level_changed_before_safe_point 11, origin_expired_before_safe_point 4, admitted_no_trigger:game_ended 1
- First admission move: {'n': 1, 'min': 8, 'median': 8, 'max': 8}
- Outcomes: died 96, harness_error 1, stalled 3
- Last turn: {'n': 100, 'min': 9, 'median': 1181.0, 'max': 1453}; final Dlvl: {'n': 4, 'min': 1, 'median': 1.0, 'max': 3}
- Qualifying-action attempts: {'whistling': 0, 'fountain_drink': 81}
- Save/restore: 84/84 restored; nonzero exits 0; harness errors 1; director sync timeouts 0

## Limits

- One simple fixed policy. Numbers describe this policy, not human play.
- The loss reason for a published-but-unadmitted envelope is inferred from public
  event timing (`turn`, not the engine's monstermoves).
- A single one-shot next-use program per game (the launcher's current design).
- The inherited start fixes one artifact (Vampire Killer); others are untested.
- In-game mail is off (`!mail`): it reads the host mail spool, not the seed.
