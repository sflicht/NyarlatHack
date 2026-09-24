# One bounded, learnable whistle/fountain relationship

This is the design contract for #96, not proof of ordinary availability, player
learning or full-run recurrence. W denotes the existing whistle-attention
capability; F denotes fountain refresh. Gameplay integration follows #66/#67;
#44 owns actual human evaluation and #45 owns live-model evidence. This document
adds no executable programme, mechanic, policy allowance or literary encounter.
At the earlier design-only checkpoint, “ordinary acceptance is still open” was
the recorded status. This note does not itself clear that gate; see the
[subsequent native ordinary evidence](next-use-ordinary.md) for its development
demonstration and limits.

## Rule and two distinguishable opportunities

A **delivered manifestation of this programme's W effect**, not merely admission,
a warning or physical application, permits a later F callback to request refresh.
Without that witness the F callback returns quiet. Thus the first opportunity is
visible companion attention; the later opportunity is a fountain drink whose
permitted intervention depends on the first outcome. Motif and prose are not
the rule, and no story-specific C edit is needed.

The existing `witness_lua` in
[`next_use_compose_fixture.c`](../tests/chaos/next_use_compose_fixture.c) already
expresses this computation. Its exact bounded-state contract is:

- Initially Lua state is 0 and both host-owned slots are pending.
- On W, return `whistle_attention` with state 0. The W slot is used once. The
  engine, not that return value, later determines whether a manifestation was
  delivered. Lua's state 0 is not a stored claim of success.
- On F with `own_witnessed` equal to `W`, return `fountain_refresh` with state 1.
- On F without that witness, return `quiet` with state 0. This also consumes F;
  drinking before W cannot reserve or resurrect a later refresh opportunity.
- There is no third callback, loop or script-created target. Once the used slots
  and any native in-flight work settle, the programme ends. Original expiry,
  level departure and other native terminal conditions can end it earlier.

The companion's native motion and the later drink are different opportunities,
not two copies of a name or message. Whether their connection is recognizable
is still an empirical question.

## Evidence available to the programme

Admission needs both independently engine-observed, eligible origins: a delivered
qualifying ordinary whistle episode and a delivered qualifying fountain-refresh
episode. Each family retains its own origin identity. Current game/level,
freshness, delivery and bounded-retention checks must all pass before admission;
an unrelated observation cannot stand in for either origin. See
[`envelope_origins_ok`](../src/chaos_next_use_safe.c) and the
[mechanics guide](../chaos/prompts/next-use-mechanics.txt).

These origins select a candidate; they do not prove that its future effects
happened. At callback time the existing copied public context supplies `trigger`,
`state` and `own_witnessed`. The last field refers to this programme's validated
W manifestation. Prior accepted/expired whisper history in the author prompt is
not a substitute for that witness. Missing historical applied/witnessed facts
remain missing, not inferred from an acknowledgement.

The engine retains private companion/level bindings. Lua does not receive map
coordinates, native target identifiers, the fountain's hidden fate, or a way to
manufacture a certificate. The [presentation contract](next-use-presentation.md)
distinguishes an applied effect, a delivered message, a completed public
manifestation and human notice. A warning alone is not the first manifestation.

## Choices the player can actually make

After admission, a player can engage by making the next qualifying whistle
attempt and, after a delivered manifestation, choosing a later fountain drink.
That drink may exercise the existing refresh remap if its native branch is
eligible. It is not a guaranteed reward for every drink.

A player can instead avoid the whistle attempt, or refuse the later encounter
by not drinking until expiry or by leaving the level. Ordinary play remains
available: no forced quest, compelled drink or companion death is introduced.
Another meaningful action order is to drink first: F is quiet and consumed,
even if W subsequently manifests. Refusal does not refund the admission debit.

**The author/host's quiet menu choice is not a player refusal interface.** This
corrects the earlier shorthand in this note. A quiet candidate is a control
condition; actual refusal here consists of ordinary player actions or inaction.
No new refusal button or script-generated dialogue is assumed.

## Bounds and ending

The following are current source-backed constraints, not proposed increases:

- One admitted next-use programme per logical game under the existing admission
  latch; no concurrent stack and no second admission after restore.
- Two declared operations cost two existing cruelty points, debited once at
  admission. Quiet, unsuccessful delivery and expiry do not refund them. The
  ordinary engine budget and its existing lifetime ceiling of 12 points remain
  in force; this design grants no budget.
- At most one W use and one F use. The existing script-state range is 0 through
  3; this source uses only 0 and 1. It does not request the optional delay.
- Programme expiry is 100 monster-clock ticks after admission. W's native
  attention opportunity begins five monster-clock ticks after its captured
  whistle and ends at ten. Observation sequence and safe-point index are not
  clocks, and player moves must not silently replace monster-clock time.
- The native W adapter retains its exact eligible-companion and visibility
  restrictions. No forced death, hostility edit or hidden weakness targeting.
- F can remap at most one eligible native fate-10-through-18 branch. The existing
  refresh path makes one native `rnd(10)` gain, in hunger or energy according to
  native race handling. Natural refresh and excluded/early-return branches stay
  native; no scripted amount, extra draw, infinite refresh or predictable farm
  is granted. See [`drinkfountain` / `fountain_refresh`](../src/fountain.c).
- Save/restore keeps the same source, identities, deadlines, used slots and
  witnessed status. It does not reread the candidate as authority or create a
  new learning opportunity. See [snapshot ownership](next-use-snapshot.md).

These bounds follow the existing
[admission commit](../src/chaos_next_use_admission.c),
[safe admission latch](../src/chaos_next_use_safe.c) and
[runtime](../src/chaos_next_use_runtime.c). A two-opportunity bounded episode is
not evidence of a recurring haunting over a whole game.

## Declared offline comparison

The following comparison is a reusable test specification, not a claim that a
new ordinary experiment ran. Reuse #67's native author-composition and Unix
fixtures and #65's exact-input replay; do not build another simulator.

1. Retain the real fixed-menu W-only and F-only baselines as separate arms. The
   current menu selects one family; do **not** call either a budget-matched
   two-family baseline. Keep their different costs/use opportunities explicit.
2. For a matched two-family mechanism control, propose a handwritten source that
   always requests attention on W and refresh on F, irrespective of witness.
   This is a proposed constant-per-family fixture, not an already supported
   two-family menu entry or evidence of model intelligence. Compare it with the
   existing witness source using the same two capabilities, costs, geometry and
   admissible origin bindings. Any new fixture execution remains separately
   identified from already measured tests.
3. Cross the source choice with W-then-F versus F-then-W, delivered versus
   genuinely unpublished W, quiet source, and no candidate. Vary prior accepted
   versus expired whisper history independently; it must not promote an
   undelivered current W to witnessed.
4. Include ordinary refusal: no later qualifying whistle/drink, expiry, or level
   departure. Record empty, unqualified and uninteresting runs as outcomes;
   never seed-fish, rescue with wizard mode or substitute a fake origin.
5. In native comparisons retain exact source/envelope, inputs, messages, target
   identity, native effect, delivery record, spend, slot use and terminal state.
   Include an actual save/exit/restore checkpoint and exact recorded-input
   playback. Missing effect, lost witness and dropped-program controls must
   still fail their positive oracles; no repair of historical comparators.

Existing controlled tests already measure the state-source versus witness-source
split, published versus unpublished W, operation order and native continuation/
replay. Their source is
[`test_next_use_author_composition.py`](../tests/chaos/test_next_use_author_composition.py),
[`test_next_use_unix_save.py`](../tests/chaos/test_next_use_unix_save.py) and
[`test_next_use_native_playback.py`](../tests/chaos/test_next_use_native_playback.py).
That evidence is not the proposed full comparison or ordinary refusal study.

## Proposed small human pilot, after the ordinary baseline

Extend #44 with a predeclared order of eligible ordinary sessions and control
conditions. Do not disclose the intended whistle/fountain connection beforehand.
At neutral stopping points ask what, if anything, changed; what the player thinks
caused it; and what they would try or avoid next. Record incorrect hypotheses,
no-notice answers, absence of qualifying opportunities and abandoned sessions.

Keep four observations separate: engine-certified delivery; the player's
unprompted report of noticing; their causal attribution; and a subsequent action
that they say followed from that hypothesis. Do not convert terminal output into
human notice. Keep the planned action and actual choice, including refusal,
without treating every action difference as a causal effect estimate.

Natural fountain refresh has the same native cue and can confound attribution.
A small hunger/energy gain may be uninteresting; the short attention window and
need for both origins may prevent a usable sequence. These are unresolved design
limitations, not excuses to select only a successful story. Human evidence,
ordinary pacing and any live-model intelligence remain unmeasured here.

## If repeated cycles are necessary

Do not reset a consumed slot. Do not raise the use cap, cruelty budget or effect
privilege under this design. The present one-admission latch blocks a later
programme even when it uses already authorized operations. If human evidence
shows that two opportunities cannot support learning, the smallest proposal for
review is **one additional admission after the first programme is terminal**:
retain the same global spending allowance, prohibit overlap, require fresh
independent origins, and give the new programme its own unchanged expiry/use
limits. A bounded admission counter and compatible save/replay representation
would need review; it must not be implemented by deleting the current latch.

This is a policy proposal only, not authorization or an implementation. It does
not increase per-capability uses, effect privileges or budget, and does not close
#22/#25 or establish full-run pacing. Gameplay integration still follows #66/#67.
