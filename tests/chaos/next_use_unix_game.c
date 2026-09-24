/* NGPL. Controlled wizard fixture, NOT ordinary play or #66 acceptance.
 * Real Unix main, commands, turn loop, dog_move, fountain, tty and save/restore.
 * No runtime imports, fake reads, manual witnesses or outcome assignments.
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
static int started, fountain_outcome;

static FILE *file(const char *name, const char *mode)
{
    FILE *f = fopen(name, mode);
    assert(f);
    return f;
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
        "\"termination_emitted\":%d,\"replay_cursor\":%lu,\"source_length\":%lu}\n",
        s.snapshot_v, s.program_id, s.phase, s.origin_w_live, s.origin_f_live,
        s.identity_unsafe, s.termination_emitted, s.replay_cursor,
        (unsigned long)s.source_length);
    assert(!fclose(f));
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

void __wrap_chaos_start(void)
{
    int fresh = u.chaos.version == 0;
    __real_chaos_start();
    started = 1;
    test_rng_control();
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
    }
}

void __wrap_chaos_next_use_fountain_result(const struct chaos_fountain_token *token, int outcome)
{
    /* Record the real fountain callback; never synthesize its result. */
    fountain_outcome = outcome;
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
    if (!admitted) for (i = 0; i < 3; ++i) (void)rn2(30);
    fountain_outcome = -1;
    __real_drinkfountain();
    f = file("native.jsonl", "a");
    fprintf(f, "{\"kind\":\"fountain\",\"outcome\":%d,\"hunger_delta\":%d,"
        "\"rng_count\":%d}\n", fountain_outcome, u.uhunger - hunger, reseed_count);
    assert(!fclose(f));
}

int main(int argc, char **argv)
{
    if (argc == 2 && strstr(argv[1], "negative-control")) {
        test_rng_negative_control(argv[1]);
        return 0;
    }
    return original_game_main(argc, argv);
}
