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

Scope limit: the tests' own `gameplay_support.Game` driver is pinned by hash
(`SOURCE_DRIVER_HASH`) and was left unchanged. Tests that already register
their directories clean up after themselves. Legacy tests that create
directories without registering them still leave them for the 7-day scan.
