/* NGPL. Linked dog_move vs no-candidate control. Handwritten test fixture. */
#define _GNU_SOURCE
#include "hack.h"
#include "chaos.h"
#include "chaos_next_use_runtime.h"
#include "chaos_next_use_safe.h"
#include "native_rng.h"

#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void quietglyph(winid w, XCHAR_P x, XCHAR_P y, int g)
{
    (void)w;
    (void)x;
    (void)y;
    (void)g;
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
    moves = 40;
    monstermoves = 40;
    flags.ident = 1;
    program_state.gameover = 0;
    windowprocs.win_print_glyph = quietglyph;
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
}

static int telegraph_ok(void *opaque, const char *text)
{
    int *count = opaque;
    if (!text || !text[0]) return 0;
    if (count) ++*count;
    return 1;
}

static int admit_and_act(const char *dirpath, struct monst *pet, int *telegraphs)
{
    struct chaos_next_use_safe_request req;
    struct chaos_next_use_safe_result admitted;
    struct chaos_state budget;
    const char *run = "abababababababababababababababababababababababababababababababab";
    int dir, acted;

    dir = open(dirpath, O_RDONLY | O_DIRECTORY);
    if (dir < 0) return -1;
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
    chaos_next_use_safe_try(&req, &admitted);
    close(dir);
    if (!admitted.active) return 0;
    acted = chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, 0);
    if (acted)
        chaos_next_use_capture_whistle(10, pet->m_id, 40);
    return admitted.active ? (acted ? 2 : 1) : 0;
}

static int run_case(const char *name, const char *dirpath)
{
    struct monst pet;
    struct chaos_whistle_witness witness;
    int telegraphs = 0, rc, ox, oy, ready, arm, public_n;
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
    if (strcmp(name, "none") && strcmp(name, "bypass")) {
        arm = admit_and_act(dirpath, &pet, &telegraphs);
        if (arm < 0) return 2;
    }
    monstermoves = 45;
    if (!strcmp(name, "late"))
        monstermoves = 50;
    if (!strcmp(name, "dead"))
        pet.mhp = 0;
    if (!strcmp(name, "wrongid"))
        pet.m_id = 8;
    ready = chaos_next_use_whistle_decision_ready(pet.m_id);
    rc = dog_move(&pet, 0, &witness);
    public_n = (int)chaos_next_use_runtime_public_count();
    printf("{\"case\":\"%s\",\"ox\":%d,\"oy\":%d,\"mx\":%d,\"my\":%d,\"rc\":%d,"
           "\"arm\":%d,\"telegraph\":%d,\"ready_before\":%d,\"ready_after\":%d,"
           "\"orig_ready_after\":%d,\"public\":%d,\"m_id\":%u}\n",
           name, ox, oy, pet.mx, pet.my, rc, arm, telegraphs, ready,
           chaos_next_use_whistle_decision_ready(pet.m_id),
           chaos_next_use_whistle_decision_ready(orig_id),
           public_n, pet.m_id);
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 3) return 2;
    fqn_prefix[TROUBLEPREFIX] = "./";
    return run_case(argv[1], argv[2]);
}
