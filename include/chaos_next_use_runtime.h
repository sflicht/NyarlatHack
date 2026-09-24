/* NetHack General Public License. Unsaved next-use runtime and replay state. */
#ifndef CHAOS_NEXT_USE_RUNTIME_H
#define CHAOS_NEXT_USE_RUNTIME_H

#include <stddef.h>
#include "chaos_next_use.h"
#include "chaos_next_use_admission.h"
#include "chaos_next_use_contract.h"

struct chaos_whistle_witness;

enum chaos_next_use_slot_w {
    CHAOS_SLOT_W_UNDECLARED = 0,
    CHAOS_SLOT_W_PENDING,
    CHAOS_SLOT_W_CONSUMED_ARMED,
    CHAOS_SLOT_W_CONSUMED_QUIET,
    CHAOS_SLOT_W_CONSUMED_DELAY,
    CHAOS_SLOT_W_CONSUMED_INVALID,
    CHAOS_SLOT_W_CONSUMED_SUPPRESSED,
    CHAOS_SLOT_W_TERMINATED_EXPIRY,
    CHAOS_SLOT_W_TERMINATED_LEVEL,
    /* Admission receipt failure only; no live-runtime transport setter. */
    CHAOS_SLOT_W_TERMINATED_TRANSPORT
};

enum chaos_next_use_slot_f {
    CHAOS_SLOT_F_UNDECLARED = 0,
    CHAOS_SLOT_F_PENDING,
    CHAOS_SLOT_F_CONSUMED_APPLIED,
    CHAOS_SLOT_F_CONSUMED_NONREMAPPABLE,
    CHAOS_SLOT_F_CONSUMED_QUIET,
    CHAOS_SLOT_F_CONSUMED_DELAY,
    CHAOS_SLOT_F_CONSUMED_INVALID,
    CHAOS_SLOT_F_CONSUMED_SUPPRESSED,
    CHAOS_SLOT_F_TERMINATED_EXPIRY,
    CHAOS_SLOT_F_TERMINATED_LEVEL,
    CHAOS_SLOT_F_TERMINATED_TRANSPORT
};

enum chaos_next_use_w_runtime_state {
    CHAOS_W_RUNTIME_INACTIVE = 0,
    CHAOS_W_RUNTIME_ARMED,
    CHAOS_W_RUNTIME_WINDOW_ENDED,
    CHAOS_W_RUNTIME_EXPIRED,
    CHAOS_W_RUNTIME_DEPARTED,
    CHAOS_W_RUNTIME_IDENTITY_UNSAFE,
    CHAOS_W_RUNTIME_INVALID_TERMINATED,
    CHAOS_W_RUNTIME_TRANSPORT_TERMINATED
};

enum chaos_next_use_end_reason {
    CHAOS_END_WINDOW_A_PLUS_10 = 1,
    CHAOS_END_LEVEL_DEPARTURE,
    CHAOS_END_ORIGIN_EVICTED,
    CHAOS_END_ORIGIN_EXPIRED,
    CHAOS_END_PROGRAM_EXPIRED,
    CHAOS_END_INVALID_CALLBACK,
    CHAOS_END_IDENTITY_UNSAFE
};

enum chaos_next_use_intent_failure_code {
    CHAOS_INTENT_FAILURE_WRONG_FAMILY = 7,
    CHAOS_INTENT_FAILURE_SECOND_DELAY = 8
};

enum chaos_next_use_record_kind {
    CHAOS_RUNTIME_PRIVATE_ATTEMPT = 1,
    CHAOS_RUNTIME_PRIVATE_ADMISSION,
    CHAOS_RUNTIME_PRIVATE_INTENT,
    CHAOS_RUNTIME_PRIVATE_EFFECT,
    CHAOS_RUNTIME_PRIVATE_TERMINATION
};

enum chaos_next_use_effect_outcome {
    CHAOS_EFFECT_W_ARMED = 1,
    CHAOS_EFFECT_W_CAPTURE_SUPPRESSED,
    CHAOS_EFFECT_W_WITNESSED,
    CHAOS_EFFECT_W_ENDED_AFTER_WITNESS,
    CHAOS_EFFECT_W_ENDED_NO_WITNESS,
    CHAOS_EFFECT_W_IDENTITY_UNSAFE,
    CHAOS_EFFECT_F_NATURAL,
    CHAOS_EFFECT_F_EARLY_RETURN,
    CHAOS_EFFECT_F_NATIVE_19_30,
    CHAOS_EFFECT_F_DEFAULT_WITHOUT_INTENT,
    CHAOS_EFFECT_F_GUARD_SUPPRESSED,
    CHAOS_EFFECT_F_REMAPPED
};

enum chaos_next_use_public_phase {
    CHAOS_PUBLIC_WITNESSED = 1
};

enum chaos_next_use_replay_operation {
    CHAOS_REPLAY_ACTION = 1,
    CHAOS_REPLAY_W_UNAVAILABLE = 2,
    CHAOS_REPLAY_W_CAPTURE = 3,
    CHAOS_REPLAY_W_DECISION = 4,
    CHAOS_REPLAY_W_MANIFEST = 5,
    CHAOS_REPLAY_F_RESULT = 6,
    CHAOS_REPLAY_BOUNDARY = 7,
    CHAOS_REPLAY_EXPIRE = 8,
    CHAOS_REPLAY_W_READY = 9,
    CHAOS_REPLAY_W_NO_ROOT = 10,
    CHAOS_REPLAY_IDENTITY_MARK = 11,
    CHAOS_REPLAY_IDENTITY_TAKE = 12,
    CHAOS_REPLAY_END_W = 13
};

enum chaos_next_use_replay_status {
    CHAOS_REPLAY_APPLIED = 0,
    CHAOS_REPLAY_BLOCKED_REPLAY = 1
};

struct chaos_next_use_runtime_private_record {
    int next_use_private_v;
    int kind;
    int seq;
    int at_move;
    int program_id;
    char source_sha256[65];
    union {
        struct { int outcome, reason, reason_present; } attempt;
        struct { int at_safe, cost, operation_count;
                 int operations[2]; long origin_roots[2];
                 int program_expiry; char envelope_b64[10925];
                 char envelope_sha256[65]; } admission;
        struct { int callback_ordinal, trigger, validation, failure_code;
                 long root; int state_before, state_after, delay_used_after;
                 char context_sha256[65]; int intent_present;
                 struct chaos_next_use_intent intent; char intent_sha256[65];
                 int intent_sha256_present, failure_code_present; } intent;
        struct { int family, outcome; long root, activation_monstermoves;
                 unsigned m_id; } effect;
        struct { int failure_code, reason, slot_f, slot_w, w_runtime; } termination;
    } data;
};

struct chaos_next_use_public_record {
    int next_use_public_v;
    int family;
    int phase;
    long root;
    long notice_seq;
    long end_seq;
};

struct chaos_next_use_termination {
    int failure_code;
    int reason;
    int slot_f;
    int slot_w;
    int w_runtime;
};

/* Production replay accepts v1 only: inputs, poststate and publication evidence.
 * Historical v0 component fixtures require an explicit TEST-ONLY entry point.
 * Neither version is a disk codec; never serialize these structs as raw bytes. */
#define CHAOS_NEXT_USE_REPLAY_INPUT_V 1
struct chaos_next_use_replay_poststate {
    int phase, delay_used, delay_until, termination_emitted, identity_unsafe;
    int pending_w_capture, f_inflight, witnessed, attention_claimed;
    int callback_w, callback_f, whistle_count, fountain_count;
    int origin_w_live, origin_f_live, manifest_success;
    unsigned armed_m_id, expected_manifest_m_id;
    long activation_monstermoves, armed_root, pending_w_root, f_root;
    long current_run_token, current_level_token;
    long expected_manifest_root, expected_notice_seq, expected_end_seq;
};

struct chaos_next_use_replay_input {
    int replay_input_v;
    long expected_last_root, activation_move, notice_root, witness_notice_seq;
    int token_present, root_present, expected_result, published, pre_public;
    /* ACTION token is output-only; absent/unsuccessful output is canonical zero. */
    struct chaos_next_use_replay_poststate post;
    int operation;
    int family;
    long root;
    char source_sha256[65];
    int callback_ordinal;
    int state;
    int seq;
    int slot_w;
    int slot_f;
    int w_runtime;
    unsigned m_id;
    long at_move;
    int fountain_outcome;
    long run_token, level_token;
    int origin_w_live, origin_f_live;
    int whistle_count, fountain_count;
    int end_reason;
    int expected_attention;
    long decision_root;
    unsigned long cursor;
    long manifest_root, notice_seq, end_seq;
    int manifestation_delivered, displaced, invalid;
    struct chaos_fountain_token expected_token;
    int private_count;
    struct chaos_next_use_runtime_private_record private_records[4];
    int public_count;
    struct chaos_next_use_public_record public_records[1];
};

/* Synchronous borrowed record, valid only during the callback. A nonzero
 * acknowledgement commits the cursor, NOT a promise of disk durability.
 * Subscriber must not mutate the live runtime or retain the borrowed pointer.
 * Configuration survives runtime reset; incompleteness latches until reset.
 * Attaching after a missed transition cannot repair an incomplete prefix. */
typedef int (*chaos_next_use_capture_sink)(
    void *, const struct chaos_next_use_replay_input *);
struct chaos_next_use_capture_status {
    int sink_connected, incomplete, transaction_open;
    unsigned long acknowledged_cursor;
};
void chaos_next_use_capture_set_sink(chaos_next_use_capture_sink, void *);
void chaos_next_use_capture_status(struct chaos_next_use_capture_status *);
/* Trace transport failure only: never terminalize/rollback the game. */
void chaos_next_use_capture_fail(void);
/* Called by native finalization after observation finish, even on failure. */
void chaos_next_use_manifestation_complete(const struct chaos_whistle_witness *,
                                          long end_seq, int published);

int chaos_next_use_runtime_install(const struct chaos_next_use_admission *admission,
                                   const char *source, size_t source_length,
                                   const char source_sha256[65], long run_token,
                                   long level_token,
                                   long origin_w, long origin_w_deadline,
                                   long origin_f, long origin_f_deadline,
                                   int variant, int whistle_count,
                                   int fountain_count);
void chaos_next_use_runtime_boundary(long run_token, long level_token,
                                     int origin_w_live, int origin_f_live,
                                     int whistle_count, int fountain_count);
void chaos_next_use_runtime_reset(void);
size_t chaos_next_use_runtime_private_count(void);
const struct chaos_next_use_runtime_private_record *
chaos_next_use_runtime_private_at(size_t index);
size_t chaos_next_use_runtime_public_count(void);
const struct chaos_next_use_public_record *
chaos_next_use_runtime_public_at(size_t index);
boolean chaos_next_use_action_preflight(int family, long completed_root);
boolean chaos_next_use_on_action(int family, long completed_root,
                                 struct chaos_fountain_token *token_out);
void chaos_next_use_end_w(enum chaos_next_use_end_reason reason,
                          const long *current_root_or_null);
void chaos_next_use_on_manifestation(const struct chaos_whistle_witness *witness,
                                     long end_seq);
void chaos_next_use_expire(enum chaos_next_use_end_reason reason);
/* Strict v1; record-controlled version fallback is forbidden. */
int chaos_next_use_replay_record(const struct chaos_next_use_replay_input *record);
#ifdef CHAOS_NEXT_USE_TEST_LEGACY_REPLAY
/* Only old in-memory component fixtures; rejects v1 and publication operations. */
int chaos_next_use_replay_legacy_fixture(const struct chaos_next_use_replay_input *record);
#endif
void chaos_next_use_mark_identity_unsafe(void);
int chaos_next_use_take_identity_unsafe(void);
void chaos_next_use_whistle_unavailable(long completed_root);
void chaos_next_use_capture_whistle(long completed_root, unsigned m_id,
                                    long at_move);
boolean chaos_next_use_whistle_decision_ready(unsigned m_id);
void chaos_next_use_whistle_no_root(unsigned m_id);
boolean chaos_next_use_whistle_attention(unsigned m_id, long decision_root);
boolean chaos_next_use_manifestation_begin(unsigned m_id, long root);
void chaos_next_use_manifestation_notice(long root, long notice_seq);
void chaos_next_use_manifestation_end(long root, long notice_seq,
                                      long end_seq, int success);
unsigned chaos_next_use_armed_reserved_identity(void);
long chaos_next_use_fountain_completed_root(void);
void chaos_next_use_fountain_result(const struct chaos_fountain_token *token,
                                    int outcome);

#define CHAOS_NEXT_USE_SNAPSHOT_V 4

struct chaos_next_use_snapshot {
    int snapshot_v;
    int program_id;
    int phase;
    int slot_w, slot_f, w_runtime;
    int state, delay_used, callback_ordinal;
    int witnessed, attention_claimed, whistle_count, fountain_count;
    int next_seq, termination_emitted, identity_unsafe;
    int callback_w, callback_f;
    long last_root;
    int admission_move, program_expiry, delay_until, variant;
    int origin_w_live, origin_f_live;
    unsigned armed_m_id;
    unsigned long replay_cursor;
    long origin_w, origin_f;
    long origin_w_deadline, origin_f_deadline;
    long run_token, level_token;
    long activation_monstermoves, armed_root;
    size_t source_length;
    char source_sha256[65];
    char binding_sha256[65];
    char source[CHAOS_NEXT_USE_SOURCE_MAX + 1];
};

int chaos_next_use_snapshot_export(struct chaos_next_use_snapshot *);
int chaos_next_use_snapshot_validate(const struct chaos_next_use_snapshot *);
int chaos_next_use_snapshot_import(const struct chaos_next_use_snapshot *);
long chaos_next_use_runtime_run_token(void);
int chaos_next_use_snapshot_write(int fd, const struct chaos_next_use_snapshot *);
int chaos_next_use_snapshot_read(int fd, struct chaos_next_use_snapshot *);
int chaos_next_use_save_status(void);
int chaos_next_use_save(int fd);
int chaos_next_use_restore(int fd);
int chaos_next_use_restore_bound(int fd, long run_token, long level_token);

#endif
