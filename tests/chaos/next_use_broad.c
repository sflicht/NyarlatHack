/* ENGINE-UNIT: C (broad next-use) runtime after real admit/install.
 * Drives the runtime's public entry points directly; not gameplay.
 * argv: run-dir at_move at_safe run_hex family(W|F) scenario */
#include "hack.h"
#include "chaos.h"
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

static void bind_origin(const char *run, int family)
{
    struct chaos_next_use_origin_ref origin;
    memset(&origin, 0, sizeof origin);
    origin.end_seq = 12;
    if (family == CHAOS_NEXT_USE_FAMILY_W)
        memcpy(origin.fact, "ordinary_whistle", 16);
    else
        memcpy(origin.fact, "water_refreshed", 15);
    origin.family = family;
    origin.level_dlevel = 1;
    origin.level_dnum = 0;
    origin.move = 40;
    origin.notice_seq = 11;
    origin.root = 10;
    memcpy(origin.run, run, 64);
    chaos_next_use_safe_bind_origin(&origin, 1);
}

/* As chaos_observe: the identity boundary keeps the runtime's own origin
 * liveness flags (an undeclared family must not claim a live origin). */
static void boundary(long level)
{
    chaos_next_use_identity_boundary(RUN_TOKEN, level);
}

static struct chaos_next_use_snapshot snap(void)
{
    struct chaos_next_use_snapshot s;
    memset(&s, 0, sizeof s);
    if (!chaos_next_use_snapshot_export(&s)) s.snapshot_v = -1;
    return s;
}

/* One whistle use at root; witnessed when deliver. Returns on_action. */
static int whistle(long root, int deliver)
{
    struct chaos_whistle_witness witness;
    unsigned m_id = 7;
    long start = monstermoves;
    if (!chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, root, 0))
        return 0;
    chaos_next_use_capture_whistle(root, m_id, start);
    monstermoves = start + 5;
    if (deliver && chaos_next_use_whistle_attention(m_id, root + 1)
        && chaos_next_use_manifestation_begin(m_id, root + 2)) {
        chaos_next_use_manifestation_notice(root + 2, root + 3);
        chaos_next_use_manifestation_end(root + 2, root + 3, root + 4, 1);
        memset(&witness, 0, sizeof witness);
        witness.root = root + 2;
        witness.notice_seq = root + 3;
        witness.manifestation_delivered = 1;
        witness.displaced = 1;
        chaos_next_use_on_manifestation(&witness, root + 4);
    }
    monstermoves = start + 10;
    boundary(LEVEL_ONE);
    return 1;
}

/* One fountain drink at root; remapped when deliver. Returns on_action. */
static int drink(long root, int deliver)
{
    struct chaos_fountain_token token;
    memset(&token, 0, sizeof token);
    if (!chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_F, root, &token))
        return 0;
    if (deliver) token.consumed = 1;
    chaos_next_use_fountain_result(&token, deliver ? CHAOS_FOUNTAIN_REMAPPED
                                                   : CHAOS_FOUNTAIN_NATURAL);
    monstermoves += 2;
    return 1;
}

static int use(int family, long root, int deliver)
{
    return family == CHAOS_NEXT_USE_FAMILY_W ? whistle(root, deliver)
                                             : drink(root, deliver);
}

static void row(const char *step, int result)
{
    struct chaos_next_use_snapshot s = snap();
    printf("{\"step\":\"%s\",\"result\":%d,\"phase\":%d,\"snapshot_v\":%d,"
           "\"broad_uses\":%d,\"delivered\":%d,\"callbacks\":%d,"
           "\"public\":%zu,\"private\":%zu,\"broad_active\":%d,"
           "\"slot_w\":%d,\"slot_f\":%d}\n",
           step, result, s.phase, s.snapshot_v, s.broad_uses, s.delivered,
           s.callback_ordinal, chaos_next_use_runtime_public_count(),
           chaos_next_use_runtime_private_count(),
           chaos_next_use_broad_active(), s.slot_w, s.slot_f);
}

int main(int argc, char **argv)
{
    struct chaos_next_use_safe_request req;
    struct chaos_next_use_safe_result admitted;
    static struct chaos_state budget;
    int dir, family, i;
    long root = 100;
    const char *scenario;

    if (argc != 7) return 2;
    dir = open(argv[1], O_RDONLY | O_DIRECTORY);
    if (dir < 0) return 2;
    family = !strcmp(argv[5], "W") ? CHAOS_NEXT_USE_FAMILY_W
                                   : CHAOS_NEXT_USE_FAMILY_F;
    scenario = argv[6];
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
    bind_origin(argv[4], family);
    chaos_next_use_safe_bind_logical(RUN_TOKEN);
    chaos_next_use_safe_try(&req, &admitted);
    close(dir);
    printf("{\"step\":\"admit\",\"result\":%d,\"telegraphs\":%d,"
           "\"telegraph\":\"%s\"}\n",
           admitted.active, telegraphs, telegraph_ids[0]);
    if (!admitted.active) return 0;
    boundary(LEVEL_ONE);
    row("installed", 1);

    if (!strcmp(scenario, "repeat")) {
        /* Deliver, then use again: a broad program answers the next use too. */
        for (i = 0; i < 3; ++i) {
            int r = use(family, root, 1);
            root += 10;
            row(i == 0 ? "use1" : i == 1 ? "use2" : "use3", r);
        }
    } else if (!strcmp(scenario, "quiet-uses")) {
        /* Undelivered uses never finish the program before the callback
         * bound; then the bound ends it. */
        for (i = 0; i < CHAOS_NEXT_USE_BROAD_CALLBACKS + 1; ++i) {
            int r = use(family, root, 0);
            root += 10;
            row("undelivered", r);
        }
    } else if (!strcmp(scenario, "level")) {
        boundary(LEVEL_TWO);
        row("level2", 1);
        row("level2-use", use(family, root, 1));
    } else if (!strcmp(scenario, "suppressed")) {
        /* No qualifying companion: suppressed before the callback. */
        chaos_next_use_whistle_suppressed(root, CHAOS_W_SUPPRESSED_NONE_IN_VIEW);
        row("suppressed", chaos_next_use_action_preflight(family, root + 1));
        row("after-suppressed", use(family, root + 10, 1));
    } else if (!strcmp(scenario, "level-window")) {
        /* The open W window ends on leaving its level; the program lives. */
        int r = chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, root, 0);
        chaos_next_use_capture_whistle(root, 7, monstermoves);
        boundary(LEVEL_TWO);
        row("window-left-level", r);
        monstermoves += 3;
        row("next-level-use", use(family, root + 10, 1));
    } else if (!strcmp(scenario, "expiry")) {
        monstermoves = req.at_move + 100;
        boundary(LEVEL_TWO);
        row("expired", 1);
    }
    return 0;
}
