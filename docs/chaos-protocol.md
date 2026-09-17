# Crawling Chaos protocol: current policy 2 and historical readers

Status: implemented Tier 2 contract and bounded observation foundation;
[local native acceptance under the approved dump contract](haunting-observations-evidence.md)
is distinct from publication; literal strict cross-build comparison remains failed.
This mailbox does not accept executable code; the separate First Haunting
Lua admission path is documented in `milestone2.md`.
All new engine code is under the NetHack General Public License (`dat/license`).

## Cosmetic pacing prototype and migration

Current native state/save version is **2**, ordinary events **3**, opt-in
observation events **4**, request grammar **1**, and admission-journal policy
**2** (journal `v` remains request version 1). These are separate version axes.
Historical ordinary v1/observation v2 readers retain their old prices and
validation semantics; historical readability does **not** authorize current
publication or replay. Never mix old and current policy within one run.

Ambient has mechanical `cost:0` and `cosmetic_cost:1`. There are exactly **three
lifetime cosmetic deliveries**, each existing value 1/2/3 at most once, with
**50 native moves** between successful deliveries. The first is eligible even
at turn zero. Repeated safe points are not elapsed turns. The saved engine-owned
`cosmetic_seen` mask and `cosmetic_last_turn` timestamp cannot be reset by a
backend switch, sidecar restart, cleared client history, expiry or waiting.
Every current event carries exact `cosmetic:{"seen":MASK,"last_turn":TURN}`.
Only a real new game in a separate run directory starts with fresh allowance.
Three/50/once is a conservative prototype, **not tuned balance or a claim of
ongoing full-run presence**. It uses the three existing messages, not new prose.

Mechanical lifetime ceiling remains **12**, with the same Sanity capacity and
prices: curio 1, haunt 2, hunger 3, ward 4. Cosmetics neither debit nor reserve
mechanical capacity. This does not reserve capacity for signatures: earlier
mechanics can still deny later curio/haunt or incidental requests.

Random and generic model selection prefer the eligible ward/hunger subset;
only when that subset is empty may they choose an unused, currently eligible
ambient **value**. The model's menu and returned-value validation enforce the
same subset. Hand packs/replay need not obey preference, but native bounds apply.

Both `load_replay` and `load_history_replay` preflight current-policy evidence,
including empty/all-mechanical schedules. Each policy-2 admitted journal row
must match an accepted current ACK's canonical request, turn, safe/at, mechanical
and cosmetic tariffs, expiry and roles. Registered prices are authoritative.
A journal or telegraph alone is not a delivery receipt; missing final ACKs need
manual reconciliation. Restore may reconcile a monotonic committed snapshot
after a lost receipt, but cannot reconstruct acceptance. With observations,
the enabled marker and following restore session must agree before publication.

**Old saves are incompatible; there is no automatic migration. Answer NO to
“Delete the old file?”** Retain the old save with its matching old binary and
`nhdat`; finish that game there. Start a separate new game/run on the new build.
The new CHAOS structural and restored-clock rejection paths preserve the save;
this is not blanket corruption protection: stock short-read corruption handling
can still delete a damaged save. Keep independent backups.

Current-policy full native save/replay acceptance is pending the reviewed fresh
build. The bounded synthetic comparison used seeds 0/7/19, turns
0/1/25/50/75/100/125/150 and Sanity 100/100/90/80/60/60/0/0, ordinary food.
Across 24 opportunities it selected/admitted 9 ambient, 3 ward and 6 hunger,
with 6 empty menus; the frozen old-policy result was 22 ambient, 2 ward, 0 hunger.
Independent native-core gate probes found ward eligible 3/24 and hunger 9/24;
budget denied 10 ward and 5 hunger probes (not submitted director requests).
Both isolated mechanical controls admitted with/without ambient; the sequential
hunger-then-ward control still denied ward for mechanical budget. Mixed Sanity-0
signature-first/incidental-first fixtures, each with/without ambient, made 16/16
mechanical admissions with identical decisions/spent/reserved per matched pair;
each finished spent10/reserved7, then spent10/reserved0 after expiry. These are
synthetic state/core-helper results, **not ordinary journeys, spawn/curio-apply
witnesses, UI effects or frequency estimates**. Historical records remain frozen.

## Contract ownership and regeneration

`chaos/protocol_contract.json` is the reviewed source for the v1 mutation rows,
versions, integer/cap limits, budget constants, request roles/bounds, event and
ACK vocabulary, numeric bounds, telegraphs, ambient messages and wire order.
Each mutation records its stable C symbol/id, wire name, cost, inclusive value
and duration ranges, telegraph, separate engine/director sanity caps, ordinary
food requirement, persistence and supported rule tag (`none`, `halve`, `double`).
The reader-policy section records compatibility constraints, not selectable modes.

```sh
python3 scripts/generate_protocol_contract.py
python3 scripts/generate_protocol_contract.py --check
```

The standard-library generator owns only the marked block in the existing
`include/chaos_protocol.h` and the complete `chaos/_protocol_contract.py` module.
Both outputs are checked in; game builds need neither Python nor runtime JSON.
Do not edit generated output. `--check` is read-only, reports missing/stale
outputs and rejects malformed sources or header markers. `--root` selects an
isolated repository-shaped fixture. Header bytes outside the block are preserved;
they are **not** certified by this check. Fixed serializer roles/order cannot be
rearranged without reviewing the corresponding handwritten C argument lists.

Before adding a mutation, review its stable enum identity and save layout, native
handler and call site, telegraph, bounds/cost/eligibility, director behavior,
prompts/packs, replay bytes and RNG draw order. Regenerate, run the contract and
native tests, and obtain independent review. The disposable fourth-row test
proves unchanged core C/Python consumers can use another existing-rule row; it
does not authorize a production fourth mutation or synthesize new game physics.

The frozen production oracle and pre-refactor seeded random bytes are independent
of the source. Do not regenerate them to bless a maintenance behavior change.
Consumer-bypass tests deliberately leave generated outputs fresh: generation
agreement alone cannot establish correct parser, admission, UI or IO behavior.
Existing native physics, restore, CHAOS-off and replay acceptance remain required.

Intentional legacy differences remain: internal C `future` is not a wire ACK
reason; future requests consume no ID and emit no ACK. Ambient has no C sanity
cap, while the director uses 100. V1 events preserve unknown top-level fields;
requests and present vitals are closed. ACK id-zero rows retain their permissive
legacy cross-field semantics. Event string caps count Python characters when
passed a string, bytes when passed bytes; requests first encode to bytes. The C
writer is not an event vocabulary validator. V2 observations remain separately
handwritten historically. That extraction's byte freeze is historical; the
explicit policy-2 changes above intentionally version accounting and layout.

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
There is no `at: 0` sentinel or late-request repair. The launcher may publish
a fixed pack before game startup, but it does not change an assigned index.

## Registry (engine-owned prices and messages)

| mutation | value | duration (game turns) | telegraph | cost | dynamic eligibility |
|---|---|---|---|---|---|
| `ambient` | 1, 2, or 3 | 0 | 1 | 0 mechanical / 1 cosmetic | conscious/living; unused value; 50-move spacing; lifetime cap 3 |
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
reserved cost, **not spent**. Ambient uses only the separate cosmetic allowance.
Three admission paths share that lifetime allowance: whispers (the registry
prices), curio admission (1), and a successfully spawned haunt (2). Curio
placement and its three uses do not charge again; failed later placement does
not refund admission. Failed curio validation/evidence or failed haunt spawning
spends nothing. Final receipt failure does not refund an already committed
admission. Existing `pre_admitted` and `admitted`/`accepted` events show the
pre- and post-charge budget; no extra spend rows or whisper IDs are introduced.
Expiry refunds none of these spenders.

At most two active effects, at most one of each rule type; no stacking or refresh.
An effect installed on turn T lasts for `[T, T+duration)`; rule queries check
expiry even between safe points. No mutation deals immediate damage or changes
raw player stats. No effect is admitted during death or negative-multi sleep.

Save/restore includes spent/reserved, last ID, sequence and safe counters, active
values and absolute expiry turns, cosmetic mask and last delivery turn. No state goes into bones. CHAOS-on and -off
save layouts have distinct version checks and are rejected across that boundary.
The mailbox is external; replaying an already-consumed ID after restore cannot
apply twice. A future request at the time of save remains pending until its
saved target index. Old saves made before this extension are incompatible with
CHAOS-on builds (use CHAOS=0 to load stock saves).

## Events and acknowledgements

By default, each event is one v3 JSON object plus newline. Envelope fields are:
`v` (3), mandatory `cosmetic`, `seq` (persistent increasing integer), `turn` (engine moves), `safe`
(persistent safe counter, initially 0), `event`, `phase`, `detail` (escaped
strings), `sanity`, `insight`, `budget`, `spent`, `reserved`, `last_id` (integers).
No inventory IDs, hidden dungeon state, RNG seed or draws are present.

New writers also include `vitals`, a bounded object containing exactly `hp`,
`hp_max`, `power`, and `power_max`: player-known hit points and energy, using
the same values shown by the status line. Health selects the current polymorph
form when applicable and clamps negative current health to zero, exactly as
`bot2str` does. Power may be negative, as in the status display. Python validates
32-bit integer bounds (no booleans); only power may be negative. No naming,
identification, hallucination rendering or random draws are needed. Readers
accept older events without this optional object. This transient observation
extension does not change the player save layout or request schema.

Action `event`s: `eat`, `read`, `zap`, `apply`, `pray`, `kill`, `level_enter`,
`level_leave`, `sanity`, `insight`, `death`, `sleep`; `phase` is `attempt` or
`result`. An attempt is not a success (cancellation, lifesaving and failed
commands exist). Generic action details intentionally omit item/monster
identities instead of risking identification/hallucination RNG side effects.
`death` reports final termination, including quit/escape as indicated by detail.
`session`/`result` begins a process; it is not a new-game reset on restore.
An explicit negative response to the prayer confirmation prompt emits
`pray`/`result` with detail `cancelled`, without a new safe point or turn.
The existing eligible prayer emits `pray`/`attempt` with detail `confirmed`;
it does not claim that the god granted a benefit. The director exposes only
these exact phase/detail combinations as a `prayer` enum. It still drops all
other detail strings, acknowledgement extras and arbitrary keys from model
context; validated vitals are retained in the bounded recent history.

Safe points: `safe_point`/`result`, detail `level_enter`, `pray`, `sleep`, or
`sanity_threshold`. Initial level entry counts. Prayer polling occurs only after
confirmation and prayer eligibility; sleep polling occurs immediately before
sleep. Sanity thresholds are 20-point buckets observed at a turn boundary;
changes inside callbacks are deferred to that boundary (no reentrant admission).
Crossings coalesce: at most one threshold safe point per observation window,
in either direction, even across multiple buckets. A second observation with
unchanged Sanity creates none. This deliberately avoids a burst of admissions.
All safe points expire effects before admission. `safe` increases even with no
mailbox; the snapshot is emitted immediately before polling.

`ack`/`result` uses `detail` = reason and adds `id`, `status` (`accepted` or
`rejected`), `mutation`, `value`, `duration`, `telegraph`, `at`, `cost`, `cosmetic_cost`, `expires`.
Malformed acknowledgements use empty mutation and zero request fields.
Reasons: `ok`, `schema`, `oversize`, `duplicate`, `schedule`, `budget`, `active`,
`ineligible`, `log_failure`, `cosmetic_budget`, `cosmetic_cooldown`,
`cosmetic_repeat`. Valid rejected requests quote both registered tariffs without
debit; malformed id-zero/unknown-mutation sentinels quote zero for both.
The admission journal uses the same request fields
plus `v:1`, `policy:2`, both tariffs, expiry, `turn`, `safe`; it records status `admitted`. `telegraph`/`result`
precedes `ack` accepted; `expiry`/`result` records effect name.

## Opt-in selected-action observations (current v4, historical v2)

Set `NYARLATHACK_OBSERVATIONS=1` **on the game process**, together with the
normal private `NYARLATHACK_RUN_DIR`, in a `CHAOS=1` build. The flag is read once
at `chaos_start`; absent or any other value means off. Healthy event transport
is required. Off emits ordinary v3. On adds
v4 records to the same `events.jsonl` and authoritative sequence, not a second
stream: an `enabled` marker immediately precedes each process's v3 `session`.
Ordinary `parse_event`, `State`, `EventReader`, replay and authoring readers reject
observation rows (v2 or v4); do not feed opt-in logs to them. The separately approved, explicit
`chaos history` pilot consumes mixed history; it is not the default director and
registration does not extend its hunger policy or model choices.

Historical v2 has exactly these envelope keys:
`v,seq,turn,safe,event,phase,detail,sanity,insight,budget,spent,reserved,last_id,vitals,observation`.
`v` is 2, `event` is `observation`, and `detail` is empty. `vitals` is mandatory,
with the four status fields defined above. Numeric fields retain the 32-bit
integer bounds (no booleans); `seq` is positive, Sanity is at most 100,
`budget/spent/reserved` at most 12, and reserved cannot exceed spent.
`observation` has exactly `operation,stage,root_seq,fact`. Duplicate/extra keys,
nonfinite numbers and illegal enum combinations reject. Requests remain v1.
Current v4 has the same exact observation fields plus mandatory `cosmetic`,
with `v:4`; its ordinary partner is v3, never v1.

| stage | operation | root_seq | fact | phase |
|---|---|---|---|---|
| `enabled` | `none` | 0 | `none` | `result` |
| `started` | `whistling` or `fountain_drink` | 0 | `none` | `attempt` |
| `notice` | same as root | earlier root's sequence | allowed fact below | `result` |
| `completed` | same as root | earlier root's sequence | `none` | `result` |
| `blocked` | `fountain_drink` | earlier root's sequence | `none` | `result` |

A root is the `started` record itself: zero is not a guessed future sequence.
It is established only after successful append and filesystem synchronization.
Its envelope captures public context **before** the selected native call;
a notice captures context at delivery; a terminal captures context **after**
return. These are snapshots, not automatic causal deltas or effect attribution.
One transient root permits at most one notice and one terminal, in that order,
linked within the same operation, turn and session. A replacement root, session,
level boundary or death ends attribution. No terminal is appended after final
death. Failed observation transport suppresses records, never cancels the native
action; a physically written line whose synchronization failed is not proof of
commitment. A parser cannot reconstruct that transport failure from bytes alone.

`completed` means the selected routine returned, not success, survival,
identification or pet obedience. `blocked` means the native fountain reach guard
ran, not player cancellation. Missing terminal means **incomplete**, even with a
notice; completed without notice means unknown selected-notice coverage, not
“nothing happened.” Selection cancel, unsupported apply, fountain decline,
no-mouth and Levitation bypass create no selected root. Decline can continue to
actual inventory-potion consumption in the same native call; that remains outside
this observation slice. A low-level reach-guard fixture is not a normal confirmed
drink through the prompt.

| operation | allowed notice facts | what is witnessed |
|---|---|---|
| `whistling` | `sound_high`, `sound_shrill`, `sound_normal`, `sound_strange`, `sound_humming` | selected native message wording |
| `fountain_drink` | `water_refreshed`, `water_foul`, `cannot_reach` | selected native message wording |
| `fountain_drink` | `detection_presented` | native blocking map presentation |

Message evidence requires rendering through the native terminal (TTY) callback,
not merely calling `pline`. NOSHOW/NOREP, pre-window fallback and WIN_STOP before
rendering can suppress a notice. A stop after rendering does not undo delivery.
Unsupported or wrapped callbacks retain normal output but produce no certified
notice. Map evidence requires the native display, glyph, clear, cursor and text
callbacks and actual map presentation; an empty detection branch is not enough.
Action-bound tokens prevent nested/replacement actions from stealing a notice.
No claim is made about every window port or whether a human perceived the output.

Whistle tones do not reveal ordinary/magic identity, curse status, hearing or
companion response. Fountain notices omit fate, magical flags, entity locations
and hidden eligibility. No names, targets, coordinates, arbitrary text or model
handles are exported. Other fountain outcomes may complete without a notice.
The hooks add no random-number-generator (RNG) draws, naming, identification,
rendering calls or safe-point polling. Native actions may themselves draw RNG;
purity compares equal draws and aftermath, not zero draws. Shadow observations
are suppressed. Scope is transient, not saved; no new gameplay effect, budget,
Lua, Luna, recurrence or save-layout mechanism is introduced.

Implementation anchors: [scope and snapshots](../src/chaos_engine.c),
[bounded writer](../src/chaos_io.c), [message delivery](../src/pline.c),
[map delivery](../src/detect.c), and [offline validation](../chaos/episodes.py).

## Offline episode projection and limits

The separate `chaos.episodes` API accepts historical v1/v2 or current v3/v4 histories:

- `parse_episode_event(raw) -> dict` validates one row, not chronology, native
  delivery or authenticity. V2 has a 4096-byte row cap; v1 retains its existing
  parser semantics, optional vitals and unknown top-level keys. A parsed legacy
  row is **not** redacted public context.
- `project_episodes(raw: bytes) -> dict` requires complete nonempty,
  newline-terminated history from `session/result/new`, optionally preceded by
  the enabled marker. Sequences start at 1 and are contiguous; turn, safe,
  spent and last_id cannot roll back. Restore sessions and enabled markers must
  form a valid chain; action records require that session's marker. References
  cannot cross attribution boundaries; records after final death reject.
- `snapshot_episodes(path, *, checkpoint=None) -> (public, proof)` reads the run
  directory's `events.jsonl` without writing or repairing it. The directory must
  be owned mode 0700, the file owned mode 0600, regular and single-link; symlink
  traversal rejects. It reopens/rechecks the supplied target. Host-only proof is
  `{directory,event:{identity,length,sha256}}`, with device/inode pairs as
  identities. A checkpoint verifies the same resource and exact consumed prefix;
  append is allowed, replacement/rewrite/truncation is not. Only the checked
  prefix is projected; even with a checkpoint the whole file must fit the byte
  cap. Proof is local integrity evidence, not a signature, hostile same-user
  authentication or future immutability. Keep it separate from public output.

Full validated history is capped at **16 MiB and 50,000 events**; do not truncate
it to make it fit. The public window keeps the **newest 32 selected roots in the
latest session**, resetting on restore. This is summary reduction, not partial
log validation. Output has exactly `episode_context_v:1`,
`scope:"selected_whistle_fountain"`, `lookback_roots:32`, `episodes`, `coverage`.
There are at most two groups, sorted by operation. Each is
`{operation,count,saturated,evidence}`; only completed roots with a notice qualify.
Each evidence entry is `{root_seq,notice_seq,end_seq,fact}`; retain at most three:
the first two and latest qualifying roots, ordered by root sequence.

Coverage has exactly `incomplete`, `blocked`, `completed_without_notice`,
`omitted_roots`, each `{count,saturated}`. All counts cap at three; saturation
means **strictly more than three**. Coverage concerns retained roots except
omitted_roots, which counts evictions since the latest session. Counts describe
actions, not distinct targets or future eligibility. Incomplete notices remain
in the raw history but are not positive episodes. Canonical ASCII JSON output
is at most **4096 bytes**, failing rather than clipping if exceeded. No hidden
facts, host identities, reward scores or editorial narrative enter this summary.
See [usage](../chaos/README.md#offline-selected-action-observations) and the
[bounded acceptance ledger](haunting-observations-evidence.md).

## Live acknowledgement boundary

An already-running director retains a copy of its exact outstanding request.
The engine consumes its identifier and emits a telegraph before presentation
finishes and the acknowledgement is written. During that narrow live interval,
the director waits only while the mailbox is unchanged and the observed
telegraph, mutation, safe index and last identifier match the known request.
This is **not acceptance**: the mailbox cannot be overwritten and no retry or
retiming is permitted. A matching acknowledgement is still required to proceed;
the existing runtime cap bounds a missing acknowledgement. Changed/deleted mail,
mismatched acknowledgements and incompatible progress fail closed. Startup has
no trusted live-request copy and retains strict reconciliation checks.

## Replay boundary

A reproducible run requires engine binary/data version, both RNG seeds and
controlled wall clock/timezone, initial options/role/race/gender/alignment,
player inputs and their order, terminal dimensions, starting save/bones/data,
and exact accepted request turn/**safe index**. Raw seed + whisper text alone
is insufficient. Stock `setrandom` seeds `random` from clock plus `/dev/urandom`
and `rand` from clock; `check_reseed` later reads fresh entropy for both seeds
and reseeding intervals. All these entropy reads must also be controlled or
recorded. Time affects moon/night rules. The test harness uses
an explicitly test-only preload interposer for stock and instrumented builds.
Private diagnostics and manifests are never director events. Full gameplay
replay/regression evidence is separate from protocol unit tests.

## Shared observation registration

The `observations` section of `chaos/protocol_contract.json` describes operation,
fact and stage identities, native message/map witnesses, family `allow_blocked`,
fact `implies_blocked`, public grouping and reviewed file/symbol/role hook
provenance. Hook references are **review-only**: the generator checks lexical
syntax and duplicates, not file existence, symbol existence, call placement or
native execution. References generate no hooks. The independent #33 upstream
lexical inventory and human source review remain required; neither proves native
delivery. Channels select the two fixed supported witnesses, not arbitrary
pluggable witness implementations. The existing generator emits header row macros
and Python metadata;
`chaos_protocol.c` owns constant tables and row-local validation. Engine root
lifetime, native delivery and projector chronology remain separate trust layers.

Build-time caps are 16 families, 64 facts and 31-byte ASCII names. Production is
still exactly two families/nine facts, scope `selected_whistle_fountain`, 32 roots,
count cap three, first-two plus latest evidence and 4096 public bytes. Family
permission for explicit blocked terminals is distinct from a blocking notice;
only cannot-reach implies blocked. No runtime JSON, saved fields or Lua API.

For an isolated extension, append reviewed rows to a temporary contract, use a
fixture-specific scope and honest test-harness provenance, regenerate/check both
outputs, and exercise unchanged C scope/IO and isolated Python projection. A
real action needs separate approval, upstream seams and native/privacy proof;
registration does not authorize new model choices or presentation channels.
