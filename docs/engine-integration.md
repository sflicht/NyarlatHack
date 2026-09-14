# Milestone 1 C integration checkpoint

Implemented: bounded opt-in transport; fixed ambient messages; real ward-count
and ordinary-food-consumption hooks; confirmed-prayer, pre-sleep, level-entry
and observed Sanity-bucket safe points; generic action attempts and state events.
Action attempts intentionally do not claim successful eating, reading, zapping,
applying or killing, nor disclose item/monster identity. Sanity and Insight are
observed at main-loop boundaries, so transient changes inside a turn coalesce.

Persistent state resides in `u.chaos`, included by existing `savegamestate` /
`restgamestate` serialization of `struct you`, not level/bones serialization.
Restore validates the state; a distinct save feature bit rejects incompatible
CHAOS layouts. Real-game save/restore acceptance remains to be exercised.

## Executed checks

- Protocol and transport plus source-seam guards: 25 unittest tests passed.
  Added RED checks before engine wiring and before fixing consumed IDs after
  display failure. Source guards verify hook presence, not gameplay outcomes.
- `make -j4 install` and final `make -j4 install CHAOS=1`: exit 0. Final build
  recompiled 152 objects after switching from CHAOS=0. No diagnostics attributed
  to chaos source files. Existing upstream diagnostics are not claimed fixed.
- `make -j4 install CHAOS=0 GAMEDIR=/tmp/nyarlathack-chaos-off`: exit 0;
  flag switch recompiled 149 objects. This checks in-place switch invalidation,
  not an independent pristine source checkout.
- Final installed CHAOS-on game ran in an isolated PTY copy. Selected a neutral
  male human Wizard with no inheritance; initial safe point admitted ambient
  request 1. Displayed fixed telegraph before ambient, recorded accepted ack,
  then confirmed quit and exited 0 with a death/result/quit event.

Local evidence (not portable test fixtures):
`/tmp/nyarlathack-hooks-red.log`, `/tmp/nyarlathack-chaos-on-build.log`,
`/tmp/nyarlathack-chaos-off-build.log`,
`/tmp/nyarlathack-chaos-final-build.log`,
`/tmp/nyarlathack-smoke-final.log`, and raw PTY/events under
`/tmp/nyarlathack-smoke-ke_wkcqj/`.

## Remaining acceptance gates

Real-game rule-effect and expiry probes, active/pending save/restore continuity,
cross-layout save rejection, stock/on-empty deterministic equivalence, complete
accepted-schedule replay, and independent review remain open. A startup/ambient/
quit smoke and transport struct round-trip do not establish those guarantees.
The sidecar and full replay harness are separate work. No Tier 3 implementation.
