# Quality control

The `Quality` GitHub Actions workflow runs on pull requests, pushes to `main`,
and manual dispatch. Continuous integration (CI) is deliberately offline with
respect to model providers: it needs no model keys, subscription authentication,
or inference allowance.

## Checks

- **Upstream hook inventory:** [reviewed seams and extension procedure](upstream-chaos-hooks.md).
  `/usr/bin/python3 -B scripts/check_upstream_hooks.py --root .` independently
  scans tracked native files; missing/extra and malformed inventory regressions
  run through existing `test_*.py` discovery in the full-history game job.
  This is lexical merge assistance, not physics or stock-equivalence evidence.

- **Protocol generation:** `python3 scripts/generate_protocol_contract.py --check`
  runs in the lint job, comparing the reviewed JSON against both checked-in
  generated targets without writing. Contract tests compile the real C core,
  check independent legacy expectations, deliberately bypass consumers, and
  exercise a disposable fourth row. Engine-unit message and transport byte tests
  are not linked-game physics or native acceptance; all native gates below remain.
- **Observation registration:** `test_observation_contract.py` pins production
  metadata independently. Hook references are review-only provenance: generator
  checks cover syntax/duplicates, not source existence, placement or execution;
  #33's independent inventory and human review remain separate obligations.
  The suite checks malformed registration through API and CLI, literal v2 bytes,
  and an isolated third-family lifecycle including registration removal. Real
  consumer-bypass controls mutate handwritten C family/channel/owner/writer checks
  and Python grouping, requiring behavioral assertion failures after successful
  compilation/import, without changing generated metadata. Existing IO/scope/episode/history
  suites retain their independent compatibility oracles. These are ENGINE-UNIT
  checks, not linked-game physics or native delivery acceptance.
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
does not accept the whole phase or establish hosted CI success. The configured
fresh local suite at `8f317763a3560bd774d0b61e134e7028a744412a` is independently
accepted: 679 unique tests in 303.455 seconds, 672 passed and seven top-level
skips (three ownership limits, four artifact-dependent matrix invocations).
Seven configured matrix-oracle child methods ran with zero skips; they are not
additional top-level tests or seven missing gates. The native command succeeded;
its reporting wrapper exited 1 on a multiline test-status parsing error and its
failed receipt is preserved. See the [evidence ledger](haunting-observations-evidence.md)
for approved turn-loop acceptance, strict-failure history and provenance.
Hosted execution and publication remain unverified; whole-phase sign-off is open.

The portable same-checkout reproduction recipe below requires authorization and a fresh
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

Native fixtures inherit their parent environment. Use only the official runner
below: it constructs a clean environment, excluding `NETHACKDIR` and `HACKDIR`.
Changing cwd alone does not isolate the frozen `Game` helper. A separately
authorized ad-hoc retained-old-save experiment must start under `env -i` with
explicit reviewed variables and launch only disposable save copies. That is a
separate experiment, not an alternative full-suite command.

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
/usr/bin/python3 scripts/run_native_tests.py \
  --root "$root" --expected-revision "$revision" --build-output "$out"
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
supervisor. All configured adapters use the same checked descriptor and derive
separate absent artifact leaves from its private invocation parent. No extra
production build or upstream comparison is added.

### Shared descriptor and result contract

`scripts/run_native_tests.py` is the official entry point in both the local
recipe and Actions. It calls the existing source selector before creating a
fresh private invocation directory under `out/fixtures`; it does not build or
infer a revision from HEAD or receipts. The required `--expected-revision` is
independently reviewed job input. The descriptor must match the actual checkout
containing the runner/tests. Source/header/object checks and native calibration
remain in the existing selector and drivers, not in a new provenance framework.

The runner writes a bounded strict JSON descriptor, owned by the current user,
mode `0600`, with no symlinks or hardlinks, and a `0700` artifact parent. Schema
version 1 has exactly `schema`, `root`, `revision`, `receipt`, `build_output`,
`artifact_parent`, `profile`, and `historical_stock`. Core uses `profile: "core"`
and `historical_stock: null`. Paths must be canonical absolute paths. Duplicate
keys, unknown fields/versions, partial selections and mixed family environment
configuration fail closed before game launch. The read-only helper is
`tests/chaos/native_fixture_config.py`; `NYARLATHACK_NATIVE_DESCRIPTOR` selects
this file. The runner supplies the independent revision separately and bridges
only the old common game-player selection keys for unchanged archived players.
Wholly unconfigured ordinary discovery still skips native gates; skips are not
acceptance. Existing archived fixture defaults and literal historical pins are
unchanged.

Registration inventory: platform, whistle, strict fountain, fountain matrix,
selected-action transport, delivery and history adapters consult the shared
helper. Platform gets the current off tuple; history maps the shared receipt
directory to its existing `1-manifest.json` interface. Delivery retains its
existing subprocess isolation. The matrix retains its fresh seven-method oracle
child and zero-skip receipt. Turn-loop is the optional profile below; its three
artifact oracles and historical mutation check use validated evidence bridges.
Other legacy game-player tests use the common compatibility bridge. The fatal
fountain CLI remains an explicitly authorized manual diagnostic, not a newly
registered death-run gate. Historical standalone CLIs keep their explicit
arguments and existing guards. A new family adds one registration and a helper-
consuming adapter, not a recipe environment prefix or copied root/revision block.

The runner invokes real unittest discovery exactly once in a sanitized environment
and returns its actual process exit status (signals remain nonzero). It never
parses printed status lines. Opaque merged output is retained in the invocation's
private `full-suite.log`, whose path is printed with the exit code. A fresh
invocation is required every time; no artifact leaves are precreated or reused.
The child umask is `022` so intentionally public negative fixtures remain public
inside private TMPDIR; descriptor/log creation is independently private.

For the additional, separately authorized local selected-command gate, use the
same command with `--profile selected-turnloop` and all three
`--historical-stock-tuple`, `--historical-stock-receipt`, and
`--historical-stock-revision` arguments selected from the frozen accepted stock
evidence. Its descriptor's `historical_stock` object has exactly `tuple`,
`receipt`, and `revision`. The existing historical verifier checks the literal
accepted tuple, revision, receipt and dump; the adapter uses the approved
`--provenance-dumps` comparison and retains the original strict result. No stock
revision is guessed or substituted. Actions has no external historical stock
baseline and runs core only, not this additional local gate.

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

The recipe above is the core native recipe, not the complete selected-command
acceptance invocation. The accepted `8f317763a` run additionally configured the
turn-loop adapter, its native evidence methods and historical-stock provenance.
Its seven-configuration gate is locally accepted under the approved
[supplemental dump contract](turnloop-dump-comparison-contract.md); all three
native strict-oracle methods and configured historical mutations executed without
skips. Literal strict cross-build dump comparison remains **FAILED**, separately
preserved; `task8_closed:false` is not rewritten by the independent review.
Whole-phase publication/sign-off and hosted CI remain unverified. The earlier
controlled native fatal run satisfies Task 7's fatal-interruption requirement,
not Task 8's turn-loop contract; no fatal-driver gate is registered here.
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
