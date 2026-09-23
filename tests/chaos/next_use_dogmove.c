/* NGPL. Linked dog_move vs no-candidate control. Handwritten test fixture. */
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

static void setup_level(struct monst *pet)
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
    u.usanity = 50;
    u.ux = 10;
    u.uy = 10;
    u.uz.dnum = 0;
    u.uz.dlevel = 1;
    u.ubirthday = 1750000001;
    u.chaos_game_token = 1750000001L;
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
    viz_array = rows;
    memset(level.objects, 0, sizeof level.objects);
    memset(level.monsters, 0, sizeof level.monsters);
    fobj = 0;
    ftrap = 0;
    chaos_state_init(&u.chaos);
    u.chaos.safe = 7;
    memset(pet, 0, sizeof *pet);
    pet->data = &mons[PM_LITTLE_DOG];
    pet->mtyp = PM_LITTLE_DOG;
    pet->mhp = pet->mhpmax = 10;
    pet->m_id = 7;
    pet->mtame = 10;
    pet->mpeaceful = 1;
    pet->mcanmove = 1;
    pet->mcansee = 1;
    add_mx(pet, MX_EDOG);
    EDOG(pet)->hungrytime = monstermoves + 10000;
    EDOG(pet)->whistletime = 0;
    place_monster(pet, 12, 10);
    fmon = pet;
    vision_init();
    vision_reset();
    vision_recalc(0);
    display_nhwindow(WIN_MAP, FALSE);
    newsym(u.ux, u.uy);
    newsym(pet->mx, pet->my);
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

static int admit_and_act(const char *dirpath, struct monst *pet, int *telegraphs,
                         int capture)
{
    struct chaos_next_use_safe_request req;
    struct chaos_next_use_safe_result admitted;
    struct chaos_state budget;
    char run[65];
    int dir, acted;

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
    if (!admitted.active) return 0;
    acted = chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, 0);
    if (acted && capture)
        chaos_next_use_capture_whistle(10, pet->m_id, 40);
    return admitted.active ? (acted ? 2 : 1) : 0;
}

static int persist_and_restore(const char *dirpath)
{
    char path[512], envelope[512];
    int fd, restored;

    if (snprintf(path, sizeof path, "%s/next-use-save.bin", dirpath) >= (int)sizeof path)
        return 0;
    fd = open(path, O_RDWR | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) return 0;
    chaos_next_use_save(fd);
    if (snprintf(envelope, sizeof envelope, "%s/next_use-envelope.json", dirpath)
        < (int)sizeof envelope)
        unlink(envelope);
    chaos_next_use_runtime_reset();
    if (lseek(fd, 0, SEEK_SET) < 0) {
        close(fd);
        return 0;
    }
    restored = chaos_next_use_restore_bound(fd, u.chaos_game_token,
        chaos_next_use_pack_level(u.uz.dnum, u.uz.dlevel));
    close(fd);
    if (restored)
        chaos_next_use_safe_mark_restored();
    return restored;
}

static int run_case(const char *name, const char *dirpath)
{
    struct monst pet;
    struct chaos_whistle_witness witness;
    int telegraphs = 0, rc, ox, oy, ready, arm, public_n, public2, f_action;
    int snapshot = 0, windowed = 0, pre_glyph = 0, restored = 0, spent2 = 0;
    unsigned orig_id;

    test_rng_control();
    test_rng_reset();
    setup_level(&pet);
    setenv("NYARLATHACK_OBSERVATIONS", "1", 1);
    setenv("NYARLATHACK_RUN_DIR", dirpath, 1);
    chaos_start();
    ox = pet.mx;
    oy = pet.my;
    orig_id = pet.m_id;
    memset(&witness, 0, sizeof witness);
    witness.production = strcmp(name, "noprod") != 0;
    arm = 0;
    if (strcmp(name, "none") && strcmp(name, "bypass")
        && strcmp(name, "safemiss") && strcmp(name, "safehit")
        && strcmp(name, "obsorigin") && strcmp(name, "unequalclock")) {
        arm = admit_and_act(dirpath, &pet, &telegraphs,
                            strcmp(name, "nonepet") != 0);
        if (arm < 0) return 2;
    }
    restored = 0;
    spent2 = 0;
    if (!strcmp(name, "save") || !strcmp(name, "savegone")
        || !strcmp(name, "saveother")) {
        restored = persist_and_restore(dirpath);
        if (!restored) return 2;
        setenv("NYARLATHACK_NEXT_USE_ADMIT", "1", 1);
        u.chaos.safe = 6;
        chaos_safe("level_enter");
        spent2 = u.chaos.spent;
    }
    if (!strcmp(name, "obsorigin") || !strcmp(name, "unequalclock")) {
        long root;

        if (!strcmp(name, "unequalclock")) {
            moves = 1;
            monstermoves = 200;
        }
        u.chaos.seq = 9;
        root = chaos_observation_begin(CHAOS_OBS_OP_WHISTLING);
        chaos_observation_arm(CHAOS_OBS_OP_WHISTLING, CHAOS_OBS_FACT_SOUND_HIGH);
        You("produce a high whistling sound.");
        chaos_observation_disarm();
        chaos_observation_end(root);
        setenv("NYARLATHACK_NEXT_USE_ADMIT", "1", 1);
        u.chaos.safe = 6;
        chaos_safe("level_enter");
        if (u.chaos.spent == 1) {
            int acted = chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, 0);
            if (acted)
                chaos_next_use_capture_whistle(10, pet.m_id, monstermoves);
            arm = acted ? 2 : 1;
        }
    }
    if (!strcmp(name, "safemiss") || !strcmp(name, "safehit")) {
        char run[65];
        int dir;

        setenv("NYARLATHACK_NEXT_USE_ADMIT", "1", 1);
        dir = open(dirpath, O_RDONLY | O_DIRECTORY);
        if (dir < 0) return 2;
        if (dir_run_hex(dir, run)) {
            close(dir);
            return 2;
        }
        close(dir);
        if (!strcmp(name, "safehit")) {
            bind_origin(run);
            u.chaos.safe = 6;
        }
        chaos_safe("level_enter");
        if (!strcmp(name, "safehit") && u.chaos.spent == 1)
            chaos_safe("level_enter");
        if (!strcmp(name, "safehit") && u.chaos.spent == 1) {
            int acted = chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, 0);
            if (acted)
                chaos_next_use_capture_whistle(10, pet.m_id, 40);
            arm = acted ? 2 : 1;
        }
    }
    monstermoves = 45;
    if (!strcmp(name, "late"))
        monstermoves = 50;
    if (!strcmp(name, "early"))
        monstermoves = 44;
    if (!strcmp(name, "dead")) {
        pet.mhp = 0;
        pet.deadmonster = DEADMONSTER_DEAD;
    }
    if (!strcmp(name, "savegone")) {
        pet.mhp = 0;
        pet.deadmonster = DEADMONSTER_DEAD;
        fmon = 0;
    }
    if (!strcmp(name, "wrongid"))
        pet.m_id = 8;
    if (!strcmp(name, "saveother"))
        pet.m_id = 9;
    if (!strcmp(name, "changed"))
        pet.mtyp = PM_KITTEN;
    f_action = 0;
    if (!strcmp(name, "wrongfam") && arm)
        f_action = chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_F, 10, 0);
    if (!strcmp(name, "hidden") && WIN_MAP != WIN_ERR && wins[WIN_MAP])
        wins[WIN_MAP]->flags |= WIN_CANCELLED;
    if (!strcmp(name, "level_lifetime")) {
        u.uz.dlevel = 2;
        chaos_observe();
    }
    if (!strcmp(name, "game_lifetime")) {
        u.chaos_game_token++;
        chaos_observe();
    }
    ready = chaos_next_use_whistle_decision_ready(pet.m_id);
    {
        int glyph = glyph_at(pet.mx, pet.my);
        snapshot = tty_snapshot_projectable(pet.mx, pet.my, glyph);
        windowed = iflags.window_inited && windowprocs.win_print_glyph == tty_print_glyph;
        pre_glyph = glyph;
    }
    rc = dog_move(&pet, 0, &witness);
    chaos_whistle_witness_finalize(&pet, &witness);
    public_n = (int)chaos_next_use_runtime_public_count();
    chaos_whistle_witness_finalize(&pet, &witness);
    public2 = (int)chaos_next_use_runtime_public_count();
    {
        FILE *out = fopen("result.json", "w");
        if (!out) return 2;
        fprintf(out,
            "{\"case\":\"%s\",\"ox\":%d,\"oy\":%d,\"mx\":%d,\"my\":%d,\"rc\":%d,"
            "\"arm\":%d,\"telegraph\":%d,\"ready_before\":%d,\"ready_after\":%d,"
            "\"orig_ready_after\":%d,\"public\":%d,\"public2\":%d,\"m_id\":%u,\"f_action\":%d,"
            "\"displaced\":%d,\"delivered\":%d,\"pre_public\":%d,"
            "\"reseed\":%d,\"rng_next\":%d,\"snapshot\":%d,\"windowed\":%d,"
            "\"pre_glyph\":%d,\"post_glyph\":%d,\"invalid\":%d,\"classifier\":%d,"
            "\"root\":%ld,\"notice\":%ld,\"spent\":%d,\"spent2\":%d,\"restored\":%d}\n",
            name, ox, oy, pet.mx, pet.my, rc, arm, telegraphs, ready,
            chaos_next_use_whistle_decision_ready(pet.m_id),
            chaos_next_use_whistle_decision_ready(orig_id),
            public_n, public2, pet.m_id, f_action,
            witness.displaced, witness.manifestation_delivered,
            witness.pre_public, reseed_count, rn2(100000),
            snapshot, windowed, pre_glyph, witness.post_glyph,
            witness.invalid, witness.classifier_ok,
            witness.root, witness.notice_seq, u.chaos.spent, spent2, restored);
        fclose(out);
    }
    return 0;
}

int main(int argc, char **argv)
{
    const char *name;
    const char *dirpath;

    if (argc != 3) return 2;
    name = argv[1];
    dirpath = argv[2];
    fqn_prefix[TROUBLEPREFIX] = "./";
    setup_tty(&argc, argv);
    return run_case(name, dirpath);
}
