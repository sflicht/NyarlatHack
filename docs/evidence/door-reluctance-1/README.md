# #1 door_reluctance: a mechanical whisper a default player can feel

Tier A evidence. The change adds a mutation, a save-state slot (chaos state v4), an RNG-consuming rule, and an admission path on the default `python3 -m chaos play --ordinary` launcher.

## The change

**Contract.** `chaos/protocol_contract.json` is the single source. It now has a fourth current mutation, `door_reluctance`:

- id 3, cost 1, value 50, duration 1 to 300 turns, telegraph 4;
- no Sanity gate;
- rule `CHAOS_RULE_HALVE`.

Two new sections sit beside the frozen shared-metadata block, which stays byte-identical:

- `telegraph_extensions` holds telegraph 4, "The doors of this place seem to lean against you.";
- `mutation_limits.duration_cap` is 300.

Duration bounds are per mutation. `hunger_rate` and `ward_efficacy` keep their 1 to 50 bounds and still reject 51; `door_reluctance` accepts 300 and rejects 301. The generator rewrote `include/chaos_protocol.h` and `chaos/_protocol_contract.py`, and `--check` passes. The chaos state goes from version 3 to 4 to add the effect slot. Saves from state 3 are refused on restore, as #164's v3 did for v2.

**Engine.** In `doopen_indir` (`src/lock.c`), the one-line hook `chaos_door` rewrites the right-hand side of the native `rnl(20) < (ACURRSTR + ACURR(A_DEX) + ACURR(A_CON)) / 3` door test:

- while an admitted door effect is active, it is halved;
- otherwise it passes through unchanged.

The roll itself is unchanged: `rnl(20)` is drawn exactly as before, so the effect consumes no extra RNG. There is no damage and no raw stat write. The player sees only the native "The door resists!" or "The door opens.". CHAOS=0 builds a stub that returns the argument, so stock play is unchanged. The same line wraps the test's result in `chaos_door_attempt`, and `chaos_door_attempt_end` closes it at the end of the function; these open and close the `door_open` observation. Both hooks are registered in `docs/upstream-chaos-hooks.json`, and CHAOS=0 stubs them out too.

**Observation.** `door_open` is a new observation family, operation 4, with facts `opened` and `resisted`. Its projection is a new, strictly validated value, `"excluded"`:

- door roots keep their place in the event chronology;
- they never enter the 32-root next-use lookback or the episode summary (`chaos/episodes.py`, `chaos/history.py`).

This means frequent door attempts cannot evict whistle or fountain origins, and next-use is unchanged.

**Director (M1, Sam 2026-09-30, answers 1b and 2c).** The default ordinary launcher now uses `OrdinaryBackend` (`chaos/director.py`):

- The DL1 arrival safe point gets only the arrival omen (id 1, cost 0), exactly as the ambient pack published it. Nothing mechanical happens there, so the hound keeps first claim on the opening budget.
- From the second level-entry safe point on, a pick keyed on (seed, id, safe index) chooses among `ward_efficacy`, `hunger_rate` and `door_reluctance`. Each keeps its own eligibility, cost and bounds, and the omen is not on that menu.
- No RNG state is saved and no model is called.

`ordinary-choice.json` becomes record v2, with `"whispers": {"backend": "m1", "seed": N}` (null when explicit whisper flags were given). Restore follows the record and refuses conflicting flags; a v1 record keeps the old pack behaviour.

**Readers.** A v1 (pre-v3) event reader rejects an ACK that names `door_reluctance` (`chaos/protocol.py`). This is a tightening: old logs cannot contain one. All 125 committed legacy event rows still validate (`tests/chaos/test_legacy_view.py`).

## Proof

**Rule, against the real engine.** `tests/chaos/test_door_room.py` with `door_room.c` links the built game objects with a controlled `rnd.o` and calls the real `doopen_indir` on a closed door:

- it predicts each `rnl(20)` from the same seed and checks every outcome against the threshold the engine must apply: 12 normally, 6 under the effect;
- 200 attempts each way: 126 opened without the effect and 66 with it, with 0 mismatches;
- with observations on, every attempt is exactly one `door_open` root (started, then completed). The fixture initialises no window, so the native message is never tty-delivered and no root carries a notice; the notice path is shown by the real-game capture below;
- with observations off, there is no root.

**Core C harness** (`tests/chaos/protocol_harness.c`, `door_tests`) covers:

- admission at cost 1 at full Sanity, and the rule halving 11 to 5 until the expiry turn;
- the parser bounds: duration 300 accepted, 0 and 301 rejected; hunger and ward still reject 51; wrong value or telegraph rejected;
- no stacking: a second request while active is refused (`CHAOS_ACTIVE`, reported as `duplicate`) with nothing spent;
- a save/restore round trip of the state that keeps the active effect, then expiry;
- ineligible when unconscious, refused for budget when capacity is spent, and the overflow guard at the 300-turn cap.

**Director** (`tests/chaos/test_ordinary_m1.py`):

- DL1 gives only the omen;
- a DL2 arrival gives door at full Sanity;
- the DL2+ menu is mechanical only, with each kind inside its bounds;
- the same seed gives the same picks;
- a budget-probe regression: with the omen at DL1 the hound is still admitted, whereas door at DL1 would have blocked it.

**Save and restore in real play.** The paired sweep saves and restores every surviving game at turn 700. In the 51 kept games where a door effect was active across that restore:

- the effect expired on its recorded turn in every one (or the game ended first);
- 16 games met a resisting door after the restore, while the effect was still active.

**Population.** Paired sweep, main vs branch, seeds 1–100, five starts: `docs/measurements/door-reluctance-paired-1/`.

- Hound acceptance on the default path is identical to main: 88 and 88 on both bard-default-path and wizard-default-path.
- Door was accepted in 165 games: first on Dlvl 2 in 160 and Dlvl 3 in 5, never on Dlvl 1.
- Door was felt in 46 games.

**Gates on `278ef4bc8`:**

- CHAOS=0 and CHAOS=1 builds with 0 warnings;
- fast suite: 1528 tests OK (skipped 227);
- native suite: 1528 tests OK (skipped 13).

## Real nonwizard capture

These are real games of `python3 -m chaos play --ordinary` on the default path: Bard, no wizard mode, no model call. The keys come from the sweep's screen-only policy (`tests/chaos/sweep_player.py`, baseline-v2, start `bard-default-path`). The sweep's clock and seed shim was replaced by an empty preload, so each game is an ordinary random game.

Games were played one after another until one showed both the door telegraph and a door resisting under the effect. That was the 5th game. All five are listed in `capture/games.json`:

| game | outcome | door accepted | first felt |
|---|---|---|---|
| 1 | died | turn 870 | hound, turn 44 |
| 2 | died | turns 397 and 1010 | hound, turn 17 |
| 3 | died | turn 655 | hound, turn 49 |
| 4 | died | none | hound, turn 18 |
| 5 | turn limit | turn 822 | next-use W, turn 517 |

Game 5 (`capture/events.jsonl`, `capture/whispers.jsonl`, `capture/screen-messages.txt`):

- **T:1, Dlvl 1.** The omen is accepted at safe 1 (id 1, cost 0). Nothing mechanical is published there.
- **T:505, arrival on Dlvl 2** (safe 2). The only ACK is the omen's `duplicate` rejection. M1 publishes its first mechanical request only after it has seen this second level entry.
- **T:822, arrival on Dlvl 3** (safe 3). The telegraph "The doors of this place seem to lean against you." is on screen. `door_reluctance` is accepted: id 2, value 50, duration 192, cost 1, expires at 1014. Budget goes from 3 to 2.
- **T:874.** "The door opens."
- **T:904.** "The door resists!", with the effect active. This is the felt moment.
- **T:931.** A second door request is rejected as `duplicate` (no stacking).
- **T:1014.** The effect expires.
- **T:1057.** "The door resists!" again, after expiry: a native failure, because doors resist sometimes anyway.

The door in this capture reached Dlvl 3 rather than Dlvl 2 because this game's Dlvl 2 safe point came before M1 had seen a second level entry. This is by design: requests are published ahead of the next safe point.

`capture/ordinary-choice.json` is the run's choice record. One field was edited: `haunt_pack` held the absolute worktree path and is shown repo-relative. Its digest, `haunt_sha256`, is unchanged.

## Player-visible delta

On the default `python3 -m chaos play --ordinary` path, from the second level on, the Chaos may now make doors harder to open for a while. The player sees the telegraph "The doors of this place seem to lean against you.", then more "The door resists!" than usual until the effect ends. Dlvl 1 is unchanged: only the arrival omen, and the hound keeps its budget.
