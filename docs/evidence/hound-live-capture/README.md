# Live model-hound capture (slice 5b, Tier A)

In live attempt 002, a real nonwizard ordinary game played with Sam's launcher
and Sam's flags, the free-design hound went from trigger to reveal. The first
public backtrack happened at turn 46. The hound lane then made one Grok 4.7
request over xai-oauth, and the answer came back ready in 293 s. The lane
published the source, and the engine admitted it at turn 52, with its
shadow-trial receipt. The telegraph appeared on screen. The hound followed the
trail 3 times, and the pet killed it at turn 88. The engine closed the hunt at
the 60-turn expiry on turn 112. At the end of the game the reveal was opened.
A curio ran in the same game too.

The model-free replay was exact for both lanes. The engine first looked at the
recorded source in exactly the recorded window (turn 52, sequence 10). Every
artifact the check names is byte-identical. The turn-700 save differs only by
the run's /dev/urandom token, the process id and raw pointers, and each
differing byte is named below.

Model calls: 2 requests in total, both disclosed below: 1 on ledger surface
"haunt" and 1 on "curio".

## What ran

- **Build:** commit `a439ad1fc`, which records Sam's decision in the proposal
  §8. It was a fresh CHAOS=1 `make install` from a `git archive` export, with
  0 warnings and the validator installed in the game root.
  `git diff --stat a439ad1fc <PR head>` touches only this directory.
- **Launcher:** Sam's entry point `scripts/hermes_play.py play`, run unchanged
  as `__main__`, with Sam's flags: `--ordinary --max-runtime 86400
  --author-provider xai-oauth --author-model grok-4.7`.
- **One extra flag:** `--curio-validator <export>/dnethackdir/curio-validator.so`.
  The capture gives each attempt its own game root holding only `dnethack`,
  `nhdat` and `license`. Sam's install keeps the validator in its game root,
  where the launcher finds it without the flag.
- **Hound:** the model hound by default (Sam, 2026-10-07, "On by default
  (Recommended)"). Nothing was installed at start, and footsteps.lua stayed
  the fallback.
- **Driver:** the `curio-capture-v1` player (`tests/chaos/curio_capture_player.py`),
  unchanged.
- **Harness:** outside the repository, under `~/.hermes/reports/nyarlathack-5b/tools/`,
  with SHA-256 digests in `artifacts.json`.
- **Timing pause:** as in #247, the harness pauses wall time after each action
  while either lane's durable record says `requested`, for at most 900 s. The
  game does not advance during that pause. The engine still decides when it
  looks.
- **Trigger:** the engine's own first `backtrack` event. Nothing was forced.

### Seed choice

Seed 12, chosen from public recorded outcomes only. The #247 evidence for
seed 12 (`docs/evidence/curio-live-capture/attempt-013/run/events.jsonl`)
shows the first public backtrack at turn 46 and the footsteps hound admitted
at turn 52. That recorded outcome shows the real trigger early in the game,
with room for a hunt to play out.

### Attempts (every one disclosed)

| Attempt | Seed | Requests | Outcome |
|---|---|---|---|
| 001 | 12 | none | Stopped before the game started. `hermes_play.py` looks for the Hermes checkout under `$HOME`, and the capture's game `HOME` is the attempt root. The harness now sets `HERMES_AGENT_DIR`. No ledger rows. |
| 002 | 12 | haunt 1, curio 1 | **Qualifying.** Details below. |

- **Ledger rows** (`attempt-002/ledger-rows.json`):
  - haunt: attempt `c242c9b7…`, HTTP 200, 293.188 s, 26,010 tokens;
  - curio: attempt `bfa3f624…`, HTTP 200, 192.65 s.
- **Per-game caps:** haunt 1 of 3, curio 1 of 3.
- **Daily cap (UTC 2026-10-07):** haunt 21 (including the 20 slice-5a pilot
  requests) and curio 1, against the 200 per day shared with Sam's own play.
- **No lane fell back to footsteps.**
- **In-game shadow-trial refusals of a model hound: 0.** One model hound
  reached the engine, and it was accepted.

## Evidence, point by point

| Requirement | Result |
|---|---|
| Lane requests after the backtrack, with latency | First public `backtrack` at turn 46, seq 7. The hound lane then moved `idle → requested` at safe point 1, with no request before that event. The answer came back `ready` in 293.197 s (lane clock; transport 293.188 s, HTTP 200), within the 480 s deadline. Transitions: `attempt-002/lane-transitions.jsonl`. |
| Model source published | `requested → ready → published` 3 ms after `ready`, written as `haunting.lua` by rename. `haunting-used.lua` equals `haunt-evidence/source.lua` byte for byte (SHA-256 `29322c2b…14a3e3`). Host pre-check: admitted, 120 grid calls, 0 failures, 64 moves, 5 distinct steps. |
| Engine admits at its next qualifying tick | `haunting pre_admitted` (turn 52, seq 10), then `haunting accepted` (turn 52, seq 11). The two cruelty points were spent at that tick. `haunt-admission.json` binds window (52, 10) and the source hash. |
| Shadow-trial receipt | `dreamlands.json`: `{"accepted":1,"sandboxed":1,"steps":64,"moved":3,"blocked":60,"contacts":0,"died":0,"script_errors":0,"escaped":1,"max_damage":0}`. |
| Telegraph on screen | `T:52 Something has learned the rhythm of your footsteps.` (`attempt-002/player-saw.txt`). |
| Hound follows the trail | `haunt_step` events at turns 82, 84 and 87. The reveal says "Delivered: yes, you saw it follow your trail 3 times." |
| Hunt ends | On screen at turn 88: "Echo hound misses the little dog. The little dog bites echo hound! Echo hound is killed!" The engine logged `haunting expired` at turn 112, the 60-turn expiry (52 + 60), and the reveal says "Ended: its hunt ended on turn 112." See the note below. |
| End-of-game reveal opened | `Do you want to know what watched you? [ynq] (n) y`, then "The Crawling Chaos remembers." with the haunting entry (`player-saw.txt`, `run/reveal.json`). |
| Curio in the same game | The curio lane requested after the hound published. Its answer came back ready in 192.66 s, and it was admitted at turn 348, safe point 2, on arrival at DL2. It is placed only on a fresh main-dungeon DL3, and this game never reached DL3, so it was never placed. Its replay holds too (below). |

**Hound death vs. expiry.** The engine records no event when the hound dies.
Its hunt state stays active until the expiry or a level change, so the reveal
gives turn 112, not the kill at turn 88. Both are legitimate ends of the hunt.
This is existing engine behaviour, not new in 5a. It is also another case of
the #201 pattern: the starting pet kills the hound.

## The model's source (verbatim, 107 lines)

```lua
return function(c)
  local s = c.state
  if s == nil or s < 0 then s = 0 end
  if s > 1000000 then s = 0 end
  local ns = s + 1
  if ns > 1000000 then ns = 0 end
  local h = c.history
  local n = 0
  if h ~= nil and h[1] ~= nil then n = 1 end
  if h ~= nil and h[2] ~= nil then n = 2 end
  if h ~= nil and h[3] ~= nil then n = 3 end
  if h ~= nil and h[4] ~= nil then n = 4 end
  if h ~= nil and h[5] ~= nil then n = 5 end
  if h ~= nil and h[6] ~= nil then n = 6 end
  if h ~= nil and h[7] ~= nil then n = 7 end
  if h ~= nil and h[8] ~= nil then n = 8 end
  local dx = 0
  local dy = 0
  if n == 0 then
    if s % 2 == 0 then dx = 1 else dx = -1 end
    return {dx = dx, dy = dy, state = ns}
  end
  local px = h[n].x
  local py = h[n].y
  local ax = px - c.mx
  local ay = py - c.my
  if ax < 0 then ax = -ax end
  if ay < 0 then ay = -ay end
  local dist = ax
  if ay > dist then dist = ay end
  if dist <= 1 then
    if px > c.mx then dx = -1 elseif px < c.mx then dx = 1 end
    if py > c.my then dy = -1 elseif py < c.my then dy = 1 end
    if dx == 0 and dy == 0 then
      if s % 2 == 0 then dx = 1 else dx = -1 end
    end
    return {dx = dx, dy = dy, state = ns}
  end
  local beat = s % 4
  if beat == 3 then
    return {dx = 0, dy = 0, state = ns}
  end
  local tx = h[1].x
  local ty = h[1].y
  local sx = 0
  local sy = 0
  local mis = 0
  if n >= 2 then
    local fx = h[2].x - h[1].x
    local fy = h[2].y - h[1].y
    local lx = h[n].x - h[n - 1].x
    local ly = h[n].y - h[n - 1].y
    local fsx = 0
    local fsy = 0
    local lsx = 0
    local lsy = 0
    if fx > 0 then fsx = 1 elseif fx < 0 then fsx = -1 end
    if fy > 0 then fsy = 1 elseif fy < 0 then fsy = -1 end
    if lx > 0 then lsx = 1 elseif lx < 0 then lsx = -1 end
    if ly > 0 then lsy = 1 elseif ly < 0 then lsy = -1 end
    if (fsx ~= 0 or fsy ~= 0) and fsx == -lsx and fsy == -lsy then
      mis = 1
      sx = fsx
      sy = fsy
    end
  end
  if mis == 0 then
    if tx > c.mx then sx = 1 elseif tx < c.mx then sx = -1 end
    if ty > c.my then sy = 1 elseif ty < c.my then sy = -1 end
  end
  if beat == 0 then
    dx = sx
  elseif beat == 1 then
    dy = sy
  else
    dx = sx
    dy = sy
  end
  if dx == 0 and dy == 0 then
    if tx > c.mx then
      dx = 1
    elseif tx < c.mx then
      dx = -1
    elseif ty > c.my then
      dy = 1
    elseif ty < c.my then
      dy = -1
    elseif s % 2 == 0 then
      dx = 1
    else
      dx = -1
    end
  end
  local qx = c.mx + dx
  local qy = c.my + dy
  local rx = qx - px
  local ry = qy - py
  if rx < 0 then rx = -rx end
  if ry < 0 then ry = -ry end
  if rx <= 1 and ry <= 1 then
    dx = 0
    dy = 0
    if px > c.mx then dx = -1 elseif px < c.mx then dx = 1 end
    if py > c.my then dy = -1 elseif py < c.my then dy = 1 end
  end
  return {dx = dx, dy = dy, state = ns}
end
```

**What it does.** The hound walks a four-beat rhythm: a horizontal step, a
vertical step, a diagonal step, then a rest. It aims at the oldest remembered
position, so it retraces the trail from its start. When the trail's first and
last legs point in opposite directions (the player doubled back), it keeps
heading along the first leg instead. It never closes in: if it is next to the
player, or its step would land next to the player, it steps away.

**How it played.** In the shadow trial it moved 3 times in 64 steps and the
player escaped. In the game it was a timid, rhythmic follower: three visible
steps on the trail (turns 82, 84 and 87), never in contact with the player,
and then the pet killed it. This matches the 5a pilot's caveat: the
keep-distance rules make these hounds less threatening than footsteps.

## Exact model-free replay (replay 002)

The launcher was the plain `python3 -m chaos play --ordinary --max-runtime 86400`,
with no author flags, so no backend can be built. On top of that, the replay
harness patches these to raise: `XaiBackend.__init__` and `generate`, both
lanes' `build_backend`, `author_hound` and `author_curio`. It never imports
Hermes.

Before the director forked, the harness staged the recorded hound with
`hound_director.stage_replay`, the same function `chaos replay --haunt-evidence`
calls. That writes the exact source plus `haunting-due` = "52 10". The curio
was staged with `curio_director.stage_replay`. Without author flags the
launcher would install footsteps.lua at start, so the harness skips that one
call (`staged.json`: `start_pack_skipped`). In the live game nothing was
installed at start either.

| Check | Result |
|---|---|
| Input guard | 1176 of 1176 input chunks matched the live tape before each was sent. |
| Byte-identical | `inputs.json`, `events.jsonl`, `whispers.jsonl`, `haunting-used.lua`, `dreamlands.json`, `reveal.json`, `xlogfile`, `curio-used.lua`: all true. |
| Engine window | `verify_replay`: first look (52, 10) `pre_admitted`, source `29322c2b…`. This equals the record. |
| Curio replay | `curio_director.verify_replay`: safe point 2, source `ace2baf9…`. This equals the record. |
| Ledger | Unchanged across the replay. |
| Save, byte for byte | The turn-700 save was copied before restore consumed it: 316,875 bytes, equal length. 3,082 bytes differ, in 772 runs. **next-use transport token:** 8 bytes. This is the /dev/urandom game token, equal to each run's `next_use-owner` (`26b950ab808f1a2f` live, `50eb52fc96f70875` replay). **hackpid:** 4 bytes, the process id (3893972 live, 3910271 replay). **Raw pointers:** 3,070 bytes, in-memory addresses that dNetHack serialises as-is (ASLR). **Unexplained:** 0. See `replay-002/save-classification.json`. |

## Rule 6

The prompt was composed from the first 1,961 bytes of native events, ending
at the turn-46 `backtrack` event (seq 7). Their SHA-256 matches
`prompt.json`'s `history_event`. The prompt's `public_history` equals
`public_context(HistoryState(prefix))` (`replay-002/result.json`:
`prefix_sha256_equal` and `public_history_equal` are both true). The literary
layer was `gilman`, seeded from the game.

## Files

- **`attempt-002/`:** the live run.
  - `inputs.json` and `manifest.json`: the input tape and session manifest.
  - `run/`: the engine and lane records, both evidence chains
    (`haunt-evidence/`, `curio-evidence/`), the admissions, the reveal and
    the shadow receipt.
  - `xlogfile`, `ledger-rows.json`, `lane-transitions.jsonl`.
  - `player-saw.txt`: screen excerpts.
  - `result.json` and `preflight.json`.
- **`replay-002/`:** the replay's checks (`result.json`), the save
  classification and what was staged.
- **`artifacts.json`:** SHA-256 digests of every retained file under
  `~/.hermes/reports/nyarlathack-5b/`, including the full terminal streams,
  saves and harness. That covers files that embed host paths, such as
  `ordinary-choice.json`.
