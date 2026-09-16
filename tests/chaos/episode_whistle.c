/* NGPL. Selected whistle sound branches: full native doapply and TTY.
 * Controlled nextgetobj selection, not a replacement action or renderer.
 * No observation begin/arm/delivery calls belong in this fixture. */
#include "hack.h"
#include "chaos.h"
#include "wintty.h"
#include "native_rng.h"
#include <stdio.h>
#include <stdlib.h>
#include <dlfcn.h>

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

/* Preflight only: the real copied rnd.o and libc, never an action reroll. */
static void seeded_reset(unsigned seed)
{
    /* replay_clock interposes srandom and ignores its argument. New seeded
     * cases deliberately use real libc; leave the baseline header unchanged. */
    static void (*libc_srandom)(unsigned);
    if (!libc_srandom) {
        void *libc = dlopen("libc.so.6", RTLD_NOW | RTLD_LOCAL);
        assert(libc);
        libc_srandom = (void (*)(unsigned))dlsym(libc, "srandom");
        assert(libc_srandom);
    }
    reseed_period = INT_MAX;
    reseed_count = 0;
    libc_srandom(seed);
}

static void calibrate(void)
{
    static const unsigned seeds[] = {1, 2, 3, 4, 5, 6, 7, 8,
                                     9, 10, 11, 12, 13, 14, 15, 16};
    unsigned i;
    int branch, zero, one;
    puts("[");
    for (i = 0; i < sizeof seeds / sizeof seeds[0]; ++i) {
        seeded_reset(seeds[i]);
        zero = rn2(100000);
        seeded_reset(seeds[i]);
        branch = rn2(2);
        one = rn2(100000);
        assert(reseed_count == 2 && reseed_period == INT_MAX);
        printf("%s{\"seed\":%u,\"first_rn2_2\":%d,\"next_after_zero\":%d,"
               "\"next_after_one\":%d}", i ? ",\n" : "", seeds[i],
               branch, zero, one);
    }
    puts("\n]");
}

struct sound_case {
    const char *name;
    int magic, cursed, hallucinated, draws, sleeping, whistle_time;
};

static const struct sound_case sound_cases[] = {
    {"ordinary-cursed", 0, 1, 0, 0, 0, 1},
    {"magic-uncursed", 1, 0, 0, 0, 1, 0},
    {"magic-hallucinated", 1, 0, 1, 0, 1, 0},
    {"magic-cursed-humming", 1, 1, 0, 1, 0, 0},
    {"magic-cursed-success", 1, 1, 0, 1, 1, 0}
};

int main(int argc, char **argv)
{
    struct obj o, saved_o;
    struct monst sleeper, saved_mon;
    struct edog saved_dog;
    struct you saved_u, after_u;
    int i, known, result, draws, next, expected;
    int saved_type_known;
    unsigned seed = 0;
    const struct sound_case *variant = 0;
    long before_moves, before_monstermoves;
    const char *injection = argc == 3 ? argv[2] : "";
    FILE *state_file;
    assert(argc == 2 || argc == 3);
    if (!strcmp(argv[1], "--calibrate")) {
        test_rng_control();
        calibrate();
        return 0;
    }
    assert(!*injection || !strcmp(injection, "--inject-native")
           || !strcmp(injection, "--inject-raw")
           || !strcmp(injection, "--inject-budget"));
    known = !strcmp(argv[1], "known");
    for (i = 0; i < (int)(sizeof sound_cases / sizeof sound_cases[0]); ++i)
        if (!strcmp(argv[1], sound_cases[i].name)) variant = &sound_cases[i];
    assert(variant || known || !strcmp(argv[1], "unknown"));
    assert(!*injection || (known && !variant));
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
    if (variant) {
        o.otyp = variant->magic ? MAGIC_WHISTLE : WHISTLE;
        o.cursed = variant->cursed;
        objects[o.otyp].oc_name_known = 0;
        youmonst.mtyp = PM_HUMAN;
        HHallucination = variant->hallucinated ? 10 : 0;
        HHalluc_resistance = EHalluc_resistance = 0;
        assert((!!Hallucination) == variant->hallucinated);
        assert(!Halluc_resistance);
    }
    saved_type_known = objects[o.otyp].oc_name_known;
    o.owt = weight(&o); invent = &o;
    memset(&sleeper, 0, sizeof sleeper);
    sleeper.data = &mons[PM_LITTLE_DOG]; sleeper.mhp = sleeper.mhpmax = 10;
    sleeper.mx = 11; sleeper.my = 10; sleeper.msleeping = 1;
    sleeper.mcanmove = 1; add_mx(&sleeper, MX_EDOG); fmon = &sleeper;
    if (variant) sleeper.mtyp = PM_LITTLE_DOG;
    assert(!sleeper.mtame);
    assert(EDOG(&sleeper)->whistletime == 0);
    chaos_start();
    assert(u.chaos.safe == 1);
    saved_o = o; saved_mon = sleeper; saved_u = u;
    saved_dog = *EDOG(&sleeper);
    before_moves = moves; before_monstermoves = monstermoves;
    expected = test_rng_begin();
    if (variant) {
        assert(getenv("WHISTLE_SEED"));
        seed = (unsigned)atoi(getenv("WHISTLE_SEED"));
        assert(seed >= 1 && seed <= 16);
        seeded_reset(seed);
        if (variant->draws) {
            int branch = rn2(2);
            assert(branch == variant->sleeping);
        }
        expected = rn2(100000);
        seeded_reset(seed);
    }
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
    if (variant) {
        assert(!nextgetobj && result == (variant->magic ? MOVE_DEFAULT : MOVE_PARTIAL));
        assert(draws == variant->draws && next == expected);
        assert(reseed_period == INT_MAX);
    } else {
        assert(!nextgetobj && result == MOVE_PARTIAL);
        assert(draws == 0 && next == expected);
    }
    assert(moves == before_moves && monstermoves == before_monstermoves);
    assert(!memcmp(&saved_o, &o, sizeof o));
    assert(objects[o.otyp].oc_name_known == saved_type_known);
    if (variant) {
        assert(sleeper.msleeping == variant->sleeping);
        assert(EDOG(&sleeper)->whistletime == (variant->whistle_time ? moves : 0));
        saved_mon.msleeping = variant->sleeping;
        saved_dog.whistletime = variant->whistle_time ? moves : 0;
    } else {
        assert(!sleeper.msleeping && EDOG(&sleeper)->whistletime == moves);
        saved_mon.msleeping = 0;
        saved_dog.whistletime = moves;
    }
    assert(!memcmp(&saved_dog, EDOG(&sleeper), sizeof saved_dog));
    assert(!memcmp(&saved_mon, &sleeper, sizeof sleeper));
    after_u = u;
    /* Only seq may differ: one legacy apply attempt plus three opted-in
     * observations. safe, version, spending, reservation, IDs and every effect
     * byte remain covered; no whole-chaos masking. Driver checks exact seqs. */
    after_u.chaos.seq = saved_u.chaos.seq;
    assert(!memcmp(&saved_u.chaos, &after_u.chaos, sizeof saved_u.chaos));
    assert(!memcmp(&saved_u, &after_u, sizeof saved_u));
    if (variant)
        fprintf(stderr, "{\"case\":\"%s\",\"seed\":%u,\"otyp\":%d,"
                "\"known\":%d,\"dknown\":%d,\"type_known\":%d,\"cursed\":%d,"
                "\"hallucination_timeout\":%ld,\"hallucinating\":%d,"
                "\"hallucination_resistance\":%d,\"tame\":%d,"
                "\"return\":%d,\"move_default\":%d,\"moves\":%ld,"
                "\"monstermoves\":%ld,\"rng_draws\":%d,\"next_draw\":%d,"
                "\"expected_next\":%d,\"sleeping\":%d,\"whistletime\":%ld,"
                "\"player_unchanged\":true,\"inventory_unchanged\":true,"
                "\"monster_other_bytes_unchanged\":true}\n",
                variant->name, seed, o.otyp, o.known, o.dknown,
                objects[o.otyp].oc_name_known, o.cursed, (long)HHallucination,
                !!Hallucination, !!Halluc_resistance, sleeper.mtame,
                result, MOVE_DEFAULT, moves, monstermoves, draws, next, expected,
                sleeper.msleeping, EDOG(&sleeper)->whistletime);
    else fprintf(stderr, "{\"known\":%d,\"return\":%d,\"move_partial\":%d,"
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
