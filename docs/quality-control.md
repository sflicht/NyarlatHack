# Quality control

The `Quality` GitHub Actions workflow runs on pull requests, pushes to `main`,
and manual dispatch. Continuous integration (CI) is deliberately offline with
respect to model providers: it needs no model keys, subscription authentication,
or inference allowance.

## Checks

- **Python lint and format:** pinned Ruff checks `chaos`, `tests/chaos`, and
  `scripts` using Python 3.11.
- **Native builds and offline tests:** Ubuntu 24.04 builds `CHAOS=0`, preserves
  that executable with its matching `nhdat` and `license`, then builds
  `CHAOS=1`. The complete unittest suite runs with real-game tests enabled and
  the freshly built off-mode installation as its comparison baseline.
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

```sh
ruff check chaos tests/chaos scripts
ruff format --check chaos tests/chaos scripts
make -j2 install CHAOS=0
# Preserve dnethack, nhdat and license together in an external directory.
make -j2 install CHAOS=1
NYARLATHACK_STOCK_DIR=/absolute/path/to/off-build \
NYARLATHACK_GAME_TESTS=1 \
python3 -m unittest discover -s tests/chaos -p 'test_*.py' -v
```

Real terminal and process fixtures are Linux-specific. A fixture needing
privileged ownership changes may be skipped; the suite also tests ownership
validation without privilege. Model tests use fake clients/local test servers,
not live-provider validation. Always inspect the actual run and its skip/failure
summary before reporting success.
