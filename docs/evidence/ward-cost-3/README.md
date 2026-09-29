# Ward effect cost 3 (Sam, 2026-09-29)

Tier A evidence: the change alters admission and the recorded spend.

## The change

Sam's decision: "Lower ward cost to 3". Under #164 pacing a game may spend at
most 3 points between one new deepest level and the next (K = 3). At cost 4
the ward effect (`ward_efficacy`) could never be admitted in a paced game,
which is the default.

- `chaos/protocol_contract.json`, the single source: the current
  `mutations` row for `ward_efficacy` now has `cost` 3. The generator
  (`scripts/generate_protocol_contract.py`) rewrote `include/chaos_protocol.h`
  (`CHAOS_MUTATION_ROWS`) and `chaos/_protocol_contract.py` (`REGISTRY`) from
  it, so the engine and the sidecar agree by construction; `--check` passes.
- The contract's `legacy` block, the frozen v1 table, keeps the ward at 4.
  It is fingerprint-pinned, and v1 (pre-v3) event logs recorded ward acks at
  cost 4. The sidecar validates each ack against the table for its own
  version (`chaos/history.py`, `chaos/director.py`), so old logs still read.
  No validator was relaxed.
- No new state, no save-format change, no RNG. Existing saves carry each
  active effect's cost, and the state validator (`chaos_state_valid`,
  `src/chaos_protocol.c`) checks it against the current table, so a save made with an active cost-4 ward under the old build is
  refused on restore. Pacing already made that combination unreachable in a
  paced game, and #164's state v3 already refuses saves made before it.

## What admission now does

With pacing on, on a level that still has its 3 points:

- the ward is admitted and spends 3 (`level_spent` 3, budget 0);
- a hunger request (3) on the same level is refused for `budget`, and so is a
  curio or haunt spend; nothing about the state changes;
- hunger alone on a fresh level still fits, as before.

Unpaced games (`NYARLATHACK_PACING=0`) are unchanged apart from the ward
costing 3 instead of 4.

## Tests

- New linked C unit (`tests/chaos/protocol_harness.c`, `pacing`): paced state on
  a fresh level admits the ward (spent 3, level spent 3, budget 0), then refuses
  hunger for budget and a curio spend for budget with the state unchanged; hunger
  alone on a fresh level still fits.
- New real-game test (`tests/chaos/test_gameplay.py`,
  `test_paced_ward_fits_level_then_nothing_else`, paced by default): wizard
  fixture, ambient then ward accepted with cost 3 and spent 3; a later hunger
  request on the same level is rejected with reason `budget`; spent stays 3.
- Changed expectations, each only the cost 4 → 3 and its sums:
  - `tests/chaos/protocol_harness.c` `state`: spent/reserved 4 → 3; ward then
    hunger spent 7 → 6; unpaced budget at Sanity 0 5 → 6. `non-effect`: ward +
    hunger + curio + haunt 10 → 9, reserved 7 → 6.
  - `tests/chaos/game_rules.c`: ward spent/reserved 4 → 3.
  - `tests/chaos/test_engine.py`: two ward admissions spent 4 → 3.
  - `tests/chaos/test_gameplay.py` save round trip (unpaced, ward and hunger):
    restored spent/reserved 4 → 3, final spent 7 → 6; the comment now says why
    it stays unpaced (ward and hunger together exceed K).
  - `tests/chaos/test_episode_io.py`: the current-writer golden now expects cost
    3, budget 9, spent 3; the v1 parser oracle in the same test keeps cost 4.
  - `tests/chaos/test_cosmetic_contract.py`: current (cost, cosmetic cost) rows
    ward (4, 0) → (3, 0); the frozen legacy costs `[1, 4, 3]` keep 4.
  - `tests/chaos/test_protocol_contract.py` `CURRENT_ROWS`,
    `test_director.py` `current_ack`, `test_cosmetic_readers.py`: current
    tariff 4 → 3. The frozen v1 `ROWS` keep 4.
  - `tests/chaos/test_episode_scopes.py`: comment only; the legacy message table
    is still exercised unpaced.
- No committed whisper log, replay fixture or evidence file records a ward ack
  at cost 4 (`git grep` for accepted `ward_efficacy` rows finds only the
  episode-io golden above).

Gates: see the PR (fast and native suites, both builds warning-clean).

## Player-visible delta

None on the default `python3 -m chaos play --ordinary` path: it never requests a
ward (its offline director is the hound and the next-use program). With
`--pack ward` or `--backend random`, in a paced game, once Sanity is 80 or less,
a ward request is now admitted (telegraph "The lines of your wards seem thin and uncertain." as before)
where it was refused for budget; after it, nothing else mechanical is admitted
on that level. The wizard-mode real-game test above is the capture; no
nonwizard capture was taken, because reaching Sanity 80 in ordinary play is not
scriptable in a short run.
