"""Executed C branch probes, NOT a linked-game restore acceptance test.

Extract the genuine rejection helper and guards from restore.c; stub only
platform cleanup, while linking the real protocol state validator. Native
save parsing, ABI/layout compatibility and UI still require the reviewed build.
"""

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class RestoreSafetyTests(unittest.TestCase):
    def test_production_rejection_branches(self):
        source = (ROOT / "src/restore.c").read_text()
        self.assertIn(
            "chaos_restore_reject(int fd)",
            source,
            "CHAOS rejection must preserve saves and terminate",
        )
        # Include the UNIX permissions branch, not its internal #endif boundary.
        start = source.index("chaos_restore_reject(int fd)")
        body_start = source.index("{", start)
        depth = 1
        end = body_start + 1
        while depth:
            depth += (source[end] == "{") - (source[end] == "}")
            end += 1
        helper = source[start:end]
        structural = source.split(
            "\tmread(fd, (genericptr_t) &u, sizeof(struct you));", 1
        )[1].split("#endif", 1)[0]
        clock = source.split("\tmread(fd, (genericptr_t) &moves, sizeof moves);", 1)[
            1
        ].split("\tmread(fd, (genericptr_t) &monstermoves", 1)[0]
        code = r"""
#include <assert.h>
#include <limits.h>
#include <setjmp.h>
#include <stdlib.h>
#include "chaos_protocol.h"
#define CHAOS 1
#define UNIX 1
#define FALSE 0
#define SAVEPREFIX 0
#define FCMASK 0660
#define SAVEF "isolated-save"
static jmp_buf stop;
static int closed, unlocked, exited, mode, restoring;
static struct { int panicking, something_worth_saving; } program_state;
static struct {
    struct chaos_state chaos;
    int haunt, curio, chaos_next_use_attempted;
    long chaos_game_token;
    struct { int dnum, dlevel; } uz;
} u;
static long moves;
static int chaos_haunt_valid(int *v) { return !*v; }
static int chaos_curio_valid(int *v) { return !*v; }
static int next_use_restore_ok = 1, bound_calls, latch_calls, restored_latch;
static long chaos_next_use_pack_level(int dnum, int dlevel) {
    return ((long)dnum + 1) * 100000L + dlevel;
}
static int chaos_next_use_restore_bound(int fd, long game, long level) {
    assert(fd == 42);
    bound_calls++;
    return next_use_restore_ok && game == 1234567L && level == 300004L;
}
static int chaos_next_use_safe_restore_attempted(int attempted) {
    latch_calls++;
    if (attempted != 0 && attempted != 1) return 0;
    restored_latch = attempted;
    return 1;
}
static int close(int fd) { assert(fd == 42); closed++; return 0; }
static const char *fqname(const char *s, int p, int n) { (void)p; (void)n; return s; }
static int chmod(const char *s, int m) { (void)s; mode = m; return 0; }
static void clearlocks(void) { unlocked++; }
static void exit_nhwindows(const char *s) { assert(s); exited++; }
static void terminate(int status) { assert(status == EXIT_FAILURE); longjmp(stop, 1); }
"""
        code += "\nstatic int " + helper + "\n"
        code += (
            "static int attempt(int fd) {\n"
            + structural
            + "#endif\n"
            + clock
            + "return 1; }\n"
        )
        code += r"""
static void probe(int bad) {
    int result;
    closed = unlocked = exited = mode = 0;
    bound_calls = latch_calls = 0;
    restored_latch = -1;
    restoring = 1;
    program_state.panicking = 0;
    program_state.something_worth_saving = 0;
    if (!setjmp(stop)) {
        result = attempt(42);
        assert(!bad && result == 1);
        assert(!closed && !unlocked && !exited);
        assert(bound_calls == 1 && latch_calls == 1);
        assert(restored_latch == u.chaos_next_use_attempted);
    } else {
        assert(bad && closed == 1 && unlocked == 1 && exited == 1);
        assert(mode == FCMASK && !restoring && program_state.panicking);
    }
}
int main(void) {
    u.chaos_game_token = 1234567L; u.uz.dnum = 2; u.uz.dlevel = 4;
    chaos_state_init(&u.chaos); moves = 0; probe(0);
    u.chaos.cosmetic_seen = 1; probe(0); /* valid first delivery at turn 0 */
    u.chaos.cosmetic_last_turn = 1; probe(1); /* future */
    moves = 1; probe(0); /* rejection must not poison next attempt */
    moves = LONG_MAX; probe(0); /* no mechanical MAX_COUNTER restriction */
    moves = -1; probe(1);
    moves = 50; u.chaos.cosmetic_seen = 8; probe(1);
    u.chaos.cosmetic_seen = 1; u.chaos.version = 1; probe(1);
    chaos_state_init(&u.chaos); u.haunt = 1; probe(1);
    u.haunt = 0; u.curio = 1; probe(1);
    u.curio = 0; probe(0);
    next_use_restore_ok = 0; probe(1);
    assert(bound_calls == 1 && !latch_calls);
    next_use_restore_ok = 1; probe(0);
    u.chaos_game_token++; probe(1); assert(!latch_calls);
    u.chaos_game_token--; u.uz.dnum++; probe(1); assert(!latch_calls);
    u.uz.dnum--; u.uz.dlevel++; probe(1); assert(!latch_calls);
    u.uz.dlevel--; u.chaos_next_use_attempted = 1; probe(0);
    u.chaos_next_use_attempted = 2; probe(1);
    assert(latch_calls == 1 && restored_latch == -1);
    u.chaos_next_use_attempted = -1; probe(1);
    assert(latch_calls == 1 && restored_latch == -1);
    u.chaos_next_use_attempted = 0; probe(0);
    return 0;
}
"""
        with tempfile.TemporaryDirectory(prefix="restore-branch-") as temporary:
            path = Path(temporary)
            (path / "probe.c").write_text(code)
            compiled = subprocess.run(
                [
                    "cc",
                    "-std=c99",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-I" + str(ROOT / "include"),
                    str(path / "probe.c"),
                    str(ROOT / "src/chaos_protocol.c"),
                    "-o",
                    str(path / "probe"),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            subprocess.run([str(path / "probe")], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
