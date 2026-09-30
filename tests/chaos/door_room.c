/* NGPL: #1 door_reluctance end to end. The real doopen_indir (src/lock.c),
 * the real rule (chaos_door -> chaos_rule) and the real door_open
 * observation, linked against the built engine objects with a controlled copy
 * of rnd.o. Nothing in the door path is wrapped.
 *
 *   door_room SEED N ACTIVE
 *
 * Opens a closed door east of the hero N times; attempt i reseeds the native
 * RNG with SEED+i. ACTIVE=1 admits a door_reluctance request (the real
 * chaos_admit) first. Before each attempt the fixture predicts rnl(20) from
 * the same seed, so every outcome is checked against the threshold the rule
 * must use: (STR+DEX+CON)/3 = 12, halved to 6 while the effect is active.
 * Messages arrive through raw_print (no window is initialised) and are
 * counted. NYARLATHACK_RUN_DIR receives events.jsonl as in play. */
#define _GNU_SOURCE
#include "hack.h"
#include "chaos.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "native_rng.h"

extern int n_dgns;
static int opens_msg, resists_msg, other_msg;
static void counting_raw_print(const char *s)
{
    if (!strcmp(s, "The door opens.")) ++opens_msg;
    else if (!strcmp(s, "The door resists!")) ++resists_msg;
    else { ++other_msg; fprintf(stderr, "unexpected message: %s\n", s); }
}
static void quietglyph(winid w, XCHAR_P x, XCHAR_P y, int g)
{ (void)w; (void)x; (void)y; (void)g; }
static char visible[ROWNO][COLNO], *rows[ROWNO];

static void seeded(unsigned seed)
{
    reseed_period = INT_MAX; reseed_count = 0; srandom(seed);
}

int main(int argc, char **argv)
{
    int seed, n, active, i, x, y, opened = 0, mismatches = 0, threshold;
    if (argc != 4) { fprintf(stderr, "usage: door_room SEED N ACTIVE\n"); return 2; }
    seed = atoi(argv[1]); n = atoi(argv[2]); active = atoi(argv[3]);
    assert(n >= 1 && n <= 1000 && (active == 0 || active == 1));
    fqn_prefix[TROUBLEPREFIX] = "./";
    test_rng_control(); id_permonst(); init_objects(); init_gods(); init_artifacts();
    memset(&u, 0, sizeof u);
    urace = races[str2race("human")]; urole = roles[str2role("Bard")];
    u.umonnum = u.umonster = PM_HUMAN; youmonst.data = &mons[PM_HUMAN];
    u.usanity = 100; u.ulevel = 1; u.uhp = u.uhpmax = 14;
    u.acurr.a[A_STR] = u.acurr.a[A_DEX] = u.acurr.a[A_CON] = 12;
    n_dgns = 2; dungeons[1].depth_start = 1; dungeons[1].num_dunlevs = 20;
    u.uz.dnum = 1; u.uz.dlevel = 1; moves = monstermoves = 10; flags.ident = 1;
    windowprocs.win_print_glyph = quietglyph;
    windowprocs.win_raw_print = counting_raw_print;
    vision_init();
    for (y = 0; y < ROWNO; ++y) {
        rows[y] = visible[y];
        for (x = 0; x < COLNO; ++x) { levl[x][y].typ = ROOM; levl[x][y].lit = 1; visible[y][x] = IN_SIGHT | COULD_SEE; }
    }
    viz_array = rows;
    u.ux = 20; u.uy = 5;
    levl[21][5].typ = DOOR;
    vision_reset(); viz_array = rows;
    chaos_state_init(&u.chaos); u.chaos.safe = 1;
    chaos_start();
    if (active) {
        struct chaos_request r = {1, 1, CHAOS_DOOR, 50, 300, 4, 1};
        assert(chaos_admit(&u.chaos, &r, moves, u.usanity, 2) == CHAOS_OK);
    }
    threshold = active ? 6 : 12;
    for (i = 0; i < n; ++i) {
        int predicted, got;
        levl[21][5].doormask = D_CLOSED;
        seeded((unsigned)(seed + i));
        predicted = rnl(20) < threshold;
        seeded((unsigned)(seed + i));
        assert(doopen_indir(21, 5) == MOVE_STANDARD);
        got = levl[21][5].doormask == D_ISOPEN;
        opened += got;
        mismatches += got != predicted;
    }
    printf("seed=%d n=%d active=%d threshold=%d opened=%d mismatches=%d "
           "opens_msg=%d resists_msg=%d other_msg=%d spent=%d events=%ld\n",
           seed, n, active, threshold, opened, mismatches, opens_msg,
           resists_msg, other_msg, u.chaos.spent, u.chaos.seq);
    return 0;
}
