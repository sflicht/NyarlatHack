# Next-use persistence snapshot

Whistle capability **W** and fountain capability **F** each permit at most one
callback in an admitted program. This document describes the bounded
snapshot contract for #63; full native save/process-exit continuation is #64 and
logical game identity is #92. Component tests are not completion of those gates.

## Authoritative values

The bounded value-only snapshot retains exact source bytes and their digest,
program identifier and variant; origin roots, deadlines and live flags;
admission time, expiry and delay time measured in native monster moves;
bounded Lua state; each slot's phase; each family's callback-used bit and total
callback count; armed companion identifier, activation time and action root;
claimed attention and witnessed state; whistle/fountain context counts;
identity-unsafe state; termination-emitted state; next private-record sequence,
last action/effect root and replay cursor.

The family callback bits distinguish a callback from terminalization of the
other still-pending slot after a failure. A total callback count alone cannot
prevent swapping the two slot phases and resurrecting the used family.

No Lua virtual machine, closure, allocator memory, file descriptor, callback,
engine pointer or executable assignment text is persisted. Import validates
before changing live state. It neither evaluates Lua nor spends, admits,
telegraphs or draws gameplay random numbers.

Record arrays are process-local output buffers, not a second source of game
state. Continuation starts an empty buffer with the persisted next sequence;
the earlier segment must be retained by the recorder. Remaining replay acceptance
belongs to #65; resetting these buffers alone is not replay evidence. The bounded
merged recording/playback tests are distinguished below.

## Owner, cache, lifetime and reset contract

Each live value has one authoritative owner. A `chaos_next_use_snapshot`, an
admission staging struct or a copied Lua context is a value transfer, **not a
second owner**. In particular, admission evidence is not an author's plan, a
candidate's asserted origin or a transport receipt reconstructed as authority.

| Values | Authoritative owner / callers | Derived or process-local copies | Lifetime and reset / restore rule |
| --- | --- | --- | --- |
| Retained W/F admission evidence | `src/chaos_engine.c:next_use_origin[2]`; `observation_notice` records a qualifying delivered notice, then `chaos_observation_end` marks readiness after schedule publication. | `next_use_bind_owned` copies ready refs to safe admission; `next_use-schedule.jsonl` is output for the offline author, not a way to repopulate engine evidence. | Process-local, initially zero; a newer qualifying notice replaces that family's retained entry. Not serialized. Safe admission checks level and original move/deadline; new-process restore does not recover unused origins from files. Already-admitted roots/deadlines belong to the runtime below. |
| Admission opportunity | `src/chaos_next_use_safe.c:settled`, read by `chaos_next_use_safe_attempted`, set by `chaos_next_use_safe_try`. | `u.chaos_next_use_attempted` is the native-save carrier, **not necessarily current during live admission**. `last_result` is a process-local report. | One settled attempt per game; `src/save.c:savegamestate` synchronizes the player field immediately before serializing `struct you`. `restgamestate` calls `chaos_next_use_safe_restore_attempted`; restore never reopens a settled opportunity. `chaos_next_use_safe_reset_for_test` is a fixture reset, not a gameplay retry. |
| Safe admission bindings | Native engine evidence/identity above supplies `chaos_next_use_safe_bind_origin`, `chaos_next_use_safe_bind_run`, `chaos_next_use_safe_bind_logical`, `chaos_next_use_safe_bind_telegraph`; `chaos_next_use_on_safe` selects the receipt sink. | Safe-layer `origin_evidence`, `owned_run`, `logical_run`, `owned_warn`, `owned_receipt` and opaque pointers are process-local bindings, not independent saved facts. `owned_run` derives from directory device/inode, not game identity. | Rebound at safe points by `next_use_bind_owned`; none is serialized. The `NUO1` marker is checked against the native player token, never repaired on restore. `resume_pending` only stages journal reconnection. Receipt success is an admission prerequisite, not restore/readmission authority. |
| Exact program, memory, uses and clocks | `src/chaos_next_use_runtime.c:live_runtime`, installed by `chaos_next_use_runtime_install`: `source`/length/digests, `state`, slots, callback bits/ordinal, origins/live flags/deadlines, admission/expiry/delay, armed ID/root/activation, claimed/witnessed, counts, termination and identity-unsafe state. | `snapshot_values` exports values; `runtime_on_action_impl` supplies a copied context to a fresh Lua VM. Admission structs cease to own the installed program; closures retain nothing. | Validated import replaces runtime values, not their age: original deadlines, used slots, claims and witness survive. `chaos_next_use_runtime_reset` clears the carrier for install/import or a valid absent payload; validation failure leaves it unchanged. Expiry/departure terminalizes rather than refreshes. Production installation supplies zero context counts, not observed-history totals. |
| Native game, level, target, time and spending | `u.chaos_game_token`, `u.uz`, native `fmon`/`m_id`, `monstermoves`, and `u.chaos` remain engine-owned. `chaos_next_use_game_identity`, `chaos_next_use_whistle_completed` and `dog_move` provide the native identity/target seams. | Runtime admission `run_token`/`level_token`/`armed_m_id` bind a capability to those owners; `current_run_token`/`current_level_token` are trusted boundary copies, not candidate authority or persisted current identity. | Native save restores player/level/monsters/clock/budget independently. `restgamestate` supplies the restored player token and packed `u.uz` to `chaos_next_use_restore_bound` **before import**; `chaos_observe` checks native identity thereafter. Data-only import leaves current identity unbound. Restore cannot refresh time, refund spend, grant another use or bind a replacement target merely from its numeric ID. |
| Presentation and record buffers | Native observation/delivery and `chaos_whistle_witness_finalize` establish publication; runtime `attention_claimed` and `witnessed` alone own the retained next-use outcomes. | `observation_*`, stack `chaos_whistle_witness`, TTY `certificate_observer`, runtime `expected_manifest_*`, action tokens and `private_records`/`public_records` are process-local handshakes or output, not saved witness authority. | `observation_clear` clears attribution at action/session/level boundaries; TTY certificates cover a single publication. `chaos_next_use_save_status` refuses unfinished runtime handshakes. Import empties output arrays while retaining `next_seq`/`last_root` and outcome bits; it neither replays presentation nor invents delivery. |
| Replay and journal progress | Runtime `next_seq`, `last_root`, `replay_cursor`, `journal_state`/bytes/hash and module `capture_incomplete` own the saved sequence/acknowledgement checkpoint; `capture_leave` advances the cursor only after sink acknowledgement. | `replay_runtime`/`staged_runtime` are isolated validation copies. `capture_record`, sink/opaque, transaction guards, and `src/chaos_next_use_journal.c:journal` descriptor/line/cursor/working tip are process-local; they cannot advance saved progress by themselves. | Snapshot import retains the checkpoint, disconnects the sink and initializes replay copies without evaluating Lua. `chaos_start` -> `chaos_next_use_safe_resume` -> `chaos_next_use_journal_resume` validates the exact saved prefix before reconnecting. Writer reset closes its descriptor; a missing/failed journal does not roll back gameplay or refresh admission. |

## Journal acknowledgement checkpoint (v5)

The runtime additionally owns `journal_state` (NONE=0, OPEN=1, COMPLETE=2,
FAILED=3), acknowledged `journal_bytes` (at most 8 MiB), lowercase
`journal_sha256[65]`, and exact Boolean `capture_incomplete`. `replay_cursor`
remains the acknowledged transition count. Journal cursors are bounded to 4096.
NONE has zero bytes/empty hash, but permits a positive custom-subscriber cursor
and an incomplete custom capture. Subscriber bindings are never serialized or
automatically reconnected by import.

OPEN requires a healthy committed runtime and a valid acknowledged anchor;
cursor zero denotes the header. COMPLETE requires a healthy terminal runtime,
positive cursor and footer acknowledgement. FAILED requires incompleteness and
retains the last acknowledged anchor; a header failure may have no anchor.
Settled failed recording remains a valid game save, not a gameplay rollback.
Capture transaction and sink-delivery saves are refused before any save write.

The writer's per-line byte count/hash is only a **working tip**. Publication to
the runtime happens after the entire sink acknowledgement: transition fsync,
and for terminal records footer fsync plus successful close. Initial header
publication additionally requires directory fsync. Failures never promote a
working tip to a checkpoint. A complete-looking file alone cannot prove success.
The initial header explicitly carries v5 NONE/zero bytes/empty hash/incomplete=0,
so it does not circularly hash its own anchor. The outer journal and replay-input
formats remain v1; the exact inner header schema is explicitly v5.

Native restore now stages recording continuation until `chaos_start` opens the
validated transport, before observation/session startup and captured boundaries.
The existing file must be a private, owned, single-link regular file reached
without following a symlink in a private owned directory. It is never created,
truncated or repaired during restore. The bounded scanner checks exact writer
framing, consecutive outer/inner cursors, source/binding positions, payload
hashes and their chain, and exact saved length/tip/cursor. Append uses that same
validated descriptor after a stability recheck. A copied transport is permitted
for the same saved game without rewriting original origins or envelope identity.

OPEN resumes recording; COMPLETE validates and closes without writing. NONE
never adopts a journal, and FAILED never becomes healthy. Missing, disabled or
rejected transport fails capture but permits restored gameplay; rejection writes
no failure marker and retains the saved anchor/cursor. The runtime-owned volatile
journal transaction guard also covers reopening, so a signal-triggered save
cannot publish a partially validated recorder. Terminal status retains a closed
subscriber for honest acknowledgement reporting, not a writable descriptor.

Merged [PR #150](https://github.com/sflicht/NyarlatHack/pull/150) supplies native
journal capture; [PR #153](https://github.com/sflicht/NyarlatHack/pull/153) adds
acknowledged checkpoints and resume. In `tests/chaos/test_next_use_unix_save.py`,
controlled real Unix WF/FW save/exit/new-process cases check native effects,
prefix preservation and a single acknowledged-complete journal. Corrupted,
fully rehashed, truncated, extra and missing prefixes are rejected without
cursor advancement or changed input bytes, including a later failed-capture
save/restore. That is recording continuation, not by itself physical playback.

Physical playback is no longer wholly absent: merged
[PR #154](https://github.com/sflicht/NyarlatHack/pull/154) adds
`test_next_use_native_playback.py:test_same_admitted_save_w_checkpoint_f_exact_input_playback`.
It records and replays the same admitted native save under controlled Unix
wizard geometry, clock and RNG fixtures, with a W checkpoint before F, exact
input bytes (including automatic answers), native/physical output comparisons,
and typed C semantic preflight before playback. This is one bounded WF pair,
not ordinary-play reproducibility or saved-RNG replay. Later merged
[PR #155](https://github.com/sflicht/NyarlatHack/pull/155) extends the bounded
evidence to four native pairs and three physical-loss controls (remaining F
hunger effect, native W effect bypass, and witness loss at save). Its reviewed
[Quality run 35980228714](https://github.com/sflicht/NyarlatHack/actions/runs/35980228714)
at `1b46972c54c04a6fa94eb311419dc2cf3e18aa4a` ran those cases, the existing
save-drop control and configured history driver; the full suite reported 1285
tests with 13 skips. These counts describe that exact reviewed head, not later
revisions. The same-save playback starts from an admitted header-only journal
(cursor zero) and exercises native resume from that saved anchor. Wider replay
and hostile-file/race coverage remains separately scoped; none of this is whole
#65 acceptance or ordinary-play evidence.

## Stable-state invariants

- Only committed or terminated programs can be represented. Terminated means
  neither slot is pending and the whistle window is not armed; the termination
  marker must agree. A committed program retains at least one pending slot or
  an armed whistle window.
- Pending and undeclared slots have no callback-used bit. Quiet, delay and
  successfully armed/applied slots require their own callback-used bit. Total
  callbacks equal the sum of the two Boolean bits. Invalid/suppressed slots
  may also arise from terminalization without their own callback.
- A declared family has a positive origin root. An undeclared family has no
  origin root, deadline or live flag. There is at least one declared family.
- A consumed-armed whistle slot requires an armed or ended runtime window,
  nonzero captured companion and action root, and an activation move within
  the admitted program lifetime. Window termination retains that metadata;
  changing only its runtime to inactive is not a legal snapshot.
- Claimed/witnessed attention belongs only to a consumed-armed whistle slot.
  Witnessed implies claimed; claimed does not imply delivered or witnessed.
- The exact 100-move lifetime, delay relationship, Boolean fields, bounded
  counts, state range and serialized integer widths are validated before
  writing. No narrowing or clamping turns an invalid value into a valid one.
- Temporary action tokens and unfinished presentation handshakes cannot be
  saved. A signal-driven save during those stages is refused, not represented
  as an absent program and not advanced by consuming the other slot.

## Save outcomes and compatibility

The save-status query distinguishes absent, valid and error. `dosave0` checks
this **before** `create_savefile` can truncate an existing recoverable save.
The next-use writer also refuses an invalid state before writing its first
byte. The native stream uses `NUS1` followed by presence and a versioned value
payload after `struct you`.

Snapshot version 2 lacks authoritative witness/count/sequence information.
It is rejected, not silently upgraded and not assigned an invented witness.
Retain the original bytes with the matching old binary/data. An incompatible
payload is not permission to delete a save or rewrite historical evidence.
The current development schema is version 5. Versions 3 and 4 are also rejected,
with their original bytes retained; it is not yet an accepted stable
persistence release. Failed parsing/validation leaves the existing live runtime
unchanged; an explicitly valid absent payload resets it.

## Game identity and trusted restore binding

The birthday is not a unique lifetime identifier: two starts can share a
second. A next-use-enabled game now allocates a positive 63-bit host token from
`/dev/urandom` using bounded descriptor reads, separately from the game's
`fopen`-based reseeding and gameplay random-number stream. The player structure
owns the token and the native save retains it. Allocation failure refuses
admission before warning or debit. This probabilistic identifier is not a
signature or a defense against a local user rewriting an entire save.
The engine's level coordinates are mapped to a separate bounded level token.

`restgamestate` passes the independently restored player token and level to
`chaos_next_use_restore_bound`. A nonpositive identity or mismatching game
token rejects before importing the runtime. Active programs additionally
require the admission level to match. Already-terminal history can accompany
that same game onto another current level; it cannot execute a callback or
reopen an ended whistle window. The data-only import/restore helper leaves
current identity unbound and cannot
execute a callback until an explicit trusted boundary is supplied. Each normal
`chaos_observe` also checks current native game/level identity, so a reused
numeric companion identifier on another level cannot inherit the attention.

A separate SHA-256 integrity digest binds program identifier, exact-source
digest, admission/expiry, variant, game/level tokens and typed origin
roots/deadlines. It detects isolated corruption/substitution of those immutable
values; it is not authentication and cannot stop coordinated local rewriting.
Its byte grammar is checked independently with Python's `hashlib`. Semantic
corruption fixtures recompute that binding independently, so a stale digest
cannot mask missing phase, clock or width checks. Separate integrity fixtures
retain the stale binding and include valid-value/recomputed-digest controls.
Bypassing the exact 100-move expiry validator must fail the semantic suite.

## Transport ownership across logical lifetimes

A transport directory is not a game identity. In particular, new native games
reset observation sequences and can repeat the same moves and safe-point index.
Previously, an unchanged envelope and receipt in a reused directory could be
admitted by a different game: the directory-bound origins matched, and only
then was the new player token attached to the installed program.

For next-use-enabled fresh starts, the engine now allocates the existing
`u.chaos_game_token` **before the first event**, rather than at a later admission
safe point. It exclusively creates a private `next_use-owner` file containing
`NUO1:` plus the token as 16 lowercase hexadecimal digits and a newline. Creation
requires no existing candidate, receipt, load-only source or used-source marker,
and no nonempty event/whisper history. The empty logs just opened by the engine
are allowed. Existing foreign, malformed, symlinked or non-private bindings are
not overwritten. This remains a local ownership check, not authentication
against an owner rewriting files or saves. Creation attempts synchronization,
but a synchronization or close failure is not a sticky process-wide admission
latch: a later safe point independently checks the readable marker. A complete,
matching marker may then establish ownership for the **same** logical game.
This check does not certify crash durability or authenticate another process.

At every admission safe point, the engine rereads that binding against the
player's persisted token. Missing or foreign ownership supplies no logical
admission authority; the existing scheduled-attempt path rejects before warning,
debit or installation. It does not rewrite the candidate, append a success
receipt, reset the budget or reset the saved attempt latch. Neither restarting
nor saving/restoring an unrelated game adopts the old directory. Normal event
and origin-schedule logging may still append; their old byte prefixes survive.

Restore never creates or repairs this binding. This deliberately means an older
unadmitted save with no marker, a game first started without next-use enabled,
or a restore redirected into an unbound transport cannot gain fresh admission
there. There is no implicit migration. Already-admitted native saved state is
still authoritative and continues without a candidate or ownership marker;
its saved attempt latch prevents readmission. Copying the transport including
its marker preserves ownership for the same logical game, but does not rebind
inode-based origin references: existing admitted relocation works; old unadmitted
references from another inode do not become valid. Start a genuinely new game
with a clean transport for a new admission lifetime; deleting or replacing old
history in place is not an automatic reset protocol.

The Unix regression uses the declared wizard geometry/RNG fixture, **not ordinary
play**. One game earns both real origins and a native receipt, saves and exits;
a distinct game with an empty save directory then uses the exact same transport
inode, birthday, seed, clock, origin sequence/move references and admission index.
The fresh game must have zero warning/debit/install/callback/attention/remap from
the old candidate. Two more cases take matching empty-save/restore paths before
origins, with the old owner present or missing, so restart cannot hide behind
nonmatching references or a process-only fresh flag. Candidate, receipt and author
bytes remain unchanged; old event/schedule prefixes remain intact. The existing
same-game two-family continuation, empty-save admission and relocation matrix
provides the positive controls.

## Still-open boundaries

The separately saved attempt latch distinguishes an unused empty game from a
rejected or consumed admission opportunity. The real Unix save test now covers
save/exit/restore before the first origin and later successful admission, plus
save/exit/restore after admission with the candidate removed and no second
admission. This is a quiet-program accounting check, not two-effect continuation.
Additional real `Game` regressions travel to level 2 before save/exit/restore
with pending and completed quiet programs. Component fixtures cover pending,
armed and completed departure histories, rejecting foreign-game identities and
active foreign-level restores without replacing live state.

Short-read evidence already exists in `tests/chaos/test_next_use_snapshot.py`:
`test_native_truncation_preserves_bytes_and_live_runtime` and
`test_native_read_errors_and_shared_decoder_state` compile the actual extracted
`src/restore.c` reader with and without `ZEROCOMP`. They exercise present/absent
payload truncation, read errors, interrupted short reads and shared decoder
state. This is reader/component coverage, not a complete compressed executable
save/restart roundtrip.

The controlled Unix matrix covers two-family save/process-exit continuation,
admitted relocation, independent saved-player-token mismatch and the unrelated
transport-reuse boundary above. Actual-process **active wrong-level and
missing/changed/reused-target negatives**, plus a next-use-specific **bones
non-inheritance regression**, remain open #64/#92 acceptance evidence, not newly
established runtime defects. This document alone closes neither #63 nor #20,
and is not whole #64/#92 or #65 sign-off. Transport device/inode binding remains
a separate local file defense; it is not logical saved-game identity.
