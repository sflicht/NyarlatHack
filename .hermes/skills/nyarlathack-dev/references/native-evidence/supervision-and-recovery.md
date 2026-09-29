# Process supervision and frozen-harness recovery

The shipped supervisor is `tests/chaos/native_driver_supervision.py`; reuse it.

## Supervision rules

- Process-wide resource, signal, environment and subreaper changes belong in a
  separate supervisor process.
- Process-group cleanup alone misses nested forkpty sessions. Enumerate only the
  subreaper's `/proc/self/task/<pid>/children`; prove ownership with
  `waitid(P_PID, WEXITED|WNOHANG|WNOWAIT)` before signaling.
- Keep leaders unreaped through group signaling (the PID pins the group). Never
  reap and then signal a remembered group; avoid `Popen.poll/wait` before cleanup.
- TERM first, then finite KILL/adoption/reap passes. Drain stdout/stderr with
  finite persisted caps.
- A missing child `exe` is fine only after confirming zombie state `Z`; keep its
  PID for post-supervisor reap checks.
- Defer catchable cancellation through cleanup, then recheck so it can't become
  success. Preserve primary exceptions and attach cleanup failures.
- Test with self-bounded fake workers and handshake-acquired pidfds; include nested
  forkpty/setsid descendants holding pipes, early exit, stale identities (mocks
  only), cancellation during cleanup.
- EOF may precede reaping; use bounded elapsed-time waits. Restore process-global
  settings (umask) with registered cleanup.
- State limits: exclusive single-threaded reaper, no hostile daemon escape, no
  guarantee after supervisor SIGKILL or host crash.

## PTY readiness

- The driver waits for the game to block on terminal input (Linux `/proc`
  syscall info, `TIOCGPTPEER`); see `docs/quality-control.md` for platform limits.
- Establish input-consumption progress before sampling a blocked-read syscall.
- Bind stdin to the slave of the driven master: compare fstat device/inode of the
  `TIOCGPTPEER` peer; test with a real second PTY that the driver fails closed.

## Recovering a frozen harness

- Preserve the failed experiment unchanged (crash saves, launch sentinel); new
  private artifact dir; a recovery launch needs explicit authorization.
- Reproduce classification defects offline from the retained response first; mark
  invented prompts synthetic; keep the predicate in an import-safe helper.
- Test unanswered apply/attack/direction/confirmation prompts, answered multiline
  output, and new prompts after status; keep stop-on-unhandled-prompt behavior.
- Before a retest, freeze protocol, driver, native build inputs, observer output
  paths and clock/entropy controls; copy rather than mutate predecessor inputs;
  check hardcoded observer destinations can't overwrite prior evidence.
- After a fresh launch, retain later failures instead of silently starting again.
- Compare pre/post-restore snapshots, accounting, cursor and journal bytes; report
  changed surrounding flags or clocks honestly.
- Verify predecessor hashes and repo cleanliness afterwards; remove only owned
  compiled assets after final use.
