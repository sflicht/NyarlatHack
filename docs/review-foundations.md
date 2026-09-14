# Review foundations: implemented scope and remaining backlog

This batch follows the review of the published First Haunting baseline
`ec53bef97fa66371bd058d954b5bc9a5179b9305`. It is not a claim that all thirteen
review issues or the larger gameplay proposals are implemented.

## Implemented behavior

- **One-command offline play (#3):** `python3 -m chaos play` supervises a
  separate pack/random director and a real terminal game. It keeps a private
  single-writer run directory, preserves it for restore, and reaps children on
  normal or catchable-signal exit. A director that finishes early does not
  stop gameplay. Model and OAuth (Open Authorization) launch modes are not
  part of this command.
- **First player-known observation slice (#4):** validated status-line health
  and power snapshots, using the same polymorph health selection and negative
  health clamp as the display. Exact prayer confirmation/cancellation enums
  are exposed without arbitrary details, hidden identities or new random draws.
  Richer item/outcome context remains future work.
- **Explicit timing contract (#5):** future exact indices remain pending;
  past indices reject without retiming. Multiple Sanity bucket crossings in
  one observation deliberately produce one safe point, not a burst. This
  documents and tests the existing policy; it does not add an index-zero mode.
- **Formatting-only cleanup (#7):** both whisper adapters can remove JSON
  whitespace and one complete bare/json Markdown fence. JSON means JavaScript
  Object Notation. The strict schema, identifiers, assigned index, eligibility
  and byte caps still apply. No extra inference/retry occurs. Exact generated
  Lua source is not normalized.
- **Behavioral evidence (#8):** native engine observation/cancellation fixtures,
  real terminal launcher admission and save/restore, process lifecycle tests,
  strict-parser/fake-provider tests, and retained stock/replay regressions.
  Source-hook searches remain tripwires, not proof of gameplay behavior.

## Review correction

Specification review reproduced an incomplete pre-existing event log being
accepted as startup history. The correction rejects unterminated history in
both parent preflight and the child's first readiness iteration, before
publication/game launch. It preserves event history byte-for-byte; a private
diagnostic may still be appended to `director.log`. Live partial writes remain
buffered until complete. Regression tests failed before the correction and
passed afterward; independent focused re-review passed.

The subsequent quality review found that an existing pending mailbox could
bypass selected-pack and past-index startup validation. A shared startup
check now requires a future pending index and an exact match to the selected
fixed pack, in both preflight and child readiness. Matching pending restore
remains allowed; conflicting history/mailboxes are not overwritten or retimed.
Its regressions failed before the correction and passed afterward. See the
evidence summary for final quality re-review status.

## Evidence and limits

See [`evidence/review-foundations/summary.json`](evidence/review-foundations/summary.json)
and its adjacent logs, review records and actual terminal artifacts for current
verification and review status. Both build modes were exercised. The suite
includes controlled stock/inactive/empty-mailbox equality, save compatibility,
real rule expiry and haunting replay. The privileged ownership fixture is
explicitly skipped; nonprivileged wrong-owner validation remains tested.

These are bounded local results, not evidence of long-run game balance,
universal provider interoperability or secure public multi-user hosting.
No live game-model calls were made in this batch. Neither the lifetime cruelty
ceiling nor the experiment's request authorization changed.

## Backlog decisions

All thirteen issue bodies were reviewed and their updates read back from
GitHub. Their original snapshot and verified update list were retained.

- #1 still needs a default-visible mechanical addition; the existing Lua
  encounter is not automatically fulfillment of that Tier 2 proposal.
- #2 still needs an explicitly tested pacing policy, preferably separating
  bounded cosmetic pacing from mechanical spending rather than lifting caps.
- #6 now requires measurement and equivalent rewrite detection. Hashing only
  appended bytes plus file identity/size does not detect prior in-place edits.
  No performance optimization or durability weakening is claimed here.
- #9 masks must differ in policy, not only wording, and follow the foundations.
- #10 starts with rumor/Oracle testimony; deceptive wards are deferred and
  truthful admission warnings and audit records remain protected.
- #11 bones testimony remains deferred, opt-in and non-executable.
- #12 remains the preferred next gameplay slice: one bounded intervention
  riding ordinary prayer resolution, not replacement of the divine resolver.
- #13 expands shadow fidelity alongside a new mechanic rather than claiming
  a complete shadow world or treating finite trials as proof of safety.
