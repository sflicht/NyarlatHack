# Save/restart evidence from actual bytes

- Reuse a verified visible-input route and its exact clock/entropy fixture; no seed
  search, hidden map data, injected state, or continuing past readiness timeouts.
- Build a standalone header-layout reporter (strict warnings, no engine objects)
  for sizeof/offsetof, integer sizes, byte order, compression config and save
  version constants. Never use it in place of the game.
- Check the real save header against compiled version constants. Locate the exact
  source uniquely, subtract its compiled field offset, bound the record and the
  containing player image before decoding. Don't assume gzip or a fixed struct size.
- Copy save bytes right after native save exits and is reaped, before restore
  consumes them; also copy unloaded level files. Don't hand-compress native files.
- Compare the whole owned-record byte array across checkpoints, allowing only
  expected integer changes. Take the owner ID from the first real save.
- Transport-independent acceptance: restart the unmodified executable with
  transport disabled; verify `/proc` environment absence, argv and executable hash.
  Absent transport config is not proof of absent bus files.
- Read status turns before/after actions and across save/restart; don't guess
  offsets. Assert warning presence/order before stage text, none on inert use.
- Player-record equality is not physical-object invariance, RNG purity or
  inventory-binding proof; label each.
- Negative decoder controls use copied bytes only; never alter a positive save.
  Don't synthesize missing events when transport-off play has none.
- Restore may legitimately append an identity boundary: require the exact saved
  prefix, first appended cursor = saved cursor + 1, strict sequence validation and
  unchanged gameplay/source/accounting.
- Completed-journal restore must not require append permission; test read-only
  evidence under a non-root user and report root skips.
- Keep pre-format-change binaries paired with their data; copy into temp game dirs;
  archived tuples stay read-only, writable copies are separate.
