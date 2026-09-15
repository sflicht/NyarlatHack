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

```bash
set -euo pipefail
ruff check chaos tests/chaos scripts
ruff format --check chaos tests/chaos scripts
# Use a fresh disposable full-history checkout: builds modify this checkout.
# Select a reviewed full revision independently, not from a receipt.
root=/absolute/path/to/disposable-checkout
revision=FULL_REVIEWED_LOWERCASE_40_HEX_REVISION
out=/absolute/path/to/nonexistent-private-output
/usr/bin/python3 "$root/scripts/prepare_native_ci.py" \
  --root "$root" --output-dir "$out" --expected-revision "$revision"
cd "$root"
umask 077
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
  /usr/bin/python3 -m unittest discover -s tests/chaos -p 'test_*.py' -v \
  2>&1 | tee "$out/full-suite.log"
```

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

The suite uses system Python (3.11+), system tool `PATH`, an empty private home,
and a private `TMPDIR` to retain fixture diagnostics without importing ambient
credentials. Uploads select build receipts/logs and fixture JSON/JSONL, raw
terminal output, logs and text only, for seven days even on failure; binaries,
object files, Git directories and the private home are not uploaded. Any ledgers
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
