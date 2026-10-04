/* ENGINE-UNIT: ring (W effect) runtime after real admit/install.
 * Drives the runtime's public entry points directly; not gameplay. The
 * engine's guard reads (ring_guard in chaos_engine.c) are not linked here:
 * each scenario names the guard value the engine would pass.
 * argv: run-dir at_move at_safe run_hex scenario */
#include "hack.h"
#include "chaos.h"
#include "chaos_next_use_journal.h"
#include "chaos_next_use_runtime.h"
#include "chaos_next_use_safe.h"

#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

long moves;
long monstermoves;
boolean panicking;

void panic(const char *str, ...)
{
    va_list args;
    va_start(args, str);
    fputs(" ERROR:  ", stderr);
    vfprintf(stderr, str, args);
    fputc('\n', stderr);
    va_end(args);
    abort();
}

#define RUN_TOKEN 1750000001L
#define LEVEL_ONE 100001L /* chaos_next_use_pack_level(0, 1) */
#define LEVEL_TWO 100002L

void bwrite(int fd, genericptr_t loc, unsigned int num)
{
    if (write(fd, loc, num) != (ssize_t)num) abort();
}
int chaos_next_use_mread(int fd, void *loc, unsigned int num)
{
    return read(fd, loc, num) == (ssize_t)num;
}

static int telegraphs;
static char telegraph_ids[4][32];

static int telegraph_ok(void *opaque, const char *text)
{
    (void)opaque;
    if (!text || !text[0]) return 0;
    if (telegraphs < 4) snprintf(telegraph_ids[telegraphs], 32, "%s", text);
    ++telegraphs;
    return 1;
}

static int receipt_ok(void *opaque, const struct chaos_next_use_private_record *record)
{
    (void)opaque;
    (void)record;
    return 1;
}

static void bind_origin(const char *run)
{
    struct chaos_next_use_origin_ref origin;
    memset(&origin, 0, sizeof origin);
    origin.end_seq = 12;
    memcpy(origin.fact, "ordinary_whistle", 16);
    origin.family = CHAOS_NEXT_USE_FAMILY_W;
    origin.level_dlevel = 1;
    origin.level_dnum = 0;
    origin.move = 40;
    origin.notice_seq = 11;
    origin.root = 10;
    memcpy(origin.run, run, 64);
    chaos_next_use_safe_bind_origin(&origin, 1);
}

static void boundary(long level)
{
    chaos_next_use_identity_boundary(RUN_TOKEN, level);
}

/* The level a use happens on (restore-level descends to LEVEL_TWO). */
static long player_level = LEVEL_ONE;

static struct chaos_next_use_snapshot snap(void)
{
    struct chaos_next_use_snapshot s;
    memset(&s, 0, sizeof s);
    if (!chaos_next_use_snapshot_export(&s)) s.snapshot_v = -1;
    return s;
}

/* One whistle use as chaos_engine.c's ring branch: preflight, callback,
 * then the guard result. Returns 0 when the program did not take the use,
 * 1 when the callback ran, 2 when the runtime recorded a delivery (the
 * engine would then print the line and apply the confusion). */
static int ring(long root, int guard)
{
    int r;
    if (!chaos_next_use_ring_active()
        || !chaos_next_use_action_preflight(CHAOS_NEXT_USE_FAMILY_W, root))
        return 0;
    if (!chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, root, 0)) {
        r = 1;
    } else {
        r = chaos_next_use_whistle_ring(root, guard) ? 2 : 1;
    }
    monstermoves += 2;
    boundary(player_level);
    return r;
}

static void row(const char *step, int result)
{
    struct chaos_next_use_snapshot s = snap();
    printf("{\"step\":\"%s\",\"result\":%d,\"phase\":%d,\"snapshot_v\":%d,"
           "\"broad_uses\":%d,\"delivered\":%d,\"callbacks\":%d,"
           "\"public\":%zu,\"private\":%zu,\"broad_active\":%d,"
           "\"ring_active\":%d,\"w_effect\":%d,\"slot_w\":%d}\n",
           step, result, s.phase, s.snapshot_v, s.broad_uses, s.delivered,
           s.callback_ordinal, chaos_next_use_runtime_public_count(),
           chaos_next_use_runtime_private_count(),
           chaos_next_use_broad_active(), chaos_next_use_ring_active(),
           s.w_effect, s.slot_w);
}

int main(int argc, char **argv)
{
    struct chaos_next_use_safe_request req;
    struct chaos_next_use_safe_result admitted;
    static struct chaos_state budget;
    int dir, i;
    long root = 100;
    const char *scenario;
    char name[32];

    if (argc != 6) return 2;
    dir = open(argv[1], O_RDONLY | O_DIRECTORY);
    if (dir < 0) return 2;
    scenario = argv[5];
    monstermoves = atoi(argv[2]);
    chaos_next_use_safe_reset_for_test();
    chaos_state_init(&budget);
    memset(&req, 0, sizeof req);
    req.dir = dir;
    req.enabled = 1;
    req.at_safe = atoi(argv[3]);
    req.at_move = atoi(argv[2]);
    req.level_dnum = 0;
    req.level_dlevel = 1;
    req.run_hex = argv[4];
    req.sanity = 50;
    req.budget = &budget;
    req.telegraph = telegraph_ok;
    req.receipt = receipt_ok;
    bind_origin(argv[4]);
    chaos_next_use_safe_bind_logical(RUN_TOKEN);
    chaos_next_use_safe_try(&req, &admitted);
    if (admitted.active && getenv("NYARL_RING_JOURNAL"))
        (void)chaos_next_use_journal_begin(dir);
    close(dir);
    printf("{\"step\":\"admit\",\"result\":%d,\"telegraphs\":%d,"
           "\"telegraph\":\"%s\"}\n",
           admitted.active, telegraphs, telegraph_ids[0]);
    if (!admitted.active) return 0;
    boundary(LEVEL_ONE);
    row("installed", 1);

    if (!strcmp(scenario, "deliver")) {
        /* Two rings reach the cap; a third use is not taken. */
        for (i = 0; i < 3; ++i) {
            snprintf(name, sizeof name, "use%d", i + 1);
            row(name, ring(root, CHAOS_RING_GUARD_NONE));
            root += 10;
        }
    } else if (!strcmp(scenario, "guards")) {
        /* Every guard holds the note and leaves the program waiting. */
        for (i = CHAOS_RING_GUARD_CONFUSED; i <= CHAOS_RING_GUARD_MAX; ++i) {
            snprintf(name, sizeof name, "guard%d", i);
            row(name, ring(root, i));
            root += 10;
        }
    } else if (!strcmp(scenario, "guard-then-ring")) {
        /* A guarded use spends no cap: guarded, rang, guarded, rang. */
        row("g1", ring(root, CHAOS_RING_GUARD_HOSTILE_ADJACENT));
        row("r1", ring(root + 10, CHAOS_RING_GUARD_NONE));
        row("g2", ring(root + 20, CHAOS_RING_GUARD_WATER_ADJACENT));
        row("r2", ring(root + 30, CHAOS_RING_GUARD_NONE));
        row("after", ring(root + 40, CHAOS_RING_GUARD_NONE));
    } else if (!strcmp(scenario, "guarded-bound")) {
        /* Guarded uses still count toward the 8-callback bound. */
        for (i = 0; i < CHAOS_NEXT_USE_BROAD_CALLBACKS + 1; ++i) {
            row("guarded", ring(root, CHAOS_RING_GUARD_LOW_HP));
            root += 10;
        }
    } else if (!strcmp(scenario, "bad-guard")) {
        /* Out-of-range guard values and a wrong root are refused. */
        int r = chaos_next_use_action_preflight(CHAOS_NEXT_USE_FAMILY_W, root)
            && chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, root, 0);
        row("callback", r);
        row("guard-high", chaos_next_use_whistle_ring(root,
                                                      CHAOS_RING_GUARD_MAX + 1));
        row("guard-negative", chaos_next_use_whistle_ring(root, -1));
        row("wrong-root", chaos_next_use_whistle_ring(root + 1,
                                                      CHAOS_RING_GUARD_NONE));
        row("right-root", chaos_next_use_whistle_ring(root,
                                                      CHAOS_RING_GUARD_NONE));
        row("repeat", chaos_next_use_whistle_ring(root, CHAOS_RING_GUARD_NONE));
    } else if (!strcmp(scenario, "callback")) {
        /* One callback, then report whether a ring answer is pending. */
        int r = chaos_next_use_action_preflight(CHAOS_NEXT_USE_FAMILY_W, root)
            && chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, root, 0);
        row("callback", r);
    } else if (!strcmp(scenario, "level")) {
        boundary(LEVEL_TWO);
        row("level2", 1);
        row("level2-use", ring(root, CHAOS_RING_GUARD_NONE));
    } else if (!strcmp(scenario, "restore")) {
        /* Save after one ring, restore into a fresh runtime, resume the
         * journal, then ring again. */
        FILE *save = tmpfile();
        int ok, resumed;
        row("use1", ring(root, CHAOS_RING_GUARD_NONE));
        ok = save && chaos_next_use_save(fileno(save));
        rewind(save);
        chaos_next_use_safe_reset_for_test();
        ok = ok && chaos_next_use_restore_bound(fileno(save), RUN_TOKEN, LEVEL_ONE);
        dir = open(argv[1], O_RDONLY | O_DIRECTORY);
        resumed = ok && chaos_next_use_journal_resume(dir);
        row("restored", ok);
        row("resumed", resumed);
        row("use2", ring(root + 10, CHAOS_RING_GUARD_NONE));
        if (save) fclose(save);
        close(dir);
    } else if (!strcmp(scenario, "restore-level")) {
        /* #239 on v8: ring once on level 1, descend, save, restore on
         * level 2. A ring program never arms a W window, so the restore
         * rule's window branch cannot apply to it. */
        FILE *save = tmpfile();
        struct chaos_next_use_snapshot s;
        int ok, resumed;
        row("use1", ring(root, CHAOS_RING_GUARD_NONE));
        player_level = LEVEL_TWO;
        boundary(player_level);
        s = snap();
        printf("{\"step\":\"window\",\"result\":1,\"w_runtime\":%d,"
               "\"armed_level_token\":%ld,\"level_token\":%ld}\n",
               (int) s.w_runtime, s.armed_level_token, s.level_token);
        row("descended", 1);
        ok = save && chaos_next_use_save(fileno(save));
        rewind(save);
        chaos_next_use_safe_reset_for_test();
        row("wrong-run",
            chaos_next_use_restore_bound(fileno(save), RUN_TOKEN + 1, LEVEL_TWO));
        rewind(save);
        chaos_next_use_safe_reset_for_test();
        ok = ok && chaos_next_use_restore_bound(fileno(save), RUN_TOKEN, LEVEL_TWO);
        dir = open(argv[1], O_RDONLY | O_DIRECTORY);
        resumed = ok && chaos_next_use_journal_resume(dir);
        row("restored", ok);
        row("resumed", resumed);
        row("use2", ring(root + 10, CHAOS_RING_GUARD_NONE));
        if (save) fclose(save);
        close(dir);
    } else if (!strcmp(scenario, "tamper")) {
        /* The effect is bound into the v8 snapshot hash and its version. */
        struct chaos_next_use_snapshot s = snap(), t;
        t = s; t.w_effect = 0;
        row("tamper-effect", chaos_next_use_snapshot_validate(&t));
        t = s; t.snapshot_v = CHAOS_NEXT_USE_SNAPSHOT_V_BROAD;
        row("tamper-version-v7", chaos_next_use_snapshot_validate(&t));
        t = s; t.snapshot_v = CHAOS_NEXT_USE_SNAPSHOT_V;
        row("tamper-version-v6", chaos_next_use_snapshot_validate(&t));
        t = s; t.broad_uses = 1;
        row("tamper-uses", chaos_next_use_snapshot_validate(&t));
        row("untampered", chaos_next_use_snapshot_validate(&s));
    } else if (!strcmp(scenario, "expiry")) {
        monstermoves = req.at_move + 100;
        boundary(LEVEL_TWO);
        row("expired", 1);
    }
    return 0;
}
