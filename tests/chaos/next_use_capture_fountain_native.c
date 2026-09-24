/* Actual drinkfountain capture. Reuse setup/admission, never seed-search main. */
#define main historical_fountain_main
#include "next_use_fountain.c"
#undef main

static int transitions, actions, results, identities, tamper_rejected;
static int native_outcome, native_consumed;
static long action_root;
static char context_identity[65], intent_identity[65];

static int fountain_sink(void *opaque, const struct chaos_next_use_replay_input *r)
{
    struct chaos_next_use_capture_status status;
    struct chaos_next_use_replay_input bad;
    int i, rng_before = reseed_count, hunger_before = u.uhunger;
    assert(opaque == &transitions);
    assert(r->replay_input_v == CHAOS_NEXT_USE_REPLAY_INPUT_V);
    assert(strlen(r->source_sha256) == 64);
    chaos_next_use_capture_status(&status);
    assert(status.transaction_open && !status.incomplete);
    assert(status.acknowledged_cursor == (unsigned long)transitions);
    assert(r->cursor == status.acknowledged_cursor + 1);
    if (r->operation == CHAOS_REPLAY_ACTION) {
        ++actions;
        assert(r->family == CHAOS_NEXT_USE_FAMILY_F);
        assert(r->token_present && r->expected_result);
        assert(r->expected_token.active && r->expected_token.remap);
        assert(!r->expected_token.consumed);
        assert(r->root == r->expected_token.root && r->root == 10);
        action_root = r->root;
    } else {
        assert(r->operation == CHAOS_REPLAY_F_RESULT);
        ++results;
        assert(r->token_present && r->expected_token.root == action_root);
        assert(r->expected_token.active && r->expected_token.remap);
        assert(r->expected_token.consumed);
        assert(r->fountain_outcome == CHAOS_FOUNTAIN_REMAPPED);
        assert(r->slot_f == CHAOS_SLOT_F_CONSUMED_APPLIED);
        assert(u.uhunger == 1004);
        native_outcome = r->fountain_outcome;
        native_consumed = r->expected_token.consumed;
    }
    for (i = 0; i < r->private_count; ++i) {
        const struct chaos_next_use_runtime_private_record *p = &r->private_records[i];
        assert(!strcmp(p->source_sha256, r->source_sha256));
        if (p->kind != CHAOS_RUNTIME_PRIVATE_INTENT) continue;
        ++identities;
        assert(p->data.intent.root == action_root);
        assert(p->data.intent.trigger == CHAOS_NEXT_USE_FAMILY_F);
        assert(p->data.intent.intent_present && p->data.intent.intent_sha256_present);
        assert(p->data.intent.intent.op == CHAOS_NEXT_USE_INTENT_FOUNTAIN_REFRESH);
        assert(strlen(p->data.intent.context_sha256) == 64);
        assert(strlen(p->data.intent.intent_sha256) == 64);
        strcpy(context_identity, p->data.intent.context_sha256);
        strcpy(intent_identity, p->data.intent.intent_sha256);
        bad = *r;
        bad.private_records[i].data.intent.context_sha256[0] =
            context_identity[0] == '0' ? '1' : '0';
        assert(chaos_next_use_replay_record(&bad) == CHAOS_REPLAY_BLOCKED_REPLAY);
        ++tamper_rejected;
        bad = *r;
        bad.private_records[i].data.intent.intent_sha256[0] =
            intent_identity[0] == '0' ? '1' : '0';
        assert(chaos_next_use_replay_record(&bad) == CHAOS_REPLAY_BLOCKED_REPLAY);
        ++tamper_rejected;
    }
    assert(chaos_next_use_replay_record(r) == CHAOS_REPLAY_APPLIED);
    assert(reseed_count == rng_before && u.uhunger == hunger_before);
    ++transitions;
    return 1;
}

int main(int argc, char **argv)
{
    struct chaos_fountain_token token;
    struct chaos_next_use_capture_status status;
    int telegraphs = 0, hunger_before;
    long completed, obs;
    FILE *out;
    const char *dirpath;
    if (argc != 2) return 2;
    dirpath = argv[1];
    setup_tty(&argc, argv);
    setup_level();
    setenv("NYARLATHACK_OBSERVATIONS", "1", 1);
    setenv("NYARLATHACK_RUN_DIR", dirpath, 1);
    chaos_start();
    assert(admit_f(dirpath, &telegraphs) == 1 && telegraphs == 1);
    chaos_next_use_capture_set_sink(fountain_sink, &transitions);
    /* Existing native_rng seed 123: first rnd(30) is 14 (remappable).
     * Reset exactly once; drinkfountain, not this driver, draws the fate. */
    test_rng_reset();
    hunger_before = u.uhunger;
    assert(hunger_before == 1000);
    completed = chaos_next_use_fountain_completed_root();
    assert(completed == 10);
    assert(chaos_next_use_fountain_contact(completed, &token));
    obs = chaos_observation_begin(CHAOS_OBS_OP_FOUNTAIN_DRINK);
    chaos_bind_drinkfountain_token(&token);
    drinkfountain();
    chaos_bind_drinkfountain_token(0);
    chaos_observation_end(obs);
    assert(u.uhunger == 1004);
    assert(!token.active && !token.root && !token.remap && !token.consumed);
    assert(chaos_next_use_fountain_completed_root() == 0);
    chaos_next_use_capture_status(&status);
    assert(!status.incomplete && !status.transaction_open);
    assert(transitions == 2 && actions == 1 && results == 1 && identities == 1);
    assert(status.acknowledged_cursor == (unsigned long)transitions);
    out = fopen("capture.json", "w");
    assert(out);
    fprintf(out, "{\"transitions\":%d,\"actions\":%d,\"results\":%d,"
                 "\"hunger_before\":%d,\"hunger_after\":%d,\"outcome\":%d,"
                 "\"consumed\":%d,\"cursor\":%lu,\"tamper_rejected\":%d,"
                 "\"context_sha256\":\"%s\",\"intent_sha256\":\"%s\"}\n",
            transitions, actions, results, hunger_before, u.uhunger,
            native_outcome, native_consumed, status.acknowledged_cursor,
            tamper_rejected, context_identity, intent_identity);
    fclose(out);
    return 0;
}
