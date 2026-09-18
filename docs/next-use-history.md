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

Empty menus and rejected intents leave stock behavior unchanged.

## What this slice does not include

- Human player testing of whether the causal link is recognizable in play.
- A live, budgeted model-authored composition on an ordinary Bard start.
- Importing or executing `chaos/ordinary_route.py` as a gameplay driver.

Those remain follow-up work: player testing is issue 44; ordinary-play
model-authored composition is issue 45. This policy is the host-owned menu
used before any model sees public context.
