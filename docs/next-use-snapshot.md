# Next-use persistence snapshot

Bound: data-only. Native save/restore is #64.

Persist authoritative values required to resume an admitted W/F program:

- source bytes, digest, program id, variant
- origin roots/deadlines and live flags
- admission/program clocks, delay/callback, Lua state 0..3
- slot phases, armed target id, replay cursor

Do not persist the Lua VM, closures, allocator state, file descriptors,
callbacks, or executable assignment text. Import validates then copies values;
it does not admit, debit, evaluate Lua, or draw RNG.

Transport `engine_run_hex` is process-local. Logical game identity is separate
(#92). A changed snapshot version is rejected, never reinterpreted.

Native save/restore (#64) writes magic `NUS1` after `struct you`. Missing magic
or a failed snapshot is an incompatible CHAOS save; the original file is
preserved. Restore marks admission settled so a leftover candidate cannot
debit again.
