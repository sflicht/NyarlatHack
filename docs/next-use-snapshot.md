# Next-use persistence snapshot

Whistle capability **W** and fountain capability **F** each permit at most one
callback in an admitted program. This document describes the in-progress
snapshot repair for #63; full native save/process-exit continuation is #64 and
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
the earlier segment must be retained by the recorder. Complete checkpointed
native replay and independently checked trace continuity remain #65; resetting
these buffers alone is not replay evidence.

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
The current development schema is version 4 (version 3 was an incomplete
unmerged development schema and is also rejected); it is not yet an accepted stable
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

Short-read handling through native compression and the remaining recovery cases
still need separate evidence before the recovery milestone closes. The controlled
Unix matrix now covers two-family save/process-exit continuation, admitted
relocation and the unrelated-directory-reuse boundary above; this is not whole
#63/#64/#92 or #65 sign-off. Transport device/inode binding remains a separate
local file defense; it is not logical saved-game identity.
