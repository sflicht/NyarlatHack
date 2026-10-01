# M2 engine opportunity and save — PR 2 evidence

Verification tier: **A**. Player-visible delta: old saves are refused and kept;
an incompatible native save header no longer offers deletion. There is no
second-program gameplay change yet. The temporary single-journal gate still
limits admission to one settled attempt. An attempt means a consumed envelope,
including a rejection; merely waiting for a future safe index does not count.

## Boundaries tested

- `test_next_use_safe.py`: real safe/admission/runtime/journal C units linked
  together. The saved attempt count and last ordinal/id cover accepted and
  rejected attempts. The opportunity predicate rejects nonterminal state,
  incomplete journal closure, the same terminal-event sequence, invalid count,
  and the configured cap of three. It accepts a strictly later sequence only
  after terminal mechanics and a complete journal acknowledgement. Production
  still returns `NOT_OPEN` at its temporary cap of one.
- `test_next_use_io.py`: explicit expected ordinals 1, 2 and 3 select distinct
  filenames; zero and out-of-range ordinals are rejected. Program 1 keeps the
  old filename. Later files are not read through production admission yet.
- `test_next_use_unix_save.py`: native PTY save/exit/restore for a completed quiet
  program, a parsed rejected attempt and the configured cap. The cap-three
  state is explicitly initialized by the fixture; it is **not** evidence of
  three natural admissions. After restore the count, ordinal/id and terminal
  sequence are unchanged; fresh observations and a preplaced ordinal-2 file
  cannot cause another admission or overwrite the old receipt.
- The same native suite checks a lost active runtime against the saved ledger.
  This negative control now refuses the inconsistent save and preserves its
  bytes, instead of restoring with a silently lost remaining effect.
- Incompatible native-header, incompatible snapshot, corrupted source,
  independent-game-identity and truncated-save controls retain the damaged
  input; healthy restoration is then tested from the retained original.
- The full native gates retain the existing stock/no-whisper and empty-program
  equality controls. The opportunity logic adds no game RNG calls.

## Ordinary capture

`ordinary/` records a real nonwizard `python3 -m chaos play --ordinary` launch,
a save after one wait, a new-process restore, another wait and quit. Both exits
were 0 and the event stream contains one restore. This is a save-path smoke
capture, not evidence of a second program or of a felt consequence.

There is no model call, wizard mode, clock replacement or seed override. The
PTY helper requires a preload pathname, so this capture uses an empty shared
object containing only `int capture_identity(void) { return 0; }`; it replaces
no game or libc function. Binary/data/preload hashes are in `result.json`.

`terminal.txt` is a decoded display capture: line endings are normalized,
the disposable root is replaced by `$CAPTURE_ROOT`, and trailing whitespace is
removed for Git hygiene. Other committed metadata is
likewise path-normalized where necessary. Exact raw files are retained at
`~/.hermes/reports/nyarlathack-m2/pr2/ordinary/`; their hashes are in
`ordinary/raw-hashes.json`. The capture driver is retained at
`~/.hermes/reports/nyarlathack-m2/pr2/capture.py`.

## Save carrier and deliberate limitation

The count lives in native state **v5**, not next-use snapshot v7, because an
attempt may be rejected before a runtime snapshot exists. Snapshot v6 is
unchanged. The old attempted byte is a checked mirror of whether the count is
nonzero, not authority to reopen anything. Runtime replay never advances the
saved terminal boundary.

PR 3 must give every ordinal its own journal and receipt identity before it
removes the cap-one admission guard. It must connect the tested opportunity
predicate and reset the one runtime slot only after the prior journal has
closed. This PR does not claim to validate natural program-2 admission or
multi-journal replay; those remain PR 3 acceptance work.

Full gate logs are retained under
`~/.hermes/reports/nyarlathack-m2/pr2/gates/`. The PR body records the tested
commit and final gate/CI results.
