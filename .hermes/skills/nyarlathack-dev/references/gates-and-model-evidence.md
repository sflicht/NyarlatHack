# Gates, live models and retained-response evidence

## Gates

- Live game-model calls, executing/importing `ordinary_route`, provider/model/
  account changes, spending, permission expansion, human playtests and deployment
  each need their own explicit authorization. Never invent human feedback.
- An approval hold or timed-out approval that forbids retry also forbids
  equivalent helpers or alternate workflows. Record the approved scope, resume only
  it, leave security settings alone, and continue other authorized work.
- Don't modify, reinstall or restart Hermes to unblock the project; use the
  repository's established integration or report the blocker. Never copy
  authentication material.
- CI and tests stay offline: fake clients and local HTTP fixtures are transport
  tests, not model gameplay. Keep the model backend explicitly opt-in.

## Before a genuine model call

- Verify the existing private ledger and lock with
  `OAuthBackend(..., require_existing=True).preflight()` (`chaos/oauth.py`).
  Inspect current authorization and count, not a remembered one. A remaining count
  is not permission to ignore a narrower purpose-specific allowance.
- Use the repository's authorized route; no model/provider switch, paid fallback,
  automatic SDK retries or tools in model output. Never reset a ledger. Persist
  reservations before requests, including failures; check output paths first.
- Subscription usage is not API-dollar billing; don't fabricate per-call cost.
  Stop on auth, quota or provider errors.
- Propagate the director deadline into requests; use an outer process timeout when
  the bound must include name resolution.

## Retained responses and replay

- Select over the exact checked pre-selection prefix, not a completed run.
  `snapshot_history(run_dir, checkpoint=proof)` (`chaos/history.py`) validates the
  original prefix; copies get new identities with a separate original-hash link.
- Retain raw response, public context, full allowed menu, prompt digest and
  durable usage receipt; read back the exact ledger record. A completed ledger
  entry does not prove a valid response.
- A retained response can drive a later matching native run without another call:
  bind full native prefix, context, menu and normalized response; use normal
  source-fresh publication. Replay an admission journal only after a genuine exact
  native acknowledgement. Call it local consistency, not signed authenticity.
- Generated Lua is data: read it via `chaos/curio_store.py` `read_candidate`, never
  execute it outside the engine or edit it to pass. Keep illustrative sources
  separate from genuine model output.

## History-conditioned features

- A history-conditioned feature must change mechanical eligibility, weighting or
  selection; personalized prose alone doesn't count.
- Test action counterfactuals at identical complete legacy summaries and fixed
  declared director seeds. Test prior acceptance separately with coherent
  accounting and qualifying actions after restore; ensure absent eligibility or
  disabled observations can't explain apparent suppression. Label all policy
  interventions synthetic.
- Continuity notes are fallible editorial metadata; don't inject unsupported fields
  into the strict engine request. Author rationale is not engine evidence.
- Cosmetic Dreamlands echoes must be grounded in actual shadow events (including
  rejected candidates), with no game-state, turn, RNG, prompt, budget or hidden-
  information effects, and separate from required mutation warnings.
- Don't claim spawn weighting, unlimited replay, balance or model quality from the
  initial registry (ambient, ward efficacy, hunger rate) and its conservative budget.

## Human-facing reports

Render substantive summaries as HTML/PDF from machine-checked data; label proposed
limits and unrun checks; keep small source/evidence metadata in Git, not compiled
artifacts. Preserve earlier incomplete reports and original failures.
