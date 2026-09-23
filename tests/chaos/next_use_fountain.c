/* NGPL. drinkfountain remap band vs adjacent fates. Not ordinary play. */
#define _GNU_SOURCE
#include "hack.h"
#include "chaos.h"
#include "chaos_next_use_runtime.h"
#include "chaos_next_use_safe.h"
#include "native_rng.h"
#include "wintty.h"

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static void setup_tty(int *argc, char **argv)
{
    if (!getenv("TERM") || !getenv("TERM")[0])
        setenv("TERM", "xterm", 1);
    choose_windows("tty");
    initoptions();
    init_nhwindows(argc, argv);
    WIN_MESSAGE = create_nhwindow(NHW_MESSAGE);
    WIN_STATUS = create_nhwindow(NHW_STATUS);
    WIN_MAP = create_nhwindow(NHW_MAP);
    display_nhwindow(WIN_MESSAGE, FALSE);
}

static void setup_level(void)
{
    int x, y;
    static char visible[ROWNO][COLNO], *rows[ROWNO];

    id_permonst();
    init_objects();
    init_gods();
    memset(&u, 0, sizeof u);
    urace.malenum = PM_HUMAN;
    urole.malenum = PM_WIZARD;
    u.umonnum = u.umonster = PM_HUMAN;
    youmonst.data = &mons[PM_HUMAN];
    youmonst.mtyp = PM_HUMAN;
    u.ulevel = 1;
    u.uhp = u.uhpmax = 20;
    u.uen = u.uenmax = 20;
    u.uhunger = 1000;
    u.usanity = 50;
    u.ux = 10;
    u.uy = 10;
    u.uz.dnum = 0;
    u.uz.dlevel = 1;
    u.ubirthday = 1750000001;
    moves = 40;
    monstermoves = 40;
    flags.ident = 1;
    program_state.gameover = 0;
    for (y = 0; y < ROWNO; ++y) {
        rows[y] = visible[y];
        for (x = 1; x < COLNO; ++x) {
            levl[x][y].typ = ROOM;
            levl[x][y].lit = 1;
            visible[y][x] = IN_SIGHT | COULD_SEE;
        }
    }
    levl[u.ux][u.uy].typ = FOUNTAIN;
    viz_array = rows;
    memset(level.objects, 0, sizeof level.objects);
    memset(level.monsters, 0, sizeof level.monsters);
    fobj = 0;
    ftrap = 0;
    fmon = 0;
    chaos_state_init(&u.chaos);
    u.chaos.safe = 7;
    vision_init();
    vision_reset();
    vision_recalc(0);
    display_nhwindow(WIN_MAP, FALSE);
    newsym(u.ux, u.uy);
    docrt();
    flush_screen(1);
}

static int telegraph_ok(void *opaque, const char *text)
{
    int *count = opaque;
    if (!text || !text[0]) return 0;
    if (count) ++*count;
    return 1;
}

static int receipt_ok(void *opaque, const struct chaos_next_use_private_record *record)
{
    (void)opaque;
    (void)record;
    return 1;
}

static int dir_run_hex(int dir, char run[65])
{
    struct stat st;

    if (dir < 0 || fstat(dir, &st)
        || snprintf(run, 65, "%016llx%016llx%016llx%016llx",
                    (unsigned long long)st.st_dev,
                    (unsigned long long)st.st_ino,
                    (unsigned long long)st.st_dev,
                    (unsigned long long)st.st_ino) != 64)
        return -1;
    return 0;
}

static void bind_origin(const char *run)
{
    struct chaos_next_use_origin_ref origin;
    memset(&origin, 0, sizeof origin);
    origin.end_seq = 12;
    memcpy(origin.fact, "water_refreshed", 15);
    origin.family = CHAOS_NEXT_USE_FAMILY_F;
    origin.level_dlevel = 1;
    origin.level_dnum = 0;
    origin.move = 40;
    origin.notice_seq = 11;
    origin.root = 10;
    memcpy(origin.run, run, 64);
    chaos_next_use_safe_bind_origin(&origin, 1);
}

static int admit_f(const char *dirpath, int *telegraphs)
{
    struct chaos_next_use_safe_request req;
    struct chaos_next_use_safe_result admitted;
    struct chaos_state budget;
    char run[65];
    int dir;

    dir = open(dirpath, O_RDONLY | O_DIRECTORY);
    if (dir < 0) return -1;
    if (dir_run_hex(dir, run)) {
        close(dir);
        return -1;
    }
    chaos_next_use_safe_reset_for_test();
    chaos_state_init(&budget);
    memset(&req, 0, sizeof req);
    req.dir = dir;
    req.enabled = 1;
    req.at_safe = 7;
    req.at_move = 40;
    req.level_dnum = 0;
    req.level_dlevel = 1;
    req.run_hex = run;
    req.sanity = 50;
    req.budget = &budget;
    req.telegraph = telegraph_ok;
    req.telegraph_opaque = telegraphs;
    req.receipt = receipt_ok;
    bind_origin(run);
    chaos_next_use_safe_bind_logical(1750000001L);
    chaos_next_use_safe_try(&req, &admitted);
    close(dir);
    return admitted.active ? 1 : 0;
}

static unsigned find_seed(int want)
{
    unsigned seed;
    int fate;

    for (seed = 1; seed < 30000U; ++seed) {
        reseed_period = INT_MAX;
        reseed_count = 0;
        srandom(seed);
        fate = rnd(30);
        if (fate == want) return seed;
    }
    return 0;
}

int main(int argc, char **argv)
{
    const char *dirpath;
    int want, admit, telegraphs = 0, hunger_before, typ_before, admitted_ok;
    long seq_before;
    unsigned seed;
    struct chaos_fountain_token token;
    long completed, completed_after;
    int contacted;

    if (argc != 4) return 2;
    want = atoi(argv[1]);
    admit = !strcmp(argv[2], "admit") || !strcmp(argv[2], "levitate");
    dirpath = argv[3];
    setup_tty(&argc, argv);
    setup_level();
    setenv("NYARLATHACK_OBSERVATIONS", "1", 1);
    setenv("NYARLATHACK_RUN_DIR", dirpath, 1);
    chaos_start();
    admitted_ok = 1;
    if (admit && admit_f(dirpath, &telegraphs) != 1)
        admitted_ok = 0;
    if (!strcmp(argv[2], "levitate")) {
        set_itimeout(&HLevitation, 500L);
        float_up();
    }
    seed = find_seed(want);
    if (!seed) return 4;
    reseed_period = INT_MAX;
    reseed_count = 0;
    srandom(seed);
    hunger_before = u.uhunger;
    typ_before = levl[u.ux][u.uy].typ;
    seq_before = u.chaos.seq;
    memset(&token, 0, sizeof token);
    completed = chaos_next_use_fountain_completed_root();
    contacted = chaos_next_use_fountain_contact(completed, &token);
    chaos_bind_drinkfountain_token(contacted ? &token : 0);
    {
        long obs = chaos_observation_begin(CHAOS_OBS_OP_FOUNTAIN_DRINK);
        drinkfountain();
        chaos_observation_end(obs);
    }
    chaos_bind_drinkfountain_token(0);
    completed_after = chaos_next_use_fountain_completed_root();
    {
        FILE *out = fopen("result.json", "w");
        if (!out) return 5;
        fprintf(out,
            "{\"want\":%d,\"seed\":%u,\"admit\":%d,\"contacted\":%d,"
            "\"token_active\":%d,\"remap\":%d,\"consumed\":%d,"
            "\"hunger_delta\":%d,\"typ_before\":%d,\"typ_after\":%d,"
            "\"telegraph\":%d,\"completed\":%ld,\"completed_after\":%ld,\"seq_delta\":%ld,\"reseed\":%d}\n",
            want, seed, admitted_ok, contacted, token.active, token.remap,
            token.consumed, u.uhunger - hunger_before, typ_before,
            levl[u.ux][u.uy].typ, telegraphs, completed, completed_after,
            u.chaos.seq - seq_before, reseed_count);
        fclose(out);
    }
    return 0;
}
