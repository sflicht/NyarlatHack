# Paired sweep: main (C attention) vs ring

- main: revision `3b89f6e2a25c7cd363d1e958e7f9ff5bce997163`, report sha256 `fad595f67bf858235e39c82f8b5ad55c26c66189f4f58eeaa8e10172cca51512`
- ring: revision `29349da082eecb669c79f5555209051c5a35e08e`, report sha256 `b1ae7d636db5875419c4f7ef31d7c28fd2171214fbf6e64a591ff07804cf94d7`

| start | games | part 1 main / ring | part 3 main / ring | proposal today / B estimate | games with a felt next-use program main / ring | delivered effects main / ring | admitted main / ring | felt W events main / ring | deaths main / ring | harness errors main / ring |
|---|---|---|---|---|---|---|---|---|---|---|
| bard-default-path | 100 | 6 / 24 | 1 / 16 | 6 / 1 → 12 / 4 | 16 / 55 | 21 / 112 | 68 / 106 | 27 / 112 | 57 / 58 | 0 / 1 |
| bard | 100 | 13 / 34 | 6 / 31 | 13 / 6 → 31 / 19 | 21 / 60 | 36 / 159 | 98 / 137 | 47 / 159 | 52 / 56 | 3 / 2 |
| bard-inherited | 100 | 3 / 5 | 0 / 3 | 3 / 0 → 6 / 2 | 11 / 36 | 12 / 57 | 46 / 75 | 18 / 57 | 92 / 91 | 0 / 1 |
| madman | 100 | 0 / 0 | 0 / 0 | – | 0 / 0 | 0 / 0 | 8 / 8 | 0 / 0 | 100 / 100 | 0 / 0 |
| wizard-default-path | 100 | 0 / 1 | 0 / 1 | – | 0 / 1 | 0 / 3 | 5 / 5 | 0 / 3 | 80 / 80 | 0 / 0 |

Hound admission by start (haunting event details summed over games; games with an accepted hound; visible steps):

| start | haunting details main | haunting details ring | games accepted main / ring | steps main / ring | seeds whose hound details differ |
|---|---|---|---|---|---|
| bard-default-path | `{'accepted': 88, 'expired': 88, 'pre_admitted': 88, 'rejected': 12}` | `{'accepted': 88, 'expired': 88, 'pre_admitted': 88, 'rejected': 12}` | 88 / 88 | 196 / 196 | none |
| bard | `{}` | `{}` | 0 / 0 | 0 / 0 | none |
| bard-inherited | `{}` | `{}` | 0 / 0 | 0 / 0 | none |
| madman | `{}` | `{}` | 0 / 0 | 0 / 0 | none |
| wizard-default-path | `{'accepted': 88, 'expired': 87, 'pre_admitted': 88, 'rejected': 11}` | `{'accepted': 88, 'expired': 87, 'pre_admitted': 88, 'rejected': 11}` | 88 / 88 | 210 / 210 | none |

HOUND_CHANGED_SEEDS=0

Final turn (status line T) by start, median main / ring:

- bard-default-path: median 1698.0 / 1667.5; total 158058 / 158472; seeds with a different final turn 53
- bard: median 1822.0 / 1688.5; total 157253 / 153985; seeds with a different final turn 60
- bard-inherited: median 475.0 / 488.5; total 65359 / 61296; seeds with a different final turn 35
- madman: median 1105.0 / 1105.0; total 98242 / 98242; seeds with a different final turn 0
- wizard-default-path: median 1169.0 / 1169.0; total 123852 / 124578; seeds with a different final turn 1

Outcome changes by start (main → ring, same seed):

- bard-default-path: same outcome 78/100; changed {('depth_limit', 'turn_limit'): 1, ('turn_limit', 'died'): 9, ('died', 'turn_limit'): 9, ('died', 'harness_error'): 1, ('depth_limit', 'died'): 2}; seeds [7, 8, 9, 11, 12, 25, 28, 29, 39, 41, 42, 46, 47, 58, 61, 64, 72, 74, 81, 89, 95, 99]
- bard: same outcome 78/100; changed {('depth_limit', 'died'): 4, ('harness_error', 'died'): 1, ('died', 'turn_limit'): 6, ('turn_limit', 'died'): 7, ('turn_limit', 'depth_limit'): 2, ('died', 'depth_limit'): 2}; seeds [5, 10, 21, 28, 30, 32, 36, 37, 43, 44, 55, 57, 60, 63, 64, 74, 77, 85, 89, 93, 95, 100]
- bard-inherited: same outcome 98/100; changed {('turn_limit', 'harness_error'): 1, ('died', 'turn_limit'): 1}; seeds [26, 36]
- madman: same outcome 100/100; changed none
- wizard-default-path: same outcome 99/100; changed {('depth_limit', 'turn_limit'): 1}; seeds [41]

<details><summary>bard-default-path main: loss reasons</summary>

`{"admitted_no_trigger:origin_expired": 2, "admitted_no_trigger:program_expired": 12, "admitted_trace_missing": 22, "delivered": 13, "native_effect_not_delivered": 9, "no_qualifying_action": 13, "rejected:budget": 16, "rejected:missed_index": 2, "rejected:no_companion_in_view": 5, "rejected:origin_expired+origin_superseded": 2, "rejected:origin_expired+origin_unbound": 2, "rejected:origin_expired+origin_unbound+no_companion_in_view": 1, "trigger_no_native_effect": 1}`

</details>

<details><summary>bard-default-path ring: loss reasons</summary>

`{"admitted_no_trigger:origin_expired": 3, "admitted_no_trigger:program_expired": 18, "admitted_trace_missing": 5, "delivered": 47, "no_qualifying_action": 13, "rejected:budget": 9, "rejected:origin_expired+origin_unbound": 3, "trigger_no_native_effect": 2}`

</details>

<details><summary>bard main: loss reasons</summary>

`{"admitted_no_trigger:origin_expired": 3, "admitted_no_trigger:program_expired": 15, "admitted_trace_incomplete": 1, "admitted_trace_missing": 27, "delivered": 18, "inferred:no_safe_point_before_game_end": 3, "native_effect_not_delivered": 5, "no_qualifying_action": 12, "rejected:budget": 1, "rejected:missed_index": 1, "rejected:no_companion_in_view": 8, "rejected:origin_expired": 2, "rejected:origin_expired+origin_superseded": 1, "rejected:origin_expired+origin_unbound": 2, "rejected:origin_expired+origin_unbound+no_companion_in_view": 1}`

</details>

<details><summary>bard ring: loss reasons</summary>

`{"admitted_no_trigger:origin_expired": 3, "admitted_no_trigger:program_expired": 19, "admitted_trace_incomplete": 1, "admitted_trace_missing": 2, "delivered": 53, "inferred:no_safe_point_before_game_end": 3, "no_qualifying_action": 12, "rejected:origin_expired": 2, "rejected:origin_expired+origin_superseded": 1, "rejected:origin_expired+origin_unbound": 3, "trigger_no_native_effect": 1}`

</details>

<details><summary>bard-inherited main: loss reasons</summary>

`{"admitted_no_trigger:program_expired": 10, "admitted_trace_incomplete": 3, "admitted_trace_missing": 10, "delivered": 7, "inferred:no_safe_point_before_game_end": 12, "native_effect_not_delivered": 10, "no_qualifying_action": 25, "rejected:no_companion_in_view": 18, "rejected:origin_expired": 2, "rejected:origin_expired+origin_superseded": 3}`

</details>

<details><summary>bard-inherited ring: loss reasons</summary>

`{"admitted_no_trigger:program_expired": 17, "admitted_trace_incomplete": 5, "admitted_trace_missing": 1, "delivered": 34, "inferred:no_safe_point_before_game_end": 12, "no_qualifying_action": 25, "rejected:origin_expired": 1, "rejected:origin_expired+origin_superseded": 1, "trigger_no_native_effect": 4}`

</details>
