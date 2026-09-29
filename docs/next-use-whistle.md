# Next-use whistle attention (W)

This is the W subset of the operation catalogue. It is not a new companion
power, not ordinary-play proof, and not fountain remap.

## Trigger

An **ordinary** `WHISTLE` in inventory, identified (`known`), quantity 1, not an
artifact. Magic/bone/artifact/eucalyptus/leaf paths are excluded. Capture runs
from `chaos_next_use_whistle_completed` after a completed whistling episode.

## Legal companion (#196)

A qualifying companion is any tame monster with dog data (`MX_EDOG`) that the
TTY map currently shows as a pet at its own square: not the steed/rider,
unleashed, not a summon, not an exploder, not under Conflict/berserk. Before
#196 only a little dog (`PM_LITTLE_DOG`) qualified, and only when it was the
only one in view. Unsafe or reused `m_id` values do not bind a replacement.
The code is `chaos_next_use_companion_pick` in `src/chaos_engine.c`.

**Several in view.** The engine binds the one nearest the player by squared
distance (`dist2`). A tie goes to the top row, then the leftmost column. The
monster list order and `m_id` never decide, and the pick draws no random
numbers.

**None in view at the safe point.** A program with a W operation is not
admitted: the safe point records `no_companion_in_view` in the decision row,
shows no telegraph and charges nothing. Only what is on screen counts.

**None in view at the whistle.** Unchanged: the program ends with
`W_CAPTURE_SUPPRESSED` and nothing is refunded. There is no waiting.

**Recorded reason.** The `W_CAPTURE_SUPPRESSED` effect row now carries
`"suppression"`: 1 no tame companion in view, 2 one in view but none
qualifying (for example leashed), 3 the chosen companion failed the recheck
at capture. The same value rides in the replay record's `end_reason`, and the
journal reader rejects a row where they disagree. Journals written before
#196 have no key and read as before.

## Window

Capture records `monstermoves` as activation A. Extra attention is offered only
when `A+5 <= monstermoves < A+10`, the bound `m_id` still matches, and the
slot is still armed. One W slot is consumed at most once.

## Native decision

`dog_move` passes `whappr || extra_attention` into `dog_goal`. The measured
effect is that extra-attention path, not a new AI. `tests/chaos/
test_next_use_dogmove.py` checks it on a dog, large dog, kitten, housecat and
pony as well as the little dog: the companion stays tame and peaceful, moves
toward the player, and the move is published on the map. Quiet/wrong-family/no
companion/dead companion/out-of-window cases must match the no-candidate
control, including RNG accounting.

## Price, cap, expiry

Admission cost is the operation count (1 for W-only). Program TTL is 100 native
moves from admission. Origin lookback is the existing 32-root public window.
Warning/telegraph precedes mechanical application.

## Identification

Hidden or undelivered map/message events are not witnessed. TTY publication
certificates are required before a public witness record. No extra RNG draw is
introduced solely to construct observations.

## Exclusions

Magic whistle rally, cursed humming, hallucination, NOREP/NOSHOW message
filters, and fountain remap are out of this ticket.
