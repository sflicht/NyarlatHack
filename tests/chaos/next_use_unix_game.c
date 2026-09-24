/* NGPL. Controlled wizard fixture, NOT ordinary play or #66 acceptance.
 * Real Unix main, commands, turn loop, dog_move, fountain, tty and save/restore.
 * No runtime imports, fake reads, live witness setters or outcome assignments.
 * Explicit fault markers below are test-only; save loss affects a copied value.
 */
#include "hack.h"
#include "chaos.h"
#include "chaos_next_use_runtime.h"
#include "native_rng.h"
#include <stdio.h>
#include <unistd.h>

int original_game_main(int, char **);
void __real_chaos_start(void);
int __real_chaos_next_use_save(int);
void __real_chaos_observe(void);
void __real_rhack(char *);
int __real_dog_move(struct monst *, int, struct chaos_whistle_witness *);
boolean __real_chaos_whistle_attention_message(struct chaos_whistle_witness *);
void __real_chaos_whistle_witness_finalize(struct monst *, struct chaos_whistle_witness *);
void __real_drinkfountain(void);
void __real_chaos_next_use_fountain_result(const struct chaos_fountain_token *, int);
static int started, fountain_outcome, reset_ordinal;
static long fountain_root;

static FILE *file(const char *name, const char *mode)
{
    FILE *f = fopen(name, mode);
    assert(f);
    return f;
}

/* Opt-in observations only; preserve native.jsonl's older parity contract.
 * Ordinals are process-local reset-site counts, NOT a persisted RNG stream. */
static void rng_observation(const char *site)
{
    FILE *f;
    ++reset_ordinal;
    if (access("detailed-native", F_OK) != 0) return;
    f = file("physical.jsonl", "a");
    fprintf(f, "{\"kind\":\"rng\",\"site\":\"%s\",\"ordinal\":%d,"
        "\"count\":%d,\"moves\":%ld,\"monstermoves\":%ld}\n",
        site, reset_ordinal, reseed_count, moves, monstermoves);
    assert(!fclose(f));
}

static void state(void)
{
    struct chaos_next_use_snapshot s;
    FILE *f;
    int valid;
    if (!started) return;
    memset(&s, 0, sizeof s);
    valid = chaos_next_use_snapshot_export(&s);
    f = file("state.json", "w");
    fprintf(f, "{\"attempted\":%d,", chaos_next_use_safe_attempted());
    fprintf(f, "\"valid\":%d,\"moves\":%ld,\"monstermoves\":%ld,"
        "\"safe\":%ld,\"spent\":%d,\"dnum\":%d,\"dlevel\":%d,"
        "\"slot_w\":%d,\"slot_f\":%d,\"w_runtime\":%d,"
        "\"witnessed\":%d,\"attention_claimed\":%d,\"callback_ordinal\":%d,\"state\":%d,"
        "\"armed_m_id\":%u,\"source_sha256\":\"%s\","
        "\"activation_monstermoves\":%ld,\"armed_root\":%ld,"
        "\"run_token\":%ld,\"level_token\":%ld,\"origin_w\":%ld,\"origin_f\":%ld,"
        "\"origin_w_deadline\":%ld,\"origin_f_deadline\":%ld,\"program_expiry\":%d",
        valid, moves, monstermoves, u.chaos.safe, u.chaos.spent,
        u.uz.dnum, u.uz.dlevel, s.slot_w, s.slot_f, s.w_runtime,
        s.witnessed, s.attention_claimed, s.callback_ordinal, s.state,
        s.armed_m_id, s.source_sha256, s.activation_monstermoves, s.armed_root,
        s.run_token, s.level_token, s.origin_w, s.origin_f,
        s.origin_w_deadline, s.origin_f_deadline, s.program_expiry);
    fprintf(f, ",\"callback_w\":%d,\"callback_f\":%d,"
        "\"whistle_count\":%d,\"fountain_count\":%d,\"next_seq\":%d,"
        "\"last_root\":%ld,\"admission_move\":%d,\"delay_used\":%d,"
        "\"delay_until\":%d,\"variant\":%d,\"binding_sha256\":\"%s\"",
        s.callback_w, s.callback_f, s.whistle_count, s.fountain_count,
        s.next_seq, s.last_root, s.admission_move, s.delay_used,
        s.delay_until, s.variant, s.binding_sha256);
    fprintf(f, ",\"snapshot_v\":%d,\"program_id\":%d,\"phase\":%d,"
        "\"origin_w_live\":%d,\"origin_f_live\":%d,\"identity_unsafe\":%d,"
        "\"termination_emitted\":%d,\"replay_cursor\":%lu,\"source_length\":%lu",
        s.snapshot_v, s.program_id, s.phase, s.origin_w_live, s.origin_f_live,
        s.identity_unsafe, s.termination_emitted, s.replay_cursor,
        (unsigned long)s.source_length);
    fprintf(f, ",\"journal_state\":%d,\"journal_bytes\":%lu,"
        "\"journal_sha256\":\"%s\",\"capture_incomplete\":%d}\n",
        s.journal_state, s.journal_bytes, s.journal_sha256, s.capture_incomplete);
    assert(!fclose(f));
    {
        struct chaos_next_use_capture_status c;
        chaos_next_use_capture_status(&c);
        f = file("capture.json", "w");
        fprintf(f, "{\"sink_connected\":%d,\"incomplete\":%d,"
            "\"transaction_open\":%d,\"acknowledged_cursor\":%lu}\n",
            c.sink_connected, c.incomplete, c.transaction_open, c.acknowledged_cursor);
        assert(!fclose(f));
    }
    if (valid && s.w_runtime == CHAOS_W_RUNTIME_WINDOW_ENDED
        && access("window-ended.json", F_OK) != 0) {
        /* Read-only first observation, including the pre-clock-advance sample. */
        f = file("window-ended.json", "w");
        fprintf(f, "{\"monstermoves\":%ld,\"activation_monstermoves\":%ld}\n",
            monstermoves, s.activation_monstermoves);
        assert(!fclose(f));
    }
    f = file("identity.json", "w");
    fprintf(f, "{\"birthday\":%ld,\"game_token\":%ld}\n",
        (long)u.ubirthday, u.chaos_game_token);
    assert(!fclose(f));
}

int __wrap_chaos_next_use_save(int fd)
{
    int result, drop = access("drop-program-on-save", F_OK) == 0;
    if (access("lose-witness-on-save", F_OK) == 0) {
        /* TEST ONLY, explicit middle full Save. Do not import into the live
         * runtime: serialize a copied VALID snapshot via the real codec. */
        struct chaos_next_use_snapshot before, copy, after;
        int present = chaos_next_use_save_status();
        FILE *f;
        assert(!drop && present == CHAOS_SNAPSHOT_VALID);
        memset(&before, 0, sizeof before);
        assert(chaos_next_use_snapshot_export(&before));
        assert(before.witnessed == 1 && before.attention_claimed == 1);
        copy = before;
        copy.witnessed = 0;
        assert(chaos_next_use_snapshot_validate(&copy));
        bwrite(fd, (genericptr_t)"NUS1", 4);
        bwrite(fd, (genericptr_t)&present, sizeof present);
        result = chaos_next_use_snapshot_write(fd, &copy);
        memset(&after, 0, sizeof after);
        assert(chaos_next_use_snapshot_export(&after));
        assert(!memcmp(&before, &after, sizeof before));
        copy.witnessed = before.witnessed;
        assert(!memcmp(&before, &copy, sizeof before));
        f = file("native.jsonl", "a");
        fprintf(f, "{\"kind\":\"witness-loss-save\",\"serializer_result\":%d,"
            "\"runtime_witnessed\":%d,\"saved_witnessed\":0,\"source_sha256\":\"%s\"}\n",
            result, after.witnessed, after.source_sha256);
        assert(!fclose(f));
        return result;
    }
    if (drop) {
        /* TEST ONLY: player state/latch has already been serialized by save.c.
         * Drop only the runtime, then let the REAL serializer write ABSENT. */
        chaos_next_use_runtime_reset();
    }
    result = __real_chaos_next_use_save(fd);
    if (drop) {
        FILE *f = file("native.jsonl", "a");
        fprintf(f, "{\"kind\":\"drop-program-save\",\"serializer_result\":%d,"
            "\"spent\":%d,\"attempted\":%d}\n",
            result, u.chaos.spent, chaos_next_use_safe_attempted());
        assert(!fclose(f));
    }
    return result;
}

/* This fault is deliberately NOT serialized missing-world evidence: dorecover
 * has restored the full world, and allmain is about to call chaos_start then
 * its first chaos_observe. Remove the actual resident through native lifecycle
 * functions; optionally allocate a different native pet (never assign m_id).
 * No runtime, capability, witness, clock or accounting setter is called. */
static void restore_target_fault(void)
{
    int missing = access("armed-missing-target", F_OK) == 0;
    int replacement = access("armed-replacement-target", F_OK) == 0;
    struct chaos_next_use_snapshot before, after;
    struct monst *pet, *old = NULL;
    long oldmoves = moves, oldmonstermoves = monstermoves;
    int spent = u.chaos.spent, count = 0, eligible = 0;
    unsigned original_id;
    FILE *f;
    if (!missing && !replacement) return;
    assert(missing != replacement && wizard);
    memset(&before, 0, sizeof before);
    memset(&after, 0, sizeof after);
    assert(chaos_next_use_snapshot_export(&before));
    assert(before.phase == CHAOS_ATTEMPT_COMMITTED);
    assert(before.w_runtime == CHAOS_W_RUNTIME_ARMED);
    assert(!before.witnessed && !before.attention_claimed);
    assert(monstermoves < before.activation_monstermoves + 5);
    for (pet = fmon; pet; pet = pet->nmon)
        if (!DEADMONSTER(pet)) { ++count; old = pet; }
    assert(count == 1 && old && old->m_id == before.armed_m_id);
    original_id = old->m_id; /* measured world ID, not substituted snapshot ID */
    mongone(old);
    dmonsfree();
    assert(!fmon);
    if (replacement) {
        int glyph;
        pet = makemon(&mons[PM_LITTLE_DOG], u.ux + 2, u.uy, MM_EDOG);
        assert(pet);
        initedog(pet);
        EDOG(pet)->hungrytime = monstermoves + 10000;
        assert(pet->m_id && pet->m_id != original_id);
        vision_recalc(0);
        docrt();
        flush_screen(1);
        glyph = glyph_at(pet->mx, pet->my);
        /* Readonly predicates from chaos_next_use_whistle_completed; do not
         * invoke another whistle/callback to prove replacement eligibility. */
        eligible = !DEADMONSTER(pet) && canseemon(pet) && !Hallucination
            && !u.uswallow && isok(pet->mx, pet->my) && glyph_is_monster(glyph)
            && glyph_to_mon(glyph) == PM_LITTLE_DOG
            && tty_snapshot_projectable(pet->mx, pet->my, glyph)
            && pet->mtyp == PM_LITTLE_DOG && pet->mtame && get_mx(pet, MX_EDOG)
            && pet != u.usteed && pet != u.urider && !pet->mleashed
            && !get_mx(pet, MX_ESUM) && !mon_attacktype(pet, AT_EXPL)
            && !Conflict && !pet->mberserk;
        assert(eligible);
    }
    assert(chaos_next_use_snapshot_export(&after));
    assert(!memcmp(&before, &after, sizeof before));
    assert(moves == oldmoves && monstermoves == oldmonstermoves && u.chaos.spent == spent);
    f = file("restore-target.json", "w");
    fprintf(f, "{\"boundary\":\"after-world-restore-before-chaos-start\","
        "\"captured_id\":%u,\"before_ids\":[%u],\"after_ids\":[",
        before.armed_m_id, original_id);
    count = 0;
    for (pet = fmon; pet; pet = pet->nmon)
        if (!DEADMONSTER(pet)) {
            assert(pet->m_id != original_id);
            fprintf(f, "%s%u", count++ ? "," : "", pet->m_id);
        }
    assert(count == replacement);
    fprintf(f, "],\"eligible_replacement\":%d,\"runtime_unchanged\":1,"
        "\"moves\":%ld,\"monstermoves\":%ld,\"spent\":%d,"
        "\"game_token\":%ld,\"level_token\":%ld}\n",
        eligible, moves, monstermoves, spent, u.chaos_game_token,
        chaos_next_use_pack_level(u.uz.dnum, u.uz.dlevel));
    assert(!fclose(f));
}

void __wrap_chaos_start(void)
{
    int fresh = u.chaos.version == 0;
    if (!fresh) restore_target_fault();
    __real_chaos_start();
    started = 1;
    test_rng_control();
    rng_observation("startup-control-complete");
    if (fresh) {
        struct monst *pet;
        struct obj *whistle;
        FILE *f;
        int x, y;
        assert(wizard);
        /* Fixed, clean lit room and one little dog: controlled preconditions,
         * not claimed natural discovery. Never repeated on restoration. */
        for (pet = fmon; pet; pet = pet->nmon) mongone(pet);
        dmonsfree();
        for (x = 35; x <= 45; ++x)
            for (y = 5; y <= 15; ++y) {
                struct trap *t = t_at(x, y);
                if (t) deltrap(t);
                while (level.objects[x][y]) delobj(level.objects[x][y]);
                levl[x][y].typ = ROOM;
                levl[x][y].lit = 1;
            }
        teleds(40, 10, FALSE);
        levl[u.ux][u.uy].typ = FOUNTAIN;
        levl[u.ux][u.uy].blessedftn = 0;
        level.flags.nfountains++;
        pet = makemon(&mons[PM_LITTLE_DOG], 42, 10, MM_EDOG);
        assert(pet);
        initedog(pet);
        EDOG(pet)->hungrytime = monstermoves + 10000;
        whistle = addinv(mksobj(WHISTLE, NO_MKOBJ_FLAGS));
        assert(whistle);
        vision_reset();
        vision_recalc(0);
        docrt();
        flush_screen(1);
        f = file("fixture.json", "w");
        fprintf(f, "{\"ordinary_play\":false,\"letter\":\"%c\",\"pet_id\":%u,"
            "\"clock\":1700000000,\"preload_srandom_seed\":7654321,"
            "\"origin_rng_warmup\":3,\"effect_rng_warmup\":0}\n",
            whistle->invlet, pet->m_id);
        assert(!fclose(f));
    }
    state();
}

void __wrap_chaos_observe(void)
{
    __real_chaos_observe();
    state();
}

void __wrap_rhack(char *command)
{
    /* chaos_observe is before native clock advancement; sample again at the
     * actual command boundary. tty_nhgetch has same-object callers that the
     * linker cannot wrap and is not a reliable command-boundary sampler. */
    state();
    __real_rhack(command);
    state();
}

int __wrap_dog_move(struct monst *pet, int after, struct chaos_whistle_witness *w)
{
    if (chaos_next_use_whistle_decision_ready(pet->m_id)) {
        int ox = pet->mx, oy = pet->my;
        /* Explicit geometry fixture at the eligible native decision. The real
         * dog_move must classify, move and deliver; this move is BEFORE its
         * witness baseline, not a claimed manifestation. */
        remove_monster(ox, oy);
        place_monster(pet, u.ux + 2, u.uy);
        newsym(ox, oy);
        newsym(pet->mx, pet->my);
        vision_recalc(0);
        docrt();
        flush_screen(1);
        test_rng_reset();
        rng_observation("dog-reset");
        if (access("bypass-w-native", F_OK) == 0) {
            /* TEST ONLY: inhibit the actual eligible native decision, never
             * assign a witness or claim this setup displacement as an effect. */
            struct chaos_next_use_snapshot s;
            int bx = pet->mx, by = pet->my;
            FILE *f;
            memset(&s, 0, sizeof s);
            assert(chaos_next_use_snapshot_export(&s));
            assert(s.callback_w == 1 && u.chaos.spent == 2);
            f = file("physical.jsonl", "a");
            fprintf(f, "{\"kind\":\"W-bypass\",\"before\":[%d,%d],"
                "\"after\":[%d,%d],\"witnessed\":%d,\"spent\":%d,"
                "\"monstermoves\":%ld}\n", bx, by, pet->mx, pet->my,
                s.witnessed, u.chaos.spent, monstermoves);
            assert(!fclose(f));
            return 0;
        }
    }
    return __real_dog_move(pet, after, w);
}

static void unsupported_message(winid window, int attr, const char *text)
{
    (void)window; (void)attr; (void)text;
}

boolean __wrap_chaos_whistle_attention_message(struct chaos_whistle_witness *w)
{
    void (*saved)(winid, int, const char *) = windowprocs.win_putstr;
    boolean result;
    /* Exercise the real unsupported-message route, without setting a witness
     * field. Restore presentation immediately; F and later UI remain native. */
    if (access("deny-w-message", F_OK) == 0)
        windowprocs.win_putstr = unsupported_message;
    result = __real_chaos_whistle_attention_message(w);
    windowprocs.win_putstr = saved;
    return result;
}

void __wrap_chaos_whistle_witness_finalize(struct monst *pet, struct chaos_whistle_witness *w)
{
    __real_chaos_whistle_witness_finalize(pet, w);
    if (w && w->active) {
        FILE *f = file("native.jsonl", "a");
        fprintf(f, "{\"kind\":\"witness\",\"displaced\":%d,\"delivered\":%d,"
            "\"classifier\":%d,\"root\":%ld,\"notice\":%ld,\"pet_id\":%u,"
            "\"monstermoves\":%ld}\n",
            w->displaced, w->manifestation_delivered, w->classifier_ok,
            w->root, w->notice_seq, pet->m_id, monstermoves);
        assert(!fclose(f));
        if (access("detailed-native", F_OK) == 0) {
            struct chaos_next_use_snapshot s;
            memset(&s, 0, sizeof s);
            assert(chaos_next_use_snapshot_export(&s));
            f = file("physical.jsonl", "a");
            fprintf(f, "{\"kind\":\"W\",\"before\":[%d,%d],\"after\":[%d,%d],"
                "\"actual\":[%d,%d],\"delivered\":%d,\"witnessed\":%d,"
                "\"displaced\":%d,\"root\":%ld,\"notice\":%ld,\"event_seq\":%ld,"
                "\"pet_id\":%u,\"moves\":%ld,\"monstermoves\":%ld,"
                "\"pre_glyph\":%d,\"post_glyph\":%d,\"rng_count\":%d,\"reset_ordinal\":%d}\n",
                w->oldx, w->oldy, w->newx, w->newy, pet->mx, pet->my,
                w->manifestation_delivered, s.witnessed, w->displaced,
                w->root, w->notice_seq, u.chaos.seq, pet->m_id, moves, monstermoves,
                w->pre_glyph, w->post_glyph, reseed_count, reset_ordinal);
            assert(!fclose(f));
        }
    }
}

void __wrap_chaos_next_use_fountain_result(const struct chaos_fountain_token *token, int outcome)
{
    /* Record the real callback's token-origin root (not this action's root);
     * never synthesize a result. */
    fountain_outcome = outcome;
    fountain_root = token ? token->root : 0;
    __real_chaos_next_use_fountain_result(token, outcome);
}

void __wrap_drinkfountain(void)
{
    int hunger = u.uhunger, i;
    /* snapshot export intentionally refuses an in-flight F token; budget is
     * already committed by the real safe point before this command begins. */
    int admitted = u.chaos.spent != 0;
    FILE *f;
    /* Existing native_rng infrastructure; one declared stream, no seed search.
     * replay_clock pins srandom to 7654321. Its first fates are 11,14,17,8:
     * three native warmup draws give the origin refresh; zero gives effect 11.
     * Native drinkfountain computes the fate and owns all effects/results. */
    test_rng_reset();
    rng_observation("fountain-reset");
    if (!admitted) for (i = 0; i < 3; ++i) (void)rn2(30);
    fountain_outcome = -1;
    fountain_root = 0; /* Do not carry a previous callback's diagnostic root. */
    __real_drinkfountain();
    f = file("native.jsonl", "a");
    fprintf(f, "{\"kind\":\"fountain\",\"outcome\":%d,\"hunger_delta\":%d,"
        "\"rng_count\":%d}\n", fountain_outcome, u.uhunger - hunger, reseed_count);
    assert(!fclose(f));
    if (access("detailed-native", F_OK) == 0) {
        f = file("physical.jsonl", "a");
        fprintf(f, "{\"kind\":\"F\",\"hunger_before\":%d,\"hunger_after\":%d,"
            "\"hunger_delta\":%d,\"outcome\":%d,\"root\":%ld,\"event_seq\":%ld,"
            "\"moves\":%ld,\"monstermoves\":%ld,\"rng_count\":%d,\"reset_ordinal\":%d}\n",
            hunger, u.uhunger, u.uhunger - hunger, fountain_outcome,
            fountain_root, u.chaos.seq, moves, monstermoves, reseed_count, reset_ordinal);
        assert(!fclose(f));
    }
}

int test_native_save_layout(void);

int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--native-save-layout"))
        return test_native_save_layout();
    if (argc == 2 && strstr(argv[1], "negative-control")) {
        test_rng_negative_control(argv[1]);
        return 0;
    }
    return original_game_main(argc, argv);
}
