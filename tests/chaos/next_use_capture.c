/* Capture subscriber tests reuse admission helpers, not reconstructed records. */
#define main historical_replay_main
#include "next_use_replay.c"
#undef main
#include "chaos.h"
#include <assert.h>

static struct chaos_next_use_replay_input received;
static int calls, reject, tamper_publication, tampered;
static const char *validation_mode;
static int noncanonical = 2;

/* Rejection must preserve live state/carriers as well as the replay cursor:
 * the untouched original is applied immediately afterward by the subscriber. */
static void assert_blocked_unchanged(const struct chaos_next_use_replay_input *bad)
{
    struct chaos_next_use_snapshot before, after;
    struct chaos_next_use_capture_status status_before, status_after;
    struct chaos_next_use_runtime_private_record private_before[16];
    struct chaos_next_use_public_record public_before[1];
    int snapshot_status;
    size_t i, private_count = chaos_next_use_runtime_private_count();
    size_t public_count = chaos_next_use_runtime_public_count();
    assert(private_count <= 16 && public_count <= 1);
    /* Export fills values even when an in-flight transition is not saveable. */
    snapshot_status = chaos_next_use_snapshot_export(&before);
    memset(&status_before, 0, sizeof status_before);
    memset(&status_after, 0, sizeof status_after);
    chaos_next_use_capture_status(&status_before);
    for (i = 0; i < private_count; ++i)
        private_before[i] = *chaos_next_use_runtime_private_at(i);
    for (i = 0; i < public_count; ++i)
        public_before[i] = *chaos_next_use_runtime_public_at(i);
    assert(chaos_next_use_replay_record(bad) == CHAOS_REPLAY_BLOCKED_REPLAY);
    assert(chaos_next_use_snapshot_export(&after) == snapshot_status);
    chaos_next_use_capture_status(&status_after);
    assert(!memcmp(&before, &after, sizeof before));
    assert(!memcmp(&status_before, &status_after, sizeof status_before));
    assert(private_count == chaos_next_use_runtime_private_count());
    assert(public_count == chaos_next_use_runtime_public_count());
    for (i = 0; i < private_count; ++i)
        assert(!memcmp(&private_before[i], chaos_next_use_runtime_private_at(i),
                       sizeof private_before[i]));
    for (i = 0; i < public_count; ++i)
        assert(!memcmp(&public_before[i], chaos_next_use_runtime_public_at(i),
                       sizeof public_before[i]));
}

static void validate_tampering(const struct chaos_next_use_replay_input *record)
{
    struct chaos_next_use_replay_input bad = *record;
    if (!validation_mode || tampered) return;
    if (!strncmp(validation_mode, "downgrade_", 10)
        && record->operation == CHAOS_REPLAY_ACTION) {
        assert(record->expected_result == 1 && record->post.pending_w_capture == 1);
        assert(record->root == record->expected_last_root);
        if (!strcmp(validation_mode, "downgrade_post"))
            bad.post.pending_w_capture = 0;
        else if (!strcmp(validation_mode, "downgrade_result"))
            bad.expected_result = 0;
        if (strcmp(validation_mode, "downgrade_version"))
            assert_blocked_unchanged(&bad); /* v1 already catches the corruption. */
        bad.replay_input_v = 0;
    } else if (!strcmp(validation_mode, "bool_attention")
               && record->operation == CHAOS_REPLAY_W_DECISION) {
        assert(record->expected_attention == 1);
        bad.expected_attention = noncanonical;
    } else if (!strncmp(validation_mode, "bool_token_", 11)
               && record->operation == CHAOS_REPLAY_F_RESULT) {
        assert(record->expected_token.active == 1
               && record->expected_token.consumed == 1
               && record->expected_token.remap == 1);
        if (!strcmp(validation_mode, "bool_token_active"))
            bad.expected_token.active = noncanonical;
        else if (!strcmp(validation_mode, "bool_token_consumed"))
            bad.expected_token.consumed = noncanonical;
        else
            bad.expected_token.remap = noncanonical;
    } else if (!strncmp(validation_mode, "bool_boundary_", 14)
               && record->operation == CHAOS_REPLAY_BOUNDARY) {
        assert(record->origin_w_live == 1 && record->origin_f_live == 1);
        if (!strcmp(validation_mode, "bool_boundary_w"))
            bad.origin_w_live = noncanonical;
        else
            bad.origin_f_live = noncanonical;
    } else return;
    assert_blocked_unchanged(&bad);
    ++tampered;
}

static int sink(void *opaque, const struct chaos_next_use_replay_input *record)
{
    struct chaos_next_use_capture_status status;
    struct chaos_next_use_replay_input bad;
    assert(opaque == &calls);
    assert(chaos_next_use_save_status() == CHAOS_SNAPSHOT_ERROR);
    {
        FILE *fp = tmpfile();
        char kept[4];
        assert(fp);
        assert(write(fileno(fp), "keep", 4) == 4);
        rewind(fp);
        assert(!chaos_next_use_save(fileno(fp)));
        assert(read(fileno(fp), kept, 4) == 4 && !memcmp(kept, "keep", 4));
        fclose(fp);
    }
    ++calls;
    received = *record;
    chaos_next_use_capture_status(&status);
    assert(status.acknowledged_cursor + 1 == record->cursor);
    assert(record->replay_input_v == CHAOS_NEXT_USE_REPLAY_INPUT_V);
    if (reject) return 0;
    if (record->operation > CHAOS_REPLAY_EXPIRE) {
        /* v0 predates these operations; it must not bypass v1 poststate checks. */
        bad = *record;
        bad.replay_input_v = 0;
        bad.root = record->expected_last_root;
        assert(chaos_next_use_replay_record(&bad) == CHAOS_REPLAY_BLOCKED_REPLAY);
    }
    if (tamper_publication && record->operation == CHAOS_REPLAY_W_MANIFEST) {
        bad = *record;
        bad.published = !record->published;
        assert(chaos_next_use_replay_record(&bad) == CHAOS_REPLAY_BLOCKED_REPLAY);
    }
    validate_tampering(record);
    assert(chaos_next_use_replay_record(record) == CHAOS_REPLAY_APPLIED);
    assert_blocked_unchanged(record); /* Duplicate cannot advance either runtime. */
    return 1;
}

static const char w_origin[] =
    "{\"end_seq\":12,\"fact\":\"ordinary_whistle\",\"family\":\"W\","
    "\"level_dlevel\":1,\"level_dnum\":0,\"move\":10,\"notice_seq\":11,"
    "\"root\":10,\"run\":\"0000000000000000000000000000000000000000000000000000000000000000\"}";
static const char f_origin[] =
    "{\"end_seq\":22,\"fact\":\"water_refreshed\",\"family\":\"F\","
    "\"level_dlevel\":1,\"level_dnum\":0,\"move\":10,\"notice_seq\":21,"
    "\"root\":20,\"run\":\"0000000000000000000000000000000000000000000000000000000000000000\"}";
static const char attention_lua[] =
    "return {on_action=function(c) return {next_use_intent_v=2,op=[[whistle_attention]],state=1} end}";

static void install_w(void)
{
    char origins[1024];
    chaos_next_use_runtime_reset();
    calls = reject = tamper_publication = 0;
    monstermoves = 40;
    snprintf(origins, sizeof origins, "%s", w_origin);
    assert(install_ops(attention_lua, "[\"W\"]", origins, 1,
                       "next-use-v2-W", 10, 0, 1, 0));
    chaos_next_use_capture_set_sink(sink, &calls);
}

int main(int argc, char **argv)
{
    struct chaos_next_use_capture_status status;
    struct chaos_next_use_snapshot snap;
    struct chaos_fountain_token token;
    struct chaos_whistle_witness witness;
    char origins[1024];
    int before;
    const char *mode = argc > 1 ? argv[1] : "action";
    validation_mode = mode;
    if (argc > 2) noncanonical = atoi(argv[2]);
    install_w();
    if (!strcmp(mode, "rejected_token") || !strcmp(mode, "invalid_root_token")) {
        struct chaos_fountain_token sentinel;
        memset(&token, 0xa5, sizeof token);
        sentinel = token;
        assert(!chaos_next_use_on_action(
            !strcmp(mode, "rejected_token") ? CHAOS_NEXT_USE_FAMILY_F : CHAOS_NEXT_USE_FAMILY_W,
            !strcmp(mode, "rejected_token") ? 30 : 0, &token));
        /* Rejected preflight leaves the caller's OUT storage untouched. The
         * trace must neither treat it as input nor expose its stale bytes. */
        assert(!memcmp(&token, &sentinel, sizeof token));
        assert(calls == 1 && received.token_present && !received.expected_result);
        assert(!received.expected_token.root && !received.expected_token.active
               && !received.expected_token.remap && !received.expected_token.consumed);
        chaos_next_use_capture_status(&status);
        assert(!status.incomplete && status.acknowledged_cursor == 1);
    } else if (!strcmp(mode, "nested")) {
        monstermoves = 140;
        assert(!chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 99, NULL));
        assert(calls == 1 && received.operation == CHAOS_REPLAY_ACTION);
        assert(received.root == 99 && received.expected_last_root == 0);
        assert(received.private_count == 1);
    } else if (!strcmp(mode, "journal_missing") || !strcmp(mode, "journal_reject")) {
        static const char anchor[] =
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        chaos_next_use_capture_journal_ack(CHAOS_JOURNAL_OPEN, 1234, anchor);
        if (!strcmp(mode, "journal_missing")) chaos_next_use_capture_set_sink(NULL, NULL);
        else reject = 1;
        assert(chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 30, NULL));
        chaos_next_use_capture_whistle(30, 7, 40);
        assert(chaos_next_use_save_status() == CHAOS_SNAPSHOT_VALID);
        assert(chaos_next_use_snapshot_export(&snap));
        assert(snap.journal_state == CHAOS_JOURNAL_FAILED && snap.capture_incomplete);
        assert(snap.replay_cursor == 0 && snap.journal_bytes == 1234);
        assert(!strcmp(snap.journal_sha256, anchor));
    } else if (!strcmp(mode, "failure") || !strcmp(mode, "missing")) {
        if (!strcmp(mode, "missing")) chaos_next_use_capture_set_sink(NULL, NULL);
        else reject = 1;
        assert(chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 30, NULL));
        chaos_next_use_capture_status(&status);
        assert(status.incomplete && status.acknowledged_cursor == 0);
        reject = 0;
        chaos_next_use_capture_set_sink(sink, &calls);
        chaos_next_use_capture_whistle(30, 7, 40);
        chaos_next_use_capture_status(&status);
        assert(status.incomplete && status.acknowledged_cursor == 0);
        assert(chaos_next_use_save_status() == CHAOS_SNAPSHOT_VALID);
        assert(chaos_next_use_snapshot_export(&snap));
        assert(snap.capture_incomplete && snap.journal_state == CHAOS_JOURNAL_NONE);
        assert(chaos_next_use_snapshot_import(&snap));
        chaos_next_use_capture_status(&status);
        assert(status.incomplete && !status.sink_connected);
    } else if (!strcmp(mode, "fountain") || !strncmp(mode, "bool_token_", 11)) {
        chaos_next_use_runtime_reset();
        snprintf(origins, sizeof origins, "%s", f_origin);
        assert(install_ops(fountain_lua, "[\"F\"]", origins, 1,
                           "next-use-v2-F", 0, 20, 0, 1));
        memset(&token, 0xa5, sizeof token);
        assert(chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_F, 30, &token));
        assert(received.expected_token.active && calls == 1);
        assert(received.token_present && received.expected_result);
        assert(received.expected_token.root == token.root && token.root == 30);
        assert(received.expected_token.remap == token.remap && token.remap == 1);
        assert(!received.expected_token.consumed && !token.consumed);
        token.consumed = 1;
        chaos_next_use_fountain_result(&token, CHAOS_FOUNTAIN_REMAPPED);
        assert(calls == 2 && received.expected_token.consumed);
        assert(received.fountain_outcome == CHAOS_FOUNTAIN_REMAPPED);
        assert(received.slot_f == CHAOS_SLOT_F_CONSUMED_APPLIED);
    } else {
        if (!strncmp(mode, "bool_boundary_", 14)) {
            chaos_next_use_runtime_reset();
            snprintf(origins, sizeof origins, "%s,%s", w_origin, f_origin);
            assert(install_ops(attention_lua, "[\"W\",\"F\"]", origins, 2,
                               "next-use-v2-WF", 10, 20, 1, 1));
        }
        assert(chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 30, NULL));
        assert(calls == 1 && received.private_count == 1);
        assert(received.root == 30 && received.expected_last_root == 30);
        assert(strlen(received.private_records[0].data.intent.context_sha256) == 64);
        assert(strlen(received.private_records[0].data.intent.intent_sha256) == 64);
        /* Activation argument differs from current clock: neither is overloaded. */
        monstermoves = 41;
        chaos_next_use_capture_whistle(30, 7, 40);
        assert(calls == 2 && received.activation_move == 40 && received.at_move == 41);
        if (!strcmp(mode, "bool_attention")) {
            monstermoves = 45;
            assert(chaos_next_use_whistle_attention(7, 99));
        } else if (!strncmp(mode, "bool_boundary_", 14)) {
            chaos_next_use_runtime_boundary(1, 1, 1, 1, 1, 0);
        } else if (!strcmp(mode, "identity")) {
            chaos_next_use_mark_identity_unsafe();
            assert(received.operation == CHAOS_REPLAY_IDENTITY_MARK);
            monstermoves = 45;
            assert(!chaos_next_use_whistle_attention(7, 99));
            assert(calls == 4 && received.w_runtime == CHAOS_W_RUNTIME_IDENTITY_UNSAFE);
        } else if (!strcmp(mode, "no_root")) {
            monstermoves = 45;
            chaos_next_use_whistle_no_root(7);
            assert(calls == 3 && received.operation == CHAOS_REPLAY_W_NO_ROOT);
        } else if (!strcmp(mode, "ready_expiry")) {
            monstermoves = 50;
            assert(!chaos_next_use_whistle_decision_ready(7));
            assert(calls == 3 && received.private_count == 2);
        } else if (!strncmp(mode, "manifest", 8)) {
            monstermoves = 45;
            assert(chaos_next_use_whistle_attention(7, 99));
            before = calls;
            assert(chaos_next_use_manifestation_begin(7, 100));
            chaos_next_use_manifestation_notice(100, 101);
            assert(calls == before);
            memset(&witness, 0, sizeof witness);
            witness.root = 100; witness.notice_seq = 101;
            witness.manifestation_delivered = witness.displaced = witness.pre_public = TRUE;
            tamper_publication = 1;
            chaos_next_use_manifestation_complete(&witness, 102,
                                                  !strcmp(mode, "manifest_published"));
            assert(calls == before + 1);
            assert(received.published == !strcmp(mode, "manifest_published"));
            assert(received.public_count == received.published);
            assert(received.expected_last_root == (received.published ? 100 : 99));
        }
        assert(chaos_next_use_snapshot_export(&snap));
        chaos_next_use_capture_status(&status);
        assert(!status.incomplete && !status.transaction_open);
        assert(snap.replay_cursor == (unsigned long)calls);
    }
    if (!strncmp(mode, "downgrade_", 10) || !strncmp(mode, "bool_", 5))
        assert(tampered == 1);
    puts("capture ok");
    return 0;
}
