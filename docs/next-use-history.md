# Next-use history policy (whistle attention and fountain remap)

This document specifies the bounded **#22 / #25** slice: recorded player
actions change which **next-use** families are eligible, not merely narration.
It does not raise the cruelty budget, authorize a model switch, or claim
ordinary-play model composition.

A **family** is eligibility: whistle attention (**W**) or fountain remap (**F**).
An **operation** inside a family is preference: quiet versus the one bounded
effect. The engine still owns legality, native RNG, spending, save, and restore.
Lua receives a copied public context. Hidden fountain fate stays hidden.

## Eligibility versus preference

Eligibility is computed from the public episode projection only (the same
32-root lookback the player-facing summary uses).

- **W** is eligible when a completed `whistling` episode has a delivered sound
  fact (`sound_high`, `sound_shrill`, `sound_normal`, `sound_strange`, or
  `sound_humming`).
- **F** is eligible when a completed `fountain_drink` episode has delivered
  `water_refreshed`.
- Incomplete drinks, foul water, blocked reach, detection-only notices, and
  merely attempted actions do **not** qualify. They are not rewritten into a
  nearby qualifying fact.

If a family has no qualifying origin, that family is absent. The selector must
not pick a different episode, a different fact, or a later object as a silent
substitute.

Preference is the legal next-use intent for an eligible family:

- W: `quiet` or `whistle_attention`
- F: `quiet` or `fountain_refresh`

Same history therefore supports more than one coherent response. Different
histories change the eligible set: whistle-only, fountain-only, both, or
neither.

## Expiry and one-shot use

Next-use remains next-use: history arms the **next** eligible whistle-attention
contact or the **next** qualifying fountain drink. After that use, the arming is
consumed. Stale origins that fall out of the lookback window expire by absence,
not by substitution.

### Native clocks

`envelope.at` is the **safe index**: scheduling only, not program lifetime.

Observation sequence (`root` / `notice_seq` / `end_seq` from `u.chaos.seq`)
is a separate counter. Do not use it as a move clock.

**Origin time** is `monstermoves` captured at the delivered observation
notice. **Admission / program time** is `monstermoves` at the safe point.
**W attention window** is `monstermoves` at capture (`activation_monstermoves`).
`moves` is the calendar/player-turn clock; it is not origin freshness and
not program age. Do not assume `moves == monstermoves` or a constant offset.

Admission records `at_move` from that native clock and sets
`program_expiry = at_move + ttl` with TTL 100. Origin freshness is
`at_move > origin.move + 100` (exclusive after the inclusive deadline
`origin.move + 100`). Unrepresentable clocks (`monstermoves < 0` or
`> 2147483547`) reject without retiming to 0 or INT_MAX. Origin capture
is skipped when the native clock cannot be stored. Do not treat a later
observation sequence, the safe index, or `moves` as a substitute.

### Intent hash compatibility

Intent digests hash the exact UTF-8 object
`{"next_use_intent_v":2,"op":"...","state":N}` with no extra quote-escaping
layer and no trailing newline. The runtime state is unsaved; there is no
on-disk intent hash to migrate. Records produced with the escaped formatter
are invalid and fail closed. There is no accept-either-hash fallback, and
historical captures are not rewritten.

### Load marker versus admission

A marker file `next_use-used.lua` is durable evidence of a complete load/copy
only. It is not admission. The process-local `checked` latch consumes this
process's one attempt after a private `next_use.lua` is opened, including
invalid Lua; absent files keep polling without latching. Partial markers are
removed and are not success.

### Admission commit

Irreversible commit is `chaos_next_use_debit` succeeding inside
`chaos_next_use_admit`: spend increases by the operation-count price and is not
refunded. One W or F costs 1; a two-operation W+F envelope costs 2. Receipt
delivery runs after that point. A failed receipt terminates the program without
installing a live mechanic. Precommit schema/budget/carrier-capacity failures
leave the caller's spend unchanged. A committed install failure does not refund
spend, does not rewind private-record sequence, and does not overwrite an
unrelated already-active runtime. Parser rejects duplicate operations and
malformed origin clocks. The admission unit does not apply native W/F effects;
install is a separate runtime step.

### Lifecycle transition table

Vocabulary is the existing slot, attention, delay and terminal enums. This is
not a broader haunting scheduler. Each declared slot acts at most once.

**W slot (`chaos_next_use_slot_w`)**

- undeclared → pending on W-only or W+F admit
- pending → consumed_quiet / consumed_delay / consumed_invalid on that
  callback
- pending → consumed_armed on extra-attention capture; consumed_suppressed
  on missing companion or failed capture
- pending → terminated_expiry / terminated_level from runtime boundary
- pending → terminated_transport only from post-commit receipt failure
  (admission, before install)

**F slot (`chaos_next_use_slot_f`)**

- undeclared → pending on F-only or W+F admit
- pending → consumed_quiet / consumed_delay / consumed_invalid on that
  callback
- pending → consumed_applied on remap; consumed_nonremappable on natural /
  early-return / native 19–30; consumed_suppressed on guard or default
  without intent
- pending → terminated_expiry / terminated_level from runtime boundary
- pending → terminated_transport only from post-commit receipt failure

W then F and F then W are both legal; a W effect record is never an F
witness, and the reverse.

**Attention runtime (`chaos_next_use_w_runtime_state`)**

- inactive until capture arms it
- armed → window_ended at A+10; departed on level change; expired on
  origin/program expiry or eviction; identity_unsafe on unsafe identity;
  invalid_terminated on invalid callback
- transport_terminated is written only by admission receipt failure

**Callback and delay**

- one `on_action` callback per pending slot use
- one delay is allowed (`delay_used`); a second delay is
  `CHAOS_INTENT_FAILURE_SECOND_DELAY` and does not act
- quiet, wrong-family, and invalid callback consume without native effect
- ticks after consume or terminate do not act, spend, refund, or resurrect

**Transport shutdown**

There is no live-runtime setter for transport shutdown. Unhealthy event
transport blocks **new** admission; it does not cancel an already-installed
native program. The `TERMINATED_TRANSPORT` slot values exist so a failed
receipt can leave a consistent terminal record without installing. Adding a
production runtime setter solely to drive that enum would invent a gameplay
path the engine does not own.

### Envelope handoff

Python publishes one complete `next_use-envelope.json` from a trusted selected
row, host scheduling fields (`at`, `id`, `run`, level, `move`, `variant`), and
engine-owned policy (`ttl` 100, cost = operation count, telegraph). Public
history facts stay in the menu; envelope `origin_refs` use engine facts
(`ordinary_whistle` / `water_refreshed`). The C reader parses that file and
returns a snapshot. Load is not admission, spend, or Lua execution. A second
publish into the same directory fails closed. Missing provenance or a
mismatched source digest is not repaired.

### Safe-point admission

`chaos_next_use_on_safe` is the production wrapper; `chaos_next_use_safe_try`
is the lower-level seam. The path is opt-in (`NYARLATHACK_NEXT_USE_ADMIT=1`)
and is not enabled merely because `next_use.lua` exists. The wrapper supplies
engine-owned 64-hex run identity (`engine_run_hex()` / `st_dev`+`st_ino`), a telegraph callback, and a receipt writer.
Admission revalidates **every** referenced origin against a two-slot
engine-owned evidence view keyed by family (W and F can coexist; binding one
family does not replace the other). Telegraph is mandatory and happens before
debit; a NULL callback is rejection, not permission to skip. A well-formed
second origin that was not independently observed, or that is stale, evicted,
wrong-run, wrong-level, or wrong-family, fails before telegraph, debit, or
install. Unrelated observations do not substitute an origin. Successful debit
is published back into the caller's `struct chaos_state` exactly once. Invalid caller
budget is rejected unchanged rather than reinitialized. A matching envelope
admits and installs once; later polls do not repeat warning or spend. Future
`envelope.at` stays pending; late, wrong-run, wrong-level, stale/missing
origin, Lua-invalid, missing/failed telegraph, receipt failure, and
tampered-source candidates reject without an effect. Linked `dog_move` now
proves extra-attention consume, TTY publication, and live `chaos_safe` admit.
F-only envelopes install as `origin_f`. `drinkfountain` remaps fate 10–18 to
`fountain_refresh` once; fate 9 stays natural; fate 19 stays native; levitation
cannot-reach; Lua `on_action` context has no fate field.
This slice does not claim save/restore or replay.

Empty menus and rejected intents leave stock behavior unchanged.

## What this slice does not include

- Human player testing of whether the causal link is recognizable in play.
- A live, budgeted model-authored composition on an ordinary Bard start.
  Host-built W/F composition now exists (`chaos/next_use_compose.py`); installing
  `next_use.lua` is not native admission.
- Importing or executing `chaos/ordinary_route.py` as a gameplay driver.

Those remain follow-up work: player testing is issue 44; ordinary-play
model-authored composition is issue 45. The public history context now
includes `next_use` so a selector can see W/F eligibility. Allowed hunger
requests remain the only choosable mailbox items in this slice.
