/* NetHack General Public License. Atomic next-use admission and carrier. */
#ifndef CHAOS_NEXT_USE_ADMISSION_H
#define CHAOS_NEXT_USE_ADMISSION_H

#include <stddef.h>
#include "chaos_next_use.h"
#include "chaos_protocol.h"

#define CHAOS_NEXT_USE_PRIVATE_RECORDS 3
#define CHAOS_NEXT_USE_PRIVATE_MAX 16384
#define CHAOS_NEXT_USE_ENVELOPE_B64_MAX 10924
#define CHAOS_NEXT_USE_CARRIER_BYTES (4096 + 16384 + 4096)

enum chaos_next_use_admission_status {
    CHAOS_NEXT_USE_ADMISSION_OK = 0,
    CHAOS_NEXT_USE_ADMISSION_SCHEMA,
    CHAOS_NEXT_USE_ADMISSION_NOT_OPEN,
    CHAOS_NEXT_USE_ADMISSION_PRIVATE_CARRIER_RESERVE,
    CHAOS_NEXT_USE_ADMISSION_BUDGET,
    CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT
};

enum chaos_next_use_attempt_phase {
    CHAOS_ATTEMPT_OPEN = 0,
    CHAOS_ATTEMPT_ABSTAINED,
    CHAOS_ATTEMPT_REJECTED_PRECOMMIT,
    CHAOS_ATTEMPT_COMMITTED,
    CHAOS_ATTEMPT_TERMINATED
};

enum chaos_next_use_slot {
    CHAOS_SLOT_UNDECLARED = 0,
    CHAOS_SLOT_PENDING,
    CHAOS_SLOT_CONSUMED_ARMED,
    CHAOS_SLOT_CONSUMED_APPLIED,
    CHAOS_SLOT_CONSUMED_NONREMAPPABLE,
    CHAOS_SLOT_CONSUMED_QUIET,
    CHAOS_SLOT_CONSUMED_DELAY,
    CHAOS_SLOT_CONSUMED_INVALID,
    CHAOS_SLOT_CONSUMED_SUPPRESSED,
    CHAOS_SLOT_TERMINATED_EXPIRY,
    CHAOS_SLOT_TERMINATED_LEVEL,
    CHAOS_SLOT_TERMINATED_TRANSPORT
};

enum chaos_next_use_w_runtime {
    CHAOS_W_INACTIVE = 0,
    CHAOS_W_ARMED,
    CHAOS_W_WINDOW_ENDED,
    CHAOS_W_EXPIRED,
    CHAOS_W_DEPARTED,
    CHAOS_W_IDENTITY_UNSAFE,
    CHAOS_W_INVALID_TERMINATED,
    CHAOS_W_TRANSPORT_TERMINATED
};

enum chaos_next_use_private_kind {
    CHAOS_PRIVATE_ATTEMPT = 1,
    CHAOS_PRIVATE_ADMISSION,
    CHAOS_PRIVATE_TERMINATION
};

enum chaos_next_use_attempt_outcome {
    CHAOS_ATTEMPT_COMMITTED_OUTCOME = 1
};

enum chaos_next_use_termination_reason {
    CHAOS_TERMINATION_TRANSPORT_FAILURE = 1
};

struct chaos_next_use_attempt_gate {
    int phase;
    int reason;
};

struct chaos_next_use_program {
    int phase;
    int slot_w;
    int slot_f;
    int w_runtime;
    int admitted;
    int state;
    int delay_used;
    int callback_ordinal;
    int program_id;
    int next_private_seq;
    int program_expiry;
};

struct chaos_next_use_private_record {
    int next_use_private_v;
    int kind;
    int seq;
    int at_move;
    int program_id;
    char source_sha256[65];
    union {
        struct { int outcome; int reason; } attempt;
        struct {
            int at_safe;
            int cost;
            int operation_count;
            int operations[2];
            int origin_roots[2];
            int program_expiry;
            size_t envelope_b64_length;
            char envelope_b64[CHAOS_NEXT_USE_ENVELOPE_B64_MAX + 1];
            char envelope_sha256[65];
        } admission;
        struct {
            int failure_code;
            int reason;
            int slot_f;
            int slot_w;
            int w_runtime;
        } termination;
    } data;
};

struct chaos_next_use_carrier {
    size_t capacity_bytes;
    size_t reserved_bytes;
    int capacity_records;
    int reserved_records;
    int count;
    struct chaos_next_use_private_record records[CHAOS_NEXT_USE_PRIVATE_RECORDS];
};

struct chaos_next_use_admission {
    struct chaos_state budget_state;
    struct chaos_next_use_program program;
    struct chaos_next_use_carrier carrier;
};

typedef int (*chaos_next_use_receipt_fn)(
    void *, const struct chaos_next_use_private_record *);

int chaos_next_use_reserve(struct chaos_next_use_carrier *);
int chaos_next_use_debit(struct chaos_next_use_admission *,
                          const struct chaos_next_use_admission *,
                          int, int, const struct chaos_next_use_envelope *);
int chaos_next_use_admit(struct chaos_next_use_admission *,
                         const struct chaos_next_use_admission *,
                         struct chaos_next_use_attempt_gate *,
                         const struct chaos_next_use_envelope *,
                         const char *, size_t, int, int, int,
                         chaos_next_use_receipt_fn, void *);
void chaos_next_use_append_private(struct chaos_next_use_carrier *,
                                   const struct chaos_next_use_private_record *,
                                   int, int, int);
int chaos_next_use_deliver_receipt(
    chaos_next_use_receipt_fn, void *,
    const struct chaos_next_use_private_record *);

#endif
