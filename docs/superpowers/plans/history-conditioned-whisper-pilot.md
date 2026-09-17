# History-conditioned whisper pilot implementation plan

> For Hermes: use subagent-driven-development and test-driven-development. Implementation must be exercised, not reported complete from this plan.

**Goal:** Connect a genuine, completed fountain-refresh observation to an existing bounded hunger intervention, with prior native admission changing later eligibility.

**Architecture:** An opt-in two-terminal history director consumes the same checked mixed-event bytes for episodes, current public state and prior accepted whispers. Host-built requests constrain a seeded offline selector or the existing Luna subscription backend. The existing engine remains authoritative; there is no new mutation, save layout, budget, launcher integration or default behavior.

**Technology:** Existing Python standard-library director, episode projection and mailbox; existing `OAuthBackend.generate`; existing C hunger effect, terminal harness and linked rule witnesses.

## Fixed scope and policy

Base: merged PR #28, commit `87f484efd5fed78b83a6e66d64aeadb7c78e9082`. This document specifies proposed implementation, not measured gameplay or completion of issues #21/#22/#26.

1. The current session must have observations enabled. A qualifying episode is `fountain_drink` with a delivered `water_refreshed` notice AND completion, retained in the foundation's 32-root window. One qualifying episode suffices. Blocked, incomplete, no-notice, foul-water and detection episodes do not qualify. No new inference about the amount of nutrition restored is allowed.
2. Intersect this evidence with existing `eligible(state, ordinary_food=True)`. An explicit ordinary-food affirmation is required. Active hunger, insufficient budget, ineligible Sanity or death prevents a candidate.
3. Any earlier exact native ACK (acknowledgement) accepting `hunger_rate` prevents another hunger proposal in this pilot, even after expiry or restore. Published, rejected or merely telegraphed requests do not count. Preserve full host admission history even if model presentation is bounded. This is admission memory, not proof of a witnessed effect.
4. The only mechanical candidates are existing protocol requests: `hunger_rate`, value 2, telegraph 3, duration **10 or 20 turns**, assigned ID `last_id+1` and safe index `safe+1`. These are selected pilot bounds within the existing 1–50 range, not a balance claim. Exclude ambient compensation. Empty domain means no request and no model call.
5. A selector returns one complete member of the frozen request list, or exact `{"abstain":true}`. Reject a registry-valid request outside this list. Never repair a response or silently substitute a candidate. A seeded offline selector is not evidence of Luna authorship.
6. No generated prose goes to the game. Native fixed warnings remain unchanged. This limited demonstration is not a rich haunting, novel native capability catalogue, ordinary-player recognition result, or broadly unpredictable repertoire.

## Shared interfaces and ownership

### Task 1 — checked mixed context and candidate policy

Own `chaos/history.py`, `tests/chaos/test_history.py` and the minimal internal snapshot refactor in `chaos/episodes.py`.

- Factor existing snapshot code into `_snapshot_projection(path, project, *, checkpoint=None)`. Preserve every security/recheck/size check and the public `snapshot_episodes` return contract. Its wrapper still uses `project_episodes`.
- Define `HistoryState(raw: bytes)`: validate the complete raw history using `project_episodes`, parse rows through `parse_episode_event`, and ingest only actual v1 rows into a contained legacy `State`. Do not renumber, synthesize v1 rows, or weaken the existing v1 reader/parser.
- Expose `latest` from the final actual mixed row; `safe`, `last_id`, `ended`, `acks`, `accepted`, and `active` as compatible host properties. Filter active eligibility using the final mixed turn. `summary()` returns the existing allowlisted summary shape with current mixed-envelope observed fields. Do not pass a v2 row through legacy `State.ingest`.
- Expose `episodes` (unchanged public projection), `enabled` (latest session opted in), and `prior_whispers` (bounded typed admission records). Prior fields: `id`, `mutation`, `duration`, `accepted_seq`, `accepted_turn`, `expires_turn`, `active_at_snapshot`, `expiry_observed`. Native expiry must actually be recorded to set the last field; inferred inactivity is distinct. Do not infer witnessed application.
- Reject inconsistent accepted-ACK identity, registered cost and expiry, conflicting repeated acceptance and malformed expiry linkage rather than inventing or repairing continuity. Do not require total spending to equal legacy ACK costs: curio/haunting costs are separate legitimate native history.
- `snapshot_history(path, *, checkpoint=None)` returns `(HistoryState, host_proof)` using the shared checked bytes.
- Define `IncompleteHistory(ValueError)` for bounded empty/incomplete trailing data so the live runner can defer without hiding schema/privacy errors. Reject caps and oversized unfinished lines before deferral. Strict offline/replay callers must not adopt partial evidence.
- `candidate_requests(state, ordinary_food=False)` returns the canonical ordered list (duration 10, then 20), or `[]` under the fixed policy.
- `public_context(state)` returns only `history_context_v:1`, allowlisted `summary`, unchanged `episodes`, bounded `prior_whispers`, and explicit prior-coverage information. No host proof, paths, inode/digest identifiers, arbitrary details or journal text. Enforce a bounded serialized size compatible with the existing model transport.

Write and run RED tests before implementation: valid mixed input; latest mixed counters; legacy still rejects v2; strict marker/sequence/linkage failures; qualifying/nonqualifying policy; prior accepted versus rejected/published/expired; malformed accepted history; source/checkpoint/privacy controls. Re-run unchanged episode/director tests. Capture actual test commands and results.

### Task 2 — bounded selectors, source-fresh runner and mixed replay

Implement the independently testable selectors first in `chaos/history_choice.py` and `tests/chaos/test_history_choice.py`, with `chaos/prompts/history-director.txt`. Their `choose(context, allowed_requests)` receives only the `public_context` output (keys `history_context_v`, `summary`, `episodes`, `prior_whispers`, `prior_coverage`) and returns an exact request or `None`. `prior_coverage` contains integer `shown` and `omitted` counts. Selectors are bounded to one decision attempt by default (at most two when explicitly constructed for this pilot); empty domains do not consume attempts. The OAuth selector receives the existing transport instance, not credentials or a new ledger. After the core interfaces stabilize, implement `chaos/history_director.py`, `tests/chaos/test_history_director.py` and small opt-in CLI additions to `chaos/__main__.py` with dedicated CLI tests. Do not change `play` or existing backend behavior.

- Add `python3 -m chaos history --run-dir ... --backend random|oauth|replay`. Random uses an explicit seed. OAuth uses only the existing `gpt-5.6-luna` / `openai-codex` route and requires an existing ledger; never create a replacement allowance. Replay requires explicit admission journal and original mixed native evidence.
- Reuse `OAuthBackend.generate`, normal response extraction and strict parsing. Send only the public context and exact allowed requests. No model tools, fallback provider, automatic retries or generated terminal text.
- Freeze candidate requests, assigned schedule and host checkpoint before choosing. Recheck the old checkpoint and obtain a fresh full snapshot before submit; any advancement, partial suffix, identity/prefix change, changed eligibility or pending conflict discards the result without retiming.
- Keep mailbox locking/pending reconciliation and exact accepted ACK checks. Checkpoint publication is verified at an instant, not atomically bound to later native admission: the unchanged C protocol does not carry a history digest. State this limitation; engine schedule/budget/active checks remain authoritative.
- A quiet domain is reconsidered when evidence changes at the same safe index. A nonempty-domain selection attempt is not retried at that safe index. Default to at most one backend decision attempt per invocation; no poll-driven calls. Runtime and source caps remain bounded. Distinguish submitted, accepted, rejected, stale, abstained and exhausted results.
- Reuse exact ScheduleBackend replay validation with the mixed consumer. Do not filter observations into an unauthenticated synthetic file. Missing/conflicting accepted evidence and missed/rejected schedules fail without retiming. Replay does not call a selector again.
- Retain a small bounded host-only decision receipt linking the checked prefix, candidate set, selection and actual admission outcome for the demonstration. It is not a new lifecycle database or proof of human rendering.

Write RED tests for exact membership, privacy, ledger missing/invalid preflight, source advancement during choice, partial suffix, quiet-to-qualified same-safe transition, pending/ACK failure paths and strict mixed replay. Fake transports prove validation, never genuine model or native behavior.

### Task 3 — one native action-to-effect demonstration

Reuse existing harnesses, ordinary commands and rule witnesses; no new general build/provenance framework. No changes to game mechanics, RNG (random-number generator), registry, native warnings, save version or cruelty capacity.

- Freeze a controlled human-Wizard route with observations enabled, ordinary food and explicit eligibility preparation. Use the unchanged deterministic clock/entropy shim and a single predeclared sequence of at most **eight ordinary confirmed drinks**, provisioning fountains through documented wizard commands. Preserve every action and outcome in that one history; do not reset the game, reseed, discard non-refresh drinks or reroll an action. Run selection only after the frozen preparation sequence. If there is no completed delivered refresh, the character dies, or another required preparation condition fails, retain that result and stop the demonstration. The previous snake-result route does not qualify. No seed search, forced outcome or synthetic positive events. Freeze the exact command list before execution, then reuse it for empty-control and replay arms. Read-only, exactly-once-forwarding `gethungry` and `chaos_food` wrappers may measure native consumption; their separate source/link receipts must remain distinct from the production build. They must not write game state, consume randomness or publish engine observation rows.
- Run the actual history director against those event bytes. Preserve selected prefix, menu, request, warning, accepted acknowledgement and terminal input/output.
- Feed the exact selected request—not a substituted pack—through real native `gethungry()` measurement. Compare ordinary consumption before, during and after expiry. A linked rule witness and terminal admission are separate evidence scopes; a claim of a full ordinary-game effect additionally requires a native turn-loop witness. Do not advertise an admission-only result as that effect.
- Exercise the accepted mixed-event schedule again with fixed clock/entropy/input controls; no new model selection or retiming. Cover active/pending save/restore accounting using existing support.
- Run quiet/empty and rejected-candidate controls without gameplay changes. Preserve the approved build-header comparison rule where needed; never rewrite earlier strict failures.

### Task 4 — finite counterfactuals, genuine Luna and publication

- At fixed latest public state, eligibility and declared seed, compare absent/nonqualifying/qualifying action history. Require mechanical domain/selection differences, not text differences.
- Hold actions fixed and vary typed prior acceptance: absent, rejected, accepted-active, accepted-expired. Require the defined suppression. Explicitly label policy interventions; never present edited histories as genuine native provenance or leave inconsistent budgets/IDs in purported valid-history fixtures.
- Use fixed offline seeds `0, 1, 7`; demonstrate both legal durations across controlled outcomes and exact repeatability. No expectation that every seed changes a winner for every comparison.
- After offline/native controls pass, perform at most **two new genuine Luna requests for this pilot**, counted within the existing ledger and allowance. Recheck the ledger before reservation. Failed/stale responses spend attempts; no retry to manufacture acceptance. No provider calls during fixture discovery or unit tests. If the limited calls do not yield a valid selected response, report that result rather than label an offline choice as Luna output.
- Run pinned Ruff lint AND format early; obtain specification and independent correctness/security review, then exact reviewed commits, fresh source receipts where required, and hosted checks. Preserve accepted foundation evidence and clean superseded reproducible products.

## Maintenance immediately after this feature

The maintainer explicitly directed that the Grok-review maintenance issues be the next work batch, before further features after this pilot. Finish the bounded pilot rather than folding a general refactor into it; preserve interfaces and evidence that the maintenance work will use.

- [#32 — common native-test configuration and official runner](https://github.com/sflicht/NyarlatHack/issues/32): first priority. This pilot now reuses `NYARLATHACK_GAME_TESTS` and the existing `NYARLATHACK_NATIVE_*` source-build profile rather than adding a `NYARLATHACK_HISTORY_*` family. Its unittest adapter consumes the existing supervisor's exit code, not a status-line parser. Four configuration regressions cover configured execution, absent configuration, partial configuration and wrong mode. This is an immediate compatibility improvement, **not** completion of the shared descriptor/official entry-point refactor.
- [#29 — C/Python protocol registry agreement](https://github.com/sflicht/NyarlatHack/issues/29): reuse `REGISTRY`, `eligible`, `encode_request` and `parse_request`; do not create another admission registry. The two selected durations are pilot policy, not new protocol bounds. Centralize mechanically checked contract data in the maintenance work.
- [#34 — engine-owned shared spending helper](https://github.com/sflicht/NyarlatHack/issues/34): this pilot adds no spender and changes no prices or ceiling. History validation must continue allowing legitimate curio/haunt spending rather than equating total spending with whisper acknowledgements. Preserve native accounting as the authority.
- [#33 — upstream hook inventory](https://github.com/sflicht/NyarlatHack/issues/33), then [#30 — observation-family registration](https://github.com/sflicht/NyarlatHack/issues/30): this pilot adds no production upstream hook or observation family. It reuses the foundation's chronology validation rather than adding a second observation schema. The passive native witness is test-only and must remain distinguishable from production hooks.
- [#31 — shared bounded Lua sandbox](https://github.com/sflicht/NyarlatHack/issues/31): this pilot adds no Lua binding or virtual machine and does not rewrite saved packs or Thimble evidence. Complete the shared sandbox maintenance before later adapter expansion.

Recommended execution order after the pilot: **#32 → #29 → #34 → #33 → #30 → #31**, with final scope/acceptance review for each. This order is a work plan, not a claim that the issues are fixed or permission for budget/protocol expansion. No new feature work is queued ahead of this batch.

Two review baselines are historical: hosted checks for PR #28 and merged main are now verified successful; the current opt-in history consumer is separately maintainer-authorized. Those facts do not satisfy the maintenance acceptance criteria or weaken their compatibility requirements.

## Stop conditions and reporting

Stop expansion when the bounded causal policy, source freshness, real selected native effect/expiry, mixed replay, save/restore and unchanged-default controls are demonstrated. Missing positive native evidence or failure to measure the selected effect is a blocker, not permission to substitute invented data. Broader repertoire, player recognition, persistent hauntings, cross-family creative evaluation and stronger models remain outside this slice. No broader issue is automatically closed.
