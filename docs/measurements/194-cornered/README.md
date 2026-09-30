# #194 cornered shadow trials: paired real-game sweep

Tier B measurement. It decided the #194 design: Sam chose option 1 (no doorways) on
2026-09-30.

## Terms

- **Shadow trial:** the echo hound's one-time rehearsal, run in a forked copy of the game
  before the hound is admitted (`src/chaos_haunt.c`, `trial`). An evasive bot plays the
  player for 64 steps. The trial passes if the bot gets at least 3 squares from the hound
  after step 8, takes at most 4 damage and doesn't die.
- **Cornered:** a refused trial with `escaped` 0. The bot never got 3 squares away, usually
  with about 30 to 60 hound contacts.
- **Stuck:** a refused trial in which the hound made at most 1 step and had no contacts.
- **No trial:** no square 3 or more away was free of the pet within the 40-key window
  (#201), so nothing was spent.

## Method

The #190 method is real nonwizard `python3 -m chaos play --ordinary --haunt`, driven by
`tests/chaos/gameplay_support.Game` and `tests/chaos/haunt_explorer.Player`. The player paces in the
start room, for up to 40 keys, until the haunting is decided. This sweep differs from #190
in two declared ways:

- **Seeded sweep clock:** the seeded clock (`tests/chaos/sweep_clock.c`,
  `NYARLATHACK_SWEEP_SEED` = seed) replaces a fresh random map per game. Seed *s* therefore
  plays the same map on both builds, and 200 of 200 games had the same start on both
  sides. The trial runs in a fork and draws nothing in the parent.
- **Admitted phase:** after an accepted haunting, the player keeps pacing for up to 70 more
  keys (the live hound lasts 60 turns). It records hound melee messages on the message
  line, HP lost and death.

Seeds are 1–200, and each build is compared with origin/main built the same way (CHAOS=1,
0 warnings). No game was retried or discarded; there were 0 harness errors.

The driver is `sweep.py`, `pair.sh` builds and runs both sides, and `analyse.py` produces
the tally (see Raw data).

## Result (games out of 200)

| Build | Revision | Accepted | Cornered | Stuck | No trial | Hound melee after acceptance | HP lost after acceptance: total / max / games with 5 or more | Deaths after acceptance |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| main | `d921cab34`, `f8bd3239b` | 151 | 3 | 4 | 42 | 0 | 137 / 12 / 5 | 0 |
| as proposed, with doorways | `89cf76230` | 148 | 6 | 4 | 42 | 0 | 133 / 12 / 4 | 0 |
| **no doorways (chosen)** | `9034e6a6f`; final head `091596fe2` | **152** | **2** | 4 | 42 | 0 | 137 / 12 / 5 | 0 |
| hound also walks the bot's squares (beyond #194) | `484686bce` | 149 | 9 | 0 | 42 | 0 | 134 / 12 / 6 | 0 |

Main gave identical results at both revisions: the first three sweeps ran against
`d921cab34` and the final one against `f8bd3239b`. The final PR head gave exactly the
no-doorways scratch result (`summary-final.json` = `summary-nodoor.json` for the build
after the change).

Per-seed changes (main → build):

- **As proposed:**
  - cornered → accepted on seeds 53, 64 and 80;
  - accepted → cornered on seeds 62, 74, 99, 103, 148 and 173.
- **No doorways:**
  - cornered → accepted on seed 64;
  - seeds 53 and 80 stay cornered;
  - no game regresses.
- **Hound too:**
  - accepted → cornered on 9 seeds;
  - all 4 stuck games become accepted.

No build had any hound melee message or death after acceptance, and HP lost after
acceptance barely moved. Passed-but-unsafe trials did not rise, although this phase had
little to measure: the pet and other monsters, not the hound, caused the HP loss.

## Why doorways made it worse

The bot is one-step greedy: each turn it takes the single step farthest from the hound.
When doorways were allowed, it stepped into a doorway or corridor mouth and stayed there.
The hound's own steps are plain floor only (`simple_floor`), so it either waited two
squares away (seed 62: 0 contacts, never escaped) or pinned the bot against the door (30
to 60 contacts). In every regressed game, the recorded final screen shows the bot next to
a doorway. Letting the hound use the same squares made it worse (9 cornered games),
because the hound then followed the bot into those dead ends.

## Linked-engine check

`tests/chaos/test_haunt_room.py` replays the recorded #190 cornered map from game 24 of the
widened sweep (`tests/chaos/haunt_maps/cornered-190-game24.txt`) in the real forked trial:

- On main's engine: accepted 0, escaped 0, 60 contacts. The test fails.
- On this branch: accepted and escaped, with the bot using the stairs and the fountain.
- If those two squares are made water, a closed door, a trap or a doorless doorway, the map
  stays cornered.

## Limits

- **Scripted player:** one scripted pacing player, in the start room only, 200 seeds. The
  remaining ~1% cornered games (seeds 53 and 80) are accepted as the residual.
- **Screen-derived measures:** the admitted-phase figures come from the screen (melee
  messages and the HP status line), not from engine state.
- **Clock bias:** the sweep clock is the same new-moon night as the other sweeps (see
  `docs/measurements/seed-sweep/README.md`).
- **Start:** Bard only, the ordinary default start.

## Files

- `summary-full.json` (as proposed), `summary-nodoor.json`, `summary-houndtoo.json`,
  `summary-final.json` (final PR head): the `analyse.py` output for each paired sweep.

Raw data is on the project host in `~/.hermes/reports/nyarlathack-194/`, with
`SHA256SUMS`. It holds:

- per-game rows with the final screen: `sweep-*/before.jsonl` and `after.jsonl`;
- build logs;
- `sweep.py` (sha256 `713d362a…`), `pair.sh` (`27fd40aa…`) and `analyse.py` (`3e2fa476…`);
- the linked replays of the six #190 cornered maps (`before/`, `after/`, `after-corr/`,
  `n24-*/`, `maps/`);
- `NOTES.md`.
