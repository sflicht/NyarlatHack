# Quality control

The `Quality` GitHub Actions workflow runs on pull requests, pushes to `main`,
and manual dispatch. Continuous integration (CI) is deliberately offline with
respect to model providers: it needs no model keys, subscription authentication,
or inference allowance.

## Checks

- **Python lint and format:** pinned Ruff checks `chaos`, `tests/chaos`, and
  `scripts` using Python 3.11.
- **Native builds and offline tests:** Ubuntu 24.04 checks out full history at
  the job's exact revision (including the pull-request merge revision).
  `scripts/prepare_native_ci.py` builds the reviewed pre-curio `CHAOS=1` revision
  `4610d90612e3c255b37786e385d86f981b016bc2` in an independent local clone,
  then current `CHAOS=0` and `CHAOS=1`, sequentially with at most two make jobs.
  It requires the fixed selector-test baseline
  `fd7a91deb1dc33244e0f72a47d3a4ec584255852` to be available too.
  The complete unittest discovery runs **once**, with real-game tests enabled,
  the authenticated old-on tuple, a writable disposable stock tuple, and
  explicit `source-build` fixture selection backed by this run's receipts.
- **Secret history scan:** checksum-pinned Gitleaks scans reachable Git history,
  including merge diffs, with redacted output and inline allow comments ignored.

Native build/test logs are retained for seven days, including on failure.
Older runs for the same workflow/ref are cancelled. Jobs have explicit timeouts.
This is not a schedule for live game-model experiments.

## Permissions and dependencies

Workflow permissions are explicitly `contents: read`. Checkout does not persist
credentials. Events use `pull_request`, not `pull_request_target`. Official
checkout/setup/upload actions are pinned to reviewed commit identifiers, and
the Gitleaks release archive is checked against a fixed published checksum
before execution. No repository or model secrets are supplied to these checks.

This workflow does not itself enable branch protection or claim a general
security certification. Required-check rules can be configured separately once
these check names have been exercised successfully on GitHub.

## Two exact historical scanner exceptions

The only `.gitleaksignore` entries refer to commit
`ec53bef97fa66371bd058d954b5bc9a5179b9305`, in
`docs/evidence/milestone2-summary.json`, lines 163 and 191. These values are
SHA-256 (Secure Hash Algorithm, 256-bit) checksums of `chaos/oauth.py` and
`tests/chaos/test_oauth.py`, not credentials. They were recomputed against the
named files **at that historical revision** before adding the exceptions.

The exceptions are exact finding fingerprints, not directory/file-wide
exemptions. Future findings must be investigated rather than automatically
added. Pattern scanning is not proof that every possible encoded or unusual
secret is absent.

## Local equivalents

**Platform/whistle process isolation is implemented and accepted.** Their
supervisors isolate process-global umask and hard resource limits. The narrow
fountain hook/fixture and strict native adapter reviews are also accepted; this
does not accept the whole phase or establish hosted CI success. Caller wiring
and source-wiring unit tests alone do not verify native receipts. Hosted execution
and whole-phase acceptance remain open.

The proposed canonical recipe below requires authorization and a fresh
full-history checkout already at the independently approved revision, with
reviewed hooks and fixtures committed. All drivers, helpers, fixtures and
discovery must come from that same checkout. Separately verified reuse of frozen
production with external committed Python tests is not a fresh production build
at the tests' revision, nor execution of this same-checkout recipe. Keep those
revision identities and evidence separate. Changing the working directory does
not make external full-suite discovery compatible with frozen receipts: some
adapters derive their source root from their own file location and reject a
revision mismatch. Use the same-checkout recipe for full-suite acceptance.
`REVIEWED_REV` below is deliberately invalid as a 40-character hexadecimal
revision: replace it with the approved
full lowercase commit identifier, never automatically with HEAD or a receipt
value.

```bash
set -euo pipefail
ruff check chaos tests/chaos scripts
ruff format --check chaos tests/chaos scripts
# Use a fresh disposable full-history checkout: builds modify this checkout.
# Select a reviewed full revision independently, not from a receipt.
root=/absolute/path/to/fresh-reviewed-checkout
revision=REVIEWED_REV
umask 077
container=$(mktemp -d /tmp/nyarl-native-ci.XXXXXX)
out="$container/output" # absent; preparer creates it
/usr/bin/python3 "$root/scripts/prepare_native_ci.py" \
  --root "$root" --output-dir "$out" --expected-revision "$revision"
cd "$root"
umask 077
invocation=$(mktemp -d "$out/fixtures/full-suite.XXXXXX")
: > "$out/full-suite.log"
# Keep the log private without changing intentionally public negative fixtures.
umask 022
env -i PATH=/usr/bin:/bin HOME="$out/home" LANG=C.UTF-8 TZ=America/New_York \
  PKG_CONFIG_LIBDIR=/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig \
  MAIL="$out/MAIL" TMPDIR="$out/fixtures" PYTHONDONTWRITEBYTECODE=1 \
  NYARLATHACK_STOCK_DIR="$out/stock" NYARLATHACK_GAME_TESTS=1 \
  NYARLATHACK_PRECURIO_DIR="$out/precurio" \
  NYARLATHACK_NATIVE_FIXTURE_MODE=source-build \
  NYARLATHACK_NATIVE_BUILD_RECEIPT="$out/system-gcc13" \
  NYARLATHACK_NATIVE_EXPECTED_REVISION="$revision" \
  NYARLATHACK_PLATFORM_ROOT="$root" \
  NYARLATHACK_PLATFORM_RECEIPT="$out/system-gcc13" \
  NYARLATHACK_PLATFORM_REVISION="$revision" \
  NYARLATHACK_PLATFORM_ARTIFACTS="$invocation/platform" \
  NYARLATHACK_PLATFORM_OFF_TUPLE="$out/stock" \
  NYARLATHACK_WHISTLE_ROOT="$root" \
  NYARLATHACK_WHISTLE_RECEIPT="$out/system-gcc13" \
  NYARLATHACK_WHISTLE_REVISION="$revision" \
  NYARLATHACK_WHISTLE_ARTIFACTS="$invocation/whistle" \
  NYARLATHACK_FOUNTAIN_ROOT="$root" \
  NYARLATHACK_FOUNTAIN_RECEIPT="$out/system-gcc13" \
  NYARLATHACK_FOUNTAIN_REVISION="$revision" \
  NYARLATHACK_FOUNTAIN_ARTIFACTS="$invocation/fountain" \
  NYARLATHACK_FOUNTAIN_MATRIX_ARTIFACTS="$invocation/fountain-matrix" \
  NYARLATHACK_ACTION_TRANSPORT_ROOT="$root" \
  NYARLATHACK_ACTION_TRANSPORT_RECEIPT="$out/system-gcc13" \
  NYARLATHACK_ACTION_TRANSPORT_REVISION="$revision" \
  NYARLATHACK_ACTION_TRANSPORT_ARTIFACTS="$invocation/action-transport" \
  /usr/bin/python3 -m unittest discover -s tests/chaos -p 'test_*.py' -v \
  2>&1 | tee "$out/full-suite.log"
```

Preparation gets an absent output child of a private unique parent under `/tmp`.
CI publishes this path as `NYARLATHACK_CI_OUT` through `GITHUB_ENV` before running
the preparer. The selected build/test diagnostic upload runs only when that path
is nonempty, including after a preparer failure. Failures before publication
skip that upload entirely; no empty-base or root fallback globs are used.
A separate always-on upload retains only `runner.temp/native-preparation.log`
when present. Both uploads ignore missing files and retain artifacts for seven
days. Each suite or separately authorized standalone native launch needs a fresh
private invocation parent under `out/fixtures` and distinct, independent
**absent** platform/whistle/fountain leaves.
Never precreate, delete for reuse, or reuse those leaves; do not use symlinks as a
canonical-path workaround. Retain distinct logs for later authorized launches,
not overwrites or automatic retries. The registered fountain native adapter
always uses `strict-desired`; the command-line interface (CLI) retains
`observed-prehook` only for explicit historical diagnosis, never acceptance.
Discovery runs the strict adapter once, without a duplicate fountain CLI launch.
The accepted fountain matrix and selected-action transport are also required
native discovery gates, run serially through the existing bounded external
supervisor. The matrix reuses the explicit `NYARLATHACK_FOUNTAIN_ROOT`,
`RECEIPT`, and `REVISION` selection; its dedicated
`NYARLATHACK_FOUNTAIN_MATRIX_ARTIFACTS` leaf must be absent. Transport retains its
existing four `NYARLATHACK_ACTION_TRANSPORT_*` selection variables and a separate
absent artifact leaf. No extra production build or upstream comparison is added.

After the new matrix succeeds, its adapter starts a separately supervised fresh
Python interpreter against the current fixture's oracle module, explicitly
setting **both** `FOUNTAIN_MATRIX_EVIDENCE` and
`FOUNTAIN_MATRIX_CONTROL_EVIDENCE` to that invocation's matrix output. The
`oracle-execution.json` receipt names all seven executed test methods and records
zero skips as a condition of success. Ordinary discovery without these evidence
variables currently skips four artifact-dependent oracle methods; those skips
are not native acceptance and cannot replace the adapter's subsequent explicit
oracle execution. Driver or oracle nonzero exits fail the gate. The new adapter
unit tests use synthetic supervision results or real preflight failures without
building; they are not native acceptance evidence.

Registration does **not** resolve the strict turn-loop gate: it remains **FAILED,
pending user decision**. Whole-phase acceptance and fresh exact-revision native
CI remain open; no fatal-driver gate is registered by this change.
Delivery allocates its own private parent
under the same `/tmp`-backed `TMPDIR`. Observations remain child-scoped, not enabled
globally in the suite environment.

The preparer rejects existing/symlinked/overlapping output paths, shallow history,
revision mismatch, tracked changes, hidden index flags, and any `local.mk`.
It creates private `0700` directories and `0600` receipts and empty `MAIL`.
Every build uses exactly `/usr/bin/make -j2 clean` then `install`, with explicit
`CHAOS=0` or `CHAOS=1`, `CC=/usr/bin/cc`, and `PKG_CONFIG=/usr/bin/pkg-config`.
No caller `MAKEFLAGS`, compiler overrides or provider credentials enter the build.
Only the existing five-field system build environment is supplied; `HOME` is
measured from the runtime, with the other values fixed to the reviewed profile.

The supported compiler remains **exactly**
`cc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`, with the existing pkg-config flag
profile and native calibration pins unchanged. Installing Ubuntu dependencies
is not proof the hosted image still supplies that compiler. A mismatch records
its actual version and fails before make; it is a compatibility blocker, not
permission to fabricate a version or relax the verifier. Hosted build/test
execution of this preparation still requires independent verification.

`system-gcc13` contains measured compiler/flags, command exits and logs, tuple
hashes/sizes, headers, objects, ELF notes, and tracked-input preservation records.
Its completion lists only current modes `[0, 1]`; `old-on` has separate real
historical build receipts and `old-checkout.json` binds the literal revision.
A failed command cannot produce a successful mode manifest. Final source
selection uses the unchanged verifier; static native calibration still occurs
inside the suite, not as a claim in preparation metadata.

`off-archive` files remain `0444`. Distinct copies in `stock` and `precurio`
use executable `0755` and data/license `0644`, so the existing cross-format
save tests can overwrite their own `copy2` copies in either direction. No
shared historical installation is touched or made writable. The isolated old
clone remains under the private output directory; no worktree cleanup or
shared-object/hardlink clone is used.

Platform `OFF_TUPLE` selects the executable current-revision mode-0 `stock` copy,
not the nonexecutable `off-archive` or the mode-1 live installation. This is not an
independently built upstream baseline or off-object calibration. Historical
`precurio` remains separate; whistle has no `OFF_TUPLE` variable.

The suite uses system Python (3.11+), system tool `PATH`, an empty private home,
and a private `TMPDIR` to retain fixture diagnostics without importing ambient
credentials. Uploads select build receipts/logs and fixture JSON/JSONL, raw
terminal output (including selected `.bin` evidence), `.stdout`, `.stderr`, logs
and text, for seven days even on failure; game executables, shared libraries,
object files, Git directories, private HOME and MAIL are not uploaded. Any ledgers
in those offline fixture records belong to fake clients, not live Luna calls.
Never add a live credential directory or real provider ledger to these globs.

Real terminal and process fixtures are Linux-specific. The terminal driver
requires readable descendant-process information under `/proc`, plus Linux
`TIOCGPTPEER` support to identify the driven terminal's actual slave. Unsupported
kernels fail closed with an operating-system error, without a quiet-time
fallback. The driver recognizes x86-64 and AArch64 read-system-call numbers;
verification so far is on x86-64, not AArch64. It waits for the actual game to
block on terminal input, not an arbitrary quiet-output interval; if readiness
cannot be established before the fixed deadline, it reports a timeout. This includes
stock/no-observation runs and games started through the launcher supervisor.
Strict input, terminal-output, event and score-log replay comparisons remain
unchanged. A fixture needing privileged ownership changes may be skipped;
the suite also tests ownership validation without privilege. Model tests use
fake clients/local test servers,
not live-provider validation. Always inspect the actual run and its skip/failure
summary before reporting success.
