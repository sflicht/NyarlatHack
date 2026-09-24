/* NGPL. LINKED-NATIVE controlled W/F composition; NOT ordinary play.
 * Reuse the existing visible pet/tty setup, with no change to its unit cases.
 * Synthetic author history/origin-cache setup is explicit. No authored Lua here:
 * admission reads the exact envelope published by Python author_offline.
 * Native dog_move, message delivery/finalization, and drinkfountain own results.
 */
#define main dogmove_fixture_main
#include "next_use_dogmove.c"
#undef main

/* A genuinely unsupported message route, not a forged delivery outcome.
 * The tty map route remains intact so attention/displacement still occur. */
static void no_message(winid window, int attr, const char *text)
{
    (void)window;
    (void)attr;
    (void)text;
}

static int show_telegraph(void *opaque, const char *text)
{
    int *count = opaque;
    if (!text || !*text) return 0;
    pline("%s", text);
    ++*count;
    return 1;
}

static int admit_composition(const char *dirpath, int *telegraphs)
{
    struct chaos_next_use_safe_request req;
    struct chaos_next_use_safe_result result;
    struct chaos_next_use_origin_ref origin;
    char run[65];
    int dir, i;

    dir = open(dirpath, O_RDONLY | O_DIRECTORY);
    if (dir < 0) return 0;
    assert(!dir_run_hex(dir, run));
    chaos_next_use_safe_reset_for_test();
    /* Same synthetic origins as the author-history fixture. These are not
     * ordinary-play observations; never used to manufacture a W witness. */
    for (i = 0; i < 2; ++i) {
        memset(&origin, 0, sizeof origin);
        origin.root = i ? 6 : 3;
        origin.notice_seq = origin.root + 1;
        origin.end_seq = origin.root + 2;
        origin.family = i ? CHAOS_NEXT_USE_FAMILY_F : CHAOS_NEXT_USE_FAMILY_W;
        strcpy(origin.fact, i ? "water_refreshed" : "ordinary_whistle");
        origin.move = 10;
        origin.level_dnum = 0;
        origin.level_dlevel = 1;
        strcpy(origin.run, run);
        chaos_next_use_safe_bind_origin(&origin, 1);
    }
    memset(&req, 0, sizeof req);
    req.dir = dir;
    req.enabled = 1;
    req.at_safe = 2;
    req.at_move = 40;
    req.level_dnum = 0;
    req.level_dlevel = 1;
    req.run_hex = run;
    req.sanity = u.usanity;
    req.budget = &u.chaos;
    req.telegraph = show_telegraph;
    req.telegraph_opaque = telegraphs;
    req.receipt = receipt_ok;
    chaos_next_use_safe_try(&req, &result);
    close(dir);
    return result.active;
}

int main(int argc, char **argv)
{
    struct monst pet;
    struct chaos_whistle_witness witness;
    struct chaos_fountain_token token;
    struct chaos_next_use_snapshot snapshot;
    const struct chaos_next_use_public_record *pub;
    const struct chaos_next_use_runtime_private_record *rec;
    const char *mode, *dirpath;
    char envelope_sha[65] = "";
    int admitted, telegraphs = 0, ox, oy, ready = 0, ready_after = 0;
    int dog_draws = 0, dog_result = 0, contacted, remap, hunger, typ, fate;
    int f_effect = 0, i, expected, snapshot_valid;
    long completed, observation;
    FILE *out;

    if (argc == 2) {
        test_rng_negative_control(argv[1]);
        return 2;
    }
    if (argc != 3) return 2;
    mode = argv[1];
    dirpath = argv[2];
    fqn_prefix[TROUBLEPREFIX] = "./";
    setup_tty(&argc, argv);
    test_rng_control();
    test_rng_reset();
    setup_level(&pet);
    /* Controlled human fixture, like next_use_fountain.c, not generated play. */
    u.uhunger = 1000;
    u.usanity = 60;
    u.chaos.safe = 2;
    u.chaos.seq = 8; /* append after the eight synthetic history records */
    setenv("NYARLATHACK_OBSERVATIONS", "1", 1);
    setenv("NYARLATHACK_RUN_DIR", dirpath, 1);
    chaos_start();
    admitted = admit_composition(dirpath, &telegraphs);
    assert(admitted);
    ox = pet.mx;
    oy = pet.my;
    memset(&witness, 0, sizeof witness);
    if (strcmp(mode, "f_first")) {
        assert(chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 3, 0));
        chaos_next_use_capture_whistle(3, pet.m_id, monstermoves);
        monstermoves = 45;
        witness.production = strcmp(mode, "w_bypass") != 0;
        ready = chaos_next_use_whistle_decision_ready(pet.m_id);
        if (!strcmp(mode, "undelivered")) windowprocs.win_putstr = no_message;
        dog_draws = reseed_count;
        dog_result = dog_move(&pet, 0, &witness);
        chaos_whistle_witness_finalize(&pet, &witness);
        dog_draws = reseed_count - dog_draws;
        ready_after = chaos_next_use_whistle_decision_ready(pet.m_id);
        windowprocs.win_putstr = tty_putstr;
    }
    /* Existing seed 123, fixed before inspecting outcomes. A probe then reset
     * documents the real first rnd(30), without searching seeds or faking fate.
     * Separate reset isolates F from W's variable number of native RNG draws. */
    test_rng_reset();
    fate = rnd(30);
    test_rng_reset();
    levl[u.ux][u.uy].typ = FOUNTAIN;
    hunger = u.uhunger;
    typ = levl[u.ux][u.uy].typ;
    memset(&token, 0, sizeof token);
    completed = chaos_next_use_fountain_completed_root();
    expected = test_rng_begin();
    contacted = chaos_next_use_fountain_contact(completed, &token);
    test_rng_unchanged(expected);
    test_rng_reset();
    remap = token.remap;
    /* Negative control bypasses only the native effect binding, NOT the Lua
     * callback or receipt: the positive oracle must reject an unconsumed token. */
    chaos_bind_drinkfountain_token(contacted && strcmp(mode, "f_bypass") ? &token : 0);
    observation = chaos_observation_begin(CHAOS_OBS_OP_FOUNTAIN_DRINK);
    drinkfountain();
    chaos_observation_end(observation);
    chaos_bind_drinkfountain_token(0);
    /* This base's snapshot-v2 validation rejects a pending sibling after a
     * callback (#144). Export fills diagnostics before validating; retain its
     * status honestly. This fixture never imports/saves/replays that snapshot. */
    snapshot_valid = chaos_next_use_snapshot_export(&snapshot);
    for (i = 0; i < (int)chaos_next_use_runtime_private_count(); ++i) {
        rec = chaos_next_use_runtime_private_at((size_t)i);
        if (rec->kind == CHAOS_RUNTIME_PRIVATE_ADMISSION)
            strcpy(envelope_sha, rec->data.admission.envelope_sha256);
        if (rec->kind == CHAOS_RUNTIME_PRIVATE_EFFECT
            && rec->data.effect.family == CHAOS_NEXT_USE_FAMILY_F)
            f_effect = rec->data.effect.outcome;
    }
    out = fopen("result.json", "w");
    assert(out);
    fprintf(out,
        "{\"mode\":\"%s\",\"admitted\":%d,\"spent\":%d,\"telegraph\":%d,"
        "\"source_sha256\":\"%s\",\"envelope_sha256\":\"%s\","
        "\"ox\":%d,\"oy\":%d,\"mx\":%d,\"my\":%d,\"dog_result\":%d,"
        "\"ready_before\":%d,\"ready_after\":%d,\"dog_rng_draws\":%d,"
        "\"displaced\":%d,\"delivered\":%d,\"classifier\":%d,\"public\":%d,"
        "\"fate_probe\":%d,\"contacted\":%d,\"remap_before\":%d,"
        "\"token_active_after\":%d,\"hunger_before\":%d,\"hunger_after\":%d,"
        "\"typ_before\":%d,\"typ_after\":%d,\"f_rng_draws\":%d,"
        "\"snapshot_valid\":%d,\"state\":%d,\"slot_f\":%d,\"f_effect\":%d,\"public_record\":",
        mode, admitted, u.chaos.spent, telegraphs,
        snapshot.source_sha256, envelope_sha, ox, oy, pet.mx, pet.my, dog_result,
        ready, ready_after, dog_draws, witness.displaced,
        witness.manifestation_delivered, witness.classifier_ok,
        (int)chaos_next_use_runtime_public_count(), fate, contacted, remap,
        token.active, hunger, u.uhunger, typ, levl[u.ux][u.uy].typ, reseed_count,
        snapshot_valid, snapshot.state, snapshot.slot_f, f_effect);
    pub = chaos_next_use_runtime_public_at(0);
    if (pub)
        fprintf(out, "{\"family\":%d,\"phase\":%d,\"root\":%ld,"
                "\"notice_seq\":%ld,\"end_seq\":%ld}",
                pub->family, pub->phase, pub->root, pub->notice_seq, pub->end_seq);
    else fputs("null", out);
    fputs("}\n", out);
    assert(!fclose(out));
    return 0;
}
