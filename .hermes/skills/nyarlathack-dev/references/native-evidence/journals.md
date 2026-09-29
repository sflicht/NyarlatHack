# Bounded offline evidence journals

- Read the producer's real emission and commit order before deriving status; a
  pre-commit receipt or output file doesn't prove acceptance.
- Bind exact source, raw editorial note, installation provenance, run identity and
  event prefixes; source hashes don't authenticate narrative.
- Persist event identity, byte length and prefix digest; replay rolling counters
  across restores. Full-prefix hashing detects in-place edits; appended-bytes plus
  inode/size does not.
- Revalidate each historical checkpoint with its own prerequisites; test a rehashed
  but internally impossible older checkpoint.
- Explicit create/update is separate from read-only preflight; missing locks or
  checkpoints reject; never repair during reads.
- Bound file counts, record/event bytes, event count and line length. Select by
  host-recorded sequence, never mtime or model status.
- The final payload-chain digest is not the SHA-256 of the whole file; verify each
  against its definition and report both.
- A footer shows structural completeness only; acknowledged completion needs
  observed runtime capture status plus matching saved bytes, cursor and chain tip.
- Durable publication differs from complete-looking bytes left after an fsync
  failure; reads can't retroactively certify a failed write or authorize retries.
- For shared ledgers, enumerate reservation/completion file and directory fsync
  boundaries per caller contract; remove only an operation's own unpublished temp
  name; an uncertain scoped write must not trigger refunds or new requests.
- State the missing trust anchor: same-UID whole-history rollback can't be detected
  by local hashes.
- Test failed commits at the consumed ID immediately after the failing admission,
  not after another safe point that may mask it.
