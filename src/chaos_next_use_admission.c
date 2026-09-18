/* NetHack General Public License. Atomic next-use admission and carrier. */
#include "chaos_next_use_admission.h"

#include <stdint.h>
#include <string.h>

static void admission_digest_hex(const unsigned char digest[32], char output[65])
{
    static const char hex[] = "0123456789abcdef";
    int index;
    for (index = 0; index < 32; ++index) {
        output[index * 2] = hex[digest[index] >> 4];
        output[index * 2 + 1] = hex[digest[index] & 15];
    }
    output[64] = '\0';
}

static int admission_base64(const unsigned char *source, size_t length,
                            char output[CHAOS_NEXT_USE_ENVELOPE_B64_MAX + 1],
                            size_t *written)
{
    static const char alphabet[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t input = 0, position = 0;
    if ((!source && length) || !output || !written || length > 8192) return 0;
    while (input + 3 <= length) {
        uint32_t word = ((uint32_t)source[input] << 16) |
                        ((uint32_t)source[input + 1] << 8) |
                        source[input + 2];
        output[position++] = alphabet[(word >> 18) & 63];
        output[position++] = alphabet[(word >> 12) & 63];
        output[position++] = alphabet[(word >> 6) & 63];
        output[position++] = alphabet[word & 63];
        input += 3;
    }
    if (input < length) {
        uint32_t word = (uint32_t)source[input] << 16;
        output[position++] = alphabet[(word >> 18) & 63];
        if (input + 1 < length) {
            word |= (uint32_t)source[input + 1] << 8;
            output[position++] = alphabet[(word >> 12) & 63];
            output[position++] = alphabet[(word >> 6) & 63];
            output[position++] = '=';
        } else {
            output[position++] = alphabet[(word >> 12) & 63];
            output[position++] = '=';
            output[position++] = '=';
        }
    }
    if (position > CHAOS_NEXT_USE_ENVELOPE_B64_MAX) return 0;
    output[position] = '\0'; *written = position; return 1;
}

int chaos_next_use_reserve(struct chaos_next_use_carrier *);
int chaos_next_use_reserve(struct chaos_next_use_carrier *carrier)
{
    struct chaos_next_use_carrier reserved_carrier;
    size_t attempt_bytes, admission_bytes, termination_bytes, needed;
    if (!carrier || carrier->count || carrier->reserved_records ||
        carrier->reserved_bytes) return CHAOS_NEXT_USE_ADMISSION_PRIVATE_CARRIER_RESERVE;
    attempt_bytes = 4096;
    admission_bytes = 16384;
    termination_bytes = 4096;
    needed = attempt_bytes + admission_bytes + termination_bytes;
    if (needed > CHAOS_NEXT_USE_CARRIER_BYTES ||
        CHAOS_NEXT_USE_PRIVATE_RECORDS < 3)
        return CHAOS_NEXT_USE_ADMISSION_PRIVATE_CARRIER_RESERVE;
    reserved_carrier = *carrier;
    if (!reserved_carrier.capacity_bytes)
        reserved_carrier.capacity_bytes = CHAOS_NEXT_USE_CARRIER_BYTES;
    if (!reserved_carrier.capacity_records)
        reserved_carrier.capacity_records = CHAOS_NEXT_USE_PRIVATE_RECORDS;
    if (needed > reserved_carrier.capacity_bytes ||
        3 > reserved_carrier.capacity_records)
        return CHAOS_NEXT_USE_ADMISSION_PRIVATE_CARRIER_RESERVE;
    reserved_carrier.reserved_bytes = needed;
    reserved_carrier.reserved_records = 3;
    *carrier = reserved_carrier;
    return CHAOS_NEXT_USE_ADMISSION_OK;
}

int chaos_next_use_debit(struct chaos_next_use_admission *,
                         const struct chaos_next_use_admission *,
                         int, int, const struct chaos_next_use_envelope *);
int chaos_next_use_debit(struct chaos_next_use_admission *destination,
                         const struct chaos_next_use_admission *source,
                         int sanity, int at_move, const struct chaos_next_use_envelope *envelope)
{
    struct chaos_next_use_admission commit;
    int cost, budget, index, slot;
    if (!destination || !source || !envelope ||
        source->program.phase != CHAOS_ATTEMPT_OPEN ||
        !chaos_state_valid(&source->budget_state) ||
        envelope->operation_count < 1 || envelope->operation_count > 2 ||
        envelope->cost != envelope->operation_count ||
        envelope->at < 0 || envelope->at > 2147483647 ||
        at_move < 0 || at_move > 2147483547 ||
        envelope->id < 1 || envelope->id > 2147483647)
        return CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    cost = envelope->cost;
    budget = chaos_budget(&source->budget_state, sanity);
    if (cost > budget || source->budget_state.spent > CHAOS_BUDGET_CEILING - cost)
        return CHAOS_NEXT_USE_ADMISSION_BUDGET;
    commit = *source;
    if (commit.budget_state.reserved != source->budget_state.reserved)
        return CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    commit.budget_state.spent += cost;
    commit.program.phase = CHAOS_ATTEMPT_COMMITTED;
    commit.program.admitted = 1;
    commit.program.state = 0;
    commit.program.delay_used = 0;
    commit.program.callback_ordinal = 0;
    commit.program.program_id = envelope->id;
    commit.program.program_expiry = at_move + 100;
    commit.program.slot_w = CHAOS_SLOT_UNDECLARED;
    commit.program.slot_f = CHAOS_SLOT_UNDECLARED;
    commit.program.w_runtime = CHAOS_W_INACTIVE;
    for (index = 0; index < envelope->operation_count; ++index) {
        slot = envelope->operations[index];
        if (slot == CHAOS_NEXT_USE_FAMILY_W)
            commit.program.slot_w = CHAOS_SLOT_PENDING;
        else if (slot == CHAOS_NEXT_USE_FAMILY_F)
            commit.program.slot_f = CHAOS_SLOT_PENDING;
        else return CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    }
    *destination = commit;
    return CHAOS_NEXT_USE_ADMISSION_OK;
}

static void admission_apply_detail(struct chaos_next_use_private_record *record,
                                   int kind, int detail)
{
    if (kind == CHAOS_PRIVATE_ATTEMPT)
        record->data.attempt.outcome = detail;
    else if (kind == CHAOS_PRIVATE_TERMINATION) {
        record->data.termination.reason = detail;
        record->data.termination.failure_code =
            detail == CHAOS_TERMINATION_TRANSPORT_FAILURE ?
                CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT : 0;
    }
}

void chaos_next_use_append_private(struct chaos_next_use_carrier *,
                                   const struct chaos_next_use_private_record *,
                                   int, int, int);
void chaos_next_use_append_private(struct chaos_next_use_carrier *carrier,
                                   const struct chaos_next_use_private_record *input,
                                   int kind, int detail, int seq)
{
    struct chaos_next_use_private_record record;
    record = *input;
    record.kind = kind;
    record.seq = seq;
    admission_apply_detail(&record, kind, detail);
    carrier->records[carrier->count++] = record;
}

int chaos_next_use_deliver_receipt(
    chaos_next_use_receipt_fn, void *,
    const struct chaos_next_use_private_record *);
int chaos_next_use_deliver_receipt(
    chaos_next_use_receipt_fn deliver, void *opaque,
    const struct chaos_next_use_private_record *admission)
{
    if (!deliver || !admission || admission->kind != CHAOS_PRIVATE_ADMISSION)
        return 0;
    return deliver(opaque, admission) == 1;
}

static int admission_common(struct chaos_next_use_private_record *record,
                            const struct chaos_next_use_envelope *envelope,
                            int at_move)
{
    if (!record || !envelope || at_move < 0 || at_move > 2147483647) return 0;
    memset(record, 0, sizeof *record);
    record->next_use_private_v = 2;
    record->at_move = at_move;
    record->program_id = envelope->id;
    memcpy(record->source_sha256, envelope->source_sha256, 65);
    return 1;
}

static int admission_record(struct chaos_next_use_private_record *record,
                            const struct chaos_next_use_envelope *envelope,
                            const char *canonical_envelope, size_t envelope_length,
                            int at_move)
{
    unsigned char digest[32];
    int index;
    if (!admission_common(record, envelope, at_move) ||
        !canonical_envelope || !envelope_length || envelope_length > 8192 ||
        chaos_next_use_sha256(canonical_envelope, envelope_length, digest) !=
            CHAOS_NEXT_USE_OK ||
        !admission_base64((const unsigned char *)canonical_envelope,
                          envelope_length,
                          record->data.admission.envelope_b64,
                          &record->data.admission.envelope_b64_length)) return 0;
    record->data.admission.at_safe = envelope->at;
    record->data.admission.cost = envelope->cost;
    record->data.admission.operation_count = envelope->operation_count;
    record->data.admission.program_expiry = at_move + 100;
    for (index = 0; index < envelope->operation_count; ++index) {
        record->data.admission.operations[index] = envelope->operations[index];
        record->data.admission.origin_roots[index] = envelope->origin_refs[index].root;
    }
    admission_digest_hex(digest, record->data.admission.envelope_sha256);
    return 1;
}

int chaos_next_use_admit(struct chaos_next_use_admission *,
                         const struct chaos_next_use_admission *,
                         struct chaos_next_use_attempt_gate *,
                         const struct chaos_next_use_envelope *,
                         const char *, size_t, int, int, int,
                         chaos_next_use_receipt_fn, void *);
int chaos_next_use_admit(struct chaos_next_use_admission *destination,
                         const struct chaos_next_use_admission *source,
                         struct chaos_next_use_attempt_gate *gate,
                         const struct chaos_next_use_envelope *envelope,
                         const char *canonical_envelope, size_t envelope_length,
                         int sanity, int at_move, int base_seq,
                         chaos_next_use_receipt_fn deliver, void *opaque)
{
    enum {
        attempt = CHAOS_PRIVATE_ATTEMPT,
        committed = CHAOS_ATTEMPT_COMMITTED_OUTCOME,
        admission = CHAOS_PRIVATE_ADMISSION,
        termination = CHAOS_PRIVATE_TERMINATION,
        TRANSPORT_FAILURE = CHAOS_TERMINATION_TRANSPORT_FAILURE
    };
    struct chaos_next_use_admission working, commit;
    struct chaos_next_use_private_record attempt_record, admission_value;
    struct chaos_next_use_private_record termination_record;
    int rc, receipt_ok, N;
    if (!gate || gate->phase != CHAOS_ATTEMPT_OPEN)
        return CHAOS_NEXT_USE_ADMISSION_NOT_OPEN;
    gate->phase = CHAOS_ATTEMPT_REJECTED_PRECOMMIT;
    gate->reason = CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    if (!destination || !source || !envelope || !deliver ||
        source->program.phase != CHAOS_ATTEMPT_OPEN ||
        at_move < 0 || at_move > 2147483547 ||
        base_seq < 1 || base_seq > 2147483645 ||
        !canonical_envelope || !envelope_length || envelope_length > 8192)
        return CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    N = base_seq;
    working = *source;
    rc = chaos_next_use_reserve(&working.carrier);
    if (rc != CHAOS_NEXT_USE_ADMISSION_OK) {
        gate->reason = rc;
        return rc;
    }
    rc = chaos_next_use_debit(&commit, &working, sanity, at_move, envelope);
    if (rc != CHAOS_NEXT_USE_ADMISSION_OK) {
        gate->reason = rc;
        return rc;
    }
    if (!admission_common(&attempt_record, envelope, at_move) ||
        !admission_record(&admission_value, envelope,
                          canonical_envelope, envelope_length, at_move) ||
        !admission_common(&termination_record, envelope, at_move))
        return CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    attempt_record.data.attempt.reason = 0;
    chaos_next_use_append_private(&commit.carrier, &attempt_record,
                                  attempt, committed, N);
    chaos_next_use_append_private(&commit.carrier, &admission_value,
                                  admission, 0, N + 1);
    commit.program.next_private_seq = N + 2;
    *destination = commit;
    gate->phase = CHAOS_ATTEMPT_COMMITTED;
    gate->reason = CHAOS_NEXT_USE_ADMISSION_OK;
    receipt_ok = chaos_next_use_deliver_receipt(
        deliver, opaque, &destination->carrier.records[1]);
    if (!receipt_ok) {
        struct chaos_next_use_admission transport;
        transport = *destination;
        if (transport.program.slot_w == CHAOS_SLOT_PENDING)
            transport.program.slot_w = CHAOS_SLOT_TERMINATED_TRANSPORT;
        if (transport.program.slot_f == CHAOS_SLOT_PENDING)
            transport.program.slot_f = CHAOS_SLOT_TERMINATED_TRANSPORT;
        transport.program.w_runtime = CHAOS_W_TRANSPORT_TERMINATED;
        transport.program.phase = CHAOS_ATTEMPT_TERMINATED;
        termination_record.data.termination.slot_w = transport.program.slot_w;
        termination_record.data.termination.slot_f = transport.program.slot_f;
        termination_record.data.termination.w_runtime = transport.program.w_runtime;
        chaos_next_use_append_private(&transport.carrier, &termination_record,
                                      termination, TRANSPORT_FAILURE, N + 2);
        transport.program.next_private_seq = N + 3;
        *destination = transport;
        gate->phase = CHAOS_ATTEMPT_TERMINATED;
        gate->reason = CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT;
        return CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT;
    }
    return CHAOS_NEXT_USE_ADMISSION_OK;
}
