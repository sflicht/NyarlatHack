# Next-use whistle attention (W)

This is the W subset of the operation catalogue. It is not a new companion
power, not ordinary-play proof, and not fountain remap.

## Trigger

An **ordinary** `WHISTLE` in inventory, identified (`known`), quantity 1, not an
artifact. Magic/bone/artifact/eucalyptus/leaf paths are excluded. Capture runs
from `chaos_next_use_whistle_completed` after a completed whistling episode.

## Legal companion

Exactly one currently visible little dog (`PM_LITTLE_DOG`) on the TTY map,
tame, with `MX_EDOG`, not the steed/rider, unleashed, not a summon, not an
exploder, not under Conflict/berserk. Unsafe or reused `m_id` values do not
bind a replacement.

## Window

Capture records `monstermoves` as activation A. Extra attention is offered only
when `A+5 <= monstermoves < A+10`, the bound `m_id` still matches, and the
slot is still armed. One W slot is consumed at most once.

## Native decision

`dog_move` passes `whappr || extra_attention` into `dog_goal`. The measured
effect is that extra-attention path, not a new AI. Quiet/wrong-family/no
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
