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
extern short disco[NUM_OBJECTS]; /* globalized external copy of o_init.o */

static void hex_record(FILE *f, const void *data, size_t size)
{
    const unsigned char *p = data;
    size_t n;
    fputc('"', f);
    for (n = 0; n < size; ++n) fprintf(f, "%02x", p[n]);
    fputc('"', f);
}

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

/* Preflight and action setup: real copied rnd.o/libc, never action rerolls. */
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
    int branch, zero, one, two, selection, wisdom;
    puts("[");
    for (i = 0; i < sizeof seeds / sizeof seeds[0]; ++i) {
        seeded_reset(seeds[i]);
        zero = rn2(100000);
        seeded_reset(seeds[i]);
        branch = rn2(2);
        one = rn2(100000);
        assert(reseed_count == 2 && reseed_period == INT_MAX);
        seeded_reset(seeds[i]);
        selection = rn2(8);
        wisdom = rn2(19);
        two = rn2(100000);
        printf("%s{\"seed\":%u,\"first_rn2_2\":%d,\"next_after_zero\":%d,"
               "\"next_after_one\":%d,\"next_after_two\":%d,"
               "\"pet_selection\":%d,\"wisdom_draw\":%d}",
               i ? ",\n" : "", seeds[i], branch, zero, one, two, selection, wisdom);
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
    int pet, pet_known, x, y, selection = -1, wisdom = -1, wisdom_delta = 0;
    int discovery_slot = -1;
    short saved_disco[NUM_OBJECTS];
    struct rm saved_map[COLNO][ROWNO];
    static const int positions[8][2] = {
        {9,9}, {10,9}, {11,9}, {9,11}, {10,11}, {11,11}, {9,10}, {11,10}
    };
    unsigned seed = 0;
    int dispatch, cancel_apply, inert, leaf;
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
    pet_known = !strcmp(argv[1], "magic-pet-known");
    pet = pet_known || !strcmp(argv[1], "magic-pet-unknown");
    cancel_apply = !strcmp(argv[1], "apply-cancel");
    inert = !strcmp(argv[1], "tagged-curio-inert");
    leaf = !strcmp(argv[1], "leaf-ordinary");
    dispatch = cancel_apply || inert || leaf;
    for (i = 0; i < (int)(sizeof sound_cases / sizeof sound_cases[0]); ++i)
        if (!strcmp(argv[1], sound_cases[i].name)) variant = &sound_cases[i];
    assert(pet || dispatch || variant || known || !strcmp(argv[1], "unknown"));
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
    if (dispatch) {
        youmonst.mtyp = PM_HUMAN;
        if (leaf) { o.otyp = EUCALYPTUS_LEAF; o.oclass = FOOD_CLASS; }
        if (inert) {
            o.curio_tag = CHAOS_CURIO_GENERATED;
            assert(!u.curio.owner && !chaos_curio_matches(&o));
        }
        objects[o.otyp].oc_name_known = 0;
        assert(!o.blessed && !o.cursed);
    }
    saved_type_known = objects[o.otyp].oc_name_known;
    if (pet) {
        youmonst.mtyp = PM_HUMAN;
        o.otyp = MAGIC_WHISTLE;
        o.known = o.dknown = pet_known;
        objects[o.otyp].oc_name_known = saved_type_known = pet_known;
        assert(!Hallucination && !Blind && !o.blessed && !o.cursed);
        assert(AEXE(A_WIS) == 0 && ACURR(A_WIS) == 12);
        for (x = 7; x <= 17; ++x)
            for (y = 7; y <= 13; ++y) {
                levl[x][y].typ = ROOM;
                levl[x][y].lit = 1;
            }
    }
    o.owt = weight(&o); invent = &o;
    memset(&sleeper, 0, sizeof sleeper);
    sleeper.data = &mons[PM_LITTLE_DOG]; sleeper.mhp = sleeper.mhpmax = 10;
    sleeper.mx = 11; sleeper.my = 10; sleeper.msleeping = 1;
    sleeper.mcanmove = 1; add_mx(&sleeper, MX_EDOG); fmon = &sleeper;
    if (variant || dispatch) sleeper.mtyp = PM_LITTLE_DOG;
    if (pet) {
        sleeper.mtyp = PM_LITTLE_DOG;
        sleeper.mtame = 10; sleeper.mpeaceful = 1;
        sleeper.msleeping = 0; sleeper.mcansee = 1;
        place_monster(&sleeper, 15, 10);
        vision_reset(); vision_recalc(0);
        for (x = 1; x < COLNO; ++x)
            for (y = 0; y < ROWNO; ++y) newsym(x, y);
        assert(canspotmon((&sleeper)) && canseemon((&sleeper)));
        assert(fmon == &sleeper && !sleeper.nmon && m_at(15,10) == &sleeper);
        assert(!ftrap && !sleeper.mtrapped && distu(15,10) > 2);
        memcpy(saved_map, levl, sizeof saved_map);
        memcpy(saved_disco, disco, sizeof saved_disco);
        for (x = 0; x < COLNO; ++x)
            for (y = 0; y < ROWNO; ++y) {
                assert(level.monsters[x][y] == ((x == 15 && y == 10) ? &sleeper : NULL));
                assert(!t_at(x,y));
            }
        for (i = 0; i < 8; ++i)
            assert(goodpos(positions[i][0], positions[i][1], &sleeper, 0));
        for (i = bases[TOOL_CLASS]; disco[i] && disco[i] != MAGIC_WHISTLE; ++i)
            assert(i < NUM_OBJECTS - 1);
        discovery_slot = i;
        assert(!disco[i]);
    } else assert(!sleeper.mtame);
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
    if (dispatch) {
        assert(getenv("WHISTLE_SEED") && !strcmp(getenv("WHISTLE_SEED"), "2"));
        seed = 2;
        seeded_reset(seed);
        expected = rn2(100000);
        seeded_reset(seed);
    }
    nextgetobj = cancel_apply ? NULL : &o;
    if (pet) {
        assert(getenv("WHISTLE_SEED") && !strcmp(getenv("WHISTLE_SEED"), "2"));
        seed = 2;
        seeded_reset(seed);
        selection = rn2(8);
        if (!pet_known) {
            wisdom = rn2(19);
            wisdom_delta = wisdom > ACURR(A_WIS);
        }
        expected = rn2(100000);
        seeded_reset(seed);
    }
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
    if (dispatch) {
        assert(!nextgetobj && result == (leaf ? MOVE_DEFAULT : MOVE_CANCELLED));
        assert(draws == 0 && next == expected && reseed_period == INT_MAX);
        assert(invent == &o);
    } else if (pet) {
        fprintf(stderr, "{\"case\":\"%s\",\"seed\":%u,\"rng_draws\":%d,"
                "\"next_draw\":%d,\"expected_next\":%d,\"selection\":%d,"
                "\"wisdom_draw\":%d,\"wisdom_before\":%d,\"wisdom_after\":%d,"
                "\"type_before\":%d,\"type_after\":%d,\"known\":%d,\"dknown\":%d,"
                "\"return\":%d,\"move_default\":%d,\"old\":[15,10],\"new\":[%d,%d],"
                "\"sleeping\":%d,\"whistletime\":%ld,"
                "\"player_before\":[%d,%d,%d,%d,%d],"
                "\"player_after\":[%d,%d,%d,%d,%d],"
                "\"monster_before\":[%d,%d,%d,%d,%d,%d,%d],"
                "\"monster_after\":[%d,%d,%d,%d,%d,%d,%d],\"map_before\":",
                argv[1], seed, draws, next, expected, selection, wisdom,
                saved_u.aexe.a[A_WIS], AEXE(A_WIS), saved_type_known,
                objects[o.otyp].oc_name_known, o.known, o.dknown, result, MOVE_DEFAULT,
                sleeper.mx, sleeper.my, sleeper.msleeping, EDOG(&sleeper)->whistletime,
                saved_u.ux, saved_u.uy, saved_u.uhp, saved_u.uen, saved_u.uluck,
                u.ux, u.uy, u.uhp, u.uen, u.uluck,
                saved_mon.mtyp, saved_mon.mtame, saved_mon.mhp, saved_mon.mhpmax,
                saved_mon.mtrapped, saved_mon.mux, saved_mon.muy,
                sleeper.mtyp, sleeper.mtame, sleeper.mhp, sleeper.mhpmax,
                sleeper.mtrapped, sleeper.mux, sleeper.muy);
        hex_record(stderr, saved_map, sizeof saved_map);
        fputs(",\"map_after\":", stderr); hex_record(stderr, levl, sizeof saved_map);
        fputs(",\"discovery_before\":", stderr);
        hex_record(stderr, saved_disco, sizeof saved_disco);
        fputs(",\"discovery_after\":", stderr); hex_record(stderr, disco, sizeof saved_disco);
        fputs("}\n", stderr); fflush(stderr);
        assert(!nextgetobj && result == MOVE_DEFAULT);
        assert(draws == (pet_known ? 1 : 2) && next == expected);
        assert(reseed_period == INT_MAX);
        assert(sleeper.mx == positions[selection][0] && sleeper.my == positions[selection][1]);
        assert(invent == &o && isok(sleeper.mx, sleeper.my));
        assert(levl[sleeper.mx][sleeper.my].typ == ROOM);
        assert(distu(sleeper.mx, sleeper.my) <= 2 && distu(sleeper.mx, sleeper.my) > 0);
        assert(canspotmon((&sleeper)) && canseemon((&sleeper)));
        assert(fmon == &sleeper && !sleeper.nmon && !ftrap && !sleeper.mtrapped);
        for (x = 0; x < COLNO; ++x)
            for (y = 0; y < ROWNO; ++y) {
                assert(level.monsters[x][y] ==
                       ((x == sleeper.mx && y == sleeper.my) ? &sleeper : NULL));
                assert(!t_at(x,y));
            }
        assert(!memcmp(saved_map, levl, sizeof saved_map));
        assert(objects[o.otyp].oc_name_known == 1);
        if (!pet_known) saved_disco[discovery_slot] = MAGIC_WHISTLE;
        assert(!memcmp(saved_disco, disco, sizeof saved_disco));
        assert(AEXE(A_WIS) == saved_u.aexe.a[A_WIS] + wisdom_delta);
    } else if (variant) {
        assert(!nextgetobj && result == (variant->magic ? MOVE_DEFAULT : MOVE_PARTIAL));
        assert(draws == variant->draws && next == expected);
        assert(reseed_period == INT_MAX);
    } else {
        assert(!nextgetobj && result == MOVE_PARTIAL);
        assert(draws == 0 && next == expected);
    }
    assert(moves == before_moves && monstermoves == before_monstermoves);
    assert(!memcmp(&saved_o, &o, sizeof o));
    assert(objects[o.otyp].oc_name_known == (pet ? 1 : saved_type_known));
    if (pet) {
        /* rloc_to -> place_monster coordinates and set_apparxy tame smell. */
        assert(!sleeper.msleeping && EDOG(&sleeper)->whistletime == 0);
        assert(sleeper.mux == u.ux && sleeper.muy == u.uy);
        saved_mon.mx = positions[selection][0]; saved_mon.my = positions[selection][1];
        saved_mon.mux = u.ux; saved_mon.muy = u.uy;
    } else if (dispatch) {
        assert(sleeper.msleeping == !leaf);
        assert(EDOG(&sleeper)->whistletime == (leaf ? moves : 0));
        saved_mon.msleeping = !leaf;
        saved_dog.whistletime = leaf ? moves : 0;
    } else if (variant) {
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
    /* For all prior cases only seq may differ: one legacy apply plus three opted-in
     * observations. safe, version, spending, reservation, IDs and every effect
     * byte remain covered; no whole-chaos masking. Driver checks exact seqs. */
    after_u.chaos.seq = saved_u.chaos.seq;
    /* Only newly discovered magic may exercise wisdom; assert before masking. */
    if (pet && !pet_known) {
        assert(after_u.aexe.a[A_WIS] == saved_u.aexe.a[A_WIS] + wisdom_delta);
        after_u.aexe.a[A_WIS] = saved_u.aexe.a[A_WIS];
    }
    assert(!memcmp(&saved_u.chaos, &after_u.chaos, sizeof saved_u.chaos));
    assert(!memcmp(&saved_u, &after_u, sizeof saved_u));
    if (pet) { /* private pet diagnostic already emitted before assertions */ }
    else if (dispatch)
        fprintf(stderr, "{\"case\":\"%s\",\"seed\":%u,\"otyp\":%d,"
                "\"oclass\":%d,\"weight\":%u,\"curio_tag\":%d,"
                "\"known\":%d,\"dknown\":%d,\"type_known\":%d,"
                "\"blessed\":%d,\"cursed\":%d,\"return\":%d,"
                "\"move_default\":%d,\"move_cancelled\":%d,"
                "\"rng_draws\":%d,\"next_draw\":%d,\"expected_next\":%d,"
                "\"sleeping\":%d,\"whistletime\":%ld,"
                "\"player_unchanged\":true,\"inventory_unchanged\":true,"
                "\"monster_other_bytes_unchanged\":true}\n",
                argv[1], seed, o.otyp, o.oclass, o.owt, o.curio_tag,
                o.known, o.dknown, objects[o.otyp].oc_name_known,
                o.blessed, o.cursed, result, MOVE_DEFAULT, MOVE_CANCELLED,
                draws, next, expected, sleeper.msleeping, EDOG(&sleeper)->whistletime);
    else if (variant)
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
