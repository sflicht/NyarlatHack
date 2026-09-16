/* NGPL. Fixture-only full native dodrink with physical TTY confirmation.
 * No observation begin/arm/delivered calls: missing production hooks stay RED. */
#include "hack.h"
#include "chaos.h"
#include "wintty.h"
#include "native_rng.h"
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>

extern short disco[NUM_OBJECTS]; /* only copied o_init.o is globalized */
extern struct obj *nextgetobj; /* inspected only; copied invent.o */

static void seeded_reset(unsigned seed)
{
    static void (*libc_srandom)(unsigned);
    if (!libc_srandom) {
        void *libc = dlopen("libc.so.6", RTLD_NOW | RTLD_LOCAL);
        assert(libc);
        libc_srandom = (void (*)(unsigned))dlsym(libc, "srandom");
        assert(libc_srandom);
    }
    reseed_period = INT_MAX; reseed_count = 0; libc_srandom(seed);
}

struct trace { int fate, hunger, dry, count, next; };
static struct trace preflight(unsigned seed)
{
    struct trace t;
    seeded_reset(seed);
    t.fate = rnd(30); t.hunger = t.dry = -1;
    if (t.fate < 10) { t.hunger = rnd(10); t.dry = rn2(3); }
    t.count = reseed_count; t.next = rn2(100000);
    return t;
}

static void hex_record(FILE *f, const void *data, size_t size)
{
    const unsigned char *p = data;
    size_t i;
    fputc('"', f);
    for (i = 0; i < size; ++i) fprintf(f, "%02x", p[i]);
    fputc('"', f);
}

static void empty_world(struct obj *potion)
{
    int x,y;
    assert(invent == potion && !fmon && !fobj && !ftrap && !migrating_mons && !migrating_objs);
    assert(!nextgetobj);
    if (potion) assert(!potion->nobj && !potion->cobj && !potion->oextra_p
                       && !potion->mp && potion->where == OBJ_INVENT);
    for (x = 0; x < COLNO; ++x) for (y = 0; y < ROWNO; ++y)
        assert(!level.monsters[x][y] && !level.objects[x][y] && !t_at(x,y));
}

static void context_record(FILE *f, const struct you *hero, long turn)
{
    fprintf(f,"{\"turn\":%ld,\"safe\":%ld,\"sanity\":%d,\"insight\":%d,"
            "\"budget\":%d,\"spent\":%d,\"reserved\":%d,\"last_id\":%d,"
            "\"vitals\":{\"hp\":%d,\"hp_max\":%d,\"power\":%d,\"power_max\":%d}}",
            turn,hero->chaos.safe,hero->usanity,hero->uinsight,
            chaos_budget(&hero->chaos,hero->usanity),hero->chaos.spent,
            hero->chaos.reserved,hero->chaos.last_id,
            hero->uhp,hero->uhpmax,hero->uen,hero->uenmax);
}

int main(int argc, char **argv)
{
    struct trace t;
    struct you before, normalized;
    struct monst saved_youmonst;
    struct rm map[COLNO][ROWNO];
    typeof(level.flags) level_flags;
    short discovery[NUM_OBJECTS];
    struct objclass definitions[NUM_OBJECTS];
    struct flag saved_flags;
    struct obj *potion = 0, saved_potion;
    long old_moves, old_monstermoves;
    unsigned seed;
    int i,x,y,result,count,next,decline, total = 0;
    const char *injection = 0;
    FILE *f;
    assert(argc == 2 || argc == 3);
    if (argc == 3) {
        assert(!strcmp(argv[1], "confirmed-refreshed"));
        if (!strcmp(argv[2], "--inject-native")) injection = "native";
        else if (!strcmp(argv[2], "--inject-raw")) injection = "raw";
        else if (!strcmp(argv[2], "--inject-budget")) injection = "budget";
        else assert(!"unsupported action injection");
    }
    test_rng_control();
    test_rng_negative_control(argv[1]);
    if (!strcmp(argv[1], "--calibrate")) {
        /* Declared candidate set: integers 1..64 inclusive, no action rerolls.
         * At most 256 native calls here, including every sentinel. */
        puts("[");
        for (seed = 1; seed <= 64; ++seed) {
            t = preflight(seed); total += t.count + 1;
            printf("%s{\"seed\":%u,\"fate\":%d,\"hunger\":%d,\"dry\":%d,"
                   "\"count\":%d,\"next\":%d}", seed == 1 ? "" : ",\n",
                   seed,t.fate,t.hunger,t.dry,t.count,t.next);
        }
        assert(total <= 256); puts("\n]"); return 0;
    }
    if (!strcmp(argv[1], "--probe-controls")) {
        assert(argc == 2 && getenv("FOUNTAIN_SEED"));
        seed = (unsigned)atoi(getenv("FOUNTAIN_SEED"));
        assert(seed >= 1 && seed <= 64);
        t = preflight(seed);
        assert(t.fate < 10 && t.dry > 0 && t.count == 3);
        /* preflight's sentinel is the extra stream draw; now measure the
         * real following value. This is calibration, never a dodrink reroll. */
        next = rn2(100000);
        printf("{\"seed\":%u,\"count\":%d,\"next\":%d,\"changed_next\":%d,\"hunger\":%d,\"calls\":%d}\n",
               seed,t.count,t.next,next,t.hunger,reseed_count);
        return 0;
    }
    decline = !strcmp(argv[1], "decline-selection-cancel");
    assert(decline || !strcmp(argv[1], "confirmed-refreshed"));
    assert(getenv("FOUNTAIN_SEED")); seed = (unsigned)atoi(getenv("FOUNTAIN_SEED"));
    assert(seed >= 1 && seed <= 64);
    t = preflight(seed); assert(t.fate < 10 && t.dry > 0 && t.count == 3);
    if (decline) {
        seeded_reset(seed);
        t.fate = t.dry = -1; t.hunger = 0;
        t.count = reseed_count; t.next = rn2(100000);
        assert(t.count == 0);
    }
    choose_windows("tty"); initoptions(); init_nhwindows(&argc, argv);
    WIN_MESSAGE = create_nhwindow(NHW_MESSAGE);
    WIN_STATUS = create_nhwindow(NHW_STATUS); WIN_MAP = create_nhwindow(NHW_MAP);
    display_nhwindow(WIN_MESSAGE,FALSE);
    assert(iflags.window_inited && windowprocs.win_putstr == tty_putstr);
    assert(ttyDisplay->cols == 80 && ttyDisplay->rows == 24);
    init_objects(); init_gods();
    urace.malenum = PM_HUMAN; urole.malenum = PM_WIZARD;
    u.umonnum = u.umonster = PM_HUMAN;
    youmonst.data = &mons[PM_HUMAN]; youmonst.mtyp = PM_HUMAN;
    u.ulevel = 1; u.uhp = u.uhprolled = 20; u.uen = u.uenrolled = 20;
    u.usanity = 73; u.uinsight = 19;
    for (i = 0; i < A_MAX; ++i) ABASE(i) = AMAX(i) = 12;
    u.ux = 10; u.uy = 10; moves = 101; u.uz.dlevel = 1; u.ualign.god = 1;
    init_artifacts(); calc_total_maxhp(); calc_total_maxen();
    u.uhungermax = 2000; u.uhunger = 500; u.uhs = NOT_HUNGRY;
    assert(YouHunger > 150*get_uhungersizemod() && YouHunger+10 <= get_satiationlimit());
    /* No init_dungeon: explicitly separate branches from ordinary dnum zero. */
    sokoban_dnum = 1; neutral_dnum = 2;
    assert(!sp_levchn && !in_town(u.ux,u.uy) && !In_sokoban(&u.uz));
    assert(!In_outlands(&u.uz) && !wizard && !Levitation && !Underwater);
    assert(!Blind && !Hallucination && !Strangled && !u.usteed && !u.uswallow);
    assert(!u.sealsActive && !u.specialSealsActive && !uarmh && !uarmc && !uarmg);
    assert(!nomouth(youracedata->mtyp) && !occupation && multi == 0);
    for (x = 7; x <= 17; ++x) for (y = 7; y <= 13; ++y) {
        levl[x][y].typ = ROOM; levl[x][y].lit = 1;
    }
    levl[u.ux][u.uy].typ = FOUNTAIN; level.flags.nfountains = 1;
    assert(!levl[u.ux][u.uy].blessedftn && !levl[u.ux][u.uy].looted);
    assert(!FOUNTAIN_IS_WARNED(u.ux,u.uy));
    vision_init(); vision_reset(); vision_recalc(0);
    for (x = 1; x < COLNO; ++x) for (y = 0; y < ROWNO; ++y) newsym(x,y);
    empty_world(0);
    if (decline) {
        potion = mksobj(POT_WATER, MKOBJ_NOINIT); assert(potion);
        potion->obj_material = objects[POT_WATER].oc_material;
        potion->quan = 1; potion->known = potion->dknown = potion->bknown = 1;
        potion->blessed = potion->cursed = 0;
        potion->owt = weight(potion);
        potion->invlet = 'a'; potion->where = OBJ_INVENT; invent = potion;
        assert(potion->oclass == POTION_CLASS && potion->owt > 0);
        saved_potion = *potion;
    }
    empty_world(potion); chaos_start(); assert(u.chaos.safe == 1);
    before = u; saved_youmonst = youmonst; level_flags = level.flags;
    saved_flags = flags;
    memcpy(map,levl,sizeof map); memcpy(discovery,disco,sizeof discovery);
    memcpy(definitions,objects,sizeof definitions);
    old_moves = moves; old_monstermoves = monstermoves;
    seeded_reset(seed);
    result = dodrink();
    /* Only after the genuine confirmed native action returns; no extra scope,
     * callback, seed reset, or production argument interpretation. */
    if (injection) {
        assert(!decline && result == MOVE_QUAFFED);
        /* abort() does not flush the native renderer's buffered stdout.
         * Retain its actual bytes, without another message/render callback. */
        assert(!fflush(stdout));
        if (!strcmp(injection, "native")) (void)rn2(100000);
        else if (!strcmp(injection, "raw")) (void)random();
        else u.chaos.spent += 1;
    }
    count = reseed_count; next = rn2(100000);
    if (injection) {
        assert(getenv("FOUNTAIN_INTERVAL"));
        f = fopen(getenv("FOUNTAIN_INTERVAL"),"w"); assert(f);
        fprintf(f,"{\"action_completed\":true,\"case\":\"confirmed-refreshed\","
                "\"injection\":\"%s\",\"seed\":%u,\"returncode\":%d,\"move_quaffed\":%d,"
                "\"count\":%d,\"next\":%d,\"expected_count\":%d,\"expected_next\":%d,"
                "\"spent_before\":%d,\"spent_after\":%d,\"hunger_before\":%d,\"hunger_after\":%d,"
                "\"context_before\":",injection,seed,result,MOVE_QUAFFED,count,next,t.count,t.next,
                before.chaos.spent,u.chaos.spent,before.uhunger,u.uhunger);
        context_record(f,&before,old_moves);
        fputs(",\"context_after\":",f); context_record(f,&u,moves);
        fputs("}\n",f); assert(!fflush(f)); assert(!fclose(f));
    }
    fprintf(stderr,"{\"case\":\"%s\",\"seed\":%u,\"return\":%d,"
            "\"move_quaffed\":%d,\"move_cancelled\":%d,\"count\":%d,\"next\":%d,\"expected_next\":%d,"
            "\"hunger_before\":%d,\"hunger_after\":%d,\"hunger_delta\":%d,"
            "\"status_before\":%d,\"status_after\":%d,\"fate\":%d,\"dry\":%d,",
            argv[1],seed,result,MOVE_QUAFFED,MOVE_CANCELLED,count,next,t.next,before.uhunger,u.uhunger,t.hunger,
            before.uhs,u.uhs,t.fate,t.dry);
    fflush(stderr);
    assert(result == (decline ? MOVE_CANCELLED : MOVE_QUAFFED) && count == t.count && next == t.next);
    assert(reseed_period == INT_MAX && moves == old_moves && monstermoves == old_monstermoves);
    assert(u.uhunger == before.uhunger+t.hunger && u.uhs == NOT_HUNGRY);
    assert(!occupation && multi == 0); empty_world(potion);
    if (potion) assert(!memcmp(&saved_potion,potion,sizeof saved_potion));
    normalized = u; normalized.uhunger = before.uhunger;
    normalized.chaos.seq = before.chaos.seq; /* driver verifies exact sequence delta */
    assert(!memcmp(&before,&normalized,sizeof before));
    assert(!memcmp(&saved_youmonst,&youmonst,sizeof youmonst));
    assert(!memcmp(map,levl,sizeof map) && !memcmp(&level_flags,&level.flags,sizeof level_flags));
    assert(!memcmp(discovery,disco,sizeof discovery) && !memcmp(definitions,objects,sizeof definitions));
    /* TTY status refresh may clear botl; all other global gameplay flags match. */
    saved_flags.botl = flags.botl;
    assert(!memcmp(&saved_flags,&flags,sizeof flags));
    assert(getenv("FOUNTAIN_STATE")); f = fopen(getenv("FOUNTAIN_STATE"),"w"); assert(f);
    fprintf(f,"{\"seq_before\":%ld,\"seq_after\":%ld,\"player_before_hex\":",before.chaos.seq,u.chaos.seq);
    hex_record(f,&before,sizeof before); fputs(",\"player_after_hex\":",f); hex_record(f,&u,sizeof u);
    fputs(",\"map_before_hex\":",f); hex_record(f,map,sizeof map);
    fputs(",\"map_after_hex\":",f); hex_record(f,levl,sizeof map);
    fputs(",\"context_before\":",f); context_record(f,&before,old_moves);
    fputs(",\"context_after\":",f); context_record(f,&u,moves);
    fputs(",\"inventory_before_hex\":",f); hex_record(f,&saved_potion,potion ? sizeof saved_potion : 0);
    fputs(",\"inventory_after_hex\":",f); hex_record(f,potion,potion ? sizeof *potion : 0);
    fputs("}\n",f); assert(!fclose(f));
    fprintf(stderr,"\"hp\":%d,\"hp_max\":%d,\"power\":%d,\"power_max\":%d,"
            "\"sanity\":%d,\"insight\":%d,\"moves\":%ld,\"monstermoves\":%ld,"
            "\"nfountains\":%d,\"native_oracles_passed\":true}\n",
            u.uhp,u.uhpmax,u.uen,u.uenmax,u.usanity,u.uinsight,moves,monstermoves,level.flags.nfountains);
    if (potion) { invent = 0; potion->where = OBJ_FREE; obfree(potion,(struct obj *)0); }
    fflush(stdout); exit_nhwindows((char *)0); return 0;
}
