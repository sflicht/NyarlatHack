# Curio acceptance and item-transfer evidence

## Transfer and unloaded owners

- Reuse unchanged `gameplay_support.py` and installed objects; don't rebuild
  production to enable a fixture. Fresh external artifact root; hash native
  objects, headers, installed data/binary, driver/RNG helpers and tests before and
  after. Compile fixture C with `-Wall -Wextra -Werror -isystem<include>`.
- Seed objects/programs only after new-game init. A delegated `dorecover` wrapper
  must never seed; `chaos_start` runs on both paths, so use a restored-process flag
  and fail on an existing seed marker.
- Exercise real Apply/drop/levelport/save/start/pickup. Observe `#levelport`
  completion by wrapping `deferred_goto`.
- Freeze a pointer-free owned-record snapshot after one successful use; compare
  exact bytes at drop, away, save, dorecover, restored moveloop, return and
  recovered inventory. Keep first/final Apply snapshots separately.
- Controlled wizard movement is not natural discovery; helper probes are not UI
  Apply. Don't claim RNG/turn purity, AI theft, nesting, throws or destruction
  without dedicated evidence.

## Exact-source curio acceptance

- Author and hash a separately named private acceptance runner and assertions
  before launch; never rewrite the committed handwritten-fixture test to claim
  generated-candidate acceptance.
- Verify helper bytes against the supplied revision before import; call
  `native_fixture_selection.prepare` in source-build mode with the trusted receipt;
  don't fall back to archived ELF pins. Validate the layout reporter schema before
  constructing `Game`; decode with measured offsets and the real candidate name.
- One-shot ordinary task: stop at first native failure; no reroute, reroll, state
  injection or second model call.
- Launch fresh, then restore the same game with explicit reuse; keep source/receipt
  metadata; never reinstall or repair transport evidence.
- `Game.pid` is the supervisor: walk its actual children, hash the executable,
  distinguish exited/zombie directors, confirm all children gone after each save.
- Account for the launcher's ambient admission separately from curio admission.
- Update continuity only after stopped-game evidence; read back prior notes.
- Compare real baseline vs candidate event values, not names/hashes.
- Report controlled-clock acceptance separately from unrestricted play, low-Sanity
  branches, feature completion, review and publication.
