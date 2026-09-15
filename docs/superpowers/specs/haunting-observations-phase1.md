# Minimal observation-only contract — parent-selected phase 1

Status: parent-selected observation-only implementation contract under the approved #19/#21 work; not authorization for gameplay effects. Read against `/home/hermes/nyarlathack`; supplied baseline `9559cd0dc8936301ae8083600e7e930fe334506c`. No code, imports, builds, tests, gameplay, network or model execution performed. The two earlier `/tmp` surveys are proposals, not binding requirements.

## Parent-selected implementation boundary

1. Record **selected whistle actions and confirmed fountain drinks only**. No companion movement, inventory potion/dip/sink coverage, adapter, haunting lifecycle, admission, budget, source-program state, persistent binding, save-layout change or authoring integration.
2. Opt-in `NYARLATHACK_OBSERVATIONS=1`, read once by `chaos_start`; any other value is off. Requires normal healthy run-directory transport. Off preserves legacy event bytes and sequence schedule. V2 shares the existing authoritative stream/sequence, not a second file.
3. Emit an enabled-marker v2 record immediately before the existing v1 `session` record in each opted-in process. This prevents legacy readers/authoring from accepting an apparently v1-only prefix before the first selected action. Do not upgrade `parse_event`, `State`, `EventReader`, requests, prompts or frozen Thimble authoring. A separate offline parser/projector explicitly accepts this mixed format. Opt-in runs are **not compatible inputs to legacy authoring**.
4. Freeze these small bounds before RED tests: one transient selected-action scope; one semantic notice per action; last 32 selected roots within the latest session; two summary groups; three evidence entries per group; counters capped at three with per-counter saturation flags; public summary at most 4096 ASCII JSON bytes. These are proposed engineering limits, not measured performance or balance. No global prompt cap or inference changes.

A v1 typed optional key would be fewer lines, but v1 events accept unknown top-level keys (`protocol.py:102–138`) and existing projections drop them. It cannot force an old consumer to recognize the changed meaning. Requests and nested vitals are exact-key validated; **v1 events as a whole are not**. Therefore choose v2, without retroactively tightening v1.

## Exact v2 schema

Exactly the existing envelope keys `v,seq,turn,safe,event,phase,detail,sanity,insight,budget,spent,reserved,last_id,vitals`, plus `observation`. Version is 2, event is `observation`, detail is empty; vitals mandatory with the current exact schema. Reuse existing integer, sanity and budget bounds; booleans are not integers. No extra keys, duplicate JSON keys, nonfinite numbers or arbitrary text. The observation object has exactly:

`{operation, stage, root_seq, fact}`

| Stage | Operation | Root | Fact | Phase |
|---|---|---|---|---|
| `enabled` | `none` | 0 | `none` | result |
| `started` | `whistling` or `fountain_drink` | 0 | `none` | attempt |
| `notice` | root's operation | earlier root's seq | allowed fact | result |
| `completed` | root's operation | earlier root's seq | `none` | result |
| `blocked` | `fountain_drink` | earlier root's seq | `none` | result |

Zero on `started` means “this record is the root,” not a guessed future sequence. Begin returns the actual `u.chaos.seq` **only after successful append/fsync**; failure returns zero. A terminal references that returned value. At most one terminal and one notice per root; notice precedes terminal. Same-session, same-operation, same-turn linkage only. A new selected root closes the attribution scope of an unfinished prior root without inventing a terminal. Session/level boundaries and death clear transient scope. Never append a terminal after final death.

`completed` means the selected native routine returned, not desirable effect, identification, survival or companion obedience. `blocked` means its native reach guard ran, not user cancellation. Missing terminal is incomplete; a previously emitted notice remains historical perception evidence but is not a completed positive summary entry. A completed root without a notice has unknown selected-notice coverage, not “nothing happened.” No cancellation enum: selection cancellation, unsupported apply, and fountain decline create no selected root. Declining can continue to a successful potion selection in the **same** `dodrink` call. Its later cancellation/consumption is outside this increment.

## Semantic facts; public delivery, not hidden dispatch

Whistling message facts: `sound_high`, `sound_shrill`, `sound_normal`, `sound_strange`, `sound_humming`. They encode the actual native wording, never ordinary/magic type: both objects have appearance `whistle` (`objects.c:1493–1494`). Do not infer known identity, curse status, hearing or pet response from the enum.

Fountain facts: `water_refreshed`, `water_foul`, `cannot_reach` (message channel); `detection_presented` (map-display channel). Their channels are fixed by this table, not another wire field. Exclude tasteless/great/other fountain branches from notice coverage initially; still terminate confirmed selected actions truthfully. Foul wording variants share one fact. Detection means the native map presentation was executed, not that any named/located entity was exported.

Message notices require delivery at the existing `vpline` `putstr(WIN_MESSAGE,...)` seam, not merely execution of `pline`: NOSHOW/NOREP can suppress messages. Arm only a fixed enum around the chosen native message call. At entry to that `vpline`, take the armed enum into a local (so nested messages cannot steal it); emit only after delivery, or discard it on an early return. Disarm immediately after the native call. Never pass message strings into observation code. Scope map delivery similarly around fountain's existing `monster_detect(NULL,0)`; record after its actual `display_nhwindow(WIN_MAP,TRUE)`, never from fate or a second detection call.

No target IDs, coordinates, object names/appearance strings, original fate, magical-fountain flags, detected entities, private eligibility reasons or model-facing handles. No extra RNG, naming, identification, rendering, native action calls, or safe-point polling. Transport failure suppresses observations, **never cancels the ordinary action**. Suppress shadow events. Transient C bookkeeping is not saved; use existing bounded transport buffers.

## Summary and evidence

Offline API in new `chaos/episodes.py`: `parse_episode_event(raw) -> dict`, `project_episodes(raw: bytes) -> dict`, `snapshot_episodes(path, *, checkpoint=None) -> (public, proof)`.

Public output has exactly `episode_context_v:1`, `scope:"selected_whistle_fountain"`, `lookback_roots:32`, `episodes`, `coverage`. Groups, ordered by operation, are `{operation,count,saturated,evidence}`. Each evidence entry is `{root_seq,notice_seq,end_seq,fact}`. Include only completed roots with delivered allowed notices; retain first two and latest qualifying entries in the window, ordered by root sequence. Count caps at three; saturated means strictly more than three. Group count is completed witnessed **actions**, not distinct targets or future capability eligibility.

Coverage has exactly `incomplete,blocked,completed_without_notice,omitted_roots`, each `{count,saturated}` with the same cap. Counts except omitted_roots concern the retained window; omitted_roots counts evicted selected roots since latest session. Reset lookback/coverage on restore, not native logs. Unsupported paths and unselected legacy apply attempts never become incomplete positives. No episodes of “current haunting,” offers, reward scores or editorial narrative.

Verify complete newline-terminated, contiguous sequence history from a fresh session (optional enabled marker immediately before it); validate monotonic turn/safe/spent/last_id, legal restore chains and final death, and require the marker for v2 action records in that session. Allow intervening v1 events, but not cross-boundary references. Use existing 16 MiB/50,000-event ceilings; the 32-root summary is not log truncation. `snapshot_episodes` reuses `curio_store._directory`, `curio_continuity._file`, `_inode`, and `curio_store._digest`; proof is `{directory,event:{identity,length,sha256}}`. A checkpoint rechecks identity and exact consumed prefix bytes/hash and projects only that prefix; append is allowed, replacement/rewrite/truncation is not. References address exact lines in that checked prefix. No hashing framework, signing claim, live tailer or authoring call.

This increment supplies useful action evidence independently. It does **not** establish a meaningful haunting pilot, ordinary-play recurrence, or wholesale completion of #21. A later explicit capability choice and behavioral acceptance remain necessary.

## Parent scope decision

Proceed with this observation-only slice under the user-approved source/observation work. Version marker, fixed notice vocabulary, delivered-message/map seams and declared small bounds are selected for implementation and testing; they are not measured results. Do not implement the surveyed whistle echo or fountain outcome remapping. Do not claim recurrence, model-quality evaluation, or complete issue #21 acceptance from this foundation. Before native acceptance, use a fresh full-history clone at the exact reviewed revision and the committed prepare_native_ci.py receipt path; never validate edited source against preserved objects or an archive without required Git history.
