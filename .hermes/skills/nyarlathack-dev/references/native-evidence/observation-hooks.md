# Observation hooks and artifact-dependent gates

## Implementing observation hooks

- Keep the executed baseline fixture and its future positive oracle byte-for-byte.
  A missing-event assertion after successful native actions is behavioral RED;
  build failure is not.
- Hash tracked inputs and untracked fixtures before and after editing to show the
  edit boundary.
- Capture each tone/wording condition once; reuse it for fact selection and the
  native message; keep short-circuit RNG conditions verbatim. End arming right
  after the message.
- Never infer delivery from reaching a message call.
- Review every changed statement before compiling. Syntax-check both CHAOS modes
  with real headers and isolated HOME/TMPDIR/MAIL; diff diagnostics against the
  pre-edit source so upstream warnings can't hide new ones.
- Never link an edited unit against immutable receipt objects and call it
  fresh-build GREEN.
- Record commands, hashes, preexisting diagnostics, skip reasons and unexecuted
  branches. An uncursed baseline doesn't validate cursed/magic/negative dispatch.
- Registration metadata checks are in `docs/quality-control.md` "Observation
  registration".

## Registering artifact-dependent native tests

- Read the driver, selector, supervisor, `scripts/prepare_native_ci.py` and the
  discovery adapter before rewiring. Reuse the bounded supervisor.
- Adapter tests without builds are synthetic: mock only the supervision boundary;
  use real preflight failures for missing receipts.
- Run oracle modules in a fresh supervised interpreter with every evidence variable
  set before import.
- Registering a narrow driver doesn't accept unrelated pending gates or hosted CI.
