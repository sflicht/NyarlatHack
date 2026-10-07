# Build and environment

- Set `TMPDIR` in the environment of the actual heavy command or its driver;
  do not depend on an export made by an earlier tool subprocess. Include any
  positively identified diagnostic spill root in this item's retirement proof.


`GNUmakefile` is the real build; `sys/unix/Makefile.*` are legacy. Official
native-acceptance builds are done only by `scripts/prepare_native_ci.py` (see
`docs/quality-control.md`); this file covers development builds.

## Recommended command

```
/usr/bin/make -j2 install CHAOS=1 CC=/usr/bin/cc PKG_CONFIG=/usr/bin/pkg-config
```

- Use it for every build that feeds a native test. It matches the preparer's
  compiler/pkg-config profile and the two-job limit on the shared host.
- `make -j4 install CHAOS=1` (README "Play in three commands") is fine for a
  quick local play build only. Never mix its outputs into test evidence.
- Test both modes when a change touches hooks: `CHAOS=0` must compile
  warning-clean and behave as stock. Compiling changed files off-mode is not a
  complete off-mode install and runtime check; say which you did.
- Keep each installed executable paired with its own `nhdat` (and `license`).
  Changing only the binary can correctly reject the dungeon data before play.
- Sequential mode builds overwrite the other mode's intermediate objects. If
  you need a mode's generated date header or objects, capture them before the
  next build and don't claim overwritten intermediates still exist.
- Don't flip shared objects while another reviewer/test process is linking them.
- Capture the real `make` exit status, not a pipeline's last command. Keep logs
  outside the repo (per-run `TMPDIR`).

## Environment traps

- An inherited `PKG_CONFIG` (for example from conda) can miss system Lua even
  when compiler tests find it. Set `PKG_CONFIG=/usr/bin/pkg-config`; if needed
  also `PKG_CONFIG_PATH=/usr/lib/x86_64-linux-gnu/pkgconfig`. When Lua setup
  fails, check `pkg-config --cflags --libs lua5.4` before treating errors as
  skips.
- For test commands launched under tmux, use an explicit clean environment
  (`env -i` plus HOME, PATH=/usr/bin:/bin, TMPDIR and the system pkg-config
  settings). The tmux server may retain a different compiler/pkg-config PATH
  from the current terminal. Merely setting PKG_CONFIG does not fix tests that
  invoke the literal `pkg-config` command; preserve setup-failure logs and rerun
  the unchanged suite with the corrected environment.
- For an A/B build of another revision (`git archive` into a scratch root), run
  it under `env -i HOME=... PATH=/usr/bin:/bin ...`. Conda variables inherited
  by background shells break the `lua.h` include.
- Use `/usr/bin/python3` for native suites. An ambient Python may lack Linux
  process-fd (pidfd) support and silently skip supervision coverage; read the
  skip reasons.
- Don't set `PYTHONPATH` in ad-hoc invocations. Run discovery from the repo root;
  named-module runs from another cwd fail to import `chaos`. Executing a test
  file via runpy may run zero tests if it lacks a `unittest.main` guard.
- Native fixtures inherit the parent environment (`NETHACKDIR`, `HACKDIR`,
  `MAIL`). The official runner sanitizes it; ad-hoc runs need `env -i` with
  explicit variables.
- For a normal executable link, select GNUmakefile's `GAME_O`, not `ALL_O`
  (which includes utility objects with their own `main`). Evaluate object
  assignments in a scratch makefile; even `make -n` on the full makefile may
  regenerate dependency includes.
- Don't regenerate `include/macromagic.h` unless its inputs changed (AGENTS.md).
- Generated headers stay git-ignored. After `make clean`, even the fast suite
  needs native headers for its compiled unit fixtures. A full development
  install regenerates them under heavy admission. Preparing only `pm.h`,
  `onames.h`, `gnames.h` and `verinfo.h` is insufficient: the save-layout reporter
  also includes `date.h`, whose make target depends on the engine objects.
  Retain missing-header failures; do not convert their setup errors into skips.

## Pitfalls

- `pkill -f <pattern>` kills your own shell if the pattern appears in your
  command line (for example a temp-root name). Kill by recorded PID.
- A build finishing is not native acceptance; a green focused suite is not the
  full recipe.

- Freeze HEAD, tracked files and shared build assets until a full native suite
  exits. The reproducibility sweep embeds `git rev-parse HEAD` in each report;
  even a test/docs-only commit during its paired runs can change the digest.
  Prepare the next change outside the worktree, then commit after the gate exits.
