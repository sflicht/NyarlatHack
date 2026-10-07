# Free-design hound: live generation pilot (slice 5a, Tier B)

What it measures: the free-design hound prompt (`chaos/prompts/haunting.txt`)
through the product authoring path (`chaos.hound_author.author_hound`, the
same function the director's hound lane calls), then every envelope-valid
source through the engine's real shadow trial. It does not measure play: no
person or bot played these hounds in a game. The live capture is slice 5b.

## Run

- 2026-10-07 05:01–05:26 UTC, run `pilot5a-202610070501`.
- Grok 4.7 (`grok-4.7`) over `xai-oauth` through Hermes, authorised by Sam on
  2026-10-05. There were 20 jobs with 4 workers, on ledger surface `haunt`,
  each job a separate ledger game (`pilot5a-…-NN`).
- Every request is disclosed in `run/ledger.jsonl`. There were **20 requests,
  20 completed and none retried**, with 447,644 total tokens. No regeneration
  was needed because no envelope was rejected.
- Histories: the 17 recorded public histories in
  `docs/measurements/model-authoring-pilot/histories-public.json` that show a
  backtrack, taken round-robin. Prompts were built by `hound_author.prepare` on
  the #241 public projection only (rule 6), each with a seeded literary layer
  (`curio.seeded_layer`) chosen from a synthetic game seed.
- Host pre-check: `hound_author.HoundValidator`, i.e. the engine's own
  `chaos_lua_step` from `curio-validator.so` (sha256 `199b29ad…`), over a
  120-call grid.
- Shadow trial: `tests/chaos/haunt_room.c` linked against the built engine
  objects, the same harness as `tests/chaos/test_haunt_room.py`. It runs the
  real `chaos_haunt_tick`: forked sandbox, 64-step evasive bot, and the
  accept/refuse rule. There are 4 rooms × 3 native RNG seeds = 12 trials per
  source. The rooms are bare 6×4, bare 12×6, bare 20×8, and the recorded #194
  cornered map. `footsteps.lua` is the baseline.

Reproduce (inside `hermes-heavy`, CHAOS=1 dev install):

    pilot.py generate --lib dnethackdir/curio-validator.so --out <dir> --model grok-4.7
    pilot.py trial <dir> --work <scratch>
    pilot.py analyze <dir>

`generate --fake` checks the plumbing with no model and no network.

## Results

| | |
|---|---|
| Requests | 20 (20 completed transport rows) |
| Ready | 18 |
| Deadline (480 s) | 2: 484 s and 616 s, both `LateResponse` |
| Envelope / pre-check rejected | 0 / 0 |
| Latency, ready | min 120 s, median 233 s, max 386 s |
| Latency, all | p90 386 s |
| Shadow trials | 210 / 216 passed (97.2 %) |
| Sources passing all 12 trials | 16 / 18 |
| Sources passing none | 0 |
| Shadow failure reasons | `cornered` × 6 (the hound never let the bot get 3 squares away) |
| Baseline footsteps.lua | 12 / 12 |

The six failures all come from two sources (`10-madman-00007`,
`13-wizard-default-path-00007`), and all six are on the #194 cornered map. Both
pass every bare room. That is the case #190/#194 studied: an
oldest-trace pursuer pressing a player who has few exits. In a game the engine
would refuse such a hound in the shadow trial, and the player would see the
hand-authored fallback. No script errors, deaths, damage or stuck hounds
occurred.

End to end, 16 of the 20 requests gave a hound that the shadow trial would
accept in every tested room. That is 80 %. With the lane's footsteps fallback,
the share of games that get a hound is unchanged.

Deadline: 2 of 20 requests (10 %) finished after the 480 s deadline, at
completion lengths of about 48k tokens. The lane would treat these as
`deadline` and publish footsteps. Latency is close to the curio's
(median 138–290 s in #247).

## Variety

All 18 sources keep within the contract. They clamp state, take a single
sign step and use no libraries. Two (08, 09) use a loop bounded at 8 steps
over the history, and the rest use none. 14 anchor on `history[1]`, the
oldest echo. The pursuit ideas differ much more
than under the old prescribed prompt, which fixed one target, "the position
three observations before the newest":

- **Oldest echo with a rest beat.** It walks to the oldest trace and halts
  every k-th turn (k = 3, 4 or 5). Examples are 05, 10 and 16.
- **A rule for when it is close.** Ten sources have a special case once the
  player is within 1–2 squares. In 02, 05 and 16 (read by hand) it steps
  away. In 14 it sidesteps instead of closing in. This rule is how the model
  reads "escapable".
- **Reversal detection.** Several sources compare the player's first and
  latest moves. When the player has doubled back, the hound keeps going the
  old way (02, 13) or picks the old heading (14), so a reversal shakes it
  off.
- **Projected trace.** Source 16 subtracts the player's latest step from the
  oldest echo and aims at where the trail would have led.
- **Mirror and transpose phases.** Source 17 ("glass", carroll layer) cycles
  three phases: chase, swap dx/dy, chase inverted.
- **Axis-alternating stalk.** Source 13 moves only in x on one beat and only
  in y on the next. It walks the player's original heading on beat 3, and
  inverts it if the player folded back.
- **Turn away from your own face.** Source 10 refuses a step onto the
  player's 8th-newest position and turns aside instead.
- **One move in three.** Source 14 acts only on `state % 3 == 0` and
  otherwise stays still. When adjacent it sidesteps rather than closing in.

By hand I count about eight distinct pursuit ideas in the 18 sources. Many
combine two of them.

Two verbatim sources:

`run/jobs/16-bard-00007/a/source.lua` (713 B, carroll layer, 12/12):

```lua
return function(c)
local h=c.history
local n=#h
local now=h[n]
local echo=h[1]
local mx=c.mx
local my=c.my
local s=c.state+1
if s>1000000 then s=0 end
local cx=mx-now.x
if cx<0 then cx=-cx end
local cy=my-now.y
if cy<0 then cy=-cy end
local dx=0
local dy=0
if cx<=2 and cy<=2 then
if now.x>mx then dx=-1 elseif now.x<mx then dx=1 end
if now.y>my then dy=-1 elseif now.y<my then dy=1 end
else
local tx=echo.x
local ty=echo.y
if n>=2 then
tx=tx-(now.x-h[n-1].x)
ty=ty-(now.y-h[n-1].y)
end
if tx>mx then dx=1 elseif tx<mx then dx=-1 end
if ty>my then dy=1 elseif ty<my then dy=-1 end
if s%4==0 then dx=-dx dy=-dy end
end
if dx==0 and dy==0 then
if s%2==0 then dx=1 else dy=1 end
end
return {dx=dx,dy=dy,state=s}
end
```

`run/jobs/05-bard-inherited-00007/a/source.lua` (931 B, poe layer, 12/12):

```lua
return function(c)
  local s = c.state + 1
  if s > 1000000 then s = 0 end
  local n = #c.history
  local live = c.history[n]
  local rx = live.x - c.mx
  local ry = live.y - c.my
  local ax = rx
  local ay = ry
  if ax < 0 then ax = -ax end
  if ay < 0 then ay = -ay end
  local span = ax
  if ay > span then span = ay end
  if span <= 2 then
    local dx = 0
    local dy = 0
    if rx > 0 then dx = -1 elseif rx < 0 then dx = 1 end
    if ry > 0 then dy = -1 elseif ry < 0 then dy = 1 end
    if dx == 0 and dy == 0 then dx = 1 end
    return {dx=dx, dy=dy, state=s}
  end
  if s % 4 == 0 then
    return {dx=0, dy=0, state=s}
  end
  local idx = 1
  if s % 4 == 3 and n >= 3 then idx = 2 end
  local echo = c.history[idx]
  local dx = 0
  local dy = 0
  if echo.x > c.mx then dx = 1 elseif echo.x < c.mx then dx = -1 end
  if echo.y > c.my then dy = 1 elseif echo.y < c.my then dy = -1 end
  return {dx=dx, dy=dy, state=s}
end
```

A third source, `13-wizard-default-path-00007` (one of the two that fail on
the cornered map), is in `run/jobs/` for comparison.

## Caveats

- The close-range rule is common, and it makes many hounds "keep their
  distance" more than "pursue". It passes the trial by design: the trial
  refuses only hounds that never let the player get away. Whether these
  hounds feel threatening is for play (5b and Sam's informal playtest).
- 20 generations is a small sample. The 10 % late rate and the 2/18 cornered
  failures are rough rates, not tight estimates.
- The shadow trial in a real game uses the room and RNG state of that moment.
  These 12 fixed trials are a proxy for it.

## Files

- `pilot.py`: the harness.
- `run/`: `run-meta.json`, `ledger.jsonl` (every request), and `summary.json`
  and `trials.json` (every shadow report). It also has `jobs/<job>/a/`, a full
  evidence directory per request: prompt, raw response, source, and receipt
  with its hash chain.
- `no-model-identity/`: the no-model byte-identity check against main (see the
  PR).
