# Native execution, evidence and reporting

The official full-suite recipe, descriptor contract and upload rules are in
`docs/quality-control.md`; don't restate or bypass them. This file is how to run
native work and report it honestly.

## Evidence scopes (never let one stand in for another)

Unit/ENGINE-UNIT → linked native fixture → real Unix process save/restore →
ordinary nonwizard play → exact recorded-input replay → hosted CI → live model →
human perception. Also keep distinct: installation, admission/debit, telegraph,
native effect, expiry, public delivery, player notice. Shadow replay validation or
an in-memory sink acknowledgement is not native playback or durable recording.

## Native execution steps

1. Run drivers through `tests/chaos/native_driver_supervision.run_driver` under
   `/usr/bin/python3`. Require `family_cleanup: verified`, not merely a reaped
   primary process.
2. Keep builds isolated, at most two compiler jobs. Reused immutable objects are
   development evidence only; record compiled-base and current-fixture identities
   separately. Fresh acceptance uses the same checkout and its real receipt.
3. Retained object manifests include generator objects and window-system
   utilities. Link engine objects from the current GNUmakefile `GAME_O` groups,
   not every object in the receipt; still verify every protected input.
4. Prefer the shared `NYARLATHACK_GAME_TESTS` / `NYARLATHACK_NATIVE_*` profile
   (`tests/chaos/native_fixture_config.py`) over new per-family env vars. Absent
   configuration may skip; partial, empty, wrong-mode or invalid must fail.
5. Distinguish publication, exact native acknowledgement, measured effect, expiry
   and replay. A synthetic oracle or admission alone isn't a turn-loop effect.
6. Passive witnesses forward each native function once, with no extra rule/RNG/
   helper calls. `near_capacity()` can refresh cached weight state: wrap real calls
   instead of querying it again. Derive extra food drains from independently
   recorded native source flags, never from the nutrition residual.
7. For same-turn admission, use raw event sequence plus effect state; an effect can
   stop at its expiry turn before the expiry event is emitted. Validate the whole
   trace after quit/reap.
8. Freeze gameplay command bytes and record prompt-only responses separately, each
   with prompt evidence (see `replay-and-fixtures.md` for the fountain prompt).
   Don't relax stock-comparison rules when defining an effect/control comparison.

## Revision identity

- Full discovery needs a fresh full-history checkout at the exact reviewed
  revision; some adapters derive their source root from `__file__`, so changing
  cwd does not rebind them. A revision-guard failure is fixed by building the
  reviewed revision with the preparer, never by rewriting receipts, roots, seeds,
  skips or pins.
- Frozen production + newer external test fixtures is not same-checkout
  acceptance; label both revisions.
- Formatting after native acceptance: prove AST/literal/comment equivalence
  separately; old byte receipts don't identify reformatted source. Hosted receipts
  may name GitHub's synthetic merge commit, not the branch tip.
- Every invocation gets a fresh private parent and distinct absent artifact leaves;
  never reuse leaves or delete successful evidence to reuse a path.
- Fountain acceptance uses `strict-desired`; `observed-prehook` is historical
  diagnosis only.
- Set all evidence variables before importing artifact-dependent oracle modules:
  skip decorators and baseline globals evaluate at import.

## Reading results

- Audit mandatory methods with structured `unittest.TestResult` outcomes, or verify
  subprocess exit + unique complete test blocks. Native artifact announcements and
  multiline descriptions split the `... ok` line; line-suffix parsers undercount.
- Require the reviewed method set, nonzero count, zero unexpected skips. Record
  executed IDs and evidence paths; a zero exit can hide skipped native checks.
- Top-level skips vs. configured nested oracle children are separate; don't add
  nested counts to the top level.
- If only a post-execution reporter fails, verify retained execution independently
  and write a separately labelled recovery record. Don't overwrite the failed
  receipt or replay games for prettier output.
- After a delegated timeout, inspect retained reports and owned processes before
  declaring failure; the run may have completed.
- A log filename containing `green` is not evidence; read its result.
- Report configured native, unconfigured offline, hosted and post-merge counts
  separately. No local run establishes remote workflow success; download and check
  hosted diagnostics rather than trusting an upload step.

## Auditing under an approval hold

When a requested native command is approval-held:

1. Retain the exact command and hold reason. Don't rephrase it, change
   interpreter, import its test bodies, or run it via another tool.
2. Continue only independently authorized read-only work, and don't call it a test
   execution: read complete changed sources; compare original assertion bodies by
   AST; hash protected inputs; validate retained raw outputs, saves, manifests and
   journal proofs.
3. Decode native records from the recorded compiled layout and actual save bytes
   (format/compression, unique exact source, bounds, padding, whole-record deltas,
   hashes), not from self-authored JSON. Never feed modified copies to a game.
4. Validate journal commit hashes, predecessor/sequence chains, exact envelope/
   source/note and latest run-proof identities. Don't invoke journal writers.
5. Retain only allowlisted process environment data. Supplement zero-exit
   manifests with driver wait/reap behavior and recorded-PID checks.
6. For mail: keep positive empty-mailbox invariants separate from any authorized
   synthetic arrival control; never inspect real host mail. An untouched mailbox
   while held is a pre-run invariant, not a post-run receipt.
7. Write explicit chronology: old blocker resolved, current blocker exact,
   executed outcomes, read-only outcomes, remaining gates. Keep one primary audit;
   reference evidence in place; don't stage/commit unless authorized.

## Negative fixtures and dependencies

- Negative native fixtures must hit the specific rejection, not any nonzero exit.
  Initialize the error path's window/logging callbacks too; a crash after the error
  message is a harness failure.
- For native-build feature assumptions, capture active preprocessor definitions and
  inspect the linked object/executable; headers alone don't prove a binary's
  capabilities.
- Freeze expected guards from case inputs, not observed effect bits, so a wrongly
  active effect can't disable its own negative comparison.
- A shared-startup correction is a new fixture identity: keep old failures, rerun
  the affected frozen surface.
- Separate unchanged-baseline, instrumentation-only and effect-on arms; an observer
  can change allocation/layout without drawing randomness. Random-helper
  invocations are not the same as random draws.
