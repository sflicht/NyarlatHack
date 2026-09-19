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
