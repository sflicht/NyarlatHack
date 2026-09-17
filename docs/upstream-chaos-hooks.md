# Upstream CHAOS integration inventory

The reviewed inventory contains stable IDs, enclosing symbols, exact token
signatures, guard context, purpose and per-seam off-mode behavior. Declaration
anchors stop before function bodies, so changing a first hook produces drift
rather than destroying its enclosing scope. File-scope conditionals are not
attributed to the preceding function.

`upstream-chaos-hooks.json` records upstream-facing seams. Run the read-only audit:

```sh
/usr/bin/python3 -B scripts/check_upstream_hooks.py --root .
/usr/bin/python3 -B -m unittest discover -s tests/chaos -p 'test_upstream_hooks.py' -v
```

Use a Git checkout with full history (Actions `fetch-depth: 0`). The checker needs
fork revision `a6f0a1c43e66f4fb1bcac34d7d9709706682ec19`; missing history is an
error, not an empty successful scan. It discovers all tracked upstream C/header
files independently of inventory rows. New unclassified native paths fail. Only
new `src/chaos_*.c`, `include/chaos*.h`, and `tests/chaos/*` native fixtures are
owned exclusions; none may hide an inherited upstream file. Untracked build
products are not scanned. Newly added native integration files must be tracked
for the Git-derived production check; tests use explicit path-list fixtures.

The lexer scans both preprocessor branches, strips comments, splices continued
lines, and retains string/character tokens in hook signatures. Signatures include
short local context, so nearby semantic edits can legitimately require review.
It is not a C compiler or general parser. Reviewed token windows label functions;
`pline`/`vpline` share a special window because their variadic macro branches do
not have a simple brace-balanced source representation. Counts are multisets;
repeating an existing hook is not accepted as existing coverage. Diagnostic lines
are logical (after line splicing), not stable matching keys.

## Semantics and off build

`CHAOS=0` in GNUmakefile means **CHAOS is undefined**, not `-DCHAOS=0`.
The actual contracts are in `include/chaos.h`, `include/chaos_curio.h`, and
`include/chaos_haunt.h`:

- Event/start/observe/safe/shadow-end and observation void macros are no-ops;
  erased arguments are not evaluated. Food and ward macros return their input.
- Observation begin returns `0L`; take-message/map return an empty token.
- Curio tagged/apply return zero; generation/safe hooks become no-ops.
- Haunt pick returns `-2`; commit is a no-op.
- CHAOS-guarded persistent fields, restoration validation, bones demotion, save
  feature bits and echo insertion are omitted. Selected delivery adapters also
  depend on `TTY_GRAPHICS`.
- Shared TTY presentation/core wrappers and the financial helper remain compiled.
  Do not claim all supporting code disappears in the off build.

The inventory includes event/safe-point/rule seams, selected observations,
curio naming/identity/financial/lifecycle paths, haunt movement, persistent fields,
bones demotion, TTY delivery, header includes and save-layout bits. Build-toggle
blocks are checked separately from C tokens. Pre-existing `chaos_dnum`,
`chaos_dvariant`, `chaos_montype`, `CHAOS_S`, and `CHAOS_SKILL` have separate exact
per-file counts, not a blanket prefix exemption.

There is **no added hook in `src/save.c`**. Existing raw player/object writes
serialize the extended structures; field layout and feature bits therefore
remain save compatibility dependencies. Internal initial-level safe points,
Sanity thresholds and haunt ticks live in owned engine files, not invented
upstream rows.

## Extending an authorized seam (#1 / #25)

1. Confirm the issue authorizes a new upstream seam rather than an owned-module
   extension. Keep the upstream diff minimal.
2. Add the linked behavioral/physics regression and the authorized seam. Inspect
   the independently discovered EXTRA diagnostic before editing inventory.
3. Add a narrow window/row with a stable unique ID, enclosing symbol, purpose,
   exact literal-preserving signature, guards, positive count and accurate
   CHAOS-off behavior. Review every equivalent repeated occurrence. Do not group
   different functions into one row or exempt a whole file.
4. Run missing/extra, argument/enum, include/guard/save-bit and non-prefix mutants.
   Keep whitespace/comment controls passing. Never remove a missing row merely
   to make the audit green. Explain inherited-count changes separately.
5. Run the existing [quality gates](quality-control.md), including the maintained
   prepared native suite when behavior changes. This lexical audit is not physics,
   replay evidence, or proof of stock equivalence. Do not replace frozen goldens,
   historical pins or native gates with token checks.

There is deliberately no automatic accept/update CLI and no CI rewrite mode.
