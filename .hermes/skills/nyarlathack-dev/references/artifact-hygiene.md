# Artifact hygiene

The repository policy is in `AGENTS.md` ("Workspace hygiene") and
`docs/workspace-hygiene.md`: per-run `TMPDIR` under `/tmp/nyarlathack-work/`,
the `scripts/clean_workspace.py` end-of-run ritual, where evidence may live, and
`NYARLATHACK_KEEP_ARTIFACTS`. Follow those; this file only adds the procedure for
cleanup beyond that ritual.

## What to keep vs. discard

- Disposable once the owning run is inactive: copied executables, object files,
  shared/static libraries, generated game data, duplicate game installs. Anything
  rebuildable from a commit need not be kept; don't keep one binary per case
  for hypothetical replay, and don't archive binaries just to keep them.
- Keep: source and fixture source, build commands and commit provenance, logs,
  prompts/responses/envelopes, receipts, assertions, native traces/events, input
  tapes, unique saves and corruption specimens, failure evidence.
- Don't imply a rebuilt binary is byte-identical to a discarded one without
  checking. A discarded binary doesn't invalidate its already-reviewed record.
- Don't retire the only current execution baseline while another task uses it.

## Cleanup procedure (beyond `clean_workspace.py`)

1. Inspect git worktrees, live processes and disk usage. Separate task-owned
   roots from other projects and other workers.
2. Build an explicit manifest. Identify ELF executables/libraries/objects and
   generated assets by content, not the executable bit (scripts are source).
   Keep core dumps and unreadable negative-test inputs as diagnostics.
3. Exclude anything a live process uses (executable, cwd, open or mapped files).
   Same-user point-in-time checks are not full-host clearance; say so.
4. For duplicate retirement, keep a matching anchor; record type/hash/inode and
   allocated blocks; journal intent → unlink → readback; rehash preserved files.
5. Read back: deleted paths absent, retained files unchanged, real free space
   measured. Count reclaimed allocation once per inode; exclude surviving
   hardlinks.
6. Resuming a partial deletion: work only from the immutable manifest and the
   durable prepared/deleted journal, reconcile every missing path to a verified
   deletion, and stop on persistent unknown inaccessible processes rather than
   weakening the scan.

## Rules

- Never hardlink mutable production build outputs into evidence cases. Shared
  immutable copies must be private to the suite; replace case executables
  atomically, never overwrite a shared inode.
- No blanket `git clean`, reset, stash, worktree removal or broad `/tmp`
  deletion. Don't change permissions to read protected evidence.
- Make a test tidy up by registering its dirs with `tests/chaos/artifact_hygiene.py`
  (`track`, `RetainOnFailure`). Don't edit `tests/chaos/gameplay_support.py` for
  hygiene: its hash is pinned by `SOURCE_DRIVER_HASH`.
- Git worktrees of one repo share branches: `git log --branches --not --remotes`
  reports the whole repo. Check each worktree's own HEAD with
  `git branch -r --contains HEAD` before `git worktree remove` on clean,
  pushed trees.
- Edits to `AGENTS.md` may hit a protected-file approval prompt. In unattended
  runs, put the text in `docs/` and flag it in the PR.

## Pitfalls

- Fixtures may copy a large executable into every case, so a short suite can
  retain hundreds of MB while logs are tiny. Bound growth before a large suite.
- Parent-directory mtimes change during your own cleanup; don't mistake that for
  a newly active run.
