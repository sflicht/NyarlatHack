# Hounds that hunt: live pilot (Tier B)

Grok 4.7 (`grok-4.7`) over xai-oauth through Hermes, ledger surface `haunt`.
Same 20 jobs, histories and synthetic game seeds as the #251 pilot
(`hunt_pilot.py`, which reuses #251's `pilot.py`). Pre-check:
`HoundValidator` with the floor in `../PREREGISTERED.md`, committed before
any of these requests. Regeneration: `HoundLane.REGENERATE`, which allows one
regeneration after an envelope or pre-check rejection, inside the same 480 s
lane deadline. Every request is in each run's `ledger.jsonl`, and every
attempt's receipt is under `jobs/`.

## Three runs, in order

| Run | Revision | Prompt | Requests | Result |
|---|---|---|---|---|
| `v1-stopped` | c2bee34d, **dirty tree** (one uncommitted file, `analyze.py`, which the run does not use) | first hunting prompt (3285 bytes) | 17 sent: 13 answered, 4 in flight when stopped | 13 of 13 deadline |
| `v2-probe` | cc615cc5, clean | tightened prompt (2186 bytes) | 4 | 3 of 3 ready (one after a regeneration) |
| `v2` | cc615cc5, clean | tightened prompt | 27 | **18 of 20 ready**, 2 deadline |

**v1 was stopped** on the orchestrator's instruction once every finished job
had missed the deadline. Its answers took 481–1062 s (median 804 s) and used
32k–89k completion tokens (median 57k). #251 took a median of 234 s and 17k
tokens. The longer prompt, which described the threat-versus-escape tension
and the full rehearsal rule, pushed Grok into much longer reasoning. v1 also
ran from a dirty tree. It is kept only to disclose those requests and is not
part of the result. A reasoning-effort setting was not available: Hermes
lists grok-4.7 among the Grok models that reject `reasoning.effort`
(`grok_supports_reasoning_effort`). So the fix was the prompt alone. It now
states the pursuit shape plainly and gives the acceptance rule in one line.

## v2 (the result)

- **Ready 18 of 20 within 480 s**, the same as #251 (18 of 20).
- **Latency per request:** median 161 s, range 80–540 s, from 27 requests.
  Completion tokens: median 10k, max 24k.
- **Lane time per job, with both attempts summed:** median 244 s. The two
  late jobs:
  - 13-wizard-default-path-00007: one request that took 540 s.
  - 16-bard-00007: cornered at 315 s, then its regeneration ran out of time
    at 279 s.
- **The pre-check refused 7 first attempts**: 5 `cornered` (the hound pinned
  the player, so the player never escaped) and 2 `never_closes`. 6 of the 7
  were ready on their one regeneration; the seventh is 16-bard-00007 above.
  No `barely_moves` refusals and no script errors.
- In play, the two deadline jobs would publish footsteps.lua.

Engine shadow metrics for the 18 ready sources (4 rooms × 3 seeds, the same
as the baseline) are in `../trials-v2.json` and `summary.json`, once that
heavy run lands.

## Requests (2026-10-07, UTC)

For the hound pilot: v1 17 + v2-probe 4 + v2 27 = **48 requests**. Today's
ledger total, counting all surfaces and Sam's play, is **70 of 200**.
