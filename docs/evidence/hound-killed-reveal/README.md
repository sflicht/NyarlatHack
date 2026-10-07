# Evidence: the reveal reports a killed hound (#201)

Head 8a605ea0cb76d3209f237f7ad6eb4cf21139424e, built from a `git archive` export with
`CHAOS=1 make -j2 install` (0 warnings). Each game is a real nonwizard
`python3 -m chaos play --ordinary` run, model-free (footsteps.lua, no author
configured), driven by the `curio-capture-v1` screen policy. The full
streams, saves and tools are in the report root named in `artifacts.json`
(sha256 for every file).

## What changed for the player

Before: when the pet killed the admitted echo hound, the engine logged
nothing, the hunt kept running until the 60-move expiry, and the reveal
said "Ended: its hunt ended on turn N." with N up to about 60 turns after
the death. After: `mondead` (after life-saving is ruled out) calls
`chaos_haunt_died`, which ends the hunt and logs `haunting/killed` on the
turn of the death. The reveal then says "Ended: it was killed on turn N."

## Games

| Game | What happens | Hunt ending | Reveal line |
|---|---|---|---|
| seed-7 | pet kills the hound in view on turn 13; save/restore at turn 700; dies on turn 1356 | `killed` turn 13 | Ended: it was killed on turn 13. |
| seed-7-replay | exact replay of seed-7 | identical | identical |
| seed-4 | pet kills the hound in view on turn 27 | `killed` turn 27 | Ended: it was killed on turn 27. |
| seed-4-replay | exact replay of seed-4 | identical | identical |
| seed-12 | the seed suggested in the brief; the kill happens out of view on turn 55 (no kill message on screen) | `killed` turn 55 | Ended: it was killed on turn 55. |

`player-saw.txt` in each game folder holds the screen lines: the haunt
telegraph and, where it was in view, "Echo hound is killed!".

## Replay and save checks (`checks.json`)

- Both replays (seed 7 and seed 4) are byte-identical to their live games on
  inputs, events, whispers, the used haunting source, dreamlands.json,
  reveal.json and xlogfile. Every input was guarded (1233/1233 and 728/728).
- Seed 7's turn-700 save, live against replay
  (`seed-7-replay/save-classification.json`): 3992 differing bytes, all
  explained. They are the process id (4), heap pointers (3851), the
  /dev/urandom game token (8, plus 8 as two 4-byte halves) and 121 bytes of
  hex digests over next-use records that embed that token. 0 unexplained.

## No-death identity against main

Seeds 1, 2, 6 and 8 were played on main (6cccef24) and on this head with the
same policy. None has a hound death. In seed 2 the hound was admitted and
expired; in seeds 1 and 8 the trial was rejected; seed 6 had no haunt. For
all four, inputs, events.jsonl, whispers, reveal.json, dreamlands.json and
xlogfile are byte-identical between main and head.
