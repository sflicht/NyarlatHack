/* Test-only fixed value wire. Journal bytes are never code. NGPL.
 * Include the unmodified production implementation in this test TU solely for
 * read-only replay-state inspection: exported snapshots describe LIVE state,
 * not the staged validator. No new production setter or replay-state writes.
 */
#include "hack.h"
#include "chaos_next_use_runtime.h"
#include <stdint.h>
#include <limits.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
long moves, monstermoves;
boolean panicking;
/* Same minimal I/O/panic stubs as next_use_replay.c. */
void panic(const char *s, ...) { (void)s; abort(); }
void bwrite(int fd, genericptr_t p, unsigned n) {
    if (write(fd, p, n) != (ssize_t)n) abort();
}
int chaos_next_use_mread(int fd, void *p, unsigned n) {
    return read(fd, p, n) == (ssize_t)n;
}
void mread(int fd, genericptr_t p, unsigned n) {
    if (!chaos_next_use_mread(fd, p, n)) abort();
}
#include "../../src/chaos_next_use_runtime.c"

static int number(FILE *in, uint64_t *v, uint64_t max) {
    unsigned char b[8]; int i;
    if (fread(b, 1, 8, in) != 8) return 0;
    *v = 0;
    for (i = 0; i < 8; ++i) *v = (*v << 8) | b[i];
    return *v <= max;
}
static int text(FILE *in, char *s, size_t cap) {
    uint64_t n;
    if (!number(in, &n, cap - 1) || fread(s, 1, n, in) != n) return 0;
    if (memchr(s, 0, n)) return 0;
    s[n] = 0; return 1;
}
#define GET(field, max) do { if (!number(in, &v, max)) return 0; field = v; } while (0)
static int record_read(FILE *in, struct chaos_next_use_replay_input *r) {
    uint64_t v; int i;
    memset(r, 0, sizeof *r);
    GET(r->replay_input_v, INT_MAX);
    GET(r->expected_last_root, LONG_MAX);
    GET(r->activation_move, LONG_MAX);
    GET(r->notice_root, LONG_MAX);
    GET(r->witness_notice_seq, LONG_MAX);
    GET(r->token_present, INT_MAX);
    GET(r->root_present, INT_MAX);
    GET(r->expected_result, INT_MAX);
    GET(r->published, INT_MAX);
    GET(r->pre_public, INT_MAX);
    GET(r->operation, INT_MAX);
    GET(r->family, INT_MAX);
    GET(r->root, LONG_MAX);
    if (!text(in, r->source_sha256, sizeof r->source_sha256)) return 0;
    GET(r->callback_ordinal, INT_MAX);
    GET(r->state, INT_MAX);
    GET(r->seq, INT_MAX);
    GET(r->slot_w, INT_MAX);
    GET(r->slot_f, INT_MAX);
    GET(r->w_runtime, INT_MAX);
    GET(r->m_id, UINT_MAX);
    GET(r->at_move, LONG_MAX);
    GET(r->fountain_outcome, INT_MAX);
    GET(r->run_token, LONG_MAX);
    GET(r->level_token, LONG_MAX);
    GET(r->origin_w_live, INT_MAX);
    GET(r->origin_f_live, INT_MAX);
    GET(r->whistle_count, INT_MAX);
    GET(r->fountain_count, INT_MAX);
    GET(r->end_reason, INT_MAX);
    GET(r->expected_attention, INT_MAX);
    GET(r->decision_root, LONG_MAX);
    GET(r->cursor, 4096);
    GET(r->manifest_root, LONG_MAX);
    GET(r->notice_seq, LONG_MAX);
    GET(r->end_seq, LONG_MAX);
    GET(r->manifestation_delivered, INT_MAX);
    GET(r->displaced, INT_MAX);
    GET(r->invalid, INT_MAX);
    GET(r->private_count, INT_MAX);
    GET(r->public_count, INT_MAX);
    GET(r->post.phase, INT_MAX);
    GET(r->post.delay_used, INT_MAX);
    GET(r->post.delay_until, INT_MAX);
    GET(r->post.termination_emitted, INT_MAX);
    GET(r->post.identity_unsafe, INT_MAX);
    GET(r->post.pending_w_capture, INT_MAX);
    GET(r->post.f_inflight, INT_MAX);
    GET(r->post.witnessed, INT_MAX);
    GET(r->post.attention_claimed, INT_MAX);
    GET(r->post.callback_w, INT_MAX);
    GET(r->post.callback_f, INT_MAX);
    GET(r->post.whistle_count, INT_MAX);
    GET(r->post.fountain_count, INT_MAX);
    GET(r->post.origin_w_live, INT_MAX);
    GET(r->post.origin_f_live, INT_MAX);
    GET(r->post.manifest_success, INT_MAX);
    GET(r->post.armed_m_id, UINT_MAX);
    GET(r->post.expected_manifest_m_id, UINT_MAX);
    GET(r->post.activation_monstermoves, LONG_MAX);
    GET(r->post.armed_root, LONG_MAX);
    GET(r->post.pending_w_root, LONG_MAX);
    GET(r->post.f_root, LONG_MAX);
    GET(r->post.current_run_token, LONG_MAX);
    GET(r->post.current_level_token, LONG_MAX);
    GET(r->post.expected_manifest_root, LONG_MAX);
    GET(r->post.expected_notice_seq, LONG_MAX);
    GET(r->post.expected_end_seq, LONG_MAX);
    GET(r->expected_token.root, LONG_MAX);
    GET(r->expected_token.active, INT_MAX);
    GET(r->expected_token.remap, INT_MAX);
    GET(r->expected_token.consumed, INT_MAX);
    if (r->private_count > 4 || r->public_count > 1) return 0;
    for (i = 0; i < r->private_count; ++i) {
        struct chaos_next_use_runtime_private_record *p = &r->private_records[i];
    GET(p->next_use_private_v, INT_MAX);
    GET(p->kind, INT_MAX);
    GET(p->seq, INT_MAX);
    GET(p->at_move, INT_MAX);
    GET(p->program_id, INT_MAX);
    if (!text(in, p->source_sha256, sizeof p->source_sha256)) return 0;
        switch (p->kind) {
        case 3:
    GET(p->data.intent.callback_ordinal, INT_MAX);
    GET(p->data.intent.trigger, INT_MAX);
    GET(p->data.intent.validation, INT_MAX);
    GET(p->data.intent.failure_code, INT_MAX);
    GET(p->data.intent.root, LONG_MAX);
    GET(p->data.intent.state_before, INT_MAX);
    GET(p->data.intent.state_after, INT_MAX);
    GET(p->data.intent.delay_used_after, INT_MAX);
    if (!text(in, p->data.intent.context_sha256, sizeof p->data.intent.context_sha256)) return 0;
    GET(p->data.intent.intent_present, INT_MAX);
    if (!text(in, p->data.intent.intent_sha256, sizeof p->data.intent.intent_sha256)) return 0;
    GET(p->data.intent.intent_sha256_present, INT_MAX);
    GET(p->data.intent.failure_code_present, INT_MAX);
    GET(p->data.intent.intent.op, INT_MAX);
    GET(p->data.intent.intent.state, INT_MAX);
            break;
        case 4:
    GET(p->data.effect.family, INT_MAX);
    GET(p->data.effect.outcome, INT_MAX);
    GET(p->data.effect.root, LONG_MAX);
    GET(p->data.effect.activation_monstermoves, LONG_MAX);
    GET(p->data.effect.m_id, UINT_MAX);
            break;
        case 5:
    GET(p->data.termination.failure_code, INT_MAX);
    GET(p->data.termination.reason, INT_MAX);
    GET(p->data.termination.slot_f, INT_MAX);
    GET(p->data.termination.slot_w, INT_MAX);
    GET(p->data.termination.w_runtime, INT_MAX);
            break;
        default: return 0;
        }
    }
    for (i = 0; i < r->public_count; ++i) {
        struct chaos_next_use_public_record *p = &r->public_records[i];
    GET(p->next_use_public_v, INT_MAX);
    GET(p->family, INT_MAX);
    GET(p->phase, INT_MAX);
    GET(p->root, LONG_MAX);
    GET(p->notice_seq, LONG_MAX);
    GET(p->end_seq, LONG_MAX);
    }
    return 1;
}
static int load_snapshot(const char *name, struct chaos_next_use_snapshot *s) {
    int fd = open(name, O_RDONLY), ok; unsigned char extra;
    if (fd < 0) return 0;
    ok = chaos_next_use_snapshot_read(fd, s) && read(fd, &extra, 1) == 0;
    close(fd); return ok;
}
/* Compare every persistent gameplay value against the ACCEPTED replay prefix.
 * The actual saved OPEN journal anchor is separately checked against its exact
 * trusted prefix before this process starts; the validator has no writer.
 * Import uses that original anchor verbatim, not a fabricated NONE/COMPLETE.
 */
static int checkpoint_equal(const struct chaos_next_use_snapshot *s) {
    if (s->program_id != replay_runtime.program_id) { fprintf(stderr, "checkpoint program_id\n"); return 0; }
    if (s->phase != replay_runtime.phase) { fprintf(stderr, "checkpoint phase\n"); return 0; }
    if (s->slot_w != replay_runtime.slot_w) { fprintf(stderr, "checkpoint slot_w\n"); return 0; }
    if (s->slot_f != replay_runtime.slot_f) { fprintf(stderr, "checkpoint slot_f\n"); return 0; }
    if (s->w_runtime != replay_runtime.w_runtime) { fprintf(stderr, "checkpoint w_runtime\n"); return 0; }
    if (s->state != replay_runtime.state) { fprintf(stderr, "checkpoint state\n"); return 0; }
    if (s->delay_used != replay_runtime.delay_used) { fprintf(stderr, "checkpoint delay_used\n"); return 0; }
    if (s->callback_ordinal != replay_runtime.callback_ordinal) { fprintf(stderr, "checkpoint callback_ordinal\n"); return 0; }
    if (s->witnessed != replay_runtime.witnessed) { fprintf(stderr, "checkpoint witnessed\n"); return 0; }
    if (s->attention_claimed != replay_runtime.attention_claimed) { fprintf(stderr, "checkpoint attention_claimed\n"); return 0; }
    if (s->whistle_count != replay_runtime.whistle_count) { fprintf(stderr, "checkpoint whistle_count\n"); return 0; }
    if (s->fountain_count != replay_runtime.fountain_count) { fprintf(stderr, "checkpoint fountain_count\n"); return 0; }
    if (s->next_seq != replay_runtime.next_seq) { fprintf(stderr, "checkpoint next_seq\n"); return 0; }
    if (s->termination_emitted != replay_runtime.termination_emitted) { fprintf(stderr, "checkpoint termination_emitted\n"); return 0; }
    if (s->identity_unsafe != replay_runtime.identity_unsafe) { fprintf(stderr, "checkpoint identity_unsafe\n"); return 0; }
    if (s->callback_w != replay_runtime.callback_w) { fprintf(stderr, "checkpoint callback_w\n"); return 0; }
    if (s->callback_f != replay_runtime.callback_f) { fprintf(stderr, "checkpoint callback_f\n"); return 0; }
    if (s->last_root != replay_runtime.last_root) { fprintf(stderr, "checkpoint last_root\n"); return 0; }
    if (s->admission_move != replay_runtime.admission_move) { fprintf(stderr, "checkpoint admission_move\n"); return 0; }
    if (s->program_expiry != replay_runtime.program_expiry) { fprintf(stderr, "checkpoint program_expiry\n"); return 0; }
    if (s->delay_until != replay_runtime.delay_until) { fprintf(stderr, "checkpoint delay_until\n"); return 0; }
    if (s->variant != replay_runtime.variant) { fprintf(stderr, "checkpoint variant\n"); return 0; }
    if (s->origin_w_live != replay_runtime.origin_w_live) { fprintf(stderr, "checkpoint origin_w_live\n"); return 0; }
    if (s->origin_f_live != replay_runtime.origin_f_live) { fprintf(stderr, "checkpoint origin_f_live\n"); return 0; }
    if (s->armed_m_id != replay_runtime.armed_m_id) { fprintf(stderr, "checkpoint armed_m_id\n"); return 0; }
    if (s->replay_cursor != replay_runtime.replay_cursor) { fprintf(stderr, "checkpoint replay_cursor\n"); return 0; }
    if (s->origin_w != replay_runtime.origin_w) { fprintf(stderr, "checkpoint origin_w\n"); return 0; }
    if (s->origin_f != replay_runtime.origin_f) { fprintf(stderr, "checkpoint origin_f\n"); return 0; }
    if (s->origin_w_deadline != replay_runtime.origin_w_deadline) { fprintf(stderr, "checkpoint origin_w_deadline\n"); return 0; }
    if (s->origin_f_deadline != replay_runtime.origin_f_deadline) { fprintf(stderr, "checkpoint origin_f_deadline\n"); return 0; }
    if (s->run_token != replay_runtime.run_token) { fprintf(stderr, "checkpoint run_token\n"); return 0; }
    if (s->level_token != replay_runtime.level_token) { fprintf(stderr, "checkpoint level_token\n"); return 0; }
    if (s->activation_monstermoves != replay_runtime.activation_monstermoves) { fprintf(stderr, "checkpoint activation_monstermoves\n"); return 0; }
    if (s->armed_root != replay_runtime.armed_root) { fprintf(stderr, "checkpoint armed_root\n"); return 0; }
    if (s->source_length != replay_runtime.source_length) { fprintf(stderr, "checkpoint source_length\n"); return 0; }
    return !strcmp(s->source_sha256, replay_runtime.source_sha256)
        && !strcmp(s->binding_sha256, replay_runtime.binding_sha256)
        && !memcmp(s->source, replay_runtime.source, s->source_length)
        && !replay_runtime.pending_w_capture && !replay_runtime.f_inflight
        && !replay_runtime.defer_termination
        && s->journal_state == CHAOS_JOURNAL_OPEN && !s->capture_incomplete;
}
int main(int argc, char **argv) {
    struct chaos_next_use_snapshot initial, middle;
    struct chaos_next_use_replay_input record;
    struct runtime_state before, live_before;
    uint64_t count, n;
    FILE *in; char magic[6]; int checkpoints = 0, terminal;
    if (argc != 4 || !load_snapshot(argv[1], &initial)
        || !load_snapshot(argv[2], &middle)
        || !chaos_next_use_snapshot_import(&initial)) return 2;
    in = fopen(argv[3], "rb");
    if (!in || fread(magic, 1, 6, in) != 6 || memcmp(magic, "NUSP1", 6)
        || !number(in, &count, 4096) || !count) return 2;
    for (n = 0; n < count; ++n) {
        if (!record_read(in, &record)) return 2;
        /* Clock values are inputs, NOT an independent clock oracle. Python
         * binds them to retained native input-boundary clock intervals. */
        monstermoves = record.at_move;
        before = replay_runtime; live_before = live_runtime;
        if (chaos_next_use_replay_record(&record) != CHAOS_REPLAY_APPLIED) {
            int unchanged = !memcmp(&before, &replay_runtime, sizeof before)
                && !memcmp(&live_before, &live_runtime, sizeof live_before);
            const char *reason = "private_or_public_carrier_mismatch";
            if (record.cursor != before.replay_cursor + 1) reason = "cursor";
            else if (record.state != staged_runtime.state)
                reason = "source_dependent_next_state";
            else if (!replay_post_equal(&record.post, &staged_runtime))
                reason = "poststate";
            printf("{\"accepted\":%lu,\"cursor\":%lu,\"rejected_cursor\":%lu,"
                   "\"operation\":%d,\"reason\":\"%s\",\"unchanged\":%d}\n",
                   (unsigned long)n, before.replay_cursor, record.cursor,
                   record.operation, reason, unchanged);
            fclose(in); return unchanged ? 1 : 2;
        }
        if (record.cursor == middle.replay_cursor) {
            if (!checkpoint_equal(&middle)
                || !chaos_next_use_snapshot_import(&middle)) return 2;
            ++checkpoints;
        }
    }
    if (fgetc(in) != EOF) return 2;
    fclose(in);
    terminal = replay_runtime.phase == CHAOS_ATTEMPT_TERMINATED
        && replay_runtime.termination_emitted && !replay_runtime.pending_w_capture
        && !replay_runtime.f_inflight && replay_runtime.slot_w != CHAOS_SLOT_W_PENDING
        && replay_runtime.slot_f != CHAOS_SLOT_F_PENDING
        && replay_runtime.w_runtime != CHAOS_W_RUNTIME_ARMED;
    printf("{\"accepted\":%lu,\"cursor\":%lu,\"checkpoints\":%d,\"terminal\":%d}\n",
           (unsigned long)count, replay_runtime.replay_cursor, checkpoints, terminal);
    return terminal && checkpoints == 1 ? 0 : 2;
}
