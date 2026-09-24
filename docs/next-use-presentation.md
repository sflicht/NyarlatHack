# Next-use presentation boundary

This is the narrow internal contract for issue #94. W means the existing
whistle-attention operation; F means the fountain-refresh operation. TTY means
the existing text-terminal window port. No new port or game mechanic is added.

## Four different claims

- **Proposed/admitted:** a candidate passed the applicable source, origin,
  legality, warning and budget checks. This is not proof of an effect.
- **Applied:** the native decision used the admitted rule. It may still lack a
  publicly delivered manifestation.
- **Publicly delivered:** the message receipt and a correctly bound native map
  publication completed. A message notice without the completed manifestation
  does not upgrade `own_witnessed` or the public witness record.
- **Human-noticed:** a player perceived/understood it. No interface return value,
  fake-port test or terminal recording establishes this; #44 remains separate.

## Ownership and bounded request

`src/chaos_presentation.c` is the only W-facing adapter that knows concrete TTY
callbacks, glyph classification and snapshot/publication primitives. Native
companion eligibility and visibility checks remain in gameplay C. Lua cannot
construct a request, call the adapter or supply a delivery certificate.

There is one synchronous outstanding request. `chaos_presentation_begin` binds
its event root, checked nonwrapping generation, native game identity, level,
player and monster clocks, target identifier, initial coordinates and exact
glyph. Private adapter state additionally binds the request address and target
address. These addresses are transient lifetime checks, not persistent identity.
A copied request cannot finish or cancel the original. A conflicting begin fails
closed; it cannot replace the outstanding request.

`chaos_presentation_publish` rechecks the binding, current visibility, target and
matching current monster glyph before invoking the existing bounded TTY reprint.
Its typed result distinguishes rejected binding, unsupported backend, attempted
but undelivered publication, and delivered publication. Completion or cancellation
consumes that request, including failed publication. W finalization cancels it on
nonpublication paths too. Unrelated redraws, stale generations and duplicate
finalization cannot supply an observation for another request.

The original `chaos_tty_publication_certificate` in `win/tty/wintty.c` remains
unchanged. It observes the exact direct print. A pending glyph-buffer bit or a
previous redraw is still not a substitute: message output may already have
drained the buffer. Existing map cancellation, clipping and output-error checks
remain authoritative. Unsupported fake callbacks do not get called to assert
success. This is no claim of curses/tiles support.

The request, generation counter and owner pointers are process-local presentation
state, absent from the value-only programme snapshot and Lua context. They do
not survive a native action, grant uses, change clocks, consume random numbers,
introduce a prompt, or enlarge source/state/budget limits. F's tested publication
path is unchanged; this is not a general rendering framework.

## Tests and a corrected linked-fixture assumption

The pre-extraction native fixture accepted a changed target identifier, changed
level and substituted floor glyph at finalization. New tests first failed with
an incorrect public record. The adapter rejects those inputs after the native
decision/message, rather than pretending the earlier physical effect did not
occur.

A stricter post-glyph check also exposed a fixture error: the standalone
`dog_move` fixture finalized directly, without `m_move`'s real `postmov` updates
of the old and new map cells. Its old positive record had a dog pre-glyph and a
floor post-glyph. The test now explicitly requires the dog post-glyph and both
linked callers perform those normal `newsym` updates. Positive assertions were
not weakened. Actual Unix-game continuation exercises `m_move` itself and does
not use this fixture repair. Original failed records are retained, not rewritten.

The small native request matrix covers real TTY success, cancellation without
retry, an unsupported fake callback after an unrelated redraw, copied requests,
changed identities/clocks/levels/glyphs and same-number different-object targets.
It is interface evidence, not ordinary-play or human-perception evidence.

A bounded before/after check compiles the prior W gameplay functions against the
same transient-witness layout and corrected fixture. Six cases compare exact
result records, events, terminal output and errors, including native position,
random-number counters and no-candidate controls. This is not a whole historical
engine rebuild. The earlier nonmatching floor-fixture comparison remains failed.

The actual author prompt and all size limits remain unchanged: an attempted
extra explanatory paragraph exceeded the existing prompt cap and was removed,
not accommodated by a larger cap. Its source manifest now also pins the adapter,
header, engine integration and real TTY backend. The manifest's historical base
revision is retained; its per-file digests identify the reviewed current bytes.
