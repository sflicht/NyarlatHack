/* NGPL. First selected ordinary-whistle baseline: full native doapply and TTY.
 * Controlled nextgetobj selection, not a replacement action or renderer.
 * No observation begin/arm/delivery calls belong in this fixture. */
#include "hack.h"
#include "chaos.h"
#include "wintty.h"
#include "native_rng.h"
#include <stdio.h>
#include <stdlib.h>

extern struct obj *nextgetobj;

/* Every chaos_state field; haunting counters are also exposed for review. */
static void state_record(FILE *f, const struct you *player)
{
    const struct chaos_state *s = &player->chaos;
    int i;
    fprintf(f, "{\"version\":%d,\"budget\":%d,\"spent\":%d,"
            "\"reserved\":%d,\"last_id\":%d,\"seq\":%ld,\"safe\":%ld,\"effects\":[",
            s->version, chaos_budget(s, player->usanity), s->spent, s->reserved,
            s->last_id, s->seq, s->safe);
    for (i = 0; i < CHAOS_KINDS; ++i)
        fprintf(f, "%s{\"value\":%d,\"cost\":%d,\"expires\":%ld}",
                i ? "," : "", s->effects[i].value,
                s->effects[i].cost, s->effects[i].expires);
    fprintf(f, "],\"haunt\":{\"active\":%d,\"count\":%d,\"backtracks\":%d,"
            "\"echo_pending\":%d,\"echo_delivered\":%d}}",
            player->haunt.active, player->haunt.count, player->haunt.backtracks,
            player->haunt.echo_pending, player->haunt.echo_delivered);
}

int main(int argc, char **argv)
{
    struct obj o, saved_o;
    struct monst sleeper, saved_mon;
    struct edog saved_dog;
    struct you saved_u, after_u;
    int i, known, result, draws, next, expected;
    long before_moves, before_monstermoves;
    const char *injection = argc == 3 ? argv[2] : "";
    FILE *state_file;
    assert(argc == 2 || argc == 3);
    assert(!*injection || !strcmp(injection, "--inject-native")
           || !strcmp(injection, "--inject-raw")
           || !strcmp(injection, "--inject-budget"));
    known = !strcmp(argv[1], "known");
    assert(known || !strcmp(argv[1], "unknown"));
    test_rng_control();
    test_rng_negative_control(argv[1]); /* Header control API; not action controls. */
    choose_windows("tty");
    initoptions();
    init_nhwindows(&argc, argv);
    WIN_MESSAGE = create_nhwindow(NHW_MESSAGE);
    WIN_STATUS = create_nhwindow(NHW_STATUS);
    WIN_MAP = create_nhwindow(NHW_MAP);
    display_nhwindow(WIN_MESSAGE, FALSE);
    assert(iflags.window_inited && windowprocs.win_putstr == tty_putstr);
    assert(ttyDisplay->cols == 80 && ttyDisplay->rows == 24);
    init_objects(); init_gods();
    urace.malenum = PM_HUMAN; urole.malenum = PM_WIZARD;
    u.umonnum = u.umonster = PM_HUMAN; youmonst.data = &mons[PM_HUMAN];
    u.ulevel = 1; u.uhp = u.uhprolled = 20; u.uen = u.uenrolled = 20;
    u.usanity = 73; u.uinsight = 19;
    for (i = 0; i < A_MAX; i++) ABASE(i) = AMAX(i) = 12;
    u.ux = 10; u.uy = 10; moves = 101;
    u.uz.dlevel = 1; u.ualign.god = 1;
    init_artifacts();
    calc_total_maxhp(); calc_total_maxen();
    vision_init();
    /* Native vision/flush execute against the bounded fixture's real level. */
    vision_reset();
    memset(&o, 0, sizeof o);
    o.otyp = WHISTLE; o.oclass = TOOL_CLASS; o.quan = 1;
    o.o_id = 42; o.invlet = 'a'; o.where = OBJ_INVENT;
    o.known = o.dknown = known; objects[WHISTLE].oc_name_known = known;
    o.owt = weight(&o); invent = &o;
    memset(&sleeper, 0, sizeof sleeper);
    sleeper.data = &mons[PM_LITTLE_DOG]; sleeper.mhp = sleeper.mhpmax = 10;
    sleeper.mx = 11; sleeper.my = 10; sleeper.msleeping = 1;
    sleeper.mcanmove = 1; add_mx(&sleeper, MX_EDOG); fmon = &sleeper;
    assert(EDOG(&sleeper)->whistletime == 0);
    chaos_start();
    assert(u.chaos.safe == 1);
    saved_o = o; saved_mon = sleeper; saved_u = u;
    saved_dog = *EDOG(&sleeper);
    before_moves = moves; before_monstermoves = monstermoves;
    expected = test_rng_begin();
    nextgetobj = &o;
    result = doapply();
    /* Test-only perturbations are inside the same measured native interval. */
    if (!strcmp(injection, "--inject-native")) (void)rn2(100000);
    if (!strcmp(injection, "--inject-raw")) (void)random();
    if (!strcmp(injection, "--inject-budget")) ++u.chaos.spent;
    draws = reseed_count;
    next = rn2(100000);
    assert(getenv("WHISTLE_CHAOS_STATE"));
    state_file = fopen(getenv("WHISTLE_CHAOS_STATE"), "w");
    assert(state_file);
    fputs("{\"before\":", state_file);
    state_record(state_file, &saved_u);
    fputs(",\"after\":", state_file);
    state_record(state_file, &u);
    fputs("}\n", state_file);
    assert(!fclose(state_file));
    if (*injection) {
        fflush(stdout);
        fprintf(stderr, "WHISTLE_INTERVAL {\"draws\":%d,\"next\":%d,"
                "\"expected\":%d,\"return\":%d}\n", draws, next, expected, result);
        fflush(stderr);
    }
    assert(!nextgetobj && result == MOVE_PARTIAL);
    assert(draws == 0 && next == expected);
    assert(moves == before_moves && monstermoves == before_monstermoves);
    assert(!memcmp(&saved_o, &o, sizeof o));
    assert(objects[WHISTLE].oc_name_known == known);
    assert(!sleeper.msleeping && EDOG(&sleeper)->whistletime == moves);
    saved_mon.msleeping = 0;
    saved_dog.whistletime = moves;
    assert(!memcmp(&saved_dog, EDOG(&sleeper), sizeof saved_dog));
    assert(!memcmp(&saved_mon, &sleeper, sizeof sleeper));
    after_u = u;
    /* Only seq may differ: one legacy apply attempt plus three opted-in
     * observations. safe, version, spending, reservation, IDs and every effect
     * byte remain covered; no whole-chaos masking. Driver checks exact seqs. */
    after_u.chaos.seq = saved_u.chaos.seq;
    assert(!memcmp(&saved_u.chaos, &after_u.chaos, sizeof saved_u.chaos));
    assert(!memcmp(&saved_u, &after_u, sizeof saved_u));
    fprintf(stderr, "{\"known\":%d,\"return\":%d,\"move_partial\":%d,"
            "\"moves\":%ld,\"monstermoves\":%ld,\"rng_draws\":%d,"
            "\"next_draw\":%d,\"sleeping\":%d,\"whistletime\":%ld,"
            "\"player_unchanged\":true,\"inventory_unchanged\":true,"
            "\"monster_other_bytes_unchanged\":true,\"selection\":\"a\"}\n",
            known, result, MOVE_PARTIAL, moves, monstermoves, draws, next,
            sleeper.msleeping, EDOG(&sleeper)->whistletime);
    fflush(stdout);
    rem_all_mx(&sleeper); fmon = 0; invent = 0;
    exit_nhwindows((char *)0);
    return 0;
}
