---
name: nyarlathack-dev
description: "Use when working on NyarlatHack. Engine and replay gates."
version: 2.0.0
author: Xiongmao
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [nyarlathack, dnethack, native-tests, replay, save-restore, lua]
    related_skills: [bounded-lua-embedding]
---

# NyarlatHack development

Procedures for changing and verifying NyarlatHack (a dNetHack/dNAO fork with a
Python director in `chaos/`). The repository documents are the rules; this skill
holds the how-to and the traps. When they disagree, the repository wins.

## When to Use

- Editing engine C (`src/chaos_*.c`, hooks in upstream files), the `chaos/`
  sidecar, prompts, the protocol contract, or `tests/chaos/`.
- Building, running native/linked/PTY tests, save/restore or replay evidence.
- Auditing or cleaning up native test artifacts.
- Don't use for: generic Lua embedding questions (see `bounded-lua-embedding`).

## Read first

1. `AGENTS.md` (architecture rules, vocabulary, git identity, workspace hygiene).
2. `docs/quality-control.md` (verification tiers A/B/C, official native recipe).
3. `docs/workspace-hygiene.md` (per-run `TMPDIR`, end-of-run cleanup).
4. The live issue body and its full comment thread, `README.md`, `chaos/README.md`,
   and the subsystem doc under `docs/` you are touching. Closed issues, old
   reports and past test totals are not current acceptance.
5. Current state: branch, HEAD, worktrees, staged/unstaged/untracked files, live
   jobs, remote main, open PRs and checks. Preserve anything unexplained.

Do not describe design notes (`docs/tier3-notes.md`, proposals) as implemented.

## Workflow

**Build** (details, env pitfalls: `references/build-and-env.md`)

```
/usr/bin/make -j2 install CHAOS=1 CC=/usr/bin/cc PKG_CONFIG=/usr/bin/pkg-config
```

Use this for all development and native-test builds; repeat with `CHAOS=0` when
the change touches hooks. Plain `make -j4 install CHAOS=1` (README) is only for
a quick local play build. Keep each binary paired with its own `nhdat`.

**Test** (pick the scope; never call one scope another)

1. Fast offline: `python3 -B -m unittest discover -s tests/chaos -p 'test_*.py' -v`
   from the repo root. Read the skip count; skips are not passes.
2. Focused native: `NYARLATHACK_GAME_TESTS=1 python3 -B -m unittest discover -s
   tests/chaos -p 'test_next_use*.py' -v` after a fresh build. Retain stdout and
   the real exit status.
3. Full native acceptance: only the `scripts/prepare_native_ci.py` +
   `scripts/run_native_tests.py` recipe in `docs/quality-control.md`, on a fresh
   full-history checkout at an independently chosen reviewed revision. Never
   use `NYARLATHACK_GAME_TESTS=1` alone for full discovery.
4. Lint: `ruff check chaos tests/chaos scripts` and
   `ruff format --check chaos tests/chaos scripts`. Keep formatting out of
   untouched upstream C.
5. Match evidence to the PR's tier (`docs/quality-control.md#verification-tiers`).
   Anything touching game state, RNG draws or saves is Tier A.

**Commit and deliver**

1. Write the failing oracle first (behavioral RED, not a build/link failure).
2. Batch one coherent behavior plus its boundary matrix per PR.
3. Spec review, then independent correctness/security review; freeze and verify
   the reviewed bytes before commit.
4. Repo-local identity from `AGENTS.md`; conventional commits; never force-push
   `main`; never commit build outputs or bulk evidence.
5. Read back pushed head, PR body and checks. Merge only with current user
   authorization and an exact head guard; verify the merge remotely and watch
   post-merge CI with a bounded watcher.
6. Report component, linked-fixture, real Unix save/restore, ordinary nonwizard
   play, replay, hosted CI and live-model claims separately.
7. End the run with the `docs/workspace-hygiene.md` ritual and report freed space.

## Pitfalls

- **Every entropy read matters.** `check_reseed()` in `src/rnd.c` reads
  `/dev/urandom` and time independently of the seed; `srandom()` alone does not
  make `rn2()` reproducible. Replay needs the test-only clock shim plus inputs.
- **`--wrap` misses same-object calls.** GNU ld cannot intercept a call whose
  caller and callee share a translation unit (`makemon`→`makemon_full`,
  `deferred_goto`→`goto_level`). Wrap the external entry instead.
- **Native tty fixtures hang on inherited stdin.** Use
  `stdin=subprocess.DEVNULL` (or `< /dev/null`); an open, unwritten pipe blocks
  at `--More--` until timeout.
- **Unbounded log reads can OOM.** Fixture logs may symlink to `/dev/full`; reject
  symlinks/non-regular files, bound reads and subprocess timeouts.
- **Pinned files.** `tests/chaos/gameplay_support.py` is pinned by
  `SOURCE_DRIVER_HASH`; `chaos/prompts/next-use-mechanics.txt` is capped by
  `MAX_PROMPT_BYTES` and hash-bound by `next-use-mechanics-sources.json`.
- **Triplicated origin lifetime**: `CHAOS_NEXT_USE_ORIGIN_LIFETIME`,
  `ORIGIN_LIFETIME`, `ORIGIN_TTL` must change together.
- **Admission is not effect.** Installation, admission/debit, telegraph, native
  effect, public delivery and player notice are separate claims.
- **Never rescue a run.** No seed hunting, rerolls, hidden-state steering, relaxed
  comparators or refreshed historical hashes to get green.
- **Gated work stays gated.** Live model calls, `ordinary_route` execution,
  provider/spend changes, human playtests: separate explicit authorization. An
  approval hold is binding; don't reroute the command through another tool.
- **Never `pkill -f` a pattern in your own command line.**

## References

- `references/build-and-env.md` — read before building, switching CHAOS modes,
  A/B builds, or when Lua/pkg-config/interpreter setup fails.
- `references/artifact-hygiene.md` — read before deleting build products or
  test roots beyond the standard hygiene ritual.
- `references/replay-and-fixtures.md` — read when driving `chaos play`, PTY
  runs, ordinary-play experiments, or exact replay from saves.
- `references/native-evidence.md` — read when running native tests for
  acceptance, reporting results, or auditing evidence under an approval hold.
- `references/native-linked-fixtures.md` — read when writing linked C
  fixtures, RNG-purity checks, or caller-accounting harnesses.
- `references/engine-integration-traps.md` — read before adding engine hooks,
  object/monster fields, save state, or presentation.
- `references/protocol-contract.md` — read when editing
  `chaos/protocol_contract.json`, its generator, or next-use guide/lifetimes.
- `references/gates-and-model-evidence.md` — read before any live model call,
  retained-response replay, or history-conditioned feature.
- `references/native-evidence/` — topic deep-dives: `pty-acceptance.md`,
  `save-restore.md`, `c-engine-units.md`, `ui-and-object-streams.md`,
  `observation-hooks.md`, `curio-transfer.md`, `journals.md`,
  `supervision-and-recovery.md`.
