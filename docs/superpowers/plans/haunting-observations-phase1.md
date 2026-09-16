# Observation-only action evidence Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task, under the parent-selected observation-only contract. Review each increment for specification compliance, then code quality.

**Goal:** Record actual selected whistle sounds and confirmed fountain outcomes, then produce bounded, deterministic, evidence-linked offline summaries without changing gameplay.

**Architecture:** Opt-in v2 observations share the existing sequenced transport; legacy v1 parsing and authoring remain unchanged and reject mixed logs. Small transient native scopes bind fixed semantic notices to selected actions. One new offline module validates and projects evidence; it has no live director connection.

**Tech Stack:** Existing C engine/transport, Python 3.11 standard-library unittest, installed Ruff, existing linked-engine and terminal fixtures.

---

## Scope and review gate

Read `docs/superpowers/specs/haunting-observations-phase1.md` as the parent-selected exact contract. Its version marker, fixed notice vocabulary/delivery seam, selected-root semantics and small bounds are selected for this observation-only implementation; tests must verify them. This plan does not approve either mechanics survey adapter. No enhanced whistle, fountain remapping, companion telemetry, inventory-potion instrumentation, persistent mapping, save ABI, model calls, prompt changes, haunting lifecycle or source-program state.

Baseline supplied by parent: `/home/hermes/nyarlathack`, `9559cd0dc8936301ae8083600e7e930fe334506c`. README/AGENTS and relevant code/tests were read. CodeGraph reported no index; direct reads were used without indexing. No implementation, imports, execution, tests, builds, git edits or network occurred while drafting.

### Source findings that constrain implementation

- `chaos_io.c:52–70` has a 3072-byte line buffer and advances sequence only after append/fsync. Keep that bound and actual-write semantics.
- `chaos_engine.c:37–86` separates observation from polling and suppresses shadow output. Reuse `context()`; never poll from new hooks.
- `apply.c:12045` logs a generic attempt before capacity/selection/curio interception. It cannot prove whistling. Both whistle cases follow interception at `12249–12255`; shared sound helpers also serve eucalyptus and an artifact (`artifact.c:6796`). Scope only the two selected whistle cases; do not accidentally cover those callers.
- `potion.c:450–454` confirms the fountain, but decline falls through to `getobj` at 492. It excludes Levitation before prompting. `drinkfountain` independently retains its reach guard **after** its existing `rnd(30)` (`fountain.c:2050–2054`). Never move that draw or create a false cancel.
- `pline.c:139–154` can suppress a requested message. Post-`pline` logging alone is not evidence of display. `detect.c:875–884` returns without displaying on an empty level; record only its map-display seam at 916.
- Existing native observation tests primarily exercise logger/status hooks; they are not full whistle/fountain purity evidence. Existing authoring `_project` validates contiguous history but only exposes Sanity/Insight. Leave it and frozen Thimble evidence unchanged.

## Execution discipline

Each numbered task below is a separate RED→GREEN increment; its listed cases are individual test-first microsteps, not permission to implement everything before running a test. Write a case, run it and retain the intended missing-behavior failure, implement minimally, rerun it, then refactor while green. Import/syntax/link failures alone are not behavioral RED evidence: use minimal interfaces or the existing weak-symbol fixture technique as needed. Specification review precedes quality review; fix and rerun before the next task. Commit only through the parent's authorized implementation workflow, not during this design task.

Commands below are **future commands**, not results. Run Python commands from the implementing checkout with `PYTHONPATH=.:tests/chaos`; use unittest, not pytest or package installation.

### 1. Freeze legacy compatibility tests

**Files:** modify `tests/chaos/test_observations.py`; test `tests/chaos/test_director.py` unchanged.

Add explicit fixtures proving that v1 unknown top-level keys remain accepted and redacted, requests remain exact-key, and v1 `parse_event`, `State`, `EventReader` reject the proposed v2 enabled marker. Preserve old logs without vitals and prayer cancellation tests. These existing guarantees should already be GREEN; do not pretend they are feature RED. New offline acceptance of the marker in task 2 is RED.

Run: `python3 -m unittest test_observations.ObservationSchemaTests test_director.DirectorTests -v`.

### 2. Add the isolated mixed parser

**Files:** create `chaos/episodes.py`, `tests/chaos/test_episodes.py`; no changes to `chaos/protocol.py`.

Implement `parse_episode_event(raw)` using `strict_json`, `integer`, `NUMBERS`, `VITALS` and unchanged `parse_event` for v1. Explicitly validate every v2 envelope/payload key and legal combination in the companion contract. Do not convert v2 into fabricated v1 events to reuse `State`.

Synthetic example for the new test file (not a native receipt):

```python
import json
import unittest
from test_director import event
from chaos.episodes import parse_episode_event, project_episodes


def obs(seq, operation, stage, root_seq=0, fact="none"):
    return event(seq, v=2, event="observation", detail="",
                 safe=0 if stage == "enabled" else 1,
                 phase="attempt" if stage == "started" else "result",
                 vitals=dict(hp=7, hp_max=20, power=2, power_max=10),
                 observation=dict(operation=operation, stage=stage,
                                  root_seq=root_seq, fact=fact))


def wire(*records):
    return b"".join(json.dumps(r).encode() + b"\n" for r in records)


class EpisodeTests(unittest.TestCase):
    def test_extension_rejects_hidden_keys(self):
        row = obs(3, "whistling", "started")
        row["observation"]["otyp"] = 999
        with self.assertRaises(ValueError):
            parse_episode_event(json.dumps(row).encode())

    def test_completed_notice_has_exact_evidence(self):
        raw = wire(obs(1, "none", "enabled"),
                   event(2, event="session", detail="new", safe=0),
                   obs(3, "whistling", "started"),
                   obs(4, "whistling", "notice", 3, "sound_high"),
                   obs(5, "whistling", "completed", 3))
        group = project_episodes(raw)["episodes"][0]
        self.assertEqual(group, dict(operation="whistling", count=1,
            saturated=False, evidence=[dict(root_seq=3, notice_seq=4,
                                            end_seq=5, fact="sound_high")]))
```

Add table-driven missing/extra keys, bool/overflow, duplicate keys, nonfinite values, illegal phase/stage/operation/fact, wrong root and unknown-version cases. Normalize malformed schema failures to `ValueError`.

Run RED/GREEN: `python3 -m unittest test_episodes -v`.

### 3. Validate linked history, then reduce the bounded window

**Files:** `chaos/episodes.py`, `tests/chaos/test_episodes.py`.

First implement chronology/reference checks: complete newline, caps, contiguous sequence, fresh counters, enabled-marker/session adjacency, restore chain, monotonic turn/safe/spent/last_id, no records after death. Keep only one active root for linkage validation. Terminal/notice must match it; reject duplicates, future/orphan/wrong-operation links, second notices and `cannot_reach` followed by completed. Boundaries end linkage; unfinished roots remain incomplete, not cancelled. V2 roots require the session's marker. V1-only history is valid but supplies no selected evidence.

Next implement the last-32-root deque and exact contract projection. Recompute groups from that deque: completed-with-notice only, two operation groups, first two/latest evidence, capped counts. Case-by-case RED tests: missing terminal excludes positive entry; blocked versus completed/no-notice; unrelated apply creates no pending root; third versus fourth count saturation; 33rd-root eviction; first-two/latest determinism; restore resets window; hostile legacy extras never appear; 4096-byte public ceiling fails rather than clipping. Repeat identical input and assert identical canonical JSON bytes.

Run: `python3 -m unittest test_episodes -v` after each case.

### 4. Bind summaries to a checked offline source prefix

**Files:** same module/tests; reuse existing helpers without refactoring their callers.

Implement `snapshot_episodes(path, *, checkpoint=None)`. Reuse `curio_store._directory`, `curio_continuity._file`/`_inode`, `curio_store._digest`, and `director.DEFAULT_BYTES/DEFAULT_EVENTS`. Return public JSON-compatible data separately from `{directory,event:{identity,length,sha256}}` host proof. A checkpoint validates identity and hashes its exact prefix, then projects only that prefix; valid appended bytes do not change its answer. Never include host paths/identities in public output.

RED tests use private `TemporaryDirectory`/0600 files: append, replacement, same-length rewrite, truncation, symlink, wrong mode, partial tail, foreign checkpoint and caps. Reopen/recheck the exact target before accepting proof. No new generalized evidence framework, tailer or CLI. Existing curio-generation functions must not import this module.

### 5. Add bounded C transport and scope helpers

**Files:** modify `include/chaos_protocol.h` (enums only), `include/chaos_io.h`, `include/chaos.h`, `src/chaos_io.c`, `src/chaos_engine.c`; create `tests/chaos/episode_observations.c`, `tests/chaos/test_episode_native.py`.

Start with standalone writer assertions and legacy byte-golden comparisons. Internal writer can accept a version argument while existing callers pass literal 1 with unchanged formatting. Typed writer interface: `int chaos_io_observation(struct chaos_io *, struct chaos_state *, const struct chaos_context *, int operation, int stage, long root_seq, int fact)`, returning write success. Use closed enum-to-literal tables, checked `snprintf`, existing 3072-byte line and at most existing 512-byte extra buffer. No string-payload API. Keep `chaos_state`, `struct you`, save/bones discriminators untouched.

Engine API: `long chaos_observation_begin(int operation)`; `void chaos_observation_end(long root)`; `void chaos_observation_arm(int operation,int fact)`; `void chaos_observation_disarm(void)`; `struct chaos_observation_token { long root; int fact; }` is transient and unsaved. `struct chaos_observation_token chaos_observation_take_message(void)` and `chaos_observation_take_map(void)` return a zero-root/none token when unavailable. `void chaos_observation_delivered(struct chaos_observation_token)` and `chaos_observation_map_delivered(struct chaos_observation_token)` validate the originating root, fact and channel before recording. `void chaos_observation_blocked(void)`. This action-bound interface supersedes the initially implemented fact-only interface before any production delivery callers are added. Define shared fixed enums in `chaos_protocol.h`, include that header from `chaos.h`, and provide no-op/zero `CHAOS=0` macros in `chaos.h`. Maintain only transient root/operation, pending fact, notice-used and blocked fields. Begin returns post-write sequence or zero; end clears even on failure. Message take consumes only message facts, not map facts. Reset stale scope on new selected begin, session/level boundary and death. Helpers reject disabled, shadow and gameover contexts without changing native control flow.

Read opt-in once at startup; prepend enabled marker before v1 session. Marker failure disables further observation transport for that process, not gameplay; never expose a falsely legacy prefix followed by later v2 actions. Test disabled/invalid flag, absent run directory, successful real sequence with interleaved legacy event, root/notice/end write or fsync failure, overflow, duplicate end, stale scope, shadow suppression. Preserve exact legacy stream bytes when off.

### 6. Record delivered whistle tones through full selected actions

**Files:** first `src/pline.c`, `win/tty/wintty.c`, `win/tty/topl.c`, `include/wintty.h`, and new `tests/chaos/episode_delivery.c` / `test_episode_delivery.py` for the delivery primitive; then `src/apply.c` and full-linked native fixtures for selected actions.

Implement the delivery primitive before selected actions. Keep a root-bound token local at `vpline` entry. Preserve the window-procedure interface and public void TTY entry points; use shared native TTY implementations returning whether the selected text reached the rendering branch. The exact `win_putstr == tty_putstr` callback selects supported delivery; unsupported or wrapped callbacks print once through the original path without a notice. Check actual rendering, including WIN_STOP already set or set by a pre-render More prompt; do not revoke delivery merely because a post-render More sets WIN_STOP. Do not use a global acknowledgement bit or pass message strings into observation code. Early suppression and raw pre-window fallback yield no notice. Validate real output functions in current-source tests before claiming delivery; host-link feasibility is not yet established.

Then bracket only the two whistle cases in `doapply` with begin/native-call/end. Do not change signatures or instrument eucalyptus/artifact callers. Inside shared native sound helpers arm the fact matching the already-selected wording, make the existing message call once, disarm; keep wake/EDOG/relocation/trap/identification paths intact. The local action-bound token and verified port result—not merely reaching `putstr`—control the notice. Full-action and full-engine acceptance remain separate from delivery-unit tests.

Fixture uses real `doapply` and `nextgetobj` from a globalized **copy** of `invent.o`, as in `test_curio_apply.py`. RED cases cover both identities known/unknown, cursed tones, both cursed-magic branches, hallucinated normal tone, NOSHOW/NOREP suppression, selection cancel, tagged curio, leaf and artifact negatives. Full native wake/EDOG and magic relocation/trap aftermath must match off/on; never emit companion evidence. Ordinary apply remains `MOVE_PARTIAL`; do not hardcode the magic return as ordinary partial movement.

### 7. Record confirmed fountain outcomes without expanding drink coverage

**Files:** `src/potion.c`, `src/fountain.c`, `src/detect.c`, same native tests.

In only the existing yes branch: begin fountain scope, call `drinkfountain()` once, end, retain `MOVE_QUAFFED`. Arm fixed facts around refreshment/foul messages; reach guard marks blocked and arms `cannot_reach`. Arm map fact only around case 26's existing detection call; consume after the actual map display inside `monster_detect`. Disarm after each call. Leave every fate, magical branch, early return and dryup order unchanged. No hooks in `dopotion`, inventory consumption, sink or dipping.

Drive real `dodrink` with controlled window-port answers: yes; no then cancelled selection; no then actual potion ingestion; no mouth; Levitation bypassing fountain prompt. Assert no fountain root for those non-yes paths. Separately exercise full `drinkfountain` under an explicitly armed test scope for its low-level reach guard; label that unreachable-through-normal-prompt coverage honestly, never pretend it was a normal confirmed drink. Test refresh/foul variants, actual detection with/without map, hallucination, unsupported fate completed/no-notice, magical early returns and fatal interruption with no terminal after death.

### 8. Prove whole-action purity and integration; publish honest receipts

**Files:** native fixture/test; add selected-action terminal cases to `tests/chaos/test_episode_native.py`, reusing `gameplay_support.Game` and `replay_clock.c` without changing legacy defaults. Document protocol in `docs/chaos-protocol.md` and limits in `chaos/README.md` after acceptance.

Reuse `native_rng.controlled_rng_objects` and `native_rng.h`; never stub `rn2/rnd` or the action routines. Compare off/on full-action transcripts: return/move clocks, public messages/maps, player/terrain/inventory/monster aftermath, RNG draw count and next native draw. Fountain and magic actions legitimately consume RNG: compare equal consumption, **not zero**. Select all 30 fate cases with bounded real-RNG seed preflight (at most 4096 seeds, then reset before the actual action), including magical/luck and depletion cases. Inject one extra native draw and one raw libc draw into the measured action interval as negative controls; both must fail this same comparison oracle. Wrap native calls only to count/forward or inject transport failure, not replace their behavior.

Preserved `/tmp/curio9f-native-jgkwrnfo/tree` and `../output/system-gcc13` are immutable references. Their manifest names revision `1f5fb7157ad0d4daff447f30cb7ebe773a5928be`, not the supplied current source. **Old objects cannot validate edited C.** Follow their system compiler/pkg-config pattern, but build fresh reviewed sources for every native RED/GREEN candidate. Parent supplies each approved committed revision; no working-tree source/old-object mixtures.

Future staging/build commands, after parent supplies `REVIEWED_REV`:

```sh
set -euo pipefail
REPO=/home/hermes/nyarlathack
: "${REVIEWED_REV:?set the parent-reviewed full commit SHA}"
STAGE=$(mktemp -d /tmp/nyarl-observation-acceptance-XXXXXX)
git clone --no-hardlinks --no-checkout "$REPO" "$STAGE/tree"
git -C "$STAGE/tree" checkout --detach "$REVIEWED_REV"
cd "$STAGE/tree"
umask 077
/usr/bin/python3 scripts/prepare_native_ci.py --root "$STAGE/tree" \
  --output-dir "$STAGE/output" --expected-revision "$REVIEWED_REV" \
  > "$STAGE/preparation.log" 2>&1
out="$STAGE/output"
: > "$out/full-suite.log"
umask 022
env -i PATH=/usr/bin:/bin HOME="$out/home" LANG=C.UTF-8 TZ=America/New_York \
  PKG_CONFIG_LIBDIR=/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig \
  MAIL="$out/MAIL" TMPDIR="$out/fixtures" PYTHONDONTWRITEBYTECODE=1 \
  NYARLATHACK_GAME_TESTS=1 NYARLATHACK_STOCK_DIR="$out/stock" \
  NYARLATHACK_CHAOS0_DIR="$out/stock" NYARLATHACK_PRECURIO_DIR="$out/precurio" \
  NYARLATHACK_NATIVE_FIXTURE_MODE=source-build \
  NYARLATHACK_NATIVE_BUILD_RECEIPT="$out/system-gcc13" \
  NYARLATHACK_NATIVE_EXPECTED_REVISION="$REVIEWED_REV" \
  /usr/bin/python3 -m unittest discover -s tests/chaos -p 'test_*.py' -v \
  > "$out/full-suite.log" 2>&1
```

The new native test reads `NYARLATHACK_CHAOS0_DIR` for its explicit off-build comparison; existing tests need no new environment interpretation. New terminal matrix uses stock, fresh CHAOS=0, inactive CHAOS=1, legacy-empty and v2-empty. Pass observation opt-in only to the relevant child (e.g. scoped `patch.dict` around `Game.start`); do not globally enable it for the old suite. Use the existing input/clock/entropy controls, bounded scripted selected actions, binary/data pairs and artifact manifests. Compare actual input, terminal, xlog/final dumps, exact legacy events and repeated v2 events. Retain fresh revision, compiler/build command, binary/data hashes and all failure logs; report skips/warnings, never synthetic receipts.

**Completion gate:** two-stage review, observed RED/GREEN evidence, fresh on/off builds, native transport-failure and RNG negative controls, offline integrity tests and controlled terminal equivalence. This is behavioral-pilot phase 1 evidence plumbing only. It neither demonstrates ordinary-play availability/recurrence nor closes #21 wholesale. Later capability selection, policy and meaningful behavioral acceptance require separate approval; no authoring/model experiment belongs here.

## Parent sequencing note

First implement only tasks 1 and 2 (legacy compatibility and isolated mixed parser), then specification and correctness/security review. Subsequent tasks remain gated by those reviews. No observation-only result establishes meaningful gameplay recurrence. No live model call or automatic provider switch is authorized. Fresh native source/receipt selection above replaces the proposed archive-based command, which lacked required Git history and current fixture selectors. Syntax-check and test any new native harness before using its evidence; never relax old assertions or replace archived pins to force a pass.
