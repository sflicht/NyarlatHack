# Milestone 2 — The First Haunting

This is a working **single-encounter constrained-runtime prototype**, not a
general-purpose script engine or a security certification. Implementation
stayed inline. A final read-only reviewer checks the completed
diff separately. Game-model experiments use plain inference through the
explicitly authorized ChatGPT subscription route, not coding-agent delegation.

## Play it with no model call

Install the additional build dependency, then build from the repository root:

```sh
sudo apt-get install liblua5.4-dev pkg-config
make -j4 install CHAOS=1
RUN=$(mktemp -d)
python3 -m chaos haunt --run-dir "$RUN" --source chaos/packs/luna-footsteps.lua
(cd dnethackdir && NYARLATHACK_RUN_DIR="$RUN" ./dnethack -D -u wizard)
```

Use the terminal (TTY) window port. Choose a human Wizard with no inheritance.
For the demo, type `#setsanity`, Enter, then `60`. Walk back and forth across
open floor, recording enough positions to establish backtracking. This was
exercised in the terminal tests; a cramped or obstructed start can defer or
reject an encounter instead of forcing a placement.

The game considers one candidate when it has observed backtracking, has at
least four recorded positions, has two available cruelty points, and can place
a creature on visible, unoccupied, trap-free floor at least three squares away.
The candidate must pass its real shadow trial first. A fixed warning precedes
the live spawn. The **echo hound** uses the existing jackal's body and ordinary
attacks; its script changes only ordinary movement selection. It is not
invulnerable, and it can be killed.

The supplied program pursues a position **three recorded observations before
the newest one**, rather than the player's present position. Observations are
sampled at turn-loop boundaries; this is not a promise of precisely three global
turns under every speed/status effect. The program has a sixty-game-turn active
window and stops controlling the creature after expiry or a level change.
History and expiry maintenance continue if the run directory is absent on
restore or the event log fails; unhealthy transport blocks new admission, not
maintenance of an already-admitted rule.
Afterward the existing creature is governed by ordinary game behavior; it is not
erased from the world.

`chaos/packs/footsteps.lua` is hand-authored. `chaos/packs/luna-footsteps.lua` is
the **exact source returned by GPT-5.6 Luna**, preserved without editing. Its
source digest and generation receipt are in `docs/evidence/`.

## See a Dreamland echo

Echoes currently enter **message history**, not a pop-up or an extra prompt.
Use the game's usual Ctrl-P history command to see them. This placement is
intentional: inserting a normal message can create an unsolicited “More” prompt
and consume the next keypress.

After an actual shadow outcome, a fragment can become perceptible when Sanity
is at most sixty, Insight is positive, or the character wakes from sleep. The
terminal port is the implemented echo surface. The fixed messages distinguish
movement in the shadow, a script failing to take shape, and a final shadow death.
Final-death capture is after the game's lifesaving path, before death-file writes.

The executed rejection test used a looping script and observed:

> Something in your dream refuses to take shape.

The fragment was grounded in an actual failed Lua execution inside the forked
simulation. A malformed file rejected before shadow execution produces no fake
Dreamlands story. Turning echoes off with `NYARLATHACK_ECHOES=0` changes only
presentation. Paired real-game tests had identical inputs, event records and
score logs with echoes on/off while the fragment appeared only in the enabled
history. No gameplay random draws, turns, sanity, damage or budget changes are
performed by history insertion. Echoes are separate from mandatory admission
warnings. Death-echo wording is implemented; the recorded echo demonstration
was the script-rejection case, not a claimed observed shadow death.

## What the script can do

Lua 5.4 source is at most 4,096 bytes. Each decision gets a **fresh interpreter**,
no standard libraries, a 256 KiB allocation limit (KiB means 1,024 bytes), and
an instruction hook that stops execution at 20,000 counted instructions.
Text-only loading rejects precompiled bytecode.

Source returns a function. Its argument `c` is a copied input table:

- `c.mx` and `c.my`: the creature's horizontal and vertical coordinates.
- `c.history`: up to eight recorded player positions, oldest first; each has
  integer `x` and `y` coordinates.
- `c.state`: a persisted integer from zero through one million.

The function returns exactly `dx`, `dy`, and `state`. Here `dx` and `dy` mean
horizontal and vertical movement offsets, each limited to minus one, zero or
one. The returned `state` must remain within the same integer bounds. No opaque
Lua heap, closure or global state persists between decisions.

The C engine matches a movement proposal against its own legal candidate list,
further restricting it to empty trap-free floor. Existing movement/region checks
still execute. Blocked movement becomes a wait; rejected proposals cannot modify
terrain, attacks, inventories or arbitrary engine fields. Successful movement
commits the typed state through the existing monster-movement path. Observed
movement events are emitted only when the creature is visible to the player.

No `io`, `os`, `load`, `require`, `debug`, `pcall`, standard-library functions or
native game pointers are exposed. This limits language capabilities; it does
**not** certify the underlying Lua/C implementation against every vulnerability.
Do not deploy this as a public untrusted-script hosting service.

## What the Dreamlands actually checks

The current shadow runner is Linux/x86-64 specific. It forks the live C process,
closes inherited live descriptors, replaces terminal callbacks, and applies a
deny-by-default system-call filter. It permits memory operations and read-only
opens needed for engine randomness, but denies filesystem writes, networking,
new child processes and execution of other programs. Only private null output
and a bounded report pipe may be written. Tests exercise memory/random-state
isolation, denied file/network/process operations, and timeout rejection.

The child runs a **targeted sixty-four-step evasive-bot trial** using the real
player movement, designated-monster movement and attack functions. It does not
run the complete normal turn loop: other monsters, all status effects and the
entire dungeon progression are not simulated. Acceptance requires completion,
movement, an observed escape opportunity, no script error or final death, and
no observed per-step damage above four. These are deliberately narrow prototype
criteria, not proof of fairness or universal escapeability.

Limits include one CPU-second (CPU means central processing unit), a two-second
child alarm, a parent pipe-poll deadline, and a 512 MiB address-space limit
(MiB means 1,048,576 bytes). A setup fault, signal, timeout or incomplete report
rejects rather than admitting a candidate without evidence.

The parent records `haunting-used.lua` and `dreamlands.json`. The latter is a
**validator result**, not by itself proof of live admission. The game separately
records `haunting` events such as `pre_admitted`, `accepted`, `rejected`, or
`spawn_failed`. Failed pre-admission logging prevents live installation.

## Authorized model connection

The model is pinned to `gpt-5.6-luna` using provider `openai-codex` at the ChatGPT
subscription endpoint. OAuth means Open Authorization. The adapter uses Hermes's
existing root-managed OAuth client and refresh machinery. It does not create an
agent/tool loop, change the default model, copy tokens, create profiles or fall
back to an API-key provider. API means application programming interface.

Use a Python environment where Hermes is installed. On this host it is:

```sh
/home/hermes/workspace/hermes-agent-integration/.venv/bin/python
```

The authorized experiments share the persistent ledger at
`~/.local/share/nyarlathack/milestone2/model-ledger.json`. It reserves an attempt
before each inference, synchronizes the ledger file and its containing directory,
and allows at most twenty attempts, including failures,
across process restarts. The recorded financial authorization is $1; the OAuth
transport returns subscription usage, **not a dollar invoice**. No paid API
fallback or purchasing of additional quota is enabled. Reported token counts
are preserved rather than inventing a cash charge.

The Codex endpoint does not accept the ordinary output-token-limit parameter.
This adapter therefore uses bounded prompt/result sizes, request deadlines and
the persistent attempt cap; it does not claim a server-enforced generation-token
ceiling. Authentication failure, rate limits or provider errors stop the call
without an automatic retry or provider switch.

To run the Tier 2 director through this route, explicitly:

```sh
/home/hermes/workspace/hermes-agent-integration/.venv/bin/python -m chaos oauth \
  --run-dir /absolute/private/run \
  --ledger /home/hermes/.local/share/nyarlathack/milestone2/model-ledger.json
```

To request another source candidate within that same approved allowance:

```sh
/home/hermes/workspace/hermes-agent-integration/.venv/bin/python \
  scripts/generate_haunting.py --execute-live \
  --events /actual/run/events.jsonl --output /new/private/candidate-directory
```

That script requires actual recorded backtracking, whitelists the summary,
checks output-directory availability before inference, and returns a candidate
only. Install its `haunting.lua` with `python3 -m chaos haunt`; the game still
must validate it. No continuous automatic script rewriting is enabled.

## Verification and remaining limits

The final suite output, exact receipts and machine-readable summary are in
`docs/evidence/milestone2-*`. Run the full tests after `make install CHAOS=1`:

```sh
NYARLATHACK_GAME_TESTS=1 python3 -m unittest discover -s tests/chaos -p 'test_*.py' -v
ruff check chaos tests/chaos scripts
```

Measured checks include the real live-model whisper, exact generated-source
admission/replay, hand-authored save/restore, harmless rejection echoes, Lua
limits and malformed results, process isolation, and all previous regression
cases. New regressions caught embedded zero bytes in Lua result keys and invalid
source poisoning a save. Independent review also found transport failure freezing
haunting history and level expiry. A failing linked-engine reproduction led to
a correction; absent-directory and failed-log cases now retain history updates,
permanent level-change expiry, and deadline expiry. Those fixes and directory
synchronization precede publication.

Save layout changed; earlier builds' saves are not supported by this build.
Always keep a game executable paired with its matching `nhdat` data. The
prototype admits only one source candidate per game and charges two cruelty
points for a live haunting. The conservative lifetime budget is not balance
validated. Continuous generation, broader hooks, all-window-port echo rendering,
full-turn-loop shadow worlds, arbitrary-session replay and public hosting remain
outside this milestone.
