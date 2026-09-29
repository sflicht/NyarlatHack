# Workspace hygiene

The VPS is shared with other projects. NyarlatHack runs leave nothing behind
that nobody will read.

- **Per-run temp root.** Every agent run and test run uses
  `/tmp/nyarlathack-work/<run-id>/`, exported as `TMPDIR` for the whole run
  (`mkdir -p` it first). It is under `/tmp`, so the tests' "artifacts under
  /tmp" checks still pass.
- **Delete it at the end** unless something failed. Failed-run artifacts may
  stay for at most 7 days. Put a `KEEP` file in a directory only while someone
  is actively using it.
- **Keep evidence properly.** Anything worth keeping goes into committed Tier A
  evidence, or into `~/.hermes/reports/nyarlathack-*` with a pointer in the PR.
  Never cite a bare `/tmp` path as the record (see #176).
- **No `/tmp` citations in `docs/`.** Small evidence (reviews, receipts, logs,
  result JSON) goes under `docs/evidence/`; larger artifacts go to a durable
  location outside Git, cited by path plus SHA-256. `scripts/check_docs_tmp.py`
  (run in Quality CI) fails when a tracked file under `docs/` has a `/tmp`
  path citation beyond `scripts/docs_tmp_allowlist.json`. That allowlist freezes the
  historical citations, per file and count; their surviving artifacts were
  moved to `~/nyarlathack-evidence/tmp-2026-09/` on the project host, mapped in
  its `MAPPING.json`. Don't add allowlist entries for new evidence. Commands
  that *create* scratch directories belong in the doc, but write them with
  `$TMPDIR` rather than a literal `/tmp` path.
- **Clones and build outputs** are removed once their branch is pushed and the
  tree is clean (no uncommitted changes, stashes or unpushed commits).
- **Tests tidy up after themselves.** `tests/chaos/artifact_hygiene.py` removes
  the temp dirs of passing tests. `scripts/seed_sweep.py` and
  `scripts/run_native_tests.py` do the same after a successful sweep or suite.
  Failures keep their dirs and print where they are (`ARTIFACTS_RETAINED=`,
  `SWEEP_WORK_RETAINED=`, `fixtures retained:`). Set
  `NYARLATHACK_KEEP_ARTIFACTS=1` to keep everything. On GitHub Actions they are
  always kept, because the workflow uploads fixture diagnostics even after a
  passing run and the runner is discarded afterwards.

## End-of-run ritual

Before the final message of a run:

```
python3 scripts/clean_workspace.py --apply /tmp/nyarlathack-work/<run-id>
python3 scripts/clean_workspace.py      # dry run: other leftovers older than 7 days
```

Report the freed space it prints in the final message or PR comment.

`scripts/clean_workspace.py` only considers:

- children of `/tmp/nyarlathack-work/`;
- `nyarlathack-*` and `nyarl-*` entries directly in `/tmp` and
  `~/.hermes/cache/scratch`.

Anything else named on the command line is refused. It never follows
symlinks, and it skips items another user owns, directories with a `KEEP`
file, and anything a live process is using (its working directory, open files
or mapped files). Without `--apply` it only reports. Named paths are removed at
any age; a scan without paths removes only items older than `--max-age` days
(default 7).

## `~/.local/share/nyarlathack`

This directory holds only what tests and docs read by default: the two test
baselines (`baselines/ff37b3a7a`, `generated-curio/prechange-on`), the
`milestone2/` ledger and smoke evidence, the acceptance evidence cited in
`docs/evidence/`, and small PDFs and write-ups. On 2026-09-27 older run output
was moved into zstd tar archives under
`~/.hermes/reports/nyarlathack-archive/local-share/` (checksums in `SHA256SUMS`;
the report is on PR #184). To restore one, for example the baseline that
`docs/evidence/milestone2-extra-checks.py` reads:

```
cd ~/.hermes/reports/nyarlathack-archive/local-share && sha256sum -c SHA256SUMS
zstd -dc --long=27 baselines-28bf1b192.tar.zst | tar -C ~/.local/share/nyarlathack -xf -
```

Scope limit: the tests' own `gameplay_support.Game` driver is pinned by hash
(`SOURCE_DRIVER_HASH`) and was left unchanged. Tests that already register
their directories clean up after themselves. Legacy tests that create
directories without registering them still leave them for the 7-day scan.
