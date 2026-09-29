# C engine units and Lua sandbox regressions

Engine-unit tests compile edited translation units directly. They are ENGINE-UNIT
evidence, not linked-game or native acceptance.

## Current-source units

- Compile edited production units with real project headers into a private temp
  dir; never combine current source with archived objects or fake umbrella headers.
- Use function/data sections plus `--gc-sections`. Stub only missing host globals
  and unrelated dependencies with native declarations.
- For test-first APIs, weak-declare missing symbols and return neutral values at
  the fixture dispatch boundary, asserting expected records, so a missing
  implementation is behavioral RED, not a link failure.
- Fresh fixture process per case when production init uses process-static guards.
- Inject write/fsync faults with linker wrappers that forward every nonfaulting
  call. Bytes left by failed fsync are not an advanced authoritative sequence.
- Test disabled macros with a tiny caller through the real public header: zero
  returns, no-op arguments, no unused-value warnings.
- Record compiler command/output, source hashes and test output; bound compile and
  subprocess time. Don't launch a full game build for a unit task.

## Lua sandbox

- Characterize current numeric errors, cleared outputs, return arity and opaque
  source bytes against old-source binaries before changing lifecycle.
- Whitebox variants include the production C unit exactly once; don't also link
  it. Keep instrumentation out of production headers.
- Wrap newstate, hook install, outer pcall, loader and close to check allocator/
  hook identity and balanced lifecycle.
- Arm allocator failure at a named stage after state creation, not an allocation
  ordinal; persist it through Lua's emergency-GC retry. Protected call entry itself
  allocates, so setup OOM may reject before the parser; record actual stage counts.
- Run fault cases in bounded children with core dumps off. Signal/abort/timeout is
  RED, never a valid sandbox rejection.
- Don't refresh golden hashes or infer gameplay acceptance from VM tests.
- See the `bounded-lua-embedding` skill for general embedding rules.
