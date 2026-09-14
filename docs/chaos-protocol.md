# Crawling Chaos engine protocol v1

Status: engine contract for Milestone 1; no arbitrary text or code execution.
All new engine code is under the NetHack General Public License (`dat/license`).

## Transport and activation

Build with `make -j4 install CHAOS=1` (default); `CHAOS=0` compiles no-op
hooks. Switching the flag rebuilds objects. I/O is **opt-in**:
`NYARLATHACK_RUN_DIR=/absolute/private/existing/directory`. Use a fresh,
owner-only directory for each new game; reuse it when restoring that game.
Never share it between games. Without this variable there is no director I/O.
The engine never creates the directory. Files are regular, non-symlink files;
create the directory yourself with mode 0700. No network calls.

* `events.jsonl`: append-only engine observations and acknowledgements.
* `whisper.json`: one request. Writer writes a temporary file in the same
  directory, flushes it, then atomically renames it. Never overwrite an
  unacknowledged request. The engine does **not** remove the mailbox.
* `whispers.jsonl`: engine admission journal, written and flushed before
  telegraph/effect. Contains the complete accepted request and application
  turn/safe index. Not a model input.

A missing mailbox means unchanged play. At most one request is handled at a
safe point, without waiting. Failed transport/journal writes fail closed for
new admissions. Previously admitted effects continue until expiry. There is no
crash-transaction guarantee across the OS filesystem and a game save: restore
is rollback to the save, not recovery of an unsaved process. Journals may
contain a preflight admission whose process terminated before application.

## Request schema (all and only these fields)

```json
{"v":1,"id":1,"mutation":"ambient","value":1,"duration":0,"telegraph":1,"at":1}
```

The entire file is at most 512 bytes, optionally surrounded by JSON whitespace.
Exactly one flat JSON object is allowed, with each key exactly once, in any
order. `v`, `id`, `value`, `duration`, `telegraph`, `at` are canonical nonnegative
JSON **integers**, maximum 2147483647; no signs, leading zeroes, decimals,
exponents, booleans or numeric strings. `v` must be 1. Keys and mutation are
literal ASCII strings: escapes/Unicode are intentionally not part of this
bounded protocol. Embedded NUL, raw control characters inside strings,
unknown/missing/duplicate keys, nested values, trailing JSON and oversized
files are rejected. External `cost` or `cruelty` fields are rejected.

`id` is 1..2147483647 and strictly greater than the persistent `last_id`.
Every statically valid request processed at its target (even a dynamic
rejection) consumes its ID. Duplicate/stale requests never apply again.
Malformed requests have acknowledgement ID 0 and consume no ID.

`at` is the **exact persistent safe-point index**, 1..2147483647. Future requests
remain pending without acknowledgement; missed indices reject `schedule`.
Publish ahead of time: a sidecar observing safe point N should target a later
index, not race the current poll. The game never pauses awaiting a director.

## Registry (engine-owned prices and messages)

| mutation | value | duration (game turns) | telegraph | cost | dynamic eligibility |
|---|---|---|---|---|---|
| `ambient` | 1, 2, or 3 | 0 | 1 | 1 | conscious/living session |
| `ward_efficacy` | 50 | 1..50 | 2 | 4 | Sanity <=80; no active ward effect |
| `hunger_rate` | 2 | 1..50 | 3 | 3 | Sanity <=90; ordinary food metabolism; no active hunger effect |

`ward_efficacy` halves (rounding down) completed ward counts **only in the
monster fear checks in `onscary`**. It does not erase engravings, affect
Elbereth/Lolth, modify immunity checks elsewhere, or draw random numbers.
`hunger_rate` multiplies ordinary food consumption by two in `gethungry`,
not ring hunger or energy consumption. Inediate, clockwork and Incantifier
forms are excluded; subsequent polymorph suppresses the effect while ineligible.
These are actual engine rule changes, not message-only handlers. Spawn weighting
is deliberately deferred to avoid the complex cached generation tables.

Telegraph 1: “A distant whisper brushes against your thoughts.”
Telegraph 2: “The lines of your wards seem thin and uncertain.”
Telegraph 3: “An unnatural hunger coils in your stomach.”

Ambient messages 1..3 respectively: “The shadows lean closer.”,
“Something beyond the walls listens.”, “For a moment, silence has teeth.”
All strings are engine constants. A telegraph is journaled and delivered through
`pline` before installing an effect (or displaying ambient text). No model text
is passed to the terminal. The synchronous UI API has no error return; a process
termination during display installs no subsequent effect in that process.

## Budget, expiry and persistence

Capacity = `2 + floor((100-clamp(Sanity,0,100))/10)` (2..12).
Available budget = max(0, capacity - **lifetime spent**). No periodic refill;
Sanity healing/loss cycles do not refund spending. `reserved` is the sum of
unexpired active costs, informational and always <= spent. Expiry releases
reserved cost, **not spent**. Ambient also costs one, preventing free spam.
At most two active effects, at most one of each rule type; no stacking or refresh.
An effect installed on turn T lasts for `[T, T+duration)`; rule queries check
expiry even between safe points. No mutation deals immediate damage or changes
raw player stats. No effect is admitted during death or negative-multi sleep.

Save/restore includes spent/reserved, last ID, sequence and safe counters, active
values and absolute expiry turns. No state goes into bones. CHAOS-on and -off
save layouts have distinct version checks and are rejected across that boundary.
The mailbox is external; replaying an already-consumed ID after restore cannot
apply twice. A future request at the time of save remains pending until its
saved target index. Old saves made before this extension are incompatible with
CHAOS-on builds (use CHAOS=0 to load stock saves).

## Events and acknowledgements

Each event is one JSON object plus newline. Envelope fields are:
`v` (1), `seq` (persistent increasing integer), `turn` (engine moves), `safe`
(persistent safe counter, initially 0), `event`, `phase`, `detail` (escaped
strings), `sanity`, `insight`, `budget`, `spent`, `reserved`, `last_id` (integers).
No inventory IDs, hidden dungeon state, RNG seed or draws are present.

Action `event`s: `eat`, `read`, `zap`, `apply`, `pray`, `kill`, `level_enter`,
`level_leave`, `sanity`, `insight`, `death`, `sleep`; `phase` is `attempt` or
`result`. An attempt is not a success (cancellation, lifesaving and failed
commands exist). Generic action details intentionally omit item/monster
identities instead of risking identification/hallucination RNG side effects.
`death` reports final termination, including quit/escape as indicated by detail.
`session`/`result` begins a process; it is not a new-game reset on restore.

Safe points: `safe_point`/`result`, detail `level_enter`, `pray`, `sleep`, or
`sanity_threshold`. Initial level entry counts. Prayer polling occurs only after
confirmation and prayer eligibility; sleep polling occurs immediately before
sleep. Sanity thresholds are 20-point buckets observed at a turn boundary;
changes inside callbacks are deferred to that boundary (no reentrant admission).
All safe points expire effects before admission. `safe` increases even with no
mailbox; the snapshot is emitted immediately before polling.

`ack`/`result` uses `detail` = reason and adds `id`, `status` (`accepted` or
`rejected`), `mutation`, `value`, `duration`, `telegraph`, `at`, `cost`, `expires`.
Malformed acknowledgements use empty mutation and zero request fields.
Reasons: `ok`, `schema`, `oversize`, `duplicate`, `schedule`, `budget`, `active`,
`ineligible`, `log_failure`. The admission journal uses the same request fields
plus `v`, `turn`, `safe`; it records status `admitted`. `telegraph`/`result`
precedes `ack` accepted; `expiry`/`result` records effect name.

## Replay boundary

A reproducible run requires engine binary/data version, both RNG seeds and
controlled wall clock/timezone, initial options/role/race/gender/alignment,
player inputs and their order, terminal dimensions, starting save/bones/data,
and exact accepted request turn/**safe index**. Raw seed + whisper text alone
is insufficient. Stock `setrandom` seeds `random` from clock plus `/dev/urandom`
and `rand` from clock; time also affects moon/night rules. The test harness uses
an explicitly test-only preload interposer for stock and instrumented builds.
Private diagnostics and manifests are never director events. Full gameplay
replay/regression evidence is separate from protocol unit tests.
