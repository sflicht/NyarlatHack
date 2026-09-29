# Protocol contract and pinned guide files

## Protocol contract

- `chaos/protocol_contract.json` is production data. The generated block in the
  existing header and the generated Python module are outputs. Independent legacy
  expectations are immutable preservation evidence.
- Preservation includes intentional C/Python asymmetries, not just shared rows.
- Run `python3 scripts/generate_protocol_contract.py --check` AND the real C/Python
  consumer tests. Fresh generated output can't detect a handwritten consumer bypass.
- Write generator rejection tests before tightening validation.
- Fixed C serializer field order must match handwritten variadic argument order;
  accepting arbitrary reordering risks malformed output or undefined behavior.
- Record message output through the real engine and a recording `pline` stub.
- Preserve native header/object inventories, saved struct layout, enum IDs, legacy
  bytes, RNG call order and historical hash pins. Offline tests with native opt-in
  skips are not linked-game acceptance.
- Checks and their scope: `docs/quality-control.md` "Checks".

## Next-use guide and lifetimes

- `chaos/prompts/next-use-mechanics.txt` is capped by `MAX_PROMPT_BYTES` in
  `chaos/next_use_author.py`; one extra line can break native authoring. Put new
  contracts in `docs/`, not the guide. Don't raise the cap to pass tests.
- `chaos/prompts/next-use-mechanics-sources.json` pins sha256 of the engine files
  the guide describes. Editing safe/runtime/admission sources requires reviewing
  the semantic diff, then refreshing only those hashes and binding new helpers.
- The origin lifetime is duplicated: `CHAOS_NEXT_USE_ORIGIN_LIFETIME`
  (`include/chaos_next_use_safe.h`), `ORIGIN_LIFETIME` (`chaos/next_use_journal.py`),
  `ORIGIN_TTL` (`tests/chaos/sweep_funnel.py`). Change all three or every journal's
  origin binding fails validation.
- Adding a production source/header: audit authenticated object/header inventories
  and lexical hook registration; keep presence anchors and rejection checks; add
  same-count replacement negatives. Never refresh historical evidence to pass CI.
- Source-byte rules differ from display-text rules: valid Lua comments/whitespace
  need not be printable ASCII; keep length bounds and NUL rejection. Check string
  lengths as well as contents so embedded NULs can't disguise unknown table keys.
