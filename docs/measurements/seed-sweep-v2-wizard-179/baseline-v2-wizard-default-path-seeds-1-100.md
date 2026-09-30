# Seed sweep funnel: baseline-v2, seeds 1-100

Engine stages only, from a scripted player (not an AI and not a human proxy).
Player notice, attribution and changed decisions are not measured (#44).

- Revision: `9579e3419c3ded0424b2f198acb1737c49b3b1d2`; `dnethack` sha256 `c0a81c6d590128b4`
- Policy `baseline-v2`: `{"flee_in_trouble": true, "fountain_quaffs_per_level": 2, "max_commands": 8000, "max_dlvl": 5, "max_turns": 2000, "min_prayer_turn": 100, "min_turns_per_level": 300, "no_food_retry_turns": 200, "p_fountain": 0.25, "p_fountain_no_whistle": 1.0, "p_search": 0.05, "p_seek_tool": 0.5, "p_travel_explore": 0.8, "p_whistle": 0.03, "prayer_gap_turns": 1000, "rest_below": 0.67, "rest_command": "20s", "save_restore_turn": 700, "settle_pages": 400, "stall_commands": 200, "travel_retries": 3, "version": 2}`
- Command: `python3 scripts/seed_sweep.py --seeds 1-100 --policy baseline-v2 --starts wizard-default-path --out <stem>`
- Report digest (sha256 of canonical JSON without this field): `7af38248f62d477e42cc539ddd323d1866ebf24e870f65f8470428bdc6a50973`

Stages: qualifying history, engine candidate (schedule row), published envelope,
admitted, trigger (Lua callback ran), native effect (W armed or F remapped),
delivered (W witnessed or F remapped).

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
