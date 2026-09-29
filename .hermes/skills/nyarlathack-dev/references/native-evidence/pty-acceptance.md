# PTY acceptance runs

Playing real games through the `Game` PTY driver (`tests/chaos/gameplay_support.py`)
using only screen output. General driving rules: `../replay-and-fixtures.md`.

- Fix one declared clock/entropy fixture before exploring; never reroll until a
  candidate appears. Record failed movement and ordinary inventory remedies as
  real inputs.
- Replay a verified route with the unchanged strict readiness driver. Keep explicit
  paging bytes; don't auto-add paging to a recorded sequence.
- Separate bundle installation, native admission, placement, visible discovery and
  use. Don't push bundle provenance through a plain-source-only verifier or rewrite
  receipts to fit.
- Use normal inventory/action menus. Observe encumbrance, stamina and pickup
  failures instead of fixing native state externally.
- Assert native requested/actual effects and turn transitions per use, including
  no extra turn on depletion.
- Reconcile continuity only against captured native events after clean exit.
  Historical "placed" status is not current ownership.
- Claim controlled reproducibility only after comparing exploratory and codified
  replay artifacts byte-for-byte, and only for the declared clock/inputs/options.
- For controlled recovery in wizard mode, use observed coordinates with real
  Ctrl-T/getpos cursor and comma pickup. Drain an observed `--More--` before cursor
  bytes or terminal flushing discards them. Runtime menu flags may reset on restore;
  follow the observed item-use menu.
- Report launcher locking, record snapshots, alternate UI and save/restore
  separately if unexercised; a focused passing path is not whole-feature acceptance.
- Launcher/stream checks: hold one single-writer lock across preflight, child
  readiness and gameplay; reject incomplete prior event history (including a tail
  arriving between preflight and readiness) and preserve it instead of appending a
  guessed terminator; keep buffering legitimate partial records during live play.
