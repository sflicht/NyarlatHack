# History-conditioned fountain-to-hunger pilot

The Crawling Chaos can now use recorded player actions to select one existing
rule change. This is an **opt-in, narrow pilot**, not a larger cruelty budget or
an unrestricted mechanic generator. The engine remains authoritative.

A **whisper** is a bounded mutation request. An **acknowledgement** is the native
record saying whether the engine accepted it. Publication alone is not admission;
admission alone is not a measured gameplay effect.

## What changes—and what stays unchanged

A completed fountain drink with a delivered `water_refreshed` notice enables a
choice between **10 or 20 turns** of the existing `hunger_rate` mutation: double
ordinary food consumption. All retained action roots are checked, including ones
not sampled into the model's presentation. Incomplete drinks, foul water,
detection notices, blocked actions and merely attempted actions do not qualify.
The character must satisfy normal engine eligibility, have sufficient budget,
and use ordinary food metabolism. The user must explicitly affirm the latter.

A previously accepted hunger whisper suppresses another in this pilot, even after
expiry or restore. Rejection and publication do not count as acceptance. This
rule uses the full checked admission history, not just the bounded model view.
An empty candidate set causes **no model call and no request**.

No native mechanic, cost, warning, save layout, default event stream, Lua binding,
or `play` launcher behavior changes. The legacy director continues rejecting
version-2 observations; only the new `history` command consumes mixed versions.
The long-term work in issues #21, #22, #26 and #27 is not completed by this pilot.

## Run it explicitly in two terminals

From the repository root, create one private directory and launch an
observation-enabled game in the first terminal:

```sh
RUN=$(mktemp -d)
printf 'Use this run directory in the second terminal: %s\n' "$RUN"
(cd dnethackdir && NYARLATHACK_RUN_DIR="$RUN" NYARLATHACK_OBSERVATIONS=1 ./dnethack)
```

In the second terminal, set `RUN` to that exact printed directory. For a
reproducible offline selector, with no credentials or network:

```sh
python3 -m chaos history --run-dir "$RUN" --backend random \
  --seed 0 --ordinary-food --max-runtime 300
```

Do not use `--ordinary-food` for a character whose metabolism it does not
describe. The flag is an explicit host assertion, not automatic race detection.
Do not run this beside another director on the same mailbox. A qualifying drink
does not override Sanity, budget, active-effect or scheduling restrictions.

The model option uses the existing pinned GPT-5.6 Luna / ChatGPT OAuth route.
OAuth is the subscription's authorization mechanism; this is not an API-key
fallback. Use the existing configured interpreter and authorized ledger:

```sh
/path/to/configured/python -m chaos history --run-dir "$RUN" \
  --backend oauth --ordinary-food --model-ledger /existing/private/model-ledger.json \
  --max-runtime 90
```

The existing ledger **and its lock must already exist**. Missing or inconsistent
authorization fails closed; this command never creates a replacement allowance.
The selector makes at most one decision attempt per invocation, with no automatic
retry, stronger-model switch, provider fallback or model tools. Repeated manual
invocations are still requests against the same persistent allowance.

`--install-only` returns after publication with `installed_pending_ack`; that is
not acceptance. Keep the game moving to an eligible native safe point if you want
it to consume the request. Model-generated prose is never sent to the terminal.
Only existing fixed engine warnings appear.

## Replay and source freshness

For a new matching controlled run, use the original admission journal and mixed
native evidence—not a response-only file:

```sh
python3 -m chaos history --run-dir "$NEW_RUN" --backend replay --ordinary-food \
  --journal "$ORIGINAL_RUN/whispers.jsonl" --evidence "$ORIGINAL_RUN/events.jsonl"
```

The original request must have an exact accepted native acknowledgement. Missing,
conflicting or stale evidence is rejected; replay never repairs identifiers or
retimes a schedule. General reproducibility requires matching game inputs,
options, clock and entropy controls; a starting seed alone is not enough.

The runner derives state and action history from the same checked bytes, freezes
the exact menu, and rechecks the source before publication. A changed prefix,
appended data, changed eligibility or conflicting pending request discards the
choice. This is a **read-instant check**, not an atomic binding between a history
digest and subsequent C admission, nor protection against a malicious process
running as the same user. Native schedule and budget checks remain authoritative.
The public context can omit the particular qualifying episode from its sampled
presentation; host qualification does not imply the model saw that exact notice.

## Measured development evidence

The retained production base is
`8f317763a3560bd774d0b61e134e7028a744412a`; current Python and test-probe identities
are separately captured in the run recipes. These development runs reuse verified
objects and **are not fresh-current-revision acceptance**.

The fixed route retains all eight natural drinks. The third produced contaminated
water and reduced health from 13 to 3. The sixth produced the delivered refresh
notice. No seeds were searched, no refresh was injected and no unfavorable drink
was discarded. An initial harness failure omitted the native “Dry up fountain?”
confirmation. It remains failed; the repaired driver explicitly declines that
prompt, and its first 12 event records are byte-identical to the failed prefix.

- **Offline seed 0:** selected duration 20. The complete trace contains 34 ordinary
  consumption calls: 10 before admission, 19 under the effect and 5 after elapsed
  expiry. Total food loss was 53; the empty control lost 34. Extra non-whisper
  drains were independently checked and zero for this route.
- **Genuine Luna:** one request on the exact native pre-selection prefix selected
  duration 10. The persistent ledger advanced from 3 to 4 of 20 attempts, with no
  retry or paid fallback. The actual raw response, public context, exact menu,
  prompt digest and completed usage receipt were retained.
- **Exact Luna choice in the game:** a separate controlled run matched the full
  source prefix, context and menu, then published the retained response without
  another model call or substitution. Its 34 consumption calls comprised 10
  before admission, 9 under the effect and 15 after elapsed expiry. Food loss was
  43 versus 34 in its empty control. The engine emitted the warning, accepted the
  exact request, charged cost 3, released its reservation at expiry and retained
  lifetime spending.
- **Both replay arms:** exact inputs, terminal output, mixed event bytes,
  consumption traces, score log and dump bytes matched their respective original
  arms. Empty controls used the same gameplay commands and native call/turn
  schedule; separately evidenced paging responses may differ. This does not
  relax the earlier stock-comparison contract.
- **After expiry:** the actual history runner made zero new selection attempts or
  submissions, with unchanged mailbox, journal, event bytes and spending.

The passive C probe forwards the original `gethungry`, `chaos_food` and
`near_capacity` calls once. It does not alter game state or consume randomness.
Nutrition is reconciled against ordinary outputs plus independently recorded
native drain sources—not against a fitted residual. Same-turn admission and
elapsed-before-emitted expiry are distinguished using native event sequence and
raw effect state. Synthetic sensitivity tests are separate from these native
measurements.

Compact development evidence: [history-pilot-development.json](evidence/history-pilot-development.json).
The recorded-response adapter proves local evidence consistency, not signed model
authenticity. The retained ledger entry was independently read back against the
actual call receipt.

## Remaining acceptance and scope boundaries

The fresh configured source suite must exercise the new driver plus the existing
real-game active-ward/pending-hunger save/restore test, unchanged-default
comparisons and incompatible-save rejection. Those are separate gates; this
pilot's measurement driver does not claim active/pending save-restore or stock
equivalence by itself. Fresh acceptance and hosted status are recorded separately
rather than inferred from development success.

Synthetic counterfactual tests hold the entire legacy public summary fixed while
varying action history, and hold actions fixed while varying prior admission.
They cover fixed seeds 0, 1 and 7, accepted-expired eligibility, and a fresh
qualifying action after a synthetic restore. These are policy interventions, not
edited native provenance or actual save files.

This pilot demonstrates one consequential history-dependent mechanism. It does
not measure player recognition, long-run balance, creative thematic continuity,
broader repertoires or unrestricted ordinary-play reproducibility. Maintenance
issues **#32, #29, #34, #33, #30 and #31** are the next work batch before further
features; their scope is recorded in the [implementation plan](superpowers/plans/history-conditioned-whisper-pilot.md#maintenance-immediately-after-this-feature).
