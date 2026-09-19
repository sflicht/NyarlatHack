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

`envelope.at` is the safe-point scheduling index. It is not the program lifetime
clock. Admission records the native move (`monstermoves` at the existing whistle
capture seam in `src/chaos_engine.c`, and the same `at_move` argument on
debit/admit) and sets `program_expiry = at_move + ttl` with the allowed TTL of
100. Runtime install keeps `envelope.at` bound to `at_safe`, checks attempt and
admission move records agree, and derives expiry and callback age from that
recorded native move. Origin deadlines also compare against `monstermoves`.
Do not treat a later observation sequence, the safe index, or `moves` as a
substitute for that native admission move.

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
refunded. Receipt delivery runs after that point. A failed receipt terminates
the program without installing a live mechanic. Precommit schema/budget
failures leave the caller's spend unchanged. The admission unit does not apply
native W/F effects; install is a separate runtime step.

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
