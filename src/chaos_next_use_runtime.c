/* NetHack General Public License. Unsaved next-use runtime/replay state. */
#include "hack.h"
#include "chaos.h"
#include "chaos_next_use_runtime.h"
#include "chaos_lua.h"

#include <stdio.h>
#include <string.h>
#include <limits.h>
#include <stdint.h>
#include <unistd.h>

#define CHAOS_RUNTIME_PRIVATE_MAX 16
#define CHAOS_RUNTIME_PUBLIC_MAX 1
#define CHAOS_NEXT_USE_ORDINARY_CONTINUE 0
#define CHAOS_NEXT_USE_EFFECT_READY 1

enum runtime_validation {
    RUNTIME_VALID = 0,
    RUNTIME_INVALID_SCHEMA,
    RUNTIME_WRONG_FAMILY,
    RUNTIME_SECOND_DELAY,
    RUNTIME_PROTECTED_FAILURE
};

enum runtime_termination_reason {
    RUNTIME_TERMINATION_COMPLETED = 1,
    RUNTIME_TERMINATION_LEVEL_DEPARTURE,
    RUNTIME_TERMINATION_ORIGIN_EVICTED,
    RUNTIME_TERMINATION_ORIGIN_EXPIRED,
    RUNTIME_TERMINATION_PROGRAM_EXPIRED,
    RUNTIME_TERMINATION_INVALID_CALLBACK,
    RUNTIME_TERMINATION_IDENTITY_UNSAFE
};

struct runtime_state {
    int phase;
    int slot_w, slot_f, w_runtime;
    int state, delay_used, callback_ordinal, program_id, program_expiry;
    int callback_w, callback_f;
    int admission_move, variant, whistle_count, fountain_count;
    int delay_until;
    int origin_w_live, origin_f_live;
    int next_seq, termination_emitted, defer_termination, identity_unsafe;
    int pending_w_capture, f_inflight, witnessed, attention_claimed;
    int manifest_success;
    int expected_manifest_root, expected_notice_seq, expected_end_seq;
    unsigned long replay_cursor;
    unsigned expected_manifest_m_id;
    unsigned armed_m_id;
    long activation_monstermoves, armed_root, pending_w_root, f_root;
    long run_token, level_token, current_run_token, current_level_token;
    long origin_w, origin_f;
    long origin_w_deadline, origin_f_deadline;
    long last_root;
    char source_sha256[65];
    char binding_sha256[65];
    char source[4097];
    size_t source_length;
    struct chaos_next_use_runtime_private_record private_records[CHAOS_RUNTIME_PRIVATE_MAX];
    int private_count;
    struct chaos_next_use_public_record public_records[CHAOS_RUNTIME_PUBLIC_MAX];
    int public_count;
};

static struct runtime_state live_runtime;
static struct runtime_state replay_runtime;
static struct runtime_state staged_runtime;
static int runtime_staging;
static struct runtime_state *runtime_current(void)
{
    return runtime_staging ? &staged_runtime : &live_runtime;
}
#define runtime (*runtime_current())
static int valid_hash_field(const char value[65]);
static void snapshot_values(struct chaos_next_use_snapshot *out);
static int snapshot_binding_hash(const struct chaos_next_use_snapshot *in, char out[65]);

static void copy_hash(char target[65], const char *source)
{
    size_t length = source ? strlen(source) : 0;
    memset(target, 0, 65);
    if (length == 64) memcpy(target, source, 64);
}

/* One borrowed carrier, never an event database. Staged replay is not capture. */
static struct chaos_next_use_replay_input capture_record;
static chaos_next_use_capture_sink capture_sink;
static void *capture_opaque;
static int capture_depth, capture_incomplete, capture_delivering;
static int capture_private_before, capture_public_before, capture_manifest_open;

void chaos_next_use_capture_set_sink(chaos_next_use_capture_sink sink, void *opaque)
{
    if (capture_depth || capture_delivering) {
        capture_incomplete = 1;
        return;
    }
    capture_sink = sink;
    capture_opaque = opaque;
}

void chaos_next_use_capture_fail(void)
{
    capture_incomplete = 1;
}

void chaos_next_use_capture_status(struct chaos_next_use_capture_status *out)
{
    if (!out) return;
    out->sink_connected = capture_sink != NULL;
    out->incomplete = capture_incomplete;
    out->transaction_open = capture_depth != 0 || capture_delivering;
    out->acknowledged_cursor = live_runtime.replay_cursor;
}

static void replay_post_values(struct chaos_next_use_replay_poststate *out,
                               const struct runtime_state *in)
{
    out->phase = in->phase;
    out->delay_used = in->delay_used;
    out->delay_until = in->delay_until;
    out->termination_emitted = in->termination_emitted;
    out->identity_unsafe = in->identity_unsafe;
    out->pending_w_capture = in->pending_w_capture;
    out->f_inflight = in->f_inflight;
    out->witnessed = in->witnessed;
    out->attention_claimed = in->attention_claimed;
    out->callback_w = in->callback_w;
    out->callback_f = in->callback_f;
    out->whistle_count = in->whistle_count;
    out->fountain_count = in->fountain_count;
    out->origin_w_live = in->origin_w_live;
    out->origin_f_live = in->origin_f_live;
    out->manifest_success = in->manifest_success;
    out->armed_m_id = in->armed_m_id;
    out->expected_manifest_m_id = in->expected_manifest_m_id;
    out->activation_monstermoves = in->activation_monstermoves;
    out->armed_root = in->armed_root;
    out->pending_w_root = in->pending_w_root;
    out->f_root = in->f_root;
    out->current_run_token = in->current_run_token;
    out->current_level_token = in->current_level_token;
    out->expected_manifest_root = in->expected_manifest_root;
    out->expected_notice_seq = in->expected_notice_seq;
    out->expected_end_seq = in->expected_end_seq;
}

static int replay_post_equal(const struct chaos_next_use_replay_poststate *out,
                             const struct runtime_state *in)
{
    return out->phase == in->phase
        && out->delay_used == in->delay_used
        && out->delay_until == in->delay_until
        && out->termination_emitted == in->termination_emitted
        && out->identity_unsafe == in->identity_unsafe
        && out->pending_w_capture == in->pending_w_capture
        && out->f_inflight == in->f_inflight
        && out->witnessed == in->witnessed
        && out->attention_claimed == in->attention_claimed
        && out->callback_w == in->callback_w
        && out->callback_f == in->callback_f
        && out->whistle_count == in->whistle_count
        && out->fountain_count == in->fountain_count
        && out->origin_w_live == in->origin_w_live
        && out->origin_f_live == in->origin_f_live
        && out->manifest_success == in->manifest_success
        && out->armed_m_id == in->armed_m_id
        && out->expected_manifest_m_id == in->expected_manifest_m_id
        && out->activation_monstermoves == in->activation_monstermoves
        && out->armed_root == in->armed_root
        && out->pending_w_root == in->pending_w_root
        && out->f_root == in->f_root
        && out->current_run_token == in->current_run_token
        && out->current_level_token == in->current_level_token
        && out->expected_manifest_root == in->expected_manifest_root
        && out->expected_notice_seq == in->expected_notice_seq
        && out->expected_end_seq == in->expected_end_seq;
}

/* Every wrapper pairs enter/leave, including nested ACTION -> boundary ->
 * expiry. Only the outer call owns arguments and emits; even zero-delta calls
 * retain ordering. Missing subscribers are trace gaps, not gameplay failures. */
static int capture_enter(int operation)
{
    if (runtime_staging) return 0;
    if (capture_delivering) {
        capture_incomplete = 1;
        return 0;
    }
    if (capture_depth) { ++capture_depth; return 1; }
    if (runtime.phase != CHAOS_ATTEMPT_COMMITTED || capture_incomplete) return 0;
    if (!capture_sink || live_runtime.replay_cursor >= INT32_MAX) {
        capture_incomplete = 1;
        return 0;
    }
    capture_depth = 1;
    memset(&capture_record, 0, sizeof capture_record);
    capture_record.replay_input_v = CHAOS_NEXT_USE_REPLAY_INPUT_V;
    capture_record.operation = operation;
    capture_record.at_move = monstermoves;
    copy_hash(capture_record.source_sha256, runtime.source_sha256);
    capture_record.cursor = runtime.replay_cursor + 1;
    capture_private_before = runtime.private_count;
    capture_public_before = runtime.public_count;
    return 1;
}

static void capture_leave(int entered)
{
    int i, acknowledged;
    if (!entered || --capture_depth) return;
    if (capture_incomplete) return;
    capture_record.expected_last_root = runtime.last_root;
    capture_record.callback_ordinal = runtime.callback_ordinal;
    capture_record.state = runtime.state;
    capture_record.seq = runtime.next_seq - 1;
    capture_record.slot_w = runtime.slot_w;
    capture_record.slot_f = runtime.slot_f;
    capture_record.w_runtime = runtime.w_runtime;
    replay_post_values(&capture_record.post, &live_runtime);
    capture_record.private_count = runtime.private_count - capture_private_before;
    capture_record.public_count = runtime.public_count - capture_public_before;
    if (capture_record.private_count < 0 || capture_record.private_count > 4
        || capture_record.public_count < 0 || capture_record.public_count > 1) {
        capture_incomplete = 1;
        return;
    }
    for (i = 0; i < capture_record.private_count; ++i)
        capture_record.private_records[i] = runtime.private_records[capture_private_before + i];
    for (i = 0; i < capture_record.public_count; ++i)
        capture_record.public_records[i] = runtime.public_records[capture_public_before + i];
    capture_delivering = 1;
    acknowledged = capture_sink(capture_opaque, &capture_record);
    capture_delivering = 0;
    if (acknowledged && !capture_incomplete)
        live_runtime.replay_cursor = capture_record.cursor;
    else
        capture_incomplete = 1;
}

static void chaos_next_use_sha256_hex(const unsigned char *data, size_t length,
                                      char digest[65])
{
    unsigned char raw[CHAOS_NEXT_USE_SHA256_BYTES];
    static const char hex[] = "0123456789abcdef";
    int index;
    memset(digest, 0, 65);
    if (chaos_next_use_sha256(data, length, raw) != CHAOS_NEXT_USE_OK)
        return;
    for (index = 0; index < CHAOS_NEXT_USE_SHA256_BYTES; ++index) {
        digest[index * 2] = hex[raw[index] >> 4];
        digest[index * 2 + 1] = hex[raw[index] & 15];
    }
}

static const char *runtime_intent_name(int op)
{
    switch (op) {
    case CHAOS_NEXT_USE_INTENT_QUIET: return "quiet";
    case CHAOS_NEXT_USE_INTENT_DELAY: return "delay";
    case CHAOS_NEXT_USE_INTENT_WHISTLE_ATTENTION: return "whistle_attention";
    case CHAOS_NEXT_USE_INTENT_FOUNTAIN_REFRESH: return "fountain_refresh";
    default: return NULL;
    }
}

static int hash_context(const struct chaos_next_use_context *context,
                        char digest[65])
{
    char canonical[512];
    int length;
    const char *own = context->own_witnessed ? "W" : "none";
    const char *trigger = context->trigger == CHAOS_NEXT_USE_FAMILY_W ? "W" : "F";
    length = snprintf(canonical, sizeof canonical,
        "{\"age\":%d,\"fountain_count\":%d,\"next_use_context_v\":2,"
        "\"own_witnessed\":\"%s\",\"source_sha256\":\"%s\","
        "\"state\":%d,\"trigger\":\"%s\",\"variant\":%d,"
        "\"whistle_count\":%d}",
        context->age, context->fountain_count, own,
        context->source_sha256, context->state, trigger,
        context->variant, context->whistle_count);
    if (length < 1 || (size_t) length >= sizeof canonical) return 0;
    chaos_next_use_sha256_hex((const unsigned char *) canonical,
                              (size_t) length, digest);
    return 1;
}

static const char chaos_next_use_intent_json[] =
    "{\"next_use_intent_v\":2,\"op\":\"%s\",\"state\":%d}";

static int format_intent(const struct chaos_next_use_intent *intent,
                         char *canonical, size_t capacity)
{
    const char *name;
    int length;
    if (!intent || !canonical || capacity < 1) return 0;
    name = runtime_intent_name(intent->op);
    if (!name) return 0;
    length = snprintf(canonical, capacity, chaos_next_use_intent_json,
                      name, intent->state);
    if (length < 1 || (size_t) length >= capacity) {
        canonical[0] = '\0';
        return 0;
    }
    return 1;
}

static int hash_intent(const struct chaos_next_use_intent *intent,
                       char digest[65])
{
    char canonical[128];
    if (!format_intent(intent, canonical, sizeof canonical)) return 0;
    chaos_next_use_sha256_hex((const unsigned char *) canonical,
                              strlen(canonical), digest);
    return 1;
}

static void private_common(struct chaos_next_use_runtime_private_record *record,
                           int kind)
{
    if (runtime.private_count >= CHAOS_RUNTIME_PRIVATE_MAX)
        panic("next-use private carrier capacity");
    memset(record, 0, sizeof *record);
    record->next_use_private_v = 2;
    record->kind = kind;
    record->seq = runtime.next_seq++;
    record->at_move = (int) monstermoves;
    record->program_id = runtime.program_id;
    copy_hash(record->source_sha256, runtime.source_sha256);
}

static void append_private_intent(
        const struct chaos_next_use_runtime_private_record *record)
{
    if (!record) panic("next-use null private record");
    runtime.private_records[runtime.private_count++] = *record;
}

static void append_effect(int family, int outcome, long root)
{
    struct chaos_next_use_runtime_private_record record;
    private_common(&record, CHAOS_RUNTIME_PRIVATE_EFFECT);
    record.data.effect.family = family;
    record.data.effect.outcome = outcome;
    record.data.effect.root = root;
    if (family == CHAOS_NEXT_USE_FAMILY_W
        && outcome != CHAOS_EFFECT_W_CAPTURE_SUPPRESSED) {
        record.data.effect.activation_monstermoves =
            runtime.activation_monstermoves;
        record.data.effect.m_id = runtime.armed_m_id;
    }
    runtime.private_records[runtime.private_count++] = record;
    runtime.last_root = root;
}

static int slots_terminal(void)
{
    return runtime.slot_w != CHAOS_SLOT_W_PENDING
        && runtime.slot_f != CHAOS_SLOT_F_PENDING
        && runtime.w_runtime != CHAOS_W_RUNTIME_ARMED;
}

static void append_termination(int reason, int failure_code)
{
    struct chaos_next_use_runtime_private_record record;
    if (runtime.termination_emitted || !slots_terminal()) return;
    private_common(&record, CHAOS_RUNTIME_PRIVATE_TERMINATION);
    record.data.termination.failure_code = failure_code;
    record.data.termination.reason = reason;
    record.data.termination.slot_f = runtime.slot_f;
    record.data.termination.slot_w = runtime.slot_w;
    record.data.termination.w_runtime = runtime.w_runtime;
    runtime.private_records[runtime.private_count++] = record;
    runtime.termination_emitted = 1;
    runtime.phase = CHAOS_ATTEMPT_TERMINATED;
}

static void maybe_append_termination(int reason, int failure_code)
{
    if (!runtime.defer_termination)
        append_termination(reason, failure_code);
}

static void terminalize_pending(int slot_w, int slot_f)
{
    if (runtime.slot_w == CHAOS_SLOT_W_PENDING) runtime.slot_w = slot_w;
    if (runtime.slot_f == CHAOS_SLOT_F_PENDING) runtime.slot_f = slot_f;
}

static void clear_action_token(struct chaos_fountain_token *token)
{
    if (token) memset(token, 0, sizeof *token);
}

void chaos_next_use_runtime_reset(void)
{
    runtime_staging = 0;
    capture_depth = capture_manifest_open = capture_incomplete = 0;
    memset(&live_runtime, 0, sizeof live_runtime);
    memset(&replay_runtime, 0, sizeof replay_runtime);
    memset(&staged_runtime, 0, sizeof staged_runtime);
    live_runtime.next_seq = 1;
    replay_runtime.next_seq = 1;
}

size_t chaos_next_use_runtime_private_count(void)
{
    return (size_t) live_runtime.private_count;
}

const struct chaos_next_use_runtime_private_record *
chaos_next_use_runtime_private_at(size_t index)
{
    return index < (size_t) live_runtime.private_count
        ? &live_runtime.private_records[index] : NULL;
}

size_t chaos_next_use_runtime_public_count(void)
{
    return (size_t) live_runtime.public_count;
}

const struct chaos_next_use_public_record *
chaos_next_use_runtime_public_at(size_t index)
{
    return index < (size_t) live_runtime.public_count
        ? &live_runtime.public_records[index] : NULL;
}

static int import_admission_carrier(
        const struct chaos_next_use_admission *admission)
{
    int index;
    if (!admission || admission->carrier.count != 2
        || admission->carrier.records[0].kind != CHAOS_PRIVATE_ATTEMPT
        || admission->carrier.records[1].kind != CHAOS_PRIVATE_ADMISSION
        || admission->carrier.records[0].data.attempt.outcome
           != CHAOS_ATTEMPT_COMMITTED_OUTCOME
        || admission->carrier.records[0].data.attempt.reason != 0
        || admission->carrier.records[0].next_use_private_v != 2
        || admission->carrier.records[1].next_use_private_v != 2
        || admission->carrier.records[0].seq < 1
        || admission->carrier.records[1].seq
           != admission->carrier.records[0].seq + 1
        || admission->carrier.records[0].program_id
           != admission->carrier.records[1].program_id
        || !valid_hash_field(admission->carrier.records[0].source_sha256)
        || !valid_hash_field(admission->carrier.records[1].source_sha256)
        || !valid_hash_field(admission->carrier.records[1].data.admission.envelope_sha256)
        || strcmp(admission->carrier.records[0].source_sha256,
                  admission->carrier.records[1].source_sha256) != 0
        || admission->carrier.records[1].data.admission.operation_count < 1
        || admission->carrier.records[1].data.admission.operation_count > 2
        || admission->carrier.records[1].data.admission.envelope_b64_length
           > CHAOS_NEXT_USE_ENVELOPE_B64_MAX
        || admission->carrier.records[1].data.admission.envelope_b64[
             admission->carrier.records[1].data.admission.envelope_b64_length] != '\0'
        || admission->program.next_private_seq
           != admission->carrier.records[1].seq + 1)
        return 0;
    for (index = 0; index < 2; ++index) {
        const struct chaos_next_use_private_record *source =
            &admission->carrier.records[index];
        struct chaos_next_use_runtime_private_record *target =
            &runtime.private_records[index];
        memset(target, 0, sizeof *target);
        target->next_use_private_v = source->next_use_private_v;
        target->kind = index == 0 ? CHAOS_RUNTIME_PRIVATE_ATTEMPT
                                  : CHAOS_RUNTIME_PRIVATE_ADMISSION;
        target->seq = source->seq;
        target->at_move = source->at_move;
        target->program_id = source->program_id;
        copy_hash(target->source_sha256, source->source_sha256);
        if (index == 0) {
            target->data.attempt.outcome = source->data.attempt.outcome;
            target->data.attempt.reason = source->data.attempt.reason;
            target->data.attempt.reason_present = source->data.attempt.reason != 0;
        } else {
            int item;
            target->data.admission.at_safe = source->data.admission.at_safe;
            target->data.admission.cost = source->data.admission.cost;
            target->data.admission.operation_count =
                source->data.admission.operation_count;
            for (item = 0; item < source->data.admission.operation_count; ++item) {
                target->data.admission.operations[item] =
                    source->data.admission.operations[item];
                target->data.admission.origin_roots[item] =
                    source->data.admission.origin_roots[item];
            }
            target->data.admission.program_expiry =
                source->data.admission.program_expiry;
            memcpy(target->data.admission.envelope_b64,
                   source->data.admission.envelope_b64,
                   source->data.admission.envelope_b64_length + 1);
            copy_hash(target->data.admission.envelope_sha256,
                      source->data.admission.envelope_sha256);
        }
    }
    runtime.private_count = 2;
    return 1;
}

static int runtime_b64_value(unsigned char value)
{
    if (value >= 'A' && value <= 'Z') return value - 'A';
    if (value >= 'a' && value <= 'z') return value - 'a' + 26;
    if (value >= '0' && value <= '9') return value - '0' + 52;
    if (value == '+') return 62;
    if (value == '/') return 63;
    return -1;
}

static int runtime_decode_base64(const char *input, size_t length,
                                 unsigned char *output, size_t capacity,
                                 size_t *written)
{
    size_t offset, used = 0;
    int a, b, c, d;
    if (!input || !output || !written || length < 4 || (length % 4) != 0)
        return 0;
    for (offset = 0; offset < length; offset += 4) {
        a = runtime_b64_value((unsigned char) input[offset]);
        b = runtime_b64_value((unsigned char) input[offset + 1]);
        c = input[offset + 2] == '=' ? -2
            : runtime_b64_value((unsigned char) input[offset + 2]);
        d = input[offset + 3] == '=' ? -2
            : runtime_b64_value((unsigned char) input[offset + 3]);
        if (a < 0 || b < 0 || c == -1 || d == -1
            || (c == -2 && d != -2) || (offset + 4 < length && (c < 0 || d < 0)))
            return 0;
        if (used >= capacity) return 0;
        output[used++] = (unsigned char) ((a << 2) | (b >> 4));
        if (c == -2) {
            if ((b & 15) != 0) return 0;
            continue;
        }
        if (used >= capacity) return 0;
        output[used++] = (unsigned char) (((b & 15) << 4) | (c >> 2));
        if (d == -2) {
            if ((c & 3) != 0) return 0;
            continue;
        }
        if (d < 0 || used >= capacity) return 0;
        output[used++] = (unsigned char) (((c & 3) << 6) | d);
    }
    *written = used;
    return used >= 1 && used <= 8192;
}

static int validate_admission_envelope(
        const struct chaos_next_use_admission *admission,
        const char source_sha256[65], int variant)
{
    unsigned char decoded[8192];
    char canonical[8193], digest[65];
    size_t decoded_length = 0, canonical_length = 0;
    struct chaos_next_use_envelope envelope;
    const struct chaos_next_use_private_record *record;
    int index;
    record = &admission->carrier.records[1];
    if (record->data.admission.envelope_b64_length < 4
        || record->data.admission.envelope_b64_length
           > CHAOS_NEXT_USE_ENVELOPE_B64_MAX
        || record->data.admission.envelope_b64[
             record->data.admission.envelope_b64_length] != '\0')
        return 0;
    if (!runtime_decode_base64(record->data.admission.envelope_b64,
            record->data.admission.envelope_b64_length,
            decoded, sizeof decoded, &decoded_length))
        return 0;
    chaos_next_use_sha256_hex(decoded, decoded_length, digest);
    if (strcmp(digest, record->data.admission.envelope_sha256) != 0)
        return 0;
    if (chaos_next_use_jcs((const char *) decoded, decoded_length,
            canonical, sizeof canonical, &canonical_length) != CHAOS_NEXT_USE_OK
        || canonical_length != decoded_length
        || memcmp(canonical, decoded, decoded_length) != 0)
        return 0;
    if (chaos_next_use_parse_envelope((const char *) decoded,
            decoded_length, &envelope) != CHAOS_NEXT_USE_OK
        || strcmp(envelope.source_sha256, source_sha256) != 0
        || envelope.id != admission->program.program_id
        || envelope.cost != record->data.admission.cost
        || envelope.variant != variant
        || envelope.at != record->data.admission.at_safe
        || envelope.ttl < 0
        || record->at_move < 0
        || record->at_move > INT_MAX - envelope.ttl
        || record->at_move + envelope.ttl
           != admission->program.program_expiry
        || envelope.operation_count != record->data.admission.operation_count)
        return 0;
    for (index = 0; index < envelope.operation_count; ++index)
        if (envelope.operations[index]
                != record->data.admission.operations[index]
            || envelope.origin_refs[index].root
                != record->data.admission.origin_roots[index])
            return 0;
    return 1;
}

int chaos_next_use_runtime_install(
        const struct chaos_next_use_admission *admission,
        const char *source, size_t source_length,
        const char source_sha256[65], long run_token,
        long level_token,
        long origin_w, long origin_w_deadline,
        long origin_f, long origin_f_deadline,
        int variant, int whistle_count, int fountain_count)
{
    char actual_source_sha256[65];
    int pending_count, operation_index;
    if (!admission || !source || !source_sha256
        || source_length < 1 || source_length > 4096
        || !valid_hash_field(source_sha256)
        || !valid_hash_field(admission->carrier.records[0].source_sha256)
        || !valid_hash_field(admission->carrier.records[1].source_sha256)
        || !valid_hash_field(admission->carrier.records[1].data.admission.envelope_sha256)
        || admission->program.phase != CHAOS_ATTEMPT_COMMITTED
        || admission->program.admitted != 1
        || admission->program.state != 0
        || admission->program.delay_used != 0
        || admission->program.callback_ordinal != 0
        || admission->program.w_runtime != CHAOS_W_INACTIVE
        || admission->program.program_id <= 0
        || admission->program.program_id
           != admission->carrier.records[0].program_id
        || admission->program.program_id
           != admission->carrier.records[1].program_id
        || admission->carrier.records[0].at_move
           != admission->carrier.records[1].at_move
        || admission->program.program_expiry
           != admission->carrier.records[1].data.admission.program_expiry
        || admission->program.program_expiry < 100
        || run_token <= 0 || level_token <= 0
        || variant < 0 || variant > 2
        || whistle_count < 0 || whistle_count > 3
        || fountain_count < 0 || fountain_count > 2)
        return 0;
    if (!((admission->program.slot_w == CHAOS_SLOT_UNDECLARED)
          || (admission->program.slot_w == CHAOS_SLOT_PENDING))
        || !((admission->program.slot_f == CHAOS_SLOT_UNDECLARED)
             || (admission->program.slot_f == CHAOS_SLOT_PENDING)))
        return 0;
    pending_count = (admission->program.slot_w == CHAOS_SLOT_PENDING)
        + (admission->program.slot_f == CHAOS_SLOT_PENDING);
    if (pending_count < 1
        || admission->carrier.records[1].data.admission.operation_count
           != pending_count
        || (admission->program.slot_w == CHAOS_SLOT_PENDING
            && (origin_w <= 0 || origin_w_deadline < 0))
        || (admission->program.slot_w == CHAOS_SLOT_UNDECLARED
            && (origin_w != 0 || origin_w_deadline != 0))
        || (admission->program.slot_f == CHAOS_SLOT_PENDING
            && (origin_f <= 0 || origin_f_deadline < 0))
        || (admission->program.slot_f == CHAOS_SLOT_UNDECLARED
            && (origin_f != 0 || origin_f_deadline != 0)))
        return 0;
    operation_index = 0;
    if (admission->program.slot_w == CHAOS_SLOT_PENDING) {
        if (admission->carrier.records[1].data.admission.operations[
                operation_index] != CHAOS_NEXT_USE_FAMILY_W
            || admission->carrier.records[1].data.admission.origin_roots[
                operation_index] != origin_w)
            return 0;
        ++operation_index;
    }
    if (admission->program.slot_f == CHAOS_SLOT_PENDING) {
        if (admission->carrier.records[1].data.admission.operations[
                operation_index] != CHAOS_NEXT_USE_FAMILY_F
            || admission->carrier.records[1].data.admission.origin_roots[
                operation_index] != origin_f)
            return 0;
    }
    if (!validate_admission_envelope(admission, source_sha256, variant))
        return 0;
    chaos_next_use_sha256_hex((const unsigned char *) source,
                              source_length, actual_source_sha256);
    if (strcmp(actual_source_sha256, source_sha256) != 0
        || strcmp(admission->carrier.records[0].source_sha256,
                  source_sha256) != 0)
        return 0;
    if (runtime.program_id != 0)
        return 0;
    chaos_next_use_runtime_reset();
    if (!import_admission_carrier(admission)) {
        chaos_next_use_runtime_reset();
        return 0;
    }
    runtime.phase = CHAOS_ATTEMPT_COMMITTED;
    runtime.slot_w = admission->program.slot_w == CHAOS_SLOT_PENDING
        ? CHAOS_SLOT_W_PENDING : CHAOS_SLOT_W_UNDECLARED;
    runtime.slot_f = admission->program.slot_f == CHAOS_SLOT_PENDING
        ? CHAOS_SLOT_F_PENDING : CHAOS_SLOT_F_UNDECLARED;
    runtime.w_runtime = CHAOS_W_RUNTIME_INACTIVE;
    runtime.state = admission->program.state;
    runtime.delay_used = admission->program.delay_used;
    runtime.callback_ordinal = admission->program.callback_ordinal;
    runtime.program_id = admission->program.program_id;
    runtime.next_seq = admission->program.next_private_seq;
    runtime.program_expiry = admission->program.program_expiry;
    runtime.admission_move = admission->carrier.records[1].at_move;
    runtime.variant = variant;
    runtime.whistle_count = whistle_count;
    runtime.fountain_count = fountain_count;
    runtime.run_token = run_token;
    runtime.level_token = level_token;
    runtime.current_run_token = run_token;
    runtime.current_level_token = level_token;
    runtime.origin_w = origin_w;
    runtime.origin_f = origin_f;
    runtime.origin_w_deadline = origin_w_deadline;
    runtime.origin_f_deadline = origin_f_deadline;
    runtime.origin_w_live = admission->program.slot_w == CHAOS_SLOT_PENDING;
    runtime.origin_f_live = admission->program.slot_f == CHAOS_SLOT_PENDING;
    runtime.source_length = source_length;
    memcpy(runtime.source, source, source_length);
    runtime.source[source_length] = '\0';
    copy_hash(runtime.source_sha256, source_sha256);
    {
        struct chaos_next_use_snapshot initial;
        snapshot_values(&initial);
        if (!snapshot_binding_hash(&initial, runtime.binding_sha256)) {
            chaos_next_use_runtime_reset();
            return 0;
        }
    }
    replay_runtime = live_runtime;
    return 1;
}

static void runtime_runtime_boundary_impl(long run_token, long level_token,
                                     int origin_w_live, int origin_f_live,
                                     int whistle_count, int fountain_count)
{
    if (runtime.phase != CHAOS_ATTEMPT_COMMITTED
        || run_token <= 0 || level_token <= 0
        || whistle_count < 0 || whistle_count > 3
        || fountain_count < 0 || fountain_count > 2)
        return;
    runtime.current_run_token = run_token;
    runtime.current_level_token = level_token;
    runtime.origin_w_live = !!origin_w_live;
    runtime.origin_f_live = !!origin_f_live;
    runtime.whistle_count = whistle_count;
    runtime.fountain_count = fountain_count;
    if (runtime.phase != CHAOS_ATTEMPT_COMMITTED) return;
    if (runtime.current_level_token != runtime.level_token) {
        chaos_next_use_expire(CHAOS_END_LEVEL_DEPARTURE);
        return;
    }
    if (runtime.current_run_token != runtime.run_token
        || (runtime.origin_w > 0 && !runtime.origin_w_live)
        || (runtime.origin_f > 0 && !runtime.origin_f_live)) {
        chaos_next_use_expire(CHAOS_END_ORIGIN_EVICTED);
        return;
    }
    if ((runtime.origin_w > 0 && monstermoves > runtime.origin_w_deadline)
        || (runtime.origin_f > 0 && monstermoves > runtime.origin_f_deadline)) {
        chaos_next_use_expire(CHAOS_END_ORIGIN_EXPIRED);
        return;
    }
    if (monstermoves >= runtime.program_expiry) {
        chaos_next_use_expire(CHAOS_END_PROGRAM_EXPIRED);
        return;
    }
    if (runtime.w_runtime == CHAOS_W_RUNTIME_ARMED
        && monstermoves >= runtime.activation_monstermoves + 10)
        chaos_next_use_end_w(CHAOS_END_WINDOW_A_PLUS_10, NULL);
}

void chaos_next_use_identity_boundary(long run_token, long level_token)
{
    if (runtime.phase != CHAOS_ATTEMPT_COMMITTED) return;
    if (run_token <= 0 || level_token <= 0) {
        chaos_next_use_expire(CHAOS_END_ORIGIN_EVICTED);
        return;
    }
    chaos_next_use_runtime_boundary(run_token, level_token,
        runtime.origin_w_live, runtime.origin_f_live,
        runtime.whistle_count, runtime.fountain_count);
}

static void runtime_mark_identity_unsafe_impl(void)
{
    if (runtime.phase == CHAOS_ATTEMPT_COMMITTED)
        runtime.identity_unsafe = 1;
}

static int runtime_take_identity_unsafe_impl(void)
{
    int unsafe;
    if (runtime.phase != CHAOS_ATTEMPT_COMMITTED) return 0;
    unsafe = runtime.identity_unsafe;
    runtime.identity_unsafe = 0;
    return unsafe;
}

static void runtime_end_w_impl(enum chaos_next_use_end_reason reason,
                          const long *current_root_or_null)
{
    int outcome = 0;
    long effect_root = 0;
    if (runtime.w_runtime != CHAOS_W_RUNTIME_ARMED) return;
    switch (reason) {
    case CHAOS_END_WINDOW_A_PLUS_10:
        if (current_root_or_null != NULL) return;
        outcome = runtime.witnessed ? CHAOS_EFFECT_W_ENDED_AFTER_WITNESS
                                    : CHAOS_EFFECT_W_ENDED_NO_WITNESS;
        runtime.w_runtime = CHAOS_W_RUNTIME_WINDOW_ENDED;
        break;
    case CHAOS_END_LEVEL_DEPARTURE:
        if (current_root_or_null != NULL) return;
        terminalize_pending(CHAOS_SLOT_W_TERMINATED_LEVEL,
                            CHAOS_SLOT_F_TERMINATED_LEVEL);
        outcome = runtime.witnessed ? CHAOS_EFFECT_W_ENDED_AFTER_WITNESS
                                    : CHAOS_EFFECT_W_ENDED_NO_WITNESS;
        runtime.w_runtime = CHAOS_W_RUNTIME_DEPARTED;
        break;
    case CHAOS_END_ORIGIN_EVICTED:
        if (current_root_or_null != NULL) return;
        terminalize_pending(CHAOS_SLOT_W_TERMINATED_EXPIRY,
                            CHAOS_SLOT_F_TERMINATED_EXPIRY);
        outcome = runtime.witnessed ? CHAOS_EFFECT_W_ENDED_AFTER_WITNESS
                                    : CHAOS_EFFECT_W_ENDED_NO_WITNESS;
        runtime.w_runtime = CHAOS_W_RUNTIME_EXPIRED;
        break;
    case CHAOS_END_ORIGIN_EXPIRED:
        if (current_root_or_null != NULL) return;
        terminalize_pending(CHAOS_SLOT_W_TERMINATED_EXPIRY,
                            CHAOS_SLOT_F_TERMINATED_EXPIRY);
        outcome = runtime.witnessed ? CHAOS_EFFECT_W_ENDED_AFTER_WITNESS
                                    : CHAOS_EFFECT_W_ENDED_NO_WITNESS;
        runtime.w_runtime = CHAOS_W_RUNTIME_EXPIRED;
        break;
    case CHAOS_END_PROGRAM_EXPIRED:
        if (current_root_or_null != NULL) return;
        terminalize_pending(CHAOS_SLOT_W_TERMINATED_EXPIRY,
                            CHAOS_SLOT_F_TERMINATED_EXPIRY);
        outcome = runtime.witnessed ? CHAOS_EFFECT_W_ENDED_AFTER_WITNESS
                                    : CHAOS_EFFECT_W_ENDED_NO_WITNESS;
        runtime.w_runtime = CHAOS_W_RUNTIME_EXPIRED;
        break;
    case CHAOS_END_INVALID_CALLBACK:
        if (current_root_or_null == NULL) return;
        effect_root = *current_root_or_null;
        outcome = runtime.witnessed ? CHAOS_EFFECT_W_ENDED_AFTER_WITNESS
                                    : CHAOS_EFFECT_W_ENDED_NO_WITNESS;
        runtime.w_runtime = CHAOS_W_RUNTIME_INVALID_TERMINATED;
        break;
    case CHAOS_END_IDENTITY_UNSAFE:
        if (current_root_or_null == NULL) return;
        effect_root = *current_root_or_null;
        outcome = CHAOS_EFFECT_W_IDENTITY_UNSAFE;
        runtime.w_runtime = CHAOS_W_RUNTIME_IDENTITY_UNSAFE;
        break;
    default:
        return;
    }
    append_effect(CHAOS_NEXT_USE_FAMILY_W, outcome, effect_root);
    maybe_append_termination(reason, 0);
}

static void runtime_expire_impl(enum chaos_next_use_end_reason reason)
{
    if (runtime.phase != CHAOS_ATTEMPT_COMMITTED) return;
    if (reason == CHAOS_END_LEVEL_DEPARTURE)
        terminalize_pending(CHAOS_SLOT_W_TERMINATED_LEVEL,
                            CHAOS_SLOT_F_TERMINATED_LEVEL);
    else if (reason == CHAOS_END_ORIGIN_EVICTED
             || reason == CHAOS_END_ORIGIN_EXPIRED
             || reason == CHAOS_END_PROGRAM_EXPIRED)
        terminalize_pending(CHAOS_SLOT_W_TERMINATED_EXPIRY,
                            CHAOS_SLOT_F_TERMINATED_EXPIRY);
    else return;
    if (runtime.w_runtime == CHAOS_W_RUNTIME_ARMED)
        chaos_next_use_end_w(reason, NULL);
    else
        append_termination(reason, 0);
}

boolean chaos_next_use_action_preflight(int family, long completed_root)
{
    if (runtime.current_run_token <= 0 || runtime.current_level_token <= 0)
        return FALSE;
    chaos_next_use_runtime_boundary(runtime.current_run_token,
        runtime.current_level_token, runtime.origin_w_live,
        runtime.origin_f_live, runtime.whistle_count, runtime.fountain_count);
    if (runtime.phase != CHAOS_ATTEMPT_COMMITTED || completed_root <= 0)
        return FALSE;
    if (runtime.delay_until > 0 && monstermoves < runtime.delay_until)
        return FALSE;
    if (family == CHAOS_NEXT_USE_FAMILY_W)
        return runtime.slot_w == CHAOS_SLOT_W_PENDING;
    if (family == CHAOS_NEXT_USE_FAMILY_F)
        return runtime.slot_f == CHAOS_SLOT_F_PENDING;
    return FALSE;
}

static boolean runtime_on_action_impl(int family, long completed_root,
                                 struct chaos_fountain_token *token_out)
{
    struct chaos_next_use_context context;
    struct chaos_next_use_intent intent;
    struct chaos_next_use_runtime_private_record intent_record;
    struct { long root; } intent_binding, effect_binding;
    char context_sha256[65], intent_sha256[65];
    int status, validation = RUNTIME_VALID, state_before;
    if (runtime.phase == CHAOS_ATTEMPT_COMMITTED
        && runtime.w_runtime == CHAOS_W_RUNTIME_ARMED
        && chaos_next_use_take_identity_unsafe())
        chaos_next_use_end_w(CHAOS_END_IDENTITY_UNSAFE, &completed_root);
    if (!chaos_next_use_action_preflight(family, completed_root))
        return FALSE;
    clear_action_token(token_out);
    memset(&context, 0, sizeof context);
    memset(&intent, 0, sizeof intent);
    context.age = monstermoves >= runtime.admission_move
        ? (int) (monstermoves - runtime.admission_move) : 0;
    context.whistle_count = runtime.whistle_count;
    context.fountain_count = runtime.fountain_count;
    context.own_witnessed = runtime.witnessed;
    context.state = runtime.state;
    context.trigger = family;
    context.variant = runtime.variant;
    copy_hash(context.source_sha256, runtime.source_sha256);
    if (!hash_context(&context, context_sha256))
        panic("next-use context canonicalization");
    intent_binding.root = completed_root;
    effect_binding.root = intent_binding.root;
    runtime.last_root = effect_binding.root;
    state_before = runtime.state;
    runtime.callback_ordinal++;
    if (family == CHAOS_NEXT_USE_FAMILY_W) runtime.callback_w = 1;
    else runtime.callback_f = 1;
    status = chaos_lua_next_use_on_action(runtime.source, runtime.source_length,
                                          &context, &intent);
    private_common(&intent_record, CHAOS_RUNTIME_PRIVATE_INTENT);
    copy_hash(intent_record.data.intent.context_sha256, context_sha256);
    intent_record.data.intent.callback_ordinal = runtime.callback_ordinal;
    intent_record.data.intent.trigger = family;
    intent_record.data.intent.root = completed_root;
    intent_record.data.intent.state_before = state_before;
    intent_record.data.intent.state_after = state_before;
    intent_record.data.intent.delay_used_after = runtime.delay_used;
    if (status >= CHAOS_LUA_NEXT_USE_SANDBOX_INSTRUCTION
        && status <= CHAOS_LUA_NEXT_USE_REENTRANCY) {
        validation = RUNTIME_PROTECTED_FAILURE;
        intent_record.data.intent.failure_code = status;
        intent_record.data.intent.failure_code_present = 1;
    } else if (status != CHAOS_NEXT_USE_OK
               || intent.op < 0
               || intent.state < 0 || intent.state > 3)
        validation = RUNTIME_INVALID_SCHEMA;
    else if ((family == CHAOS_NEXT_USE_FAMILY_W
             && intent.op == CHAOS_NEXT_USE_INTENT_FOUNTAIN_REFRESH)
        || (family == CHAOS_NEXT_USE_FAMILY_F
            && intent.op == CHAOS_NEXT_USE_INTENT_WHISTLE_ATTENTION)) {
        validation = RUNTIME_WRONG_FAMILY;
        intent_record.data.intent.failure_code =
            CHAOS_INTENT_FAILURE_WRONG_FAMILY;
        intent_record.data.intent.failure_code_present = 1;
    } else if (intent.op == CHAOS_NEXT_USE_INTENT_DELAY && runtime.delay_used) {
        validation = RUNTIME_SECOND_DELAY;
        intent_record.data.intent.failure_code =
            CHAOS_INTENT_FAILURE_SECOND_DELAY;
        intent_record.data.intent.failure_code_present = 1;
    }
    else if (intent.op < CHAOS_NEXT_USE_INTENT_QUIET
             || intent.op > CHAOS_NEXT_USE_INTENT_FOUNTAIN_REFRESH)
        validation = RUNTIME_INVALID_SCHEMA;
    if (status == CHAOS_NEXT_USE_OK && hash_intent(&intent, intent_sha256)) {
        intent_record.data.intent.intent_present = 1;
        intent_record.data.intent.intent = intent;
        copy_hash(intent_record.data.intent.intent_sha256, intent_sha256);
        intent_record.data.intent.intent_sha256_present = 1;
    }
    intent_record.data.intent.validation = validation;

    if (validation != RUNTIME_VALID) {
        append_private_intent(&intent_record);
        clear_action_token(token_out);
        if (runtime.slot_w == CHAOS_SLOT_W_PENDING)
            runtime.slot_w = CHAOS_SLOT_W_CONSUMED_INVALID;
        if (runtime.slot_f == CHAOS_SLOT_F_PENDING)
            runtime.slot_f = CHAOS_SLOT_F_CONSUMED_INVALID;
        runtime.defer_termination = 1;
        chaos_next_use_end_w(CHAOS_END_INVALID_CALLBACK, &completed_root);
        runtime.defer_termination = 0;
        append_termination(RUNTIME_TERMINATION_INVALID_CALLBACK,
            intent_record.data.intent.failure_code_present
                ? intent_record.data.intent.failure_code : 0);
        return CHAOS_NEXT_USE_ORDINARY_CONTINUE;
    }

    runtime.state = intent.state;
    intent_record.data.intent.state_after = runtime.state;
    if (intent.op == CHAOS_NEXT_USE_INTENT_DELAY) {
        runtime.delay_used = 1;
        runtime.delay_until = runtime.admission_move + 10;
        if (runtime.delay_until < monstermoves + 10)
            runtime.delay_until = (int) monstermoves + 10;
        intent_record.data.intent.delay_used_after = 1;
    }
    append_private_intent(&intent_record);

    if (intent.op == CHAOS_NEXT_USE_INTENT_QUIET) {
        if (family == CHAOS_NEXT_USE_FAMILY_W)
            runtime.slot_w = CHAOS_SLOT_W_CONSUMED_QUIET;
        else runtime.slot_f = CHAOS_SLOT_F_CONSUMED_QUIET;
        maybe_append_termination(RUNTIME_TERMINATION_COMPLETED, 0);
        return FALSE;
    }
    if (intent.op == CHAOS_NEXT_USE_INTENT_DELAY) {
        if (family == CHAOS_NEXT_USE_FAMILY_W)
            runtime.slot_w = CHAOS_SLOT_W_CONSUMED_DELAY;
        else runtime.slot_f = CHAOS_SLOT_F_CONSUMED_DELAY;
        maybe_append_termination(RUNTIME_TERMINATION_COMPLETED, 0);
        return FALSE;
    }
    if (family == CHAOS_NEXT_USE_FAMILY_W
        && intent.op == CHAOS_NEXT_USE_INTENT_WHISTLE_ATTENTION) {
        runtime.pending_w_capture = 1;
        runtime.pending_w_root = effect_binding.root;
        return TRUE;
    }
    if (family == CHAOS_NEXT_USE_FAMILY_F
        && intent.op == CHAOS_NEXT_USE_INTENT_FOUNTAIN_REFRESH && token_out) {
        runtime.f_inflight = 1;
        runtime.f_root = effect_binding.root;
        token_out->root = effect_binding.root;
        token_out->active = 1;
        token_out->remap = 1;
        token_out->consumed = 0;
        return TRUE;
    }

    return FALSE;
}

static void runtime_whistle_unavailable_impl(long completed_root)
{
    if (runtime.phase != CHAOS_ATTEMPT_COMMITTED
        || runtime.slot_w != CHAOS_SLOT_W_PENDING || completed_root <= 0)
        return;
    runtime.pending_w_capture = 0;
    runtime.slot_w = CHAOS_SLOT_W_CONSUMED_SUPPRESSED;
    append_effect(CHAOS_NEXT_USE_FAMILY_W,
                  CHAOS_EFFECT_W_CAPTURE_SUPPRESSED, completed_root);
    maybe_append_termination(RUNTIME_TERMINATION_COMPLETED, 0);
}

static void runtime_capture_whistle_impl(long completed_root, unsigned m_id,
                                    long at_move)
{
    if (!runtime.pending_w_capture
        || runtime.slot_w != CHAOS_SLOT_W_PENDING
        || completed_root != runtime.pending_w_root
        || completed_root <= 0 || m_id == 0 || at_move < 0) {
        chaos_next_use_whistle_unavailable(completed_root);
        return;
    }
    runtime.pending_w_capture = 0;
    runtime.slot_w = CHAOS_SLOT_W_CONSUMED_ARMED;
    runtime.w_runtime = CHAOS_W_RUNTIME_ARMED;
    runtime.armed_m_id = m_id;
    runtime.armed_root = completed_root;
    runtime.activation_monstermoves = at_move;
    runtime.witnessed = 0;
    runtime.attention_claimed = 0;
    runtime.expected_manifest_m_id = 0;
    append_effect(CHAOS_NEXT_USE_FAMILY_W, CHAOS_EFFECT_W_ARMED,
                  completed_root);
}

static boolean runtime_whistle_decision_ready_impl(unsigned m_id)
{
    if (runtime.current_run_token <= 0 || runtime.current_level_token <= 0
        || runtime.current_run_token != runtime.run_token
        || runtime.current_level_token != runtime.level_token)
        return FALSE;
    if (runtime.w_runtime != CHAOS_W_RUNTIME_ARMED
        || runtime.armed_m_id == 0 || m_id != runtime.armed_m_id)
        return FALSE;
    if (runtime.identity_unsafe) return TRUE;
    if (monstermoves >= runtime.activation_monstermoves + 10) {
        chaos_next_use_end_w(CHAOS_END_WINDOW_A_PLUS_10, NULL);
        return FALSE;
    }
    return !runtime.witnessed && !runtime.attention_claimed
        && monstermoves >= runtime.activation_monstermoves + 5;
}

static void runtime_whistle_no_root_impl(unsigned m_id)
{
    if (runtime.w_runtime == CHAOS_W_RUNTIME_ARMED
        && runtime.armed_m_id != 0 && m_id == runtime.armed_m_id
        && !runtime.witnessed && !runtime.attention_claimed
        && monstermoves >= runtime.activation_monstermoves + 5
        && monstermoves < runtime.activation_monstermoves + 10)
        runtime.attention_claimed = 1;
}

static boolean runtime_whistle_attention_impl(unsigned m_id, long decision_root)
{
    if (decision_root <= 0 || !chaos_next_use_whistle_decision_ready(m_id))
        return FALSE;
    runtime.last_root = decision_root;
    if (chaos_next_use_take_identity_unsafe()) {
        chaos_next_use_end_w(CHAOS_END_IDENTITY_UNSAFE, &decision_root);
        return FALSE;
    }
    runtime.attention_claimed = 1;
    runtime.expected_manifest_m_id = m_id;
    return TRUE;
}

static boolean runtime_manifestation_begin_impl(unsigned m_id, long root)
{
    if (runtime.w_runtime != CHAOS_W_RUNTIME_ARMED
        || !runtime.attention_claimed || runtime.witnessed
        || runtime.expected_manifest_m_id != m_id
        || root <= 0 || runtime.expected_manifest_root != 0)
        return FALSE;
    runtime.expected_manifest_root = (int) root;
    runtime.expected_notice_seq = 0;
    runtime.expected_end_seq = 0;
    runtime.manifest_success = 0;
    return TRUE;
}

void chaos_next_use_manifestation_notice(long root, long notice_seq)
{
    if (!runtime_staging && capture_manifest_open && capture_depth == 1) {
        capture_record.notice_root = root;
        capture_record.notice_seq = notice_seq;
    }
    if (runtime.expected_manifest_root == root
        && notice_seq > root && runtime.expected_notice_seq == 0)
        runtime.expected_notice_seq = (int) notice_seq;
}

void chaos_next_use_manifestation_end(long root, long notice_seq,
                                      long end_seq, int success)
{
    if (runtime.expected_manifest_root != root) return;
    runtime.manifest_success = 0;
    if (end_seq <= root) {
        runtime.expected_manifest_root = 0;
        runtime.expected_notice_seq = 0;
        runtime.expected_end_seq = 0;
        return;
    }
    runtime.expected_end_seq = (int) end_seq;
    runtime.manifest_success = !!success;
    if (success && (runtime.expected_notice_seq != notice_seq
                    || !(root < notice_seq && notice_seq < end_seq)))
        runtime.manifest_success = 0;
    if (!runtime.manifest_success) {
        runtime.expected_manifest_root = 0;
        runtime.expected_notice_seq = 0;
        runtime.expected_end_seq = 0;
    }
}

unsigned chaos_next_use_armed_reserved_identity(void)
{
    return runtime.w_runtime == CHAOS_W_RUNTIME_ARMED
        ? runtime.armed_m_id : 0U;
}

long chaos_next_use_fountain_completed_root(void)
{
    return runtime.phase == CHAOS_ATTEMPT_COMMITTED
        && runtime.slot_f == CHAOS_SLOT_F_PENDING ? runtime.origin_f : 0;
}

static void runtime_fountain_result_impl(const struct chaos_fountain_token *token,
                                    int outcome)
{
    int effect = 0;
    if (!token || !token->active || !runtime.f_inflight
        || runtime.slot_f != CHAOS_SLOT_F_PENDING
        || token->root != runtime.f_root)
        return;
    switch (outcome) {
    case CHAOS_FOUNTAIN_NATURAL:
        runtime.slot_f = CHAOS_SLOT_F_CONSUMED_NONREMAPPABLE;
        effect = CHAOS_EFFECT_F_NATURAL;
        break;
    case CHAOS_FOUNTAIN_EARLY_RETURN:
        runtime.slot_f = CHAOS_SLOT_F_CONSUMED_NONREMAPPABLE;
        effect = CHAOS_EFFECT_F_EARLY_RETURN;
        break;
    case CHAOS_FOUNTAIN_NATIVE_19_30:
        runtime.slot_f = CHAOS_SLOT_F_CONSUMED_NONREMAPPABLE;
        effect = CHAOS_EFFECT_F_NATIVE_19_30;
        break;
    case CHAOS_FOUNTAIN_DEFAULT_WITHOUT_INTENT:
        runtime.slot_f = CHAOS_SLOT_F_CONSUMED_SUPPRESSED;
        effect = CHAOS_EFFECT_F_DEFAULT_WITHOUT_INTENT;
        break;
    case CHAOS_FOUNTAIN_GUARD_SUPPRESSED:
        runtime.slot_f = CHAOS_SLOT_F_CONSUMED_SUPPRESSED;
        effect = CHAOS_EFFECT_F_GUARD_SUPPRESSED;
        break;
    case CHAOS_FOUNTAIN_REMAPPED:
        if (!token->consumed) return;
        runtime.slot_f = CHAOS_SLOT_F_CONSUMED_APPLIED;
        effect = CHAOS_EFFECT_F_REMAPPED;
        break;
    default:
        return;
    }
    runtime.f_inflight = 0;
    append_effect(CHAOS_NEXT_USE_FAMILY_F, effect, token->root);
    maybe_append_termination(RUNTIME_TERMINATION_COMPLETED, 0);
}

void chaos_next_use_on_manifestation(
        const struct chaos_whistle_witness *witness, long end_seq)
{
    struct chaos_next_use_public_record public_record;
    long expected_root, expected_notice_seq, expected_end_seq;
    if (!witness || runtime.w_runtime != CHAOS_W_RUNTIME_ARMED
        || runtime.witnessed || !runtime.manifest_success
        || runtime.expected_manifest_m_id != runtime.armed_m_id
        || !witness->manifestation_delivered
        || !witness->displaced || witness->invalid)
        return;
    if (runtime.public_count >= CHAOS_RUNTIME_PUBLIC_MAX)
        return;
    memset(&public_record, 0, sizeof public_record);
    public_record.next_use_public_v = 2;
    public_record.family = CHAOS_NEXT_USE_FAMILY_W;
    public_record.phase = CHAOS_PUBLIC_WITNESSED;
    public_record.root = witness->root;
    public_record.notice_seq = witness->notice_seq;
    public_record.end_seq = end_seq;
    expected_root = runtime.expected_manifest_root;
    expected_notice_seq = runtime.expected_notice_seq;
    expected_end_seq = runtime.expected_end_seq;
    if (witness->root != expected_root
        || witness->notice_seq != expected_notice_seq
        || end_seq != expected_end_seq
        || !(expected_root < expected_notice_seq
             && expected_notice_seq < expected_end_seq))
        return;
    append_effect(CHAOS_NEXT_USE_FAMILY_W, CHAOS_EFFECT_W_WITNESSED,
                  witness->root);
    runtime.public_records[runtime.public_count++] = public_record;
    runtime.witnessed = 1;
    runtime.manifest_success = 0;
    runtime.expected_manifest_root = 0;
    runtime.expected_notice_seq = 0;
    runtime.expected_end_seq = 0;
}

/* Capture wrappers leave gameplay implementations above unchanged. */
void chaos_next_use_runtime_boundary(long run_token, long level_token,
                                     int origin_w_live, int origin_f_live,
                                     int whistle_count, int fountain_count)
{
    int entered = capture_enter(CHAOS_REPLAY_BOUNDARY);
    if (entered && capture_depth == 1) {
        capture_record.run_token = run_token;
        capture_record.level_token = level_token;
        capture_record.origin_w_live = origin_w_live;
        capture_record.origin_f_live = origin_f_live;
        capture_record.whistle_count = whistle_count;
        capture_record.fountain_count = fountain_count;
    }
    runtime_runtime_boundary_impl(run_token, level_token, origin_w_live, origin_f_live, whistle_count, fountain_count);
    capture_leave(entered);
}

void chaos_next_use_mark_identity_unsafe(void)
{
    int entered = capture_enter(CHAOS_REPLAY_IDENTITY_MARK);
    runtime_mark_identity_unsafe_impl();
    capture_leave(entered);
}

int chaos_next_use_take_identity_unsafe(void)
{
    int entered = capture_enter(CHAOS_REPLAY_IDENTITY_TAKE);
    int result;
    result = runtime_take_identity_unsafe_impl();
    if (entered && capture_depth == 1)
        capture_record.expected_result = result;
    capture_leave(entered);
    return result;
}

void chaos_next_use_end_w(enum chaos_next_use_end_reason reason,
                          const long *current_root_or_null)
{
    int entered = capture_enter(CHAOS_REPLAY_END_W);
    if (entered && capture_depth == 1) {
        capture_record.end_reason = reason;
        capture_record.root_present = current_root_or_null != NULL;
        if (current_root_or_null) capture_record.root = *current_root_or_null;
    }
    runtime_end_w_impl(reason, current_root_or_null);
    capture_leave(entered);
}

void chaos_next_use_expire(enum chaos_next_use_end_reason reason)
{
    int entered = capture_enter(CHAOS_REPLAY_EXPIRE);
    if (entered && capture_depth == 1) {
        capture_record.end_reason = reason;
    }
    runtime_expire_impl(reason);
    capture_leave(entered);
}

boolean chaos_next_use_on_action(int family, long completed_root,
                                 struct chaos_fountain_token *token_out)
{
    int entered = capture_enter(CHAOS_REPLAY_ACTION);
    boolean result;
    if (entered && capture_depth == 1) {
        capture_record.family = family;
        capture_record.root = completed_root;
        capture_record.token_present = token_out != NULL;
    }
    result = runtime_on_action_impl(family, completed_root, token_out);
    if (entered && capture_depth == 1)
        capture_record.expected_result = result;
    /* OUT storage is undefined on rejected preflight. Never read it before
     * the call or on failure, and do not change the caller's native storage. */
    if (entered && capture_depth == 1 && result && token_out)
        capture_record.expected_token = *token_out;
    capture_leave(entered);
    return result;
}

void chaos_next_use_whistle_unavailable(long completed_root)
{
    int entered = capture_enter(CHAOS_REPLAY_W_UNAVAILABLE);
    if (entered && capture_depth == 1) {
        capture_record.root = completed_root;
    }
    runtime_whistle_unavailable_impl(completed_root);
    capture_leave(entered);
}

void chaos_next_use_capture_whistle(long completed_root, unsigned m_id, long at_move)
{
    int entered = capture_enter(CHAOS_REPLAY_W_CAPTURE);
    if (entered && capture_depth == 1) {
        capture_record.m_id = m_id;
        capture_record.root = completed_root;
        capture_record.activation_move = at_move;
    }
    runtime_capture_whistle_impl(completed_root, m_id, at_move);
    capture_leave(entered);
}

boolean chaos_next_use_whistle_decision_ready(unsigned m_id)
{
    int entered = capture_enter(CHAOS_REPLAY_W_READY);
    boolean result;
    if (entered && capture_depth == 1) {
        capture_record.m_id = m_id;
    }
    result = runtime_whistle_decision_ready_impl(m_id);
    if (entered && capture_depth == 1)
        capture_record.expected_result = result;
    capture_leave(entered);
    return result;
}

void chaos_next_use_whistle_no_root(unsigned m_id)
{
    int entered = capture_enter(CHAOS_REPLAY_W_NO_ROOT);
    if (entered && capture_depth == 1) {
        capture_record.m_id = m_id;
    }
    runtime_whistle_no_root_impl(m_id);
    capture_leave(entered);
}

boolean chaos_next_use_whistle_attention(unsigned m_id, long decision_root)
{
    int entered = capture_enter(CHAOS_REPLAY_W_DECISION);
    boolean result;
    if (entered && capture_depth == 1) {
        capture_record.m_id = m_id;
        capture_record.decision_root = decision_root;
    }
    result = runtime_whistle_attention_impl(m_id, decision_root);
    if (entered && capture_depth == 1)
        capture_record.expected_result = result;
    if (entered && capture_depth == 1)
        capture_record.expected_attention = result;
    capture_leave(entered);
    return result;
}

void chaos_next_use_fountain_result(const struct chaos_fountain_token *token, int outcome)
{
    int entered = capture_enter(CHAOS_REPLAY_F_RESULT);
    if (entered && capture_depth == 1) {
        capture_record.token_present = token != NULL;
        if (token) capture_record.expected_token = *token;
        capture_record.fountain_outcome = outcome;
    }
    runtime_fountain_result_impl(token, outcome);
    capture_leave(entered);
}

/* A manifestation spans native movement/presentation, not just its last
 * witness callback. Finish only after the real publication certificate and
 * observation end are known, including unsuccessful delivery. */
boolean chaos_next_use_manifestation_begin(unsigned m_id, long root)
{
    int entered = capture_enter(CHAOS_REPLAY_W_MANIFEST);
    boolean result;
    if (entered && capture_depth == 1) {
        capture_record.m_id = m_id;
        capture_record.manifest_root = root;
    }
    result = runtime_manifestation_begin_impl(m_id, root);
    if (entered && capture_depth == 1) capture_record.expected_result = result;
    if (!result) capture_leave(entered);
    else if (!runtime_staging) capture_manifest_open = entered;
    return result;
}

void chaos_next_use_manifestation_complete(
    const struct chaos_whistle_witness *witness, long end_seq, int published)
{
    int entered = !runtime_staging && capture_manifest_open;
    if (!witness) {
        if (entered) capture_incomplete = 1;
    } else {
        if (entered && capture_depth == 1) {
            capture_record.root = witness->root;
            capture_record.witness_notice_seq = witness->notice_seq;
            capture_record.end_seq = end_seq;
            capture_record.published = !!published;
            capture_record.pre_public = !!witness->pre_public;
            capture_record.manifestation_delivered = !!witness->manifestation_delivered;
            capture_record.displaced = !!witness->displaced;
            capture_record.invalid = !!witness->invalid;
        }
        chaos_next_use_manifestation_end(witness->root, witness->notice_seq,
                                          end_seq, published);
        if (published && witness->pre_public)
            chaos_next_use_on_manifestation(witness, end_seq);
    }
    if (!runtime_staging) capture_manifest_open = 0;
    capture_leave(entered);
}

static int valid_hash_field(const char value[65])
{
    int index;
    if (!value || value[64] != '\0') return 0;
    for (index = 0; index < 64; ++index)
        if (!((value[index] >= '0' && value[index] <= '9')
              || (value[index] >= 'a' && value[index] <= 'f')))
            return 0;
    return 1;
}

static int replay_slot_w_valid(int value)
{
    return value >= CHAOS_SLOT_W_UNDECLARED
        && value <= CHAOS_SLOT_W_TERMINATED_TRANSPORT;
}

static int replay_slot_f_valid(int value)
{
    return value >= CHAOS_SLOT_F_UNDECLARED
        && value <= CHAOS_SLOT_F_TERMINATED_TRANSPORT;
}

static int replay_w_runtime_valid(int value)
{
    return value >= CHAOS_W_RUNTIME_INACTIVE
        && value <= CHAOS_W_RUNTIME_TRANSPORT_TERMINATED;
}

static int private_record_equal(
        const struct chaos_next_use_runtime_private_record *left,
        const struct chaos_next_use_runtime_private_record *right)
{
    int index;
    if (!left || !right
        || left->next_use_private_v != 2 || right->next_use_private_v != 2
        || left->kind != right->kind || left->seq != right->seq
        || left->at_move != right->at_move
        || left->program_id != right->program_id
        || !valid_hash_field(left->source_sha256)
        || !valid_hash_field(right->source_sha256)
        || strcmp(left->source_sha256, right->source_sha256) != 0)
        return 0;
    switch (left->kind) {
    case CHAOS_RUNTIME_PRIVATE_ATTEMPT:
        return left->data.attempt.outcome == right->data.attempt.outcome
            && left->data.attempt.reason == right->data.attempt.reason
            && left->data.attempt.reason_present
               == right->data.attempt.reason_present;
    case CHAOS_RUNTIME_PRIVATE_ADMISSION:
        if (left->data.admission.at_safe != right->data.admission.at_safe
            || left->data.admission.cost != right->data.admission.cost
            || left->data.admission.operation_count
               != right->data.admission.operation_count
            || left->data.admission.operation_count < 1
            || left->data.admission.operation_count > 2
            || left->data.admission.program_expiry
               != right->data.admission.program_expiry
            || !valid_hash_field(left->data.admission.envelope_sha256)
            || !valid_hash_field(right->data.admission.envelope_sha256)
            || !memchr(left->data.admission.envelope_b64, '\0',
                       sizeof left->data.admission.envelope_b64)
            || !memchr(right->data.admission.envelope_b64, '\0',
                       sizeof right->data.admission.envelope_b64)
            || strcmp(left->data.admission.envelope_sha256,
                      right->data.admission.envelope_sha256) != 0
            || strcmp(left->data.admission.envelope_b64,
                      right->data.admission.envelope_b64) != 0)
            return 0;
        for (index = 0; index < left->data.admission.operation_count; ++index)
            if (left->data.admission.operations[index]
                    != right->data.admission.operations[index]
                || left->data.admission.origin_roots[index]
                    != right->data.admission.origin_roots[index])
                return 0;
        return 1;
    case CHAOS_RUNTIME_PRIVATE_INTENT:
        if (left->data.intent.callback_ordinal
                != right->data.intent.callback_ordinal
            || left->data.intent.trigger != right->data.intent.trigger
            || left->data.intent.root != right->data.intent.root
            || left->data.intent.state_before != right->data.intent.state_before
            || left->data.intent.state_after != right->data.intent.state_after
            || left->data.intent.delay_used_after
                != right->data.intent.delay_used_after
            || left->data.intent.validation != right->data.intent.validation
            || left->data.intent.failure_code != right->data.intent.failure_code
            || left->data.intent.failure_code_present
               != right->data.intent.failure_code_present
            || !valid_hash_field(left->data.intent.context_sha256)
            || !valid_hash_field(right->data.intent.context_sha256)
            || strcmp(left->data.intent.context_sha256,
                      right->data.intent.context_sha256) != 0
            || left->data.intent.intent_present
                != right->data.intent.intent_present
            || left->data.intent.intent_sha256_present
                != right->data.intent.intent_sha256_present)
            return 0;
        if (!left->data.intent.intent_present)
            return !left->data.intent.intent_sha256_present;
        if (!left->data.intent.intent_sha256_present) return 0;
        return left->data.intent.intent.op
                   == right->data.intent.intent.op
            && left->data.intent.intent.op == right->data.intent.intent.op
            && left->data.intent.intent.state == right->data.intent.intent.state
            && valid_hash_field(left->data.intent.intent_sha256)
            && valid_hash_field(right->data.intent.intent_sha256)
            && strcmp(left->data.intent.intent_sha256,
                      right->data.intent.intent_sha256) == 0;
    case CHAOS_RUNTIME_PRIVATE_EFFECT:
        return left->data.effect.family == right->data.effect.family
            && left->data.effect.outcome == right->data.effect.outcome
            && left->data.effect.root == right->data.effect.root
            && left->data.effect.activation_monstermoves
               == right->data.effect.activation_monstermoves
            && left->data.effect.m_id == right->data.effect.m_id;
    case CHAOS_RUNTIME_PRIVATE_TERMINATION:
        return left->data.termination.failure_code
                   == right->data.termination.failure_code
            && left->data.termination.reason == right->data.termination.reason
            && left->data.termination.slot_f == right->data.termination.slot_f
            && left->data.termination.slot_w == right->data.termination.slot_w
            && left->data.termination.w_runtime
               == right->data.termination.w_runtime;
    default:
        return 0;
    }
}

static int public_record_equal(const struct chaos_next_use_public_record *left,
                               const struct chaos_next_use_public_record *right)
{
    return left && right && left->next_use_public_v == 2
        && right->next_use_public_v == 2
        && left->family == right->family && left->phase == right->phase
        && left->root == right->root
        && left->notice_seq == right->notice_seq
        && left->end_seq == right->end_seq;
}

static int replay_token_equal(const struct chaos_fountain_token *left,
                              const struct chaos_fountain_token *right)
{
    return left->root == right->root && left->active == right->active
        && left->remap == right->remap && left->consumed == right->consumed;
}

/* The caller chooses semantics; an untrusted record cannot negotiate them. */
static int replay_record_impl(
        const struct chaos_next_use_replay_input *record, int legacy_fixture)
{
    struct chaos_fountain_token token;
    struct chaos_whistle_witness witness;
    int private_before, public_before, index, attention = 0;
    int applied = 1, result = 0;
    if (!record || !valid_hash_field(record->source_sha256))
        return CHAOS_REPLAY_BLOCKED_REPLAY;
    if (record->replay_input_v != (legacy_fixture ? 0 : CHAOS_NEXT_USE_REPLAY_INPUT_V)
        || (legacy_fixture
            && (record->operation == CHAOS_REPLAY_W_MANIFEST
                || record->operation > CHAOS_REPLAY_EXPIRE)))
        return CHAOS_REPLAY_BLOCKED_REPLAY;
    if (!legacy_fixture &&
        ((record->published != 0 && record->published != 1)
         || (record->pre_public != 0 && record->pre_public != 1)
         || (record->manifestation_delivered != 0 && record->manifestation_delivered != 1)
         || (record->displaced != 0 && record->displaced != 1)
         || (record->invalid != 0 && record->invalid != 1)
         || (record->token_present != 0 && record->token_present != 1)
         || (record->root_present != 0 && record->root_present != 1)
         || (record->expected_result != 0 && record->expected_result != 1)
         || (record->expected_attention != 0 && record->expected_attention != 1)
         || (record->expected_token.active != 0 && record->expected_token.active != 1)
         || (record->expected_token.consumed != 0 && record->expected_token.consumed != 1)
         || (record->expected_token.remap != 0 && record->expected_token.remap != 1)
         || (record->origin_w_live != 0 && record->origin_w_live != 1)
         || (record->origin_f_live != 0 && record->origin_f_live != 1)
         || (record->published && (!record->manifestation_delivered
             || !record->displaced || !record->pre_public || record->invalid
             || !(record->root < record->witness_notice_seq
                  && record->witness_notice_seq < record->end_seq)))))
        return CHAOS_REPLAY_BLOCKED_REPLAY;
    if (replay_runtime.phase == CHAOS_ATTEMPT_TERMINATED
        || replay_runtime.replay_cursor == ULONG_MAX
        || record->cursor != replay_runtime.replay_cursor + 1)
        return CHAOS_REPLAY_BLOCKED_REPLAY;
    if (record->private_count < 0 || record->private_count > 4
        || record->public_count < 0 || record->public_count > 1
        || record->at_move != monstermoves
        || !replay_slot_w_valid(record->slot_w)
        || !replay_slot_f_valid(record->slot_f)
        || !replay_w_runtime_valid(record->w_runtime)
        || strcmp(record->source_sha256, replay_runtime.source_sha256) != 0)
        return CHAOS_REPLAY_BLOCKED_REPLAY;

    staged_runtime = replay_runtime;
    runtime_staging = 1;
    private_before = runtime.private_count;
    public_before = runtime.public_count;
    memset(&token, 0, sizeof token);
    memset(&witness, 0, sizeof witness);
    switch (record->operation) {
    case CHAOS_REPLAY_ACTION:
        result = chaos_next_use_on_action(record->family, record->root,
            legacy_fixture || record->token_present ? &token : NULL);
        if (!replay_token_equal(&token, &record->expected_token)) applied = 0;
        break;
    case CHAOS_REPLAY_W_UNAVAILABLE:
        chaos_next_use_whistle_unavailable(record->root);
        break;
    case CHAOS_REPLAY_W_CAPTURE:
        chaos_next_use_capture_whistle(record->root, record->m_id,
                                       legacy_fixture
                                           ? record->at_move : record->activation_move);
        break;
    case CHAOS_REPLAY_W_DECISION:
        if (!legacy_fixture) {
            attention = chaos_next_use_whistle_attention(record->m_id,
                                                          record->decision_root);
        } else if (chaos_next_use_whistle_decision_ready(record->m_id)) {
            if (record->decision_root > 0)
                attention = chaos_next_use_whistle_attention(
                    record->m_id, record->decision_root);
            else
                chaos_next_use_whistle_no_root(record->m_id);
        }
        result = attention;
        if (attention != record->expected_attention) applied = 0;
        break;
    case CHAOS_REPLAY_W_MANIFEST:
        witness.root = record->root;
        witness.notice_seq = record->witness_notice_seq;
        witness.production = TRUE;
        witness.pre_public = record->pre_public;
        witness.manifestation_delivered = !!record->manifestation_delivered;
        witness.displaced = !!record->displaced;
        witness.invalid = !!record->invalid;
        result = chaos_next_use_manifestation_begin(record->m_id,
                                                     record->manifest_root);
        if (!result) break;
        if (record->notice_root)
            chaos_next_use_manifestation_notice(record->notice_root,
                                                 record->notice_seq);
        chaos_next_use_manifestation_complete(&witness, record->end_seq,
                                               record->published);
        break;
    case CHAOS_REPLAY_F_RESULT:
        chaos_next_use_fountain_result(
            legacy_fixture || record->token_present ? &record->expected_token : NULL,
                                       record->fountain_outcome);
        break;
    case CHAOS_REPLAY_BOUNDARY:
        chaos_next_use_runtime_boundary(record->run_token,
            record->level_token, record->origin_w_live,
            record->origin_f_live, record->whistle_count,
            record->fountain_count);
        break;
    case CHAOS_REPLAY_EXPIRE:
        chaos_next_use_expire((enum chaos_next_use_end_reason)
                              record->end_reason);
        break;
    case CHAOS_REPLAY_W_READY:
        result = chaos_next_use_whistle_decision_ready(record->m_id);
        break;
    case CHAOS_REPLAY_W_NO_ROOT:
        chaos_next_use_whistle_no_root(record->m_id);
        break;
    case CHAOS_REPLAY_IDENTITY_MARK:
        chaos_next_use_mark_identity_unsafe();
        break;
    case CHAOS_REPLAY_IDENTITY_TAKE:
        result = chaos_next_use_take_identity_unsafe();
        break;
    case CHAOS_REPLAY_END_W:
        chaos_next_use_end_w((enum chaos_next_use_end_reason) record->end_reason,
                             record->root_present ? &record->root : NULL);
        break;
    default:
        applied = 0;
        break;
    }
    runtime_staging = 0;
    if (!applied
        || (!legacy_fixture && (result != record->expected_result
            || !replay_post_equal(&record->post, &staged_runtime)))
        || staged_runtime.private_count - private_before
           != record->private_count
        || staged_runtime.public_count - public_before
           != record->public_count
        || staged_runtime.last_root != (legacy_fixture
            ? record->root : record->expected_last_root)
        || staged_runtime.callback_ordinal != record->callback_ordinal
        || staged_runtime.state != record->state
        || staged_runtime.slot_w != record->slot_w
        || staged_runtime.slot_f != record->slot_f
        || staged_runtime.w_runtime != record->w_runtime)
        return CHAOS_REPLAY_BLOCKED_REPLAY;
    for (index = 0; index < record->private_count; ++index)
        if (!private_record_equal(
                &staged_runtime.private_records[private_before + index],
                &record->private_records[index]))
            return CHAOS_REPLAY_BLOCKED_REPLAY;
    for (index = 0; index < record->public_count; ++index)
        if (!public_record_equal(
                &staged_runtime.public_records[public_before + index],
                &record->public_records[index]))
            return CHAOS_REPLAY_BLOCKED_REPLAY;
    if (record->private_count > 0
        && staged_runtime.private_records[staged_runtime.private_count - 1].seq
           != record->seq)
        return CHAOS_REPLAY_BLOCKED_REPLAY;
    /* Restored checkpoints retain sequence identity, not old carrier arrays.
     * A no-output transition must match that authoritative preceding sequence. */
    if (record->private_count == 0
        && (staged_runtime.next_seq < 1
            || staged_runtime.next_seq - 1 != record->seq))
        return CHAOS_REPLAY_BLOCKED_REPLAY;
    staged_runtime.replay_cursor = record->cursor;
    replay_runtime = staged_runtime;
    return CHAOS_REPLAY_APPLIED;
}

int chaos_next_use_replay_record(
        const struct chaos_next_use_replay_input *record)
{
    return replay_record_impl(record, 0);
}

#ifdef CHAOS_NEXT_USE_TEST_LEGACY_REPLAY
/* Historical component fixtures only; absent from production builds. */
int chaos_next_use_replay_legacy_fixture(
        const struct chaos_next_use_replay_input *record)
{
    return replay_record_impl(record, 1);
}
#endif

static void snapshot_values(struct chaos_next_use_snapshot *out)
{
    memset(out, 0, sizeof *out);
    out->snapshot_v = CHAOS_NEXT_USE_SNAPSHOT_V;
    out->program_id = runtime.program_id;
    out->phase = runtime.phase;
    out->slot_w = runtime.slot_w;
    out->slot_f = runtime.slot_f;
    out->w_runtime = runtime.w_runtime;
    out->state = runtime.state;
    out->delay_used = runtime.delay_used;
    out->callback_ordinal = runtime.callback_ordinal;
    out->witnessed = runtime.witnessed;
    out->attention_claimed = runtime.attention_claimed;
    out->whistle_count = runtime.whistle_count;
    out->fountain_count = runtime.fountain_count;
    out->next_seq = runtime.next_seq;
    out->callback_w = runtime.callback_w;
    out->callback_f = runtime.callback_f;
    out->termination_emitted = runtime.termination_emitted;
    out->identity_unsafe = runtime.identity_unsafe;
    out->last_root = runtime.last_root;
    out->admission_move = runtime.admission_move;
    out->program_expiry = runtime.program_expiry;
    out->delay_until = runtime.delay_until;
    out->variant = runtime.variant;
    out->origin_w_live = runtime.origin_w_live;
    out->origin_f_live = runtime.origin_f_live;
    out->armed_m_id = runtime.armed_m_id;
    out->replay_cursor = runtime.replay_cursor;
    out->activation_monstermoves = runtime.activation_monstermoves;
    out->armed_root = runtime.armed_root;
    out->origin_w = runtime.origin_w;
    out->origin_f = runtime.origin_f;
    out->origin_w_deadline = runtime.origin_w_deadline;
    out->origin_f_deadline = runtime.origin_f_deadline;
    out->run_token = runtime.run_token;
    out->level_token = runtime.level_token;
    out->source_length = runtime.source_length;
    copy_hash(out->source_sha256, runtime.source_sha256);
    copy_hash(out->binding_sha256, runtime.binding_sha256);
    if (runtime.source_length > CHAOS_NEXT_USE_SOURCE_MAX)
        return;
    memcpy(out->source, runtime.source, runtime.source_length);
    out->source[runtime.source_length] = '\0';
}

static int snapshot_binding_hash(const struct chaos_next_use_snapshot *in, char out[65])
{
    char canonical[512];
    int n = snprintf(canonical, sizeof canonical,
        "next-use-bind-v1|%d|%s|%d|%d|%d|%ld|%ld|%ld|%ld|%ld|%ld",
        in->program_id, in->source_sha256, in->admission_move,
        in->program_expiry, in->variant, in->run_token, in->level_token,
        in->origin_w, in->origin_w_deadline, in->origin_f, in->origin_f_deadline);
    if (n < 1 || (size_t)n >= sizeof canonical) return 0;
    chaos_next_use_sha256_hex((const unsigned char *)canonical, (size_t)n, out);
    return 1;
}

int chaos_next_use_snapshot_export(struct chaos_next_use_snapshot *out)
{
    if (!out) return 0;
    memset(out, 0, sizeof *out);
    if (runtime.program_id <= 0 || runtime.phase == 0) return 0;
    snapshot_values(out);
    return chaos_next_use_snapshot_validate(out);
}

int chaos_next_use_snapshot_validate(const struct chaos_next_use_snapshot *in)
{
    char actual[65];

    if (!in || in->snapshot_v != CHAOS_NEXT_USE_SNAPSHOT_V)
        return 0;
    if (in->program_id <= 0 || in->source_length < 1
        || in->source_length > CHAOS_NEXT_USE_SOURCE_MAX)
        return 0;
    if (in->source[in->source_length] != '\0')
        return 0;
    if (!valid_hash_field(in->source_sha256))
        return 0;
    chaos_next_use_sha256_hex((const unsigned char *)in->source,
                              in->source_length, actual);
    if (strcmp(actual, in->source_sha256) != 0)
        return 0;
    if (!valid_hash_field(in->binding_sha256)
        || !snapshot_binding_hash(in, actual)
        || strcmp(actual, in->binding_sha256))
        return 0;
    if (!replay_slot_w_valid(in->slot_w) || !replay_slot_f_valid(in->slot_f)
        || !replay_w_runtime_valid(in->w_runtime))
        return 0;
    if (in->state < 0 || in->state > 3 || in->delay_used < 0
        || in->delay_used > 1 || in->callback_ordinal < 0
        || in->variant < 0 || in->variant > 2)
        return 0;
    /* Snapshot scalars must fit their wire representation before casting.
     * TTL is fixed at 100 native moves by the envelope contract. */
    if (in->admission_move < 0 || in->admission_move > INT32_MAX - 100
        || in->program_expiry != in->admission_move + 100
        || in->delay_until < 0
        || (!in->delay_used && in->delay_until != 0)
        || (in->delay_used && in->delay_until < in->admission_move + 10)
        || in->run_token <= 0 || in->level_token <= 0
        || in->origin_w < 0 || in->origin_w > INT32_MAX
        || in->origin_f < 0 || in->origin_f > INT32_MAX
        || in->origin_w_deadline < 0 || in->origin_w_deadline > INT32_MAX
        || in->origin_f_deadline < 0 || in->origin_f_deadline > INT32_MAX
        || in->activation_monstermoves < 0
        || in->activation_monstermoves > INT32_MAX - 10
        || in->armed_root < 0 || in->armed_root > INT32_MAX
        || in->replay_cursor > INT32_MAX
        || in->last_root < 0 || in->last_root > INT32_MAX
        || in->next_seq < 3 || in->next_seq > CHAOS_RUNTIME_PRIVATE_MAX + 1
        || (in->origin_w_live != 0 && in->origin_w_live != 1)
        || (in->origin_f_live != 0 && in->origin_f_live != 1)
        || (in->identity_unsafe != 0 && in->identity_unsafe != 1))
        return 0;
    if ((in->phase != CHAOS_ATTEMPT_COMMITTED
         && in->phase != CHAOS_ATTEMPT_TERMINATED)
        || in->termination_emitted != (in->phase == CHAOS_ATTEMPT_TERMINATED)
        || (in->phase == CHAOS_ATTEMPT_TERMINATED)
           != (in->slot_w != CHAOS_SLOT_W_PENDING
               && in->slot_f != CHAOS_SLOT_F_PENDING
               && in->w_runtime != CHAOS_W_RUNTIME_ARMED))
        return 0;
    if ((in->slot_w == CHAOS_SLOT_W_UNDECLARED
         && (in->origin_w || in->origin_w_deadline || in->origin_w_live))
        || (in->slot_f == CHAOS_SLOT_F_UNDECLARED
            && (in->origin_f || in->origin_f_deadline || in->origin_f_live))
        || (in->slot_w != CHAOS_SLOT_W_UNDECLARED && in->origin_w <= 0)
        || (in->slot_f != CHAOS_SLOT_F_UNDECLARED && in->origin_f <= 0)
        || (in->slot_w == CHAOS_SLOT_W_UNDECLARED
            && in->slot_f == CHAOS_SLOT_F_UNDECLARED))
        return 0;
    if ((in->witnessed && !in->attention_claimed)
        || (in->slot_w != CHAOS_SLOT_W_CONSUMED_ARMED
            && (in->witnessed || in->attention_claimed
                || in->w_runtime != CHAOS_W_RUNTIME_INACTIVE
                || in->armed_m_id || in->armed_root
                || in->activation_monstermoves)))
        return 0;
    if ((in->slot_w == CHAOS_SLOT_W_PENDING && in->origin_w <= 0)
        || (in->slot_f == CHAOS_SLOT_F_PENDING && in->origin_f <= 0))
        return 0;
    /* One callback at most per declared family. Terminalizing the other
     * pending slot on failure is not a callback for that family. */
    if ((in->callback_w != 0 && in->callback_w != 1)
        || (in->callback_f != 0 && in->callback_f != 1)
        || in->callback_ordinal != in->callback_w + in->callback_f
        || ((in->slot_w == CHAOS_SLOT_W_PENDING
             || in->slot_w == CHAOS_SLOT_W_UNDECLARED) && in->callback_w)
        || ((in->slot_f == CHAOS_SLOT_F_PENDING
             || in->slot_f == CHAOS_SLOT_F_UNDECLARED) && in->callback_f)
        || ((in->slot_w == CHAOS_SLOT_W_CONSUMED_ARMED
             || in->slot_w == CHAOS_SLOT_W_CONSUMED_QUIET
             || in->slot_w == CHAOS_SLOT_W_CONSUMED_DELAY) && !in->callback_w)
        || ((in->slot_f == CHAOS_SLOT_F_CONSUMED_APPLIED
             || in->slot_f == CHAOS_SLOT_F_CONSUMED_NONREMAPPABLE
             || in->slot_f == CHAOS_SLOT_F_CONSUMED_QUIET
             || in->slot_f == CHAOS_SLOT_F_CONSUMED_DELAY) && !in->callback_f))
        return 0;
    if (in->witnessed < 0 || in->witnessed > 1
        || in->attention_claimed < 0 || in->attention_claimed > 1
        || in->whistle_count < 0 || in->whistle_count > 3
        || in->fountain_count < 0 || in->fountain_count > 2)
        return 0;
    if (in->level_token > INT32_MAX)
        return 0;
    /* Capture metadata survives every window end. The consumed-armed slot
     * cannot become inactive, nor can an ended window discard its capture. */
    if (in->slot_w == CHAOS_SLOT_W_CONSUMED_ARMED
        && (in->w_runtime == CHAOS_W_RUNTIME_INACTIVE
            || in->armed_m_id == 0 || in->armed_root <= 0
            || in->activation_monstermoves < in->admission_move
            || in->activation_monstermoves >= in->program_expiry))
        return 0;
    return 1;
}

int chaos_next_use_snapshot_import(const struct chaos_next_use_snapshot *in)
{
    if (!chaos_next_use_snapshot_validate(in))
        return 0;
    chaos_next_use_runtime_reset();
    live_runtime.program_id = in->program_id;
    live_runtime.phase = in->phase;
    live_runtime.slot_w = in->slot_w;
    live_runtime.slot_f = in->slot_f;
    live_runtime.w_runtime = in->w_runtime;
    live_runtime.state = in->state;
    live_runtime.delay_used = in->delay_used;
    live_runtime.callback_ordinal = in->callback_ordinal;
    live_runtime.witnessed = in->witnessed;
    live_runtime.attention_claimed = in->attention_claimed;
    live_runtime.whistle_count = in->whistle_count;
    live_runtime.fountain_count = in->fountain_count;
    live_runtime.next_seq = in->next_seq;
    live_runtime.callback_w = in->callback_w;
    live_runtime.callback_f = in->callback_f;
    live_runtime.termination_emitted = in->termination_emitted;
    live_runtime.identity_unsafe = in->identity_unsafe;
    live_runtime.last_root = in->last_root;
    live_runtime.admission_move = in->admission_move;
    live_runtime.program_expiry = in->program_expiry;
    live_runtime.delay_until = in->delay_until;
    live_runtime.variant = in->variant;
    live_runtime.origin_w_live = in->origin_w_live;
    live_runtime.origin_f_live = in->origin_f_live;
    live_runtime.armed_m_id = in->armed_m_id;
    live_runtime.replay_cursor = in->replay_cursor;
    live_runtime.activation_monstermoves = in->activation_monstermoves;
    live_runtime.armed_root = in->armed_root;
    live_runtime.origin_w = in->origin_w;
    live_runtime.origin_f = in->origin_f;
    live_runtime.origin_w_deadline = in->origin_w_deadline;
    live_runtime.origin_f_deadline = in->origin_f_deadline;
    live_runtime.run_token = in->run_token;
    live_runtime.level_token = in->level_token;
    live_runtime.current_run_token = 0;
    live_runtime.current_level_token = 0;
    live_runtime.source_length = in->source_length;
    copy_hash(live_runtime.source_sha256, in->source_sha256);
    copy_hash(live_runtime.binding_sha256, in->binding_sha256);
    memcpy(live_runtime.source, in->source, in->source_length);
    live_runtime.source[in->source_length] = '\0';
    replay_runtime = live_runtime;
    return 1;
}

long chaos_next_use_runtime_run_token(void)
{
    return live_runtime.run_token;
}

static int snapshot_io_all(int fd, void *buf, size_t n, int writing)
{
    if (writing)
        bwrite(fd, buf, (unsigned)n);
    else
        return chaos_next_use_mread(fd, buf, (unsigned)n);
    return 1;
}

int chaos_next_use_snapshot_write(int fd, const struct chaos_next_use_snapshot *in)
{
    int32_t header[37];

    if (fd < 0 || !chaos_next_use_snapshot_validate(in))
        return 0;
    memset(header, 0, sizeof header);
    header[0] = in->snapshot_v;
    header[1] = in->program_id;
    header[2] = in->phase;
    header[3] = in->slot_w;
    header[4] = in->slot_f;
    header[5] = in->w_runtime;
    header[6] = in->state;
    header[7] = in->delay_used;
    header[8] = in->callback_ordinal;
    header[9] = in->admission_move;
    header[10] = in->program_expiry;
    header[11] = in->delay_until;
    header[12] = in->variant;
    header[13] = (int32_t)in->source_length;
    header[14] = in->origin_w_live;
    header[15] = in->origin_f_live;
    header[16] = (int32_t)in->origin_w;
    header[17] = (int32_t)in->origin_f;
    header[18] = (int32_t)in->origin_w_deadline;
    header[19] = (int32_t)in->origin_f_deadline;
    header[20] = (int32_t)in->armed_m_id;
    header[21] = (int32_t)in->replay_cursor;
    header[22] = (int32_t)in->run_token;
    header[23] = (int32_t)in->level_token;
    header[24] = (int32_t)in->activation_monstermoves;
    header[25] = (int32_t)in->armed_root;
    header[26] = in->witnessed;
    header[27] = in->attention_claimed;
    header[28] = in->whistle_count;
    header[29] = in->fountain_count;
    header[30] = in->next_seq;
    header[31] = in->termination_emitted;
    header[32] = in->identity_unsafe;
    header[33] = (int32_t)in->last_root;
    header[34] = in->callback_w;
    header[35] = in->callback_f;
    header[36] = (int32_t)((uint64_t)in->run_token >> 32);
    if (!snapshot_io_all(fd, header, sizeof header, 1))
        return 0;
    if (!snapshot_io_all(fd, (void *)in->source_sha256, 65, 1)
        || !snapshot_io_all(fd, (void *)in->binding_sha256, 65, 1))
        return 0;
    if (!snapshot_io_all(fd, (void *)in->source, in->source_length, 1))
        return 0;
    return 1;
}

int chaos_next_use_snapshot_read(int fd, struct chaos_next_use_snapshot *out)
{
    int32_t header[26];
    struct chaos_next_use_snapshot snap;

    if (fd < 0 || !out)
        return 0;
    memset(&snap, 0, sizeof snap);
    if (!snapshot_io_all(fd, header, sizeof header[0], 0)
        || header[0] != CHAOS_NEXT_USE_SNAPSHOT_V)
        return 0;
    if (!snapshot_io_all(fd, header + 1, sizeof header - sizeof header[0], 0))
        return 0;
    snap.snapshot_v = header[0];
    snap.program_id = header[1];
    snap.phase = header[2];
    snap.slot_w = header[3];
    snap.slot_f = header[4];
    snap.w_runtime = header[5];
    snap.state = header[6];
    snap.delay_used = header[7];
    snap.callback_ordinal = header[8];
    snap.admission_move = header[9];
    snap.program_expiry = header[10];
    snap.delay_until = header[11];
    snap.variant = header[12];
    if (header[13] < 1 || header[13] > CHAOS_NEXT_USE_SOURCE_MAX)
        return 0;
    snap.source_length = (size_t)header[13];
    snap.origin_w_live = header[14];
    snap.origin_f_live = header[15];
    snap.origin_w = header[16];
    snap.origin_f = header[17];
    snap.origin_w_deadline = header[18];
    snap.origin_f_deadline = header[19];
    snap.armed_m_id = (unsigned)header[20];
    snap.replay_cursor = (unsigned long)header[21];
    snap.run_token = header[22];
    snap.level_token = header[23];
    snap.activation_monstermoves = header[24];
    snap.armed_root = header[25];
    {
        int32_t extra[11];
        if (!snapshot_io_all(fd, extra, sizeof extra, 0))
            return 0;
        snap.witnessed = extra[0];
        snap.attention_claimed = extra[1];
        snap.whistle_count = extra[2];
        snap.fountain_count = extra[3];
        snap.next_seq = extra[4];
        snap.termination_emitted = extra[5];
        snap.identity_unsafe = extra[6];
        snap.last_root = extra[7];
        snap.callback_w = extra[8];
        snap.callback_f = extra[9];
        {
            uint64_t token = ((uint64_t)(uint32_t)extra[10] << 32)
                             | (uint32_t)header[22];
            if (extra[10] < 0 || token > (uint64_t)LONG_MAX) return 0;
            snap.run_token = (long)token;
        }
    }
    if (!snapshot_io_all(fd, snap.source_sha256, 65, 0)
        || !snapshot_io_all(fd, snap.binding_sha256, 65, 0))
        return 0;
    if (!snapshot_io_all(fd, snap.source, snap.source_length, 0))
        return 0;
    snap.source[snap.source_length] = '\0';
    if (!chaos_next_use_snapshot_validate(&snap))
        return 0;
    *out = snap;
    return 1;
}

int chaos_next_use_save_status(void)
{
    struct chaos_next_use_snapshot snap;
    if (live_runtime.program_id == 0 && live_runtime.phase == 0)
        return CHAOS_SNAPSHOT_ABSENT;
    /* Native save may be interrupted into during an action. The action's
     * temporary token/presentation handshake is not a persistent value. */
    if (live_runtime.pending_w_capture || live_runtime.f_inflight
        || live_runtime.defer_termination
        || (live_runtime.expected_manifest_root && !live_runtime.witnessed))
        return CHAOS_SNAPSHOT_ERROR;
    return chaos_next_use_snapshot_export(&snap)
        ? CHAOS_SNAPSHOT_VALID : CHAOS_SNAPSHOT_ERROR;
}

int chaos_next_use_save(int fd)
{
    static const char magic[4] = { 'N', 'U', 'S', '1' };
    struct chaos_next_use_snapshot snap;
    int present = chaos_next_use_save_status();

    if (fd < 0 || present == CHAOS_SNAPSHOT_ERROR)
        return 0;
    if (present == CHAOS_SNAPSHOT_VALID && !chaos_next_use_snapshot_export(&snap))
        return 0;
    bwrite(fd, (genericptr_t)magic, 4);
    bwrite(fd, (genericptr_t)&present, sizeof present);
    return present == CHAOS_SNAPSHOT_ABSENT
        || chaos_next_use_snapshot_write(fd, &snap);
}

static int restore_snapshot(int fd, long run_token, long level_token, int bound)
{
    char magic[4];
    int present = 0;
    struct chaos_next_use_snapshot snap;

    if (!chaos_next_use_mread(fd, magic, 4)
        || memcmp(magic, "NUS1", 4) != 0)
        return 0;
    if (!chaos_next_use_mread(fd, &present, sizeof present))
        return 0;
    if (present == 0) {
        chaos_next_use_runtime_reset();
        return 1;
    }
    if (present != 1)
        return 0;
    memset(&snap, 0, sizeof snap);
    if (!chaos_next_use_snapshot_read(fd, &snap))
        return 0;
    /* Admission level binds executable state, not terminal history carried
     * by the same saved game after travelling elsewhere. Read validated the
     * terminal phase/slots/window agreement before this identity check. */
    if (bound && (run_token <= 0 || level_token <= 0
                  || snap.run_token != run_token
                  || (snap.phase != CHAOS_ATTEMPT_TERMINATED
                      && snap.level_token != level_token)))
        return 0;
    if (!chaos_next_use_snapshot_import(&snap)) return 0;
    if (bound) {
        live_runtime.current_run_token = run_token;
        live_runtime.current_level_token = level_token;
        replay_runtime = live_runtime;
    }
    return 1;
}

int chaos_next_use_restore_bound(int fd, long run_token, long level_token)
{
    return restore_snapshot(fd, run_token, level_token, 1);
}

int chaos_next_use_restore(int fd)
{
    /* Data-only fixture API: requires an explicit boundary before action. */
    return restore_snapshot(fd, 0, 0, 0);
}

#ifdef CHAOS_NEXT_USE_HASH_FIXTURE
int chaos_next_use_test_hash_intent(const struct chaos_next_use_intent *intent,
                                    char digest[65])
{
    if (!intent || !digest) return 0;
    return hash_intent(intent, digest);
}

int chaos_next_use_test_hash_context(const struct chaos_next_use_context *context,
                                     char digest[65])
{
    if (!context || !digest) return 0;
    return hash_context(context, digest);
}

int chaos_next_use_test_format_intent(const struct chaos_next_use_intent *intent,
                                      char *out, size_t capacity)
{
    return format_intent(intent, out, capacity);
}
#endif
