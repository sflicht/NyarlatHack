# Pets never attack the echo hound: real-play before/after (Tier B)

Sam's decision (2026-10-08, about 11:22Z): "Pets won't attack it". The change
makes tame monsters never target, hold a grudge against, or return an attack
on the admitted echo hound. The player can still kill it, and it still gives
up after about 60 turns. This measurement checks what that does in real play.

## Protocol (written and committed before any game was run)

- **Games:** 50 real nonwizard `python3 -m chaos play --ordinary` games per
  tree (#198 defaults: hound and next-use on), each on a fresh random map.
- **Trees:** `main` at 8715309f against this branch's head. Both are git
  archive exports, each built with `make -j2 install CHAOS=1` (clean env).
  The games alternate between trees (main 0, head 0, main 1, ...) under
  hermes-heavy.
- **No model:** no `NYARLATHACK_AUTHOR_*` settings, so the hound is
  `footsteps.lua` and there is no hound lane. `measure.py` refuses to start
  if any author setting is present and records whether a hound lane appeared.
- **Driver:** the #190 screen driver (`tests/chaos/haunt_explorer.Player`),
  exactly as #201's `baseline.py`. It paces the start room until the trial is
  decided (at most 40 keys). If the hound is admitted, it keeps pacing until
  the haunt expires, the hound is killed, or 90 keys pass.
- **Measures** (per admitted hound; `analyze.py`, #201's attribution):
  - admitted;
  - killed by the pet / by the player / expired alive (and alive at end);
  - live steps (`haunt_step` events, which the engine emits only when the
    player can see the hound): median, mean with a bootstrap 95% interval,
    and the distribution;
  - lived 10+ turns after admission.

## Expected direction (stated before running)

- **Primary:** killed by the pet falls from most admitted hounds on main (26 of
  36 in #201's after run) to **0** on the head. Any pet kill on the head is a
  path this change left open and will be reported as such.
- **Secondary:** mean live steps and "lived 10+ turns" rise on the head, and
  "expired alive" and "killed by the player" rise with them.
- **Unchanged (no direction expected):** admitted count and admission turn.
  Placement is untouched, so differences there are noise.
- The pet may still stand in the hound's path, and the driver stops at 90
  keys, so a hound that is still alive then counts as "alive at end", not
  "expired alive".

## Results

Not run yet. The results and the evidence revision are added below once the
runs are finished, whatever they show.
