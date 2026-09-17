/* NGPL. Full native dodrink with physical TTY confirmation/cancellation.
 * Only labelled low-level reach cases create a test scope (begin/end).
 * Never manufacture blocked/arm/delivered/take: missing hooks stay RED. */
#include "hack.h"
#include "chaos.h"
#include "wintty.h"
#include "native_rng.h"
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>

extern int msgpline_type(const char *);
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
static int predicted_wisdom;
static struct monst *prepared_monster;
static int forwarded_calls, forwarded_returns, forwarded_blocking_maps;
/* Unsupported identity, not a renderer stub. Forward once per callback;
 * the public native renderer's internal recursion stays unchanged. */
static void forwarding_display(winid window, BOOLEAN_P blocking)
{
    ++forwarded_calls;
    if (window == WIN_MAP && blocking) ++forwarded_blocking_maps;
    tty_display_nhwindow(window, blocking);
    ++forwarded_returns;
}
static struct trace preflight_detection(unsigned seed)
{
    struct trace t;
    seeded_reset(seed);
    t.fate = rnd(30); t.hunger = 0; t.dry = -1;
    predicted_wisdom = 0;
    if (t.fate == 26) {
        predicted_wisdom = rn2(19) > 12;
        t.dry = rn2(3);
    }
    t.count = reseed_count; t.next = rn2(100000);
    return t;
}
static struct trace preflight(unsigned seed)
{
    struct trace t;
    seeded_reset(seed);
    t.fate = rnd(30); t.hunger = t.dry = -1;
    if (t.fate < 10) { t.hunger = rnd(10); t.dry = rn2(3); }
    if (t.fate == 20) { t.hunger = -rn1(20,11); t.dry = rn2(3); }
    t.count = reseed_count; t.next = rn2(100000);
    return t;
}

/* Only case 20 is modeled: native branch skips rn1/morehungry/vomit. */
static struct trace preflight_mechanoid(unsigned seed)
{
    struct trace t;
    seeded_reset(seed);
    t.fate = rnd(30); t.hunger = 0; t.dry = -1;
    if (t.fate == 20) t.dry = rn2(3);
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
    assert(invent == potion && fmon == prepared_monster && !fobj && !ftrap && !migrating_mons && !migrating_objs);
    if (prepared_monster) {
        assert(!prepared_monster->nmon && !prepared_monster->minvent && !prepared_monster->mextra_p);
        assert(prepared_monster->mhp > 0 && prepared_monster->mhpmax >= prepared_monster->mhp);
        assert(prepared_monster->mx == 12 && prepared_monster->my == 10);
        assert(prepared_monster->data == &mons[PM_LITTLE_DOG]);
        assert(prepared_monster->mtyp == PM_LITTLE_DOG);
    }
    assert(!nextgetobj);
    if (potion) assert(!potion->nobj && !potion->cobj && !potion->oextra_p
                       && !potion->mp && potion->where == OBJ_INVENT);
    for (x = 0; x < COLNO; ++x) for (y = 0; y < ROWNO; ++y)
        assert(level.monsters[x][y] == ((prepared_monster && x == 12 && y == 10) ? prepared_monster : 0)
               && !level.objects[x][y] && !t_at(x,y));
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
    struct monst saved_youmonst, saved_monster;
    struct rm map[COLNO][ROWNO];
    typeof(level.flags) level_flags;
    short discovery[NUM_OBJECTS];
    struct objclass definitions[NUM_OBJECTS];
    struct flag saved_flags;
    struct obj *potion = 0, saved_potion;
    long old_moves, old_monstermoves;
    unsigned seed;
    int i,x,y,result,count,next,decline,foul,mechanoid, total = 0;
    int reach, noshow, lev_cancel, levitating, returned = 0;
    int detection, map_cancelled, no_live, map_flags = 0;
    int map_escape, map_forwarded, message_flags = 0;
    long root = 0;
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
        /* Declared candidate set: integers 1..256 inclusive, no action rerolls.
         * At most 1024 native calls here, including every sentinel. */
        puts("[");
        for (seed = 1; seed <= 256; ++seed) {
            t = preflight(seed); total += t.count + 1;
            printf("%s{\"seed\":%u,\"fate\":%d,\"hunger\":%d,\"dry\":%d,"
                   "\"count\":%d,\"next\":%d}", seed == 1 ? "" : ",\n",
                   seed,t.fate,t.hunger,t.dry,t.count,t.next);
        }
        assert(total <= 1024); puts("\n]"); return 0;
    }
    if (!strcmp(argv[1], "--calibrate-detection")) {
        puts("[");
        for (seed = 1; seed <= 256; ++seed) {
            t = preflight_detection(seed); total += t.count + 1;
            printf("%s{\"seed\":%u,\"fate\":%d,\"hunger\":%d,\"dry\":%d,\"count\":%d,\"next\":%d,\"wisdom\":%d}",
                   seed == 1 ? "" : ",\n",seed,t.fate,t.hunger,t.dry,t.count,t.next,predicted_wisdom);
        }
        assert(total <= 1024); puts("\n]"); return 0;
    }
    if (!strcmp(argv[1], "--calibrate-mechanoid")) {
        puts("[");
        for (seed = 1; seed <= 256; ++seed) {
            t = preflight_mechanoid(seed); total += t.count + 1;
            printf("%s{\"seed\":%u,\"fate\":%d,\"hunger\":%d,\"dry\":%d,"
                   "\"count\":%d,\"next\":%d}", seed == 1 ? "" : ",\n",
                   seed,t.fate,t.hunger,t.dry,t.count,t.next);
        }
        assert(total <= 768); puts("\n]"); return 0;
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
    foul = !strcmp(argv[1], "confirmed-foul");
    mechanoid = !strcmp(argv[1], "confirmed-foul-mechanoid");
    noshow = !strcmp(argv[1], "lowlevel-reach-noshow");
    reach = noshow || !strcmp(argv[1], "lowlevel-reach-delivered");
    lev_cancel = !strcmp(argv[1], "levitating-dodrink-selection-cancel");
    levitating = reach || lev_cancel;
    map_cancelled = !strcmp(argv[1], "confirmed-detection-map-cancelled");
    no_live = !strcmp(argv[1], "confirmed-detection-empty");
    map_escape = !strcmp(argv[1], "confirmed-detection-escape");
    map_forwarded = !strcmp(argv[1], "confirmed-detection-forwarded");
    detection = map_cancelled || no_live || map_escape || map_forwarded
        || !strcmp(argv[1], "confirmed-detection-presented");
    assert(decline || foul || mechanoid || levitating || detection || !strcmp(argv[1], "confirmed-refreshed"));
    assert(getenv("FOUNTAIN_SEED")); seed = (unsigned)atoi(getenv("FOUNTAIN_SEED"));
    assert(seed >= 1 && seed <= 256);
    if (levitating) {
        /* Fixed legal seed; runtime native continuation, no fate search. */
        assert(seed == 1); seeded_reset(seed);
        t.fate = t.dry = -1; t.hunger = 0;
        if (reach) (void)rnd(30);
        t.count = reseed_count; t.next = rn2(100000);
        assert(t.count == (reach ? 1 : 0));
    } else {
    t = detection ? preflight_detection(seed) : (mechanoid ? preflight_mechanoid(seed) : preflight(seed));
    assert((detection ? t.fate == 26 : ((foul || mechanoid) ? t.fate == 20 : t.fate < 10)) && t.dry > 0);
    assert(t.count == (mechanoid ? 2 : 3));
    if (decline) {
        seeded_reset(seed);
        t.fate = t.dry = -1; t.hunger = 0;
        t.count = reseed_count; t.next = rn2(100000);
        assert(t.count == 0);
    }
    }
    choose_windows("tty"); initoptions(); init_nhwindows(&argc, argv);
    WIN_MESSAGE = create_nhwindow(NHW_MESSAGE);
    WIN_STATUS = create_nhwindow(NHW_STATUS); WIN_MAP = create_nhwindow(NHW_MAP);
    display_nhwindow(WIN_MESSAGE,FALSE);
    assert(iflags.window_inited && windowprocs.win_putstr == tty_putstr);
    assert(ttyDisplay->cols == 80 && ttyDisplay->rows == 24);
    init_objects(); init_gods();
    if (levitating || detection) id_permonst(); /* genuine native startup mtyp initialization */
    urace.malenum = PM_HUMAN; urole.malenum = PM_WIZARD;
    u.umonnum = u.umonster = PM_HUMAN;
    youmonst.data = &mons[PM_HUMAN]; youmonst.mtyp = PM_HUMAN;
    u.ulevel = 1; u.uhp = u.uhprolled = 20; u.uen = u.uenrolled = 20;
    u.usanity = 73; u.uinsight = 19;
    for (i = 0; i < A_MAX; ++i) ABASE(i) = AMAX(i) = 12;
    u.ux = 10; u.uy = 10; moves = 101; u.uz.dlevel = 1; u.ualign.god = 1;
    init_artifacts(); calc_total_maxhp(); calc_total_maxen();
    if (mechanoid) {
        /* Human in a mouth-bearing native clockwork polyform. set_uasmon
         * uses set_mon_data; never redefine umechanoid or manufacture a flag.
         * Setup only, not a simulated polyself action or its RNG accounting. */
        id_permonst(); /* native startup assigns mons[].mtyp before set_uasmon */
        u.umonnum = PM_CLOCKWORK_AUTOMATON;
        u.mtimedone = 500; u.mh = u.mhrolled = 20;
        u.macurr = u.acurr; u.mamax = u.amax;
        set_uasmon(); calc_total_maxhp();
        assert(Race_if(PM_HUMAN) && Upolyd && uclockwork && umechanoid);
        assert(youracedata == &mons[PM_CLOCKWORK_AUTOMATON]);
        assert(youmonst.mtyp == PM_CLOCKWORK_AUTOMATON && u.mh > 0 && u.mhmax >= u.mh);
        assert(!Sick && !multi_txt[0] && !afternmv && !nomovemsg);
    }
    u.uhungermax = 2000; u.uhunger = 500; u.uhs = NOT_HUNGRY;
    assert(YouHunger > 150*get_uhungersizemod() && YouHunger+10 <= get_satiationlimit());
    /* No init_dungeon: explicitly separate branches from ordinary dnum zero. */
    sokoban_dnum = 1; neutral_dnum = 2;
    assert(!sp_levchn && !in_town(u.ux,u.uy) && !In_sokoban(&u.uz));
    assert(!In_outlands(&u.uz) && !wizard && !Levitation && !Underwater);
    assert(!Blind && !Hallucination && !Strangled && !u.usteed && !u.uswallow);
    assert(!u.sealsActive && !u.specialSealsActive && !uarmh && !uarmc && !uarmg);
    assert(!nomouth(youracedata->mtyp) && !occupation && multi == 0);
    if (foul) {
        /* Healthy ordinary metabolism; retain real vomiting incapacitation. */
        assert(!umechanoid && !inediate(youracedata) && !Free_action && !Sick);
        assert(YouHunger-30 > 150*get_uhungersizemod());
        assert(!u.uinvulnerable && !u.usleep && !u.puzzle_time);
        assert(!flags.forcefight && !flags.travel && !iflags.travel1);
        assert(!flags.mv && !flags.run && !multi_txt[0] && !afternmv && !nomovemsg);
    }
    for (x = 7; x <= 17; ++x) for (y = 7; y <= 13; ++y) {
        levl[x][y].typ = ROOM; levl[x][y].lit = 1;
    }
    levl[u.ux][u.uy].typ = FOUNTAIN; level.flags.nfountains = 1;
    assert(!levl[u.ux][u.uy].blessedftn && !levl[u.ux][u.uy].looted);
    assert(!FOUNTAIN_IS_WARNED(u.ux,u.uy));
    vision_init(); vision_reset(); vision_recalc(0);
    for (x = 1; x < COLNO; ++x) for (y = 0; y < ROWNO; ++y) newsym(x,y);
    empty_world(0);
    if (detection) {
        u.ulycn = NON_PM; u.ugrave_arise = NON_PM;
        assert(Race_if(PM_HUMAN) && !Sick && !Hallucination && !Blind);
        assert(!Upolyd && !umechanoid && ACURR(A_WIS) == 12 && AEXE(A_WIS) == 0);
        if (!no_live) {
            prepared_monster = makemon(&mons[PM_LITTLE_DOG],12,10,NO_MINVENT);
            assert(prepared_monster && canseemon(prepared_monster));
        }
        docrt(); clear_nhwindow(WIN_MESSAGE); flush_screen(1); assert(!fflush(stdout));
        empty_world(0);
        if (prepared_monster) saved_monster = *prepared_monster;
        assert(windowprocs.win_display_nhwindow == tty_display_nhwindow);
        assert(windowprocs.win_print_glyph == tty_print_glyph);
        assert(!(wins[WIN_MAP]->flags & WIN_CANCELLED));
        if (map_cancelled) wins[WIN_MAP]->flags |= WIN_CANCELLED;
        map_flags = wins[WIN_MAP]->flags;
        if (map_escape || map_forwarded) {
            message_flags = wins[WIN_MESSAGE]->flags;
            assert(message_flags == 0 && map_flags == 0);
            assert(windowprocs.win_clear_nhwindow == tty_clear_nhwindow);
            assert(windowprocs.win_curs == tty_curs);
            if (map_forwarded)
                windowprocs.win_display_nhwindow = forwarding_display;
        }
        /* Matched control: suppress only sense text in BOTH map cases.
         * vpline still flushes real glyphs before NOSHOW. Otherwise cancelled
         * map display is followed by an unrelated message More in docrt/cls.
         * The positive blocking map itself creates More with an empty toplin. */
        iflags.msgtype_regex = FALSE;
        msgpline_add(MSGTYP_NOSHOW, "You sense the presence of monsters.");
        assert(msgpline_type("You sense the presence of monsters.") == MSGTYP_NOSHOW);
    }
    if (decline || lev_cancel) {
        potion = mksobj(POT_WATER, MKOBJ_NOINIT); assert(potion);
        potion->obj_material = objects[POT_WATER].oc_material;
        potion->quan = 1; potion->known = potion->dknown = potion->bknown = 1;
        potion->blessed = potion->cursed = 0;
        potion->owt = weight(potion);
        potion->invlet = 'a'; potion->where = OBJ_INVENT; invent = potion;
        assert(potion->oclass == POTION_CLASS && potion->owt > 0);
        saved_potion = *potion;
    }
    if (levitating) {
        assert(Race_if(PM_HUMAN) && !Upolyd && youracedata == &mons[PM_HUMAN]);
        assert(youracedata->mtyp == PM_HUMAN && !nomouth(youracedata->mtyp));
        assert(!Levitation && !Flying && !Weightless && !ELevitation);
        assert(!u.utrap && !u.uinwater && !u.uswallow && !u.usteed);
        assert(!Is_waterlevel(&u.uz) && !Hallucination && !Sick);
        assert(!uarm && !uarmu && !uarmf && !uarms && !uarmh && !uarmc && !uarmg);
        assert(!multi_txt[0] && !afternmv && !nomovemsg && !occupation && !multi);
        assert(!u.uinvulnerable && !u.usleep && !u.puzzle_time);
        set_itimeout(&HLevitation, 500L); float_up();
        assert(HLevitation == 500L && !ELevitation && Levitation && !Flying);
        assert(!can_reach_floor()); /* diagnostic, not fountain eligibility */
        clear_nhwindow(WIN_MESSAGE); flush_screen(1); assert(!fflush(stdout));
        if (noshow) {
            iflags.msgtype_regex = FALSE;
            msgpline_add(MSGTYP_NOSHOW, "You are floating high above the fountain.");
            assert(msgpline_type("You are floating high above the fountain.") == MSGTYP_NOSHOW);
        }
    }
    empty_world(potion); chaos_start(); assert(u.chaos.safe == 1);
    before = u; saved_youmonst = youmonst; level_flags = level.flags;
    saved_flags = flags;
    memcpy(map,levl,sizeof map); memcpy(discovery,disco,sizeof discovery);
    memcpy(definitions,objects,sizeof definitions);
    old_moves = moves; old_monstermoves = monstermoves;
    seeded_reset(seed);
    if (reach) {
        root = chaos_observation_begin(CHAOS_OBS_OP_FOUNTAIN_DRINK);
        assert(root == (getenv("NYARLATHACK_OBSERVATIONS")
                       && !strcmp(getenv("NYARLATHACK_OBSERVATIONS"), "1")
                       ? before.chaos.seq + 1 : 0));
        drinkfountain(); /* actual void native call, exactly once */
        returned = 1;
        chaos_observation_end(root);
        result = 0; /* not a MOVE_* return from the void routine */
    } else result = dodrink();
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
    if (levitating) {
        assert((reach ? returned && result == 0 : result == MOVE_CANCELLED));
        assert(count == t.count && next == t.next && count == (reach ? 1 : 0));
        assert(HLevitation == 500L && HLevitation == before.uprops[LEVITATION].intrinsic);
        assert(u.uhunger == before.uhunger && t.hunger == 0);
        assert(!multi_txt[0] && !afternmv && !nomovemsg && !Sick);
    } else
    assert(result == (decline ? MOVE_CANCELLED : MOVE_QUAFFED) && count == t.count && next == t.next);
    assert(reseed_period == INT_MAX && moves == old_moves && monstermoves == old_monstermoves);
    assert(u.uhunger == before.uhunger+t.hunger && u.uhs == NOT_HUNGRY);
    assert(!occupation && multi == (foul ? -2 : 0)); empty_world(potion);
    if (foul) {
        assert(!strcmp(multi_txt,"vomiting") && !afternmv && !nomovemsg);
        assert(!iflags.travel1 && !Sick && !Free_action);
    }
    if (mechanoid) {
        assert(umechanoid && Upolyd && u.mtimedone == before.mtimedone);
        assert(!multi_txt[0] && !afternmv && !nomovemsg && !Sick);
    }
    if (potion) assert(!memcmp(&saved_potion,potion,sizeof saved_potion));
    normalized = u; normalized.uhunger = before.uhunger;
    normalized.chaos.seq = before.chaos.seq; /* driver verifies exact sequence delta */
    if (detection) {
        assert(AEXE(A_WIS) == before.aexe.a[A_WIS] + predicted_wisdom);
        normalized.aexe.a[A_WIS] = before.aexe.a[A_WIS];
        assert(wins[WIN_MAP]->flags == map_flags);
        if (prepared_monster) assert(!memcmp(&saved_monster,prepared_monster,sizeof saved_monster));
        if (map_escape || map_forwarded) {
            /* Native post-render Escape sets STOP; final docrt does not clear
             * it. Assert the exact aftermath, never clear/normalize it. */
            assert(wins[WIN_MESSAGE]->flags == (map_escape ? WIN_STOP : 0));
            assert(windowprocs.win_display_nhwindow ==
                   (map_forwarded ? forwarding_display : tty_display_nhwindow));
            assert(forwarded_calls == forwarded_returns);
            assert(forwarded_blocking_maps == map_forwarded);
            assert(map_forwarded ? forwarded_calls > 0 : forwarded_calls == 0);
        }
    }
    assert(!memcmp(&before,&normalized,sizeof before));
    assert(!memcmp(&saved_youmonst,&youmonst,sizeof youmonst));
    assert(!memcmp(map,levl,sizeof map) && !memcmp(&level_flags,&level.flags,sizeof level_flags));
    assert(!memcmp(discovery,disco,sizeof discovery) && !memcmp(definitions,objects,sizeof definitions));
    /* TTY status refresh may clear botl; all other global gameplay flags match. */
    saved_flags.botl = flags.botl;
    if (detection && !no_live) {
        /* monster_detect's final docrt schedules a full status redraw. */
        assert(!saved_flags.botlx && flags.botlx == 1);
        saved_flags.botlx = 1;
    }
    assert(!memcmp(&saved_flags,&flags,sizeof flags));
    assert(getenv("FOUNTAIN_STATE")); f = fopen(getenv("FOUNTAIN_STATE"),"w"); assert(f);
    fprintf(f,"{\"seq_before\":%ld,\"seq_after\":%ld,\"player_before_hex\":",before.chaos.seq,u.chaos.seq);
    hex_record(f,&before,sizeof before); fputs(",\"player_after_hex\":",f); hex_record(f,&u,sizeof u);
    fputs(",\"map_before_hex\":",f); hex_record(f,map,sizeof map);
    fputs(",\"map_after_hex\":",f); hex_record(f,levl,sizeof map);
    fputs(",\"context_before\":",f); context_record(f,&before,old_moves);
    fputs(",\"context_after\":",f); context_record(f,&u,moves);
    fputs(",\"inventory_before_hex\":",f); hex_record(f,&saved_potion,potion ? sizeof saved_potion : 0);
    if (foul)
        fprintf(f,",\"vomiting\":{\"multi\":%d,\"reason\":\"%s\",\"occupation\":false,"
                "\"afternmv\":false,\"nomovemsg\":false,\"free_action\":false}",multi,multi_txt);
    if (mechanoid || levitating)
        fprintf(f,",\"motion\":{\"multi\":%d,\"reason\":\"%s\",\"occupation\":%s,"
                "\"afternmv\":%s,\"nomovemsg\":%s}",multi,multi_txt,
                occupation ? "true" : "false", afternmv ? "true" : "false",
                nomovemsg ? "true" : "false");
    if (levitating)
        fprintf(f,",\"reach\":{\"lowlevel_calls\":%d,\"void_returned\":%s,\"dodrink_calls\":%d,\"timeout_before\":%ld,\"timeout_after\":%ld}",
                reach ? 1 : 0, returned ? "true" : "false", reach ? 0 : 1,
                before.uprops[LEVITATION].intrinsic,HLevitation);
    fputs(",\"inventory_after_hex\":",f); hex_record(f,potion,potion ? sizeof *potion : 0);
    if (detection)
        fprintf(f,",\"detection\":{\"wisdom_before\":%d,\"wisdom_after\":%d,\"predicted_wisdom\":%d,\"map_flags_before\":%d,\"map_flags_after\":%d,\"population\":%d,\"monster_hp\":%d,\"monster_type\":%d,\"monster_x\":%d,\"monster_y\":%d,\"monster_bytes_unchanged\":true}",
                before.aexe.a[A_WIS],AEXE(A_WIS),predicted_wisdom,map_flags,wins[WIN_MAP]->flags,
                !!prepared_monster,prepared_monster ? prepared_monster->mhp : 0,
                prepared_monster ? prepared_monster->mtyp : -1,
                prepared_monster ? prepared_monster->mx : 0,prepared_monster ? prepared_monster->my : 0);
    if (map_escape || map_forwarded)
        fprintf(f,",\"presentation_followup\":{\"message_flags_before\":%d,\"message_flags_after\":%d,\"forwarded_calls\":%d,\"forwarded_returns\":%d,\"forwarded_blocking_maps\":%d}",
                message_flags,wins[WIN_MESSAGE]->flags,forwarded_calls,
                forwarded_returns,forwarded_blocking_maps);
    fputs("}\n",f); assert(!fclose(f));
    fprintf(stderr,"\"hp\":%d,\"hp_max\":%d,\"power\":%d,\"power_max\":%d,"
            "\"sanity\":%d,\"insight\":%d,\"moves\":%ld,\"monstermoves\":%ld,"
            "\"nfountains\":%d,\"native_oracles_passed\":true}\n",
            u.uhp,u.uhpmax,u.uen,u.uenmax,u.usanity,u.uinsight,moves,monstermoves,level.flags.nfountains);
    if (potion) { invent = 0; potion->where = OBJ_FREE; obfree(potion,(struct obj *)0); }
    fflush(stdout); exit_nhwindows((char *)0); return 0;
}
