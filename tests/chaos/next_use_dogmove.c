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

/* #196 (A2): NYARLATHACK_TEST_PET selects the companion's species; unset is
 * the little dog every earlier case used. Unknown names fail the run. */
static int pet_type(void)
{
    const char *name = getenv("NYARLATHACK_TEST_PET");
    if (!name || !*name || !strcmp(name, "little_dog")) return PM_LITTLE_DOG;
    if (!strcmp(name, "dog")) return PM_DOG;
    if (!strcmp(name, "large_dog")) return PM_LARGE_DOG;
    if (!strcmp(name, "kitten")) return PM_KITTEN;
    if (!strcmp(name, "housecat")) return PM_HOUSECAT;
    if (!strcmp(name, "pony")) return PM_PONY;
    /* #196 evidence: a tame iguana was the companion in view in one sweep
     * game (bard-inherited 56); #200 folds it into the linked matrix. */
    if (!strcmp(name, "iguana")) return PM_IGUANA;
    exit(3);
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
    pet->data = &mons[pet_type()];
    pet->mtyp = pet_type();
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
    /* The safe layer retains this ledger through runtime termination. */
    static struct chaos_state budget;
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

/* The fresh native transport must claim its logical owner before publication.
 * This controlled fixture already has exact candidate bytes prepared by Python;
 * defer only their publication, without rewriting bytes or forging ownership.
 * Both links are no-clobber and preserve failed-run evidence on error. */
static int defer_candidate(const char *dirpath, int restore)
{
    char candidate[512], held[512];
    const char *from, *to;
    if (snprintf(candidate, sizeof candidate, "%s/next_use-envelope.json", dirpath)
            >= (int)sizeof candidate
        || snprintf(held, sizeof held, "%s/fixture-envelope-held.json", dirpath)
            >= (int)sizeof held)
        return 0;
    from = restore ? held : candidate;
    to = restore ? candidate : held;
    return !link(from, to) && !unlink(from);
}

static int run_case(const char *name, const char *dirpath)
{
    struct monst pet;
    struct chaos_whistle_witness witness;
    int telegraphs = 0, rc, ox, oy, ready, arm, public_n, public2, f_action;
    int snapshot = 0, windowed = 0, pre_glyph = 0, restored = 0, spent2 = 0;
    int rebind = !strcmp(name, "obsrebind") || !strcmp(name, "obsrebind_save")
        || !strcmp(name, "obsrebind_level");
    int obs = !strcmp(name, "obsorigin") || !strcmp(name, "unequalclock")
        || !strcmp(name, "obslevel");
    int owned_start = !strcmp(name, "safehit") || !strcmp(name, "safemiss")
        || obs || rebind;
    long bound_root = 0;
    unsigned orig_id;

    test_rng_control();
    test_rng_reset();
    setup_level(&pet);
    setenv("NYARLATHACK_OBSERVATIONS", "1", 1);
    setenv("NYARLATHACK_RUN_DIR", dirpath, 1);
    if (owned_start) {
        if (!defer_candidate(dirpath, 0)) return 2;
        setenv("NYARLATHACK_NEXT_USE_ADMIT", "1", 1);
        /* Other linked cases intentionally preinitialize restore-like state.
         * These safe-point cases must exercise genuine fresh initialization. */
        u.chaos.version = 0;
        u.chaos_game_token = 0;
    }
    chaos_start();
    if (owned_start && !defer_candidate(dirpath, 1)) return 2;
    ox = pet.mx;
    oy = pet.my;
    orig_id = pet.m_id;
    memset(&witness, 0, sizeof witness);
    witness.production = strcmp(name, "noprod") != 0;
    arm = 0;
    if (strcmp(name, "none") && strcmp(name, "bypass")
        && strcmp(name, "safemiss") && strcmp(name, "safehit")
        && !obs && !rebind) {
        arm = admit_and_act(dirpath, &pet, &telegraphs,
                            strcmp(name, "nonepet") != 0
                            && strncmp(name, "suppress_", 9) != 0);
        if (arm < 0) return 2;
        /* #196: the whistle found no companion to bind; record why. The
         * "unrecorded" case is the pre-#196 entry point (reason 0). */
        if (arm == 2 && !strcmp(name, "suppress_unrecorded"))
            chaos_next_use_whistle_unavailable(10);
        else if (arm == 2 && !strcmp(name, "suppress_none"))
            chaos_next_use_whistle_suppressed(10, CHAOS_W_SUPPRESSED_NONE_IN_VIEW);
        else if (arm == 2 && !strcmp(name, "suppress_ineligible"))
            chaos_next_use_whistle_suppressed(10, CHAOS_W_SUPPRESSED_NOT_ELIGIBLE);
        else if (arm == 2 && !strcmp(name, "suppress_recheck"))
            chaos_next_use_whistle_suppressed(10, CHAOS_W_SUPPRESSED_RECHECK_FAILED);
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
    if (obs) {
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
        /* #200 (A): the whistle was on level 1; the safe point is arriving
         * on level 2, where the program is installed and its effect lands. */
        if (!strcmp(name, "obslevel")) u.uz.dlevel = 2;
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
    if (rebind) {
        /* #177: the envelope names the first whistle (root 10); a second,
         * newer whistle replaces it before the safe point. The engine binds
         * the newest same-family origin, on any level (#200 C). */
        long root;
        int acted;

        u.chaos.seq = 9;
        root = chaos_observation_begin(CHAOS_OBS_OP_WHISTLING);
        chaos_observation_arm(CHAOS_OBS_OP_WHISTLING, CHAOS_OBS_FACT_SOUND_HIGH);
        You("produce a high whistling sound.");
        chaos_observation_disarm();
        chaos_observation_end(root);
        /* A repeated identical top line is not re-rendered, so it would give
         * no notice; the player's --More--/next turn clears it in play. */
        clear_nhwindow(WIN_MESSAGE);
        if (!strcmp(name, "obsrebind_level")) u.uz.dlevel = 2;
        bound_root = chaos_observation_begin(CHAOS_OBS_OP_WHISTLING);
        chaos_observation_arm(CHAOS_OBS_OP_WHISTLING, CHAOS_OBS_FACT_SOUND_HIGH);
        You("produce a high whistling sound.");
        chaos_observation_disarm();
        chaos_observation_end(bound_root);
        clear_nhwindow(WIN_MESSAGE);
        if (!strcmp(name, "obsrebind_level")) u.uz.dlevel = 1;
        setenv("NYARLATHACK_NEXT_USE_ADMIT", "1", 1);
        u.chaos.safe = 6;
        chaos_safe("level_enter");
        if (u.chaos.spent == 1 && !strcmp(name, "obsrebind_save")) {
            restored = persist_and_restore(dirpath);
            if (!restored) return 2;
            u.chaos.safe = 7;
            chaos_safe("level_enter");
            spent2 = u.chaos.spent;
        }
        /* The engine telegraph occupies the top line; the player's key
         * acknowledges it before the companion's next move in play. */
        clear_nhwindow(WIN_MESSAGE);
        if (u.chaos.spent == 1) {
            /* A later ordinary whistle triggers; its root is the trigger,
             * the target is resolved from the one eligible companion. */
            acted = chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 30, 0);
            if (acted)
                chaos_next_use_capture_whistle(30, pet.m_id, monstermoves);
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
    /* dog_move does not publish its new map cell. The production m_move
     * postmov path updates both cells before witness finalization. */
    if (rc == 1 && !DEADMONSTER(&pet)) {
        newsym(ox, oy);
        newsym(pet.mx, pet.my);
    }
    /* The native decision/message occurred; replace only finalization input. */
    if (!strcmp(name, "postid")) pet.m_id++;
    if (!strcmp(name, "postglyph"))
        show_glyph(pet.mx, pet.my, cmap_to_glyph(S_litroom));
    if (!strcmp(name, "postlevel")) u.uz.dlevel++;
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
            "\"root\":%ld,\"notice\":%ld,\"spent\":%d,\"spent2\":%d,\"restored\":%d,"
            "\"bound_root\":%ld,\"mtyp\":%d,\"mtame\":%d,\"mpeaceful\":%d,"
            "\"alive\":%d,\"ux\":%d,\"uy\":%d,\"dist_before\":%d,\"dist_after\":%d}\n",
            name, ox, oy, pet.mx, pet.my, rc, arm, telegraphs, ready,
            chaos_next_use_whistle_decision_ready(pet.m_id),
            chaos_next_use_whistle_decision_ready(orig_id),
            public_n, public2, pet.m_id, f_action,
            witness.displaced, witness.manifestation_delivered,
            witness.pre_public, reseed_count, rn2(100000),
            snapshot, windowed, pre_glyph, witness.post_glyph,
            witness.invalid, witness.classifier_ok,
            witness.root, witness.notice_seq, u.chaos.spent, spent2, restored,
            bound_root, pet.mtyp, (int)pet.mtame, (int)pet.mpeaceful,
            !DEADMONSTER(&pet), u.ux, u.uy, dist2(ox, oy, u.ux, u.uy),
            dist2(pet.mx, pet.my, u.ux, u.uy));
        fclose(out);
    }
    return 0;
}

/* #196 (B1): the production pick over several companions.
 * NYARLATHACK_TEST_PICK="x,y,kind[,m_id];..." places them in fmon list order
 * (m_id defaults to 7, 8, ...). kind is a species name for pet_type(), or
 * "hostile" (an untamed dog) or "leashed" (a leashed tame dog). Prints the
 * picked square/m_id, the recorded reason, and the RNG draw after the pick
 * next to a control draw with no pick. */
static int run_pick(void)
{
    static struct monst pets[8];
    const char *spec = getenv("NYARLATHACK_TEST_PICK");
    char buf[256], *entry, *save = 0;
    struct monst *picked, *prev = 0;
    int n = 0, reason = -1, after_pick, control, seen_draws;
    FILE *out;

    if (!spec || strlen(spec) >= sizeof buf) return 2;
    unsetenv("NYARLATHACK_TEST_PET");
    test_rng_control();
    test_rng_reset();
    setup_level(&pets[0]);
    remove_monster(pets[0].mx, pets[0].my);
    fmon = 0;
    strcpy(buf, spec);
    for (entry = strtok_r(buf, ";", &save); entry && n < 8;
         entry = strtok_r(0, ";", &save), ++n) {
        struct monst *m = &pets[n];
        char kind[32];
        int x, y, id = 7 + n, got;
        got = sscanf(entry, "%d,%d,%31[a-z_],%d", &x, &y, kind, &id);
        if (got < 3 || !isok(x, y) || m_at(x, y)) return 2;
        if (!strcmp(kind, "hostile") || !strcmp(kind, "leashed"))
            setenv("NYARLATHACK_TEST_PET", "dog", 1);
        else
            setenv("NYARLATHACK_TEST_PET", kind, 1);
        memset(m, 0, sizeof *m);
        m->mtyp = pet_type();
        m->data = &mons[m->mtyp];
        m->mhp = m->mhpmax = 10;
        m->m_id = (unsigned)id;
        m->mtame = strcmp(kind, "hostile") ? 10 : 0;
        m->mpeaceful = m->mtame ? 1 : 0;
        m->mleashed = !strcmp(kind, "leashed");
        m->mcanmove = 1;
        m->mcansee = 1;
        if (m->mtame) {
            add_mx(m, MX_EDOG);
            EDOG(m)->hungrytime = monstermoves + 10000;
        }
        place_monster(m, x, y);
        if (prev) prev->nmon = m; else fmon = m;
        prev = m;
    }
    unsetenv("NYARLATHACK_TEST_PET");
    vision_recalc(0);
    docrt();
    flush_screen(1);
    test_rng_reset();
    seen_draws = reseed_count;
    picked = chaos_next_use_companion_pick(&reason);
    seen_draws = reseed_count - seen_draws; /* before the comparison draw */
    after_pick = rn2(100000);
    test_rng_reset();
    control = rn2(100000);
    out = fopen("result.json", "w");
    if (!out) return 2;
    fprintf(out, "{\"case\":\"pick\",\"picked\":%d,\"px\":%d,\"py\":%d,"
            "\"m_id\":%u,\"reason\":%d,\"after_pick\":%d,\"control\":%d,"
            "\"reseed_delta\":%d,\"ux\":%d,\"uy\":%d,\"count\":%d}\n",
            picked != 0, picked ? picked->mx : -1, picked ? picked->my : -1,
            picked ? picked->m_id : 0, reason, after_pick, control,
            seen_draws, u.ux, u.uy, n);
    fclose(out);
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
    if (!strcmp(name, "pick")) {
        setenv("NYARLATHACK_RUN_DIR", dirpath, 1);
        return run_pick();
    }
    return run_case(name, dirpath);
}
