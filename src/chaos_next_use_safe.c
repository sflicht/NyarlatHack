/* NetHack General Public License. Opt-in next-use admission at a safe point. */
#define _GNU_SOURCE
#include "hack.h"
#include "chaos_lua.h"
#include "chaos_next_use.h"
#include "chaos_next_use_io.h"
#include "chaos_next_use_runtime.h"
#include "chaos_next_use_safe.h"
#include "chaos_next_use_journal.h"

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>

/* The game-owned state is the save authority, including rejected attempts.
 * legacy_closed supports snapshot-only component fixtures, not native saves. */
static struct chaos_state *policy_state;
static int legacy_closed, resume_pending, resume_failed;
static char owned_run[65];
static int owned_run_set;
static int (*owned_warn)(void *, const char *);
static void *owned_warn_opaque;
int chaos_next_use_companion_in_view(void *) __attribute__((weak));
static int (*owned_companion)(void *);
static void *owned_companion_opaque;
static chaos_next_use_receipt_fn owned_receipt;
static void *owned_receipt_opaque;
static struct {
    int bound;
    int qualifying;
    struct chaos_next_use_origin_ref origin;
} origin_evidence[2];
static long logical_run;
static struct chaos_next_use_safe_result last_result;
static int last_at;

void chaos_next_use_safe_bind_logical(long run_token)
{
    logical_run = run_token > 0 ? run_token : 0;
}

void chaos_next_use_safe_reset_for_test(void)
{
    chaos_next_use_journal_reset();
    policy_state = NULL;
    chaos_next_use_history_reset();
    legacy_closed = resume_pending = resume_failed = 0;
    owned_run_set = 0;
    logical_run = 0;
    owned_run[0] = '\0';
    owned_warn = 0;
    owned_warn_opaque = 0;
    owned_companion = 0;
    owned_companion_opaque = 0;
    owned_receipt = 0;
    owned_receipt_opaque = 0;
    memset(origin_evidence, 0, sizeof origin_evidence);
    memset(&last_result, 0, sizeof last_result);
    last_at = 0;
    chaos_next_use_runtime_reset();
}

void chaos_next_use_safe_bind_run(const char *run_hex)
{
    int i;
    owned_run_set = 0;
    owned_run[0] = '\0';
    if (!run_hex) return;
    for (i = 0; i < 64; ++i) {
        char c = run_hex[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')))
            return;
        owned_run[i] = c;
    }
    if (run_hex[64] != '\0') return;
    owned_run[64] = '\0';
    owned_run_set = 1;
}

void chaos_next_use_safe_bind_telegraph(int (*fn)(void *, const char *), void *opaque)
{
    owned_warn = fn;
    owned_warn_opaque = opaque;
}

void chaos_next_use_safe_bind_companion(int (*fn)(void *), void *opaque)
{
    owned_companion = fn;
    owned_companion_opaque = opaque;
}

void chaos_next_use_safe_bind_receipt(chaos_next_use_receipt_fn fn, void *opaque)
{
    owned_receipt = fn;
    owned_receipt_opaque = opaque;
}

void chaos_next_use_safe_bind_origin(const struct chaos_next_use_origin_ref *origin,
                                    int qualifying)
{
    int slot;

    if (!origin) return;
    if (origin->family == CHAOS_NEXT_USE_FAMILY_W) slot = 0;
    else if (origin->family == CHAOS_NEXT_USE_FAMILY_F) slot = 1;
    else return;
    origin_evidence[slot].origin = *origin;
    origin_evidence[slot].bound = 1;
    origin_evidence[slot].qualifying = qualifying ? 1 : 0;
}

int chaos_next_use_safe_attempted(void)
{
    return legacy_closed || (policy_state && policy_state->next_use_count > 0);
}

int chaos_next_use_safe_restore_attempted(int attempted)
{
    if ((attempted != 0 && attempted != 1)
        || (!attempted && chaos_next_use_runtime_run_token() > 0))
        return 0;
    if (attempted || chaos_next_use_runtime_run_token() > 0)
        resume_pending = 1;
    legacy_closed = attempted;
    return 1;
}

void chaos_next_use_safe_mark_restored(void)
{
    resume_pending = 1;
    legacy_closed = 1;
}

void chaos_next_use_safe_resume(int dir)
{
    if (!resume_pending) return;
    resume_failed = !chaos_next_use_journal_resume(dir);
    resume_pending = 0;
}

int chaos_next_use_safe_restore_state(struct chaos_state *state, int attempted)
{
    struct chaos_next_use_snapshot snapshot;
    if (!chaos_state_valid(state) || (attempted != 0 && attempted != 1)
        || attempted != (state->next_use_count > 0)
        || state->next_use_count != chaos_next_use_program_ordinal()) return 0;
    memset(&snapshot, 0, sizeof snapshot);
    if (chaos_next_use_runtime_run_token() > 0
        && !chaos_next_use_snapshot_export(&snapshot)) return 0;
    if (snapshot.run_token > 0
        && (!state->next_use_count || state->next_use_id != snapshot.program_id
            || state->next_use_terminal != !!snapshot.termination_emitted)) return 0;
    if (state->next_use_count && !state->next_use_terminal
        && snapshot.run_token <= 0) return 0;
    policy_state = state;
    legacy_closed = 0;
    resume_pending = attempted;
    return 1;
}

/* Called only by the live runtime's terminal transition, never replay. The
 * event stream counter already includes the observation causing termination. */
void chaos_next_use_safe_terminal(int program_id)
{
    if (policy_state && policy_state->next_use_count
        && policy_state->next_use_id == program_id
        && !policy_state->next_use_terminal) {
        policy_state->next_use_terminal = 1;
        policy_state->next_use_terminal_seq = policy_state->seq;
    }
}

/* Policy predicate for sequential journal-backed programs.
 * COMPLETE is the durable writer acknowledgement, not just terminal mechanics. */
int chaos_next_use_safe_opportunity(const struct chaos_state *state,
                                    long completed_seq)
{
    struct chaos_next_use_snapshot snapshot;
    if (!chaos_state_valid(state) || completed_seq <= 0
        || completed_seq > state->seq
        || state->next_use_count >= CHAOS_NEXT_USE_PROGRAM_CAP) return 0;
    if (!state->next_use_count) return chaos_next_use_runtime_run_token() == 0;
    if (!state->next_use_terminal
        || completed_seq <= state->next_use_terminal_seq) return 0;
    if (!chaos_next_use_runtime_run_token()) return 1; /* rejected, no journal */
    if (!chaos_next_use_snapshot_export(&snapshot)) return 0;
    return snapshot.program_id == state->next_use_id
        && snapshot.termination_emitted
        && snapshot.journal_state == CHAOS_JOURNAL_COMPLETE
        && !snapshot.capture_incomplete;
}

/* Arc 1: was this family felt in an earlier, closed program of this game?
 * Only the engine's own saved closed-program snapshots are read: a W the
 * player saw answered (witnessed), or an F drink that was changed (applied).
 * The same facts publish next_use-felt.jsonl. Rejected attempts have no
 * snapshot and never count. */
int chaos_next_use_felt_in(const struct chaos_next_use_snapshot *const *closed,
                           int n, int family)
{
    int k;
    for (k = 0; closed && k < n; ++k) {
        const struct chaos_next_use_snapshot *s = closed[k];
        if (!s) continue;
        if (family == CHAOS_NEXT_USE_FAMILY_W && s->witnessed) return 1;
        if (family == CHAOS_NEXT_USE_FAMILY_F
            && s->slot_f == CHAOS_SLOT_F_CONSUMED_APPLIED) return 1;
    }
    return 0;
}

static int family_felt_before(int family)
{
    const struct chaos_next_use_snapshot *closed[CHAOS_NEXT_USE_PROGRAM_CAP];
    int k, n = 0, ordinal = chaos_next_use_program_ordinal();
    for (k = 1; k < ordinal && k <= CHAOS_NEXT_USE_PROGRAM_CAP; ++k)
        closed[n++] = chaos_next_use_closed_program(k);
    return chaos_next_use_felt_in(closed, n, family);
}

/* Shown before the program's own telegraph, so before any effect. Text is
 * fixed engine wording about an engine fact; no hidden state is named.
 * Presentation only: the result is ignored, so admission, budget, RNG and
 * saves are exactly as without it. */
static void recurrence_telegraph(const struct chaos_next_use_safe_request *request,
                                 const struct chaos_next_use_envelope *envelope)
{
    int i, family;
    if (chaos_next_use_program_ordinal() < 2) return;
    for (family = CHAOS_NEXT_USE_FAMILY_W; family <= CHAOS_NEXT_USE_FAMILY_F; ++family)
        for (i = 0; i < envelope->operation_count && i < 2; ++i)
            if (envelope->operations[i] == family) {
                if (family_felt_before(family))
                    (void)request->telegraph(request->telegraph_opaque,
                        family == CHAOS_NEXT_USE_FAMILY_W ? CHAOS_NEXT_USE_AGAIN_W
                                                          : CHAOS_NEXT_USE_AGAIN_F);
                break;
            }
}

static int settle_attempt(struct chaos_state *state, int id)
{
    if (!state || !chaos_state_valid(state)) {
        legacy_closed = 1; /* malformed engine state cannot be saved */
        return 1; /* preserve the existing diagnostic rejection path */
    }
    if (!chaos_next_use_retire_program()
        || !chaos_next_use_set_ordinal(state->next_use_count + 1)) return 0;
    if (state->next_use_count > 0) chaos_next_use_journal_reset();
    policy_state = state;
    ++state->next_use_count;
    state->next_use_ordinal = state->next_use_count;
    state->next_use_id = id;
    /* Rejections are terminal without a runtime. Successful install clears
     * this flag, then the live termination hook supplies its event boundary. */
    state->next_use_terminal = 1;
    state->next_use_terminal_seq = state->seq;
    return 1;
}

int chaos_next_use_safe_last(struct chaos_next_use_safe_result *out)
{
    if (!out) return 0;
    *out = last_result;
    return 1;
}

static int hex64(const char *text)
{
    int i;
    if (!text) return 0;
    for (i = 0; i < 64; ++i) {
        char c = text[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')))
            return 0;
    }
    return text[64] == '\0';
}

/* 0 when the envelope names the engine's current bound origin for its family;
 * otherwise the reason bit. A different bound origin means a newer qualifying
 * notice replaced it (the engine keeps one origin per family). */
static int origin_evidence_reason(const struct chaos_next_use_origin_ref *origin)
{
    int slot;
    const struct chaos_next_use_origin_ref *bound;

    if (!origin) return CHAOS_NEXT_USE_SAFE_SCHEMA;
    if (origin->family == CHAOS_NEXT_USE_FAMILY_W) slot = 0;
    else if (origin->family == CHAOS_NEXT_USE_FAMILY_F) slot = 1;
    else return CHAOS_NEXT_USE_SAFE_SCHEMA;
    if (!origin_evidence[slot].bound || !origin_evidence[slot].qualifying)
        return CHAOS_NEXT_USE_SAFE_ORIGIN_UNBOUND;
    bound = &origin_evidence[slot].origin;
    if (bound->root != origin->root
        || bound->notice_seq != origin->notice_seq
        || bound->end_seq != origin->end_seq
        || bound->family != origin->family
        || bound->level_dnum != origin->level_dnum
        || bound->level_dlevel != origin->level_dlevel
        || bound->move != origin->move
        || strcmp(bound->fact, origin->fact)
        || strcmp(bound->run, origin->run))
        return CHAOS_NEXT_USE_SAFE_ORIGIN_SUPERSEDED;
    return 0;
}

/* #177 option 1, widened by #200 (C): the engine's own newest origin for the
 * published origin's family replaces it when it is strictly newer, completed
 * and noted by the engine (qualifying), from this run, and within the origin
 * lifetime at this safe point, on whatever level it happened: a second
 * whistle refreshes the origin instead of superseding it. The director never
 * chooses or retimes; no game state or RNG is read beyond the engine's
 * recorded evidence. */
static int origin_rebind(const struct chaos_next_use_origin_ref *published,
                         const struct chaos_next_use_safe_request *request,
                         struct chaos_next_use_origin_ref *out)
{
    const struct chaos_next_use_origin_ref *newest;
    int slot;

    if (!published || !request || !out || !hex64(request->run_hex)) return 0;
    if (published->family == CHAOS_NEXT_USE_FAMILY_W) slot = 0;
    else if (published->family == CHAOS_NEXT_USE_FAMILY_F) slot = 1;
    else return 0;
    if (!origin_evidence[slot].bound || !origin_evidence[slot].qualifying)
        return 0;
    newest = &origin_evidence[slot].origin;
    if (newest->family != published->family
        || strcmp(newest->fact, published->fact)
        || strcmp(newest->run, request->run_hex)
        || strcmp(published->run, request->run_hex)
        || newest->root <= published->root
        || newest->notice_seq <= published->notice_seq
        || newest->end_seq <= published->end_seq
        || !(newest->root < newest->notice_seq
             && newest->notice_seq < newest->end_seq)
        || newest->move < published->move
        || newest->move < 0 || newest->move > 2147483547
        || request->at_move < newest->move
        || request->at_move > newest->move + CHAOS_NEXT_USE_ORIGIN_LIFETIME)
        return 0;
    *out = *newest;
    return 1;
}

/* Every failing origin check, not just the first: the recorded decision is
 * measurement (#177). A superseded origin that the engine can rebind (above)
 * passes; otherwise the same checks and outcome as before. bound[i] receives
 * the origin the program will be bound to; *rebound gets bit i per rebind. */
static int envelope_origin_reasons(const struct chaos_next_use_envelope *envelope,
                                   const struct chaos_next_use_safe_request *request,
                                   struct chaos_next_use_origin_ref bound[2],
                                   int *rebound, long fresh_after)
{
    int i, reasons = 0;

    if (!envelope || !request || !bound || !rebound)
        return CHAOS_NEXT_USE_SAFE_SCHEMA;
    *rebound = 0;
    if (!hex64(request->run_hex))
        reasons |= CHAOS_NEXT_USE_SAFE_RUN_UNAVAILABLE;
    if (envelope->operation_count < 1 || envelope->operation_count > 2)
        return reasons | CHAOS_NEXT_USE_SAFE_SCHEMA;
    if (request->at_move < 0)
        reasons |= CHAOS_NEXT_USE_SAFE_SCHEMA;
    for (i = 0; i < envelope->operation_count; ++i) {
        const struct chaos_next_use_origin_ref *origin = &envelope->origin_refs[i];
        int own = 0;

        bound[i] = *origin;
        if (origin->move < 0 || origin->move > 2147483547) {
            reasons |= CHAOS_NEXT_USE_SAFE_SCHEMA;
            continue;
        }
        if (hex64(request->run_hex) && strcmp(origin->run, request->run_hex))
            own |= CHAOS_NEXT_USE_SAFE_RUN_MISMATCH;
        /* #200 (A): no level check here. The program is installed on the
         * level of this safe point, where its effect lands, and ends if the
         * player leaves it (runtime boundary); the origin may be from an
         * earlier level. level_mismatch keeps its bit for the row format. */
        if (request->at_move > origin->move + CHAOS_NEXT_USE_ORIGIN_LIFETIME)
            own |= CHAOS_NEXT_USE_SAFE_ORIGIN_EXPIRED;
        own |= origin_evidence_reason(origin);
        if ((own & CHAOS_NEXT_USE_SAFE_ORIGIN_SUPERSEDED)
            && !(own & CHAOS_NEXT_USE_SAFE_RUN_MISMATCH)
            && origin_rebind(origin, request, &bound[i])) {
            *rebound |= 1 << i;
            own = 0;
        }
        if (bound[i].end_seq <= fresh_after)
            own |= CHAOS_NEXT_USE_SAFE_ORIGIN_NOT_FRESH;
        reasons |= own;
    }
    return reasons;
}

static int production_receipt(void *opaque,
                              const struct chaos_next_use_private_record *record)
{
    char line[512];
    int dir, fd, n;
    ssize_t wrote;

    if (!record) return 0;
    dir = (int)(intptr_t)opaque;
    if (dir < 0) return 0;
    if (!chaos_next_use_safe_receipt_row(record, line, sizeof line)) return 0;
    n = (int)strlen(line);
    fd = openat(dir, "next_use-receipt.jsonl",
                O_WRONLY | O_CREAT | O_APPEND | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) return 0;
    wrote = write(fd, line, (size_t)n);
    if (wrote != n || fsync(fd)) {
        close(fd);
        return 0;
    }
    if (close(fd)) return 0;
    return 1;
}

/* The admission receipt row (#177): identity plus, per operation in envelope
 * order, the published origin root and the origin root the engine bound. */
int chaos_next_use_safe_receipt_row(const struct chaos_next_use_private_record *record,
                                    char *out, size_t cap)
{
    const char *family[3] = { "", "W", "F" };
    size_t used;
    int i, n, count, op;

    if (!record || !out || cap < 1) return 0;
    out[0] = '\0';
    count = record->data.admission.operation_count;
    if (record->kind != CHAOS_PRIVATE_ADMISSION || count < 1 || count > 2)
        return 0;
    n = snprintf(out, cap,
                 "{\"next_use_private_v\":%d,\"kind\":%d,\"seq\":%d,"
                 "\"program_ordinal\":%d,\"program_id\":%d,\"origins\":[",
                 record->next_use_private_v, record->kind, record->seq,
                 chaos_next_use_program_ordinal() ? chaos_next_use_program_ordinal() : 1,
                 record->program_id);
    if (n < 1 || (size_t)n >= cap) { out[0] = '\0'; return 0; }
    used = (size_t)n;
    for (i = 0; i < count; ++i) {
        op = record->data.admission.operations[i];
        if (op != CHAOS_NEXT_USE_FAMILY_W && op != CHAOS_NEXT_USE_FAMILY_F) {
            out[0] = '\0';
            return 0;
        }
        n = snprintf(out + used, cap - used,
                     "%s{\"family\":\"%s\",\"published\":%d,\"bound\":%d}",
                     i ? "," : "", family[op],
                     record->data.admission.origin_roots[i],
                     record->data.admission.bound_roots[i]);
        if (n < 1 || (size_t)n >= cap - used) { out[0] = '\0'; return 0; }
        used += (size_t)n;
    }
    n = snprintf(out + used, cap - used, "]}\n");
    if (n < 1 || (size_t)n >= cap - used) { out[0] = '\0'; return 0; }
    return 1;
}

static int finish(struct chaos_next_use_safe_result *result, int rc)
{
    last_result = *result;
    return rc;
}

static int reject(struct chaos_next_use_safe_result *result, int reasons, int rc)
{
    result->rejected = 1;
    result->reasons |= reasons;
    return finish(result, rc);
}

static const char *const reason_names[] = {
    "schema", "identity", "run_unavailable", "level_invalid", "budget_state",
    "missed_index", "run_mismatch", "level_mismatch", "origin_expired",
    "origin_unbound", "origin_superseded", "source", "telegraph", "budget",
    "receipt", "internal", "no_companion_in_view", "origin_not_fresh"
};

/* #177 recorded decision: one row appended to the existing receipt file when
 * a parsed envelope was rejected in a transport this game owns (admission
 * keeps its kind-2 row). Empty mailboxes, pending or unparseable envelopes and
 * foreign transports are never written. The row names every failing check;
 * it is not a new capability or state. */
int chaos_next_use_safe_decision_row(const struct chaos_next_use_safe_result *result,
                                     int at, long at_safe, long at_move,
                                     char *out, size_t cap)
{
    size_t used;
    int i, n, first = 1;

    if (!result || !out || cap < 1) return 0;
    out[0] = '\0';
    if (!result->loaded || !result->rejected || result->admitted) return 0;
    /* Unparsed envelopes (at < 1) and transports this game does not own
     * (identity) leave the directory's existing evidence untouched. */
    if (at < 1 || (result->reasons & CHAOS_NEXT_USE_SAFE_IDENTITY)) return 0;
    n = snprintf(out, cap, "{\"next_use_decision_v\":1,\"decision\":\"rejected\","
                 "\"at\":%d,\"safe\":%ld,\"move\":%ld,\"program_ordinal\":%d,"
                 "\"program_id\":%d,\"reasons\":[",
                 at, at_safe, at_move, chaos_next_use_program_ordinal(),
                 policy_state ? policy_state->next_use_id : 0);
    if (n < 1 || (size_t)n >= cap) { out[0] = '\0'; return 0; }
    used = (size_t)n;
    for (i = 0; i < (int)(sizeof reason_names / sizeof reason_names[0]); ++i) {
        if (!(result->reasons & (1 << i))) continue;
        n = snprintf(out + used, cap - used, "%s\"%s\"", first ? "" : ",",
                     reason_names[i]);
        if (n < 1 || (size_t)n >= cap - used) { out[0] = '\0'; return 0; }
        used += (size_t)n;
        first = 0;
    }
    n = snprintf(out + used, cap - used, "%s]}\n", first ? "\"other\"" : "");
    if (n < 1 || (size_t)n >= cap - used) { out[0] = '\0'; return 0; }
    return 1;
}

static void append_public_receipt(int dir, const char *name, const char *line,
                                  size_t length, size_t limit)
{
    struct stat st;
    size_t done = 0;
    int fd = openat(dir, name,
        O_WRONLY | O_CREAT | O_APPEND | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC, 0600);
    if (fd < 0) return;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != getuid()
        || st.st_nlink != 1 || (st.st_mode & 077) || st.st_size < 0
        || (size_t)st.st_size > limit || length > limit - (size_t)st.st_size) {
        close(fd); return;
    }
    while (done < length) {
        ssize_t wrote = write(fd, line + done, length - done);
        if (wrote < 0 && errno == EINTR) continue;
        if (wrote <= 0) break;
        done += (size_t)wrote;
    }
    (void)fsync(fd); (void)close(fd); (void)fsync(dir);
}

/* Only witnessed W / remapped F: public identity, never a private runtime row. */
void chaos_next_use_felt_receipt(int dir, int program_id, int family, long root)
{
    char line[256];
    int n;
    if (dir < 0 || !policy_state || program_id < 1 || root < 1
        || policy_state->next_use_id != program_id
        || policy_state->next_use_count < 1
        || policy_state->next_use_count > CHAOS_NEXT_USE_PROGRAM_CAP
        || (family != CHAOS_NEXT_USE_FAMILY_W && family != CHAOS_NEXT_USE_FAMILY_F)) return;
    n = snprintf(line, sizeof line,
        "{\"next_use_felt_v\":1,\"program_ordinal\":%d,\"program_id\":%d,"
        "\"family\":%d,\"root_seq\":%ld}\n",
        policy_state->next_use_count, program_id, family, root);
    if (n > 0 && (size_t)n < sizeof line)
        append_public_receipt(dir, "next_use-felt.jsonl", line, (size_t)n, 6 * 256);
}

/* Diagnostic-only public boundary. Called after durable journal closure, or
 * after a parsed, settled refusal. Losing this file suppresses further director
 * publications; it never changes admission, saved state, capture status or RNG. */
void chaos_next_use_terminal_receipt(int dir, int program_id, int reason)
{
    static const char *const reasons[] = {
        "rejected", "completed", "level_departure", "origin_evicted",
        "origin_expired", "program_expired", "invalid_callback", "identity_unsafe"
    };
    char line[384];
    int n;
    if (dir < 0 || reason < 0 || reason > 7 || !policy_state
        || !policy_state->next_use_terminal || program_id < 1
        || policy_state->next_use_id != program_id
        || policy_state->next_use_count < 1
        || policy_state->next_use_count > CHAOS_NEXT_USE_PROGRAM_CAP) return;
    n = snprintf(line, sizeof line,
        "{\"next_use_lifecycle_v\":1,\"program_ordinal\":%d,\"program_id\":%d,"
        "\"terminal_seq\":%ld,\"reason\":\"%s\",\"journal_closed\":%s}\n",
        policy_state->next_use_count, program_id, policy_state->next_use_terminal_seq,
        reasons[reason], reason ? "true" : "false");
    if (n <= 0 || (size_t)n >= sizeof line) return;
    append_public_receipt(dir, "next_use-lifecycle.jsonl", line, (size_t)n, 3 * 384);
}

static void production_decision(int dir, const struct chaos_next_use_safe_result *result,
                                int at, long at_safe, long at_move)
{
    char line[512];
    size_t n, done = 0;
    int fd;

    if (dir < 0
        || !chaos_next_use_safe_decision_row(result, at, at_safe, at_move,
                                             line, sizeof line))
        return;
    n = strlen(line);
    fd = openat(dir, "next_use-receipt.jsonl",
                O_WRONLY | O_CREAT | O_APPEND | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) return;
    while (done < n) {
        ssize_t wrote = write(fd, line + done, n - done);
        if (wrote < 0 && errno == EINTR) continue;
        if (wrote <= 0) break;
        done += (size_t)wrote;
    }
    /* A lost diagnostic row is a trace gap, never a game-state change. */
    (void)fsync(fd);
    (void)close(fd);
    if (policy_state)
        chaos_next_use_terminal_receipt(dir, policy_state->next_use_id, 0);
}

int chaos_next_use_on_safe(int dir, long at_safe, int sanity,
                           struct chaos_state *budget, int dnum, int dlevel)
{
    struct chaos_next_use_safe_request req;
    struct chaos_next_use_safe_result res;
    memset(&req, 0, sizeof req);
    memset(&res, 0, sizeof res);
    if (at_safe < 0 || at_safe > 2147483647L
        || monstermoves < 0 || monstermoves > 2147483547L) {
        res.rejected = 1;
        return finish(&res, CHAOS_NEXT_USE_ADMISSION_SCHEMA);
    }
    req.dir = dir;
    req.enabled = 1;
    req.at_safe = (int)at_safe;
    req.at_move = (int)monstermoves;
    req.level_dnum = dnum;
    req.level_dlevel = dlevel;
    req.sanity = sanity;
    req.budget = budget;
    if (owned_run_set)
        req.run_hex = owned_run;
    req.telegraph = owned_warn;
    req.telegraph_opaque = owned_warn_opaque;
    /* #196 (C3): a bound check (fixtures) wins; otherwise the engine's own,
     * resolved weakly so harnesses linked without the game skip it. */
    req.companion = owned_companion ? owned_companion
                                    : chaos_next_use_companion_in_view;
    req.companion_opaque = owned_companion_opaque;
    if (owned_receipt) {
        req.receipt = owned_receipt;
        req.receipt_opaque = owned_receipt_opaque;
    } else {
        req.receipt = production_receipt;
        req.receipt_opaque = (void *)(intptr_t)dir;
    }
    {
        int rc = chaos_next_use_safe_try(&req, &res);
        production_decision(dir, &res, last_at, at_safe, monstermoves);
        /* Validated source/admission remain in the installed runtime carrier.
         * Journal failure is a trace gap, NOT a rejected paid admission. */
        if (rc == CHAOS_NEXT_USE_ADMISSION_OK && res.active)
            (void)chaos_next_use_journal_begin(dir);
        return rc;
    }
}

int chaos_next_use_safe_try(const struct chaos_next_use_safe_request *request,
                            struct chaos_next_use_safe_result *result)
{
    char raw[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    struct chaos_next_use_envelope envelope;
    struct chaos_next_use_admission source, admitted;
    struct chaos_next_use_attempt_gate gate;
    struct chaos_next_use_origin_ref bound[2];
    size_t n = 0, written = 0;
    int rc, reasons, rebound = 0;
    long fresh_after;

    if (!result)
        return CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    memset(result, 0, sizeof *result);
    if (!request || !request->enabled || request->dir < 0 || legacy_closed)
        return finish(result, CHAOS_NEXT_USE_ADMISSION_NOT_OPEN);
    if (request->budget && request->budget->next_use_count >= CHAOS_NEXT_USE_PROGRAM_CAP)
        return finish(result, CHAOS_NEXT_USE_ADMISSION_NOT_OPEN);
    if (resume_pending || resume_failed)
        return finish(result, CHAOS_NEXT_USE_ADMISSION_NOT_OPEN);
    if (request->budget && request->budget->next_use_count > 0) {
        int i, fresh = 0;
        for (i = 0; i < 2; ++i)
            if (origin_evidence[i].bound && origin_evidence[i].qualifying
                && chaos_next_use_safe_opportunity(request->budget,
                    origin_evidence[i].origin.end_seq)) fresh = 1;
        if (!fresh) return finish(result, CHAOS_NEXT_USE_ADMISSION_NOT_OPEN);
    }
    if (chaos_next_use_envelope_read_ordinal(request->dir,
            request->budget ? request->budget->next_use_ordinal + 1 : 1,
            raw, sizeof raw, &n)
        != CHAOS_NEXT_USE_OK)
        return finish(result, CHAOS_NEXT_USE_ADMISSION_SCHEMA);
    if (chaos_next_use_parse_envelope(raw, n, &envelope) != CHAOS_NEXT_USE_OK
        || chaos_next_use_jcs(raw, n, canonical, sizeof canonical, &written)
           != CHAOS_NEXT_USE_OK) {
        if (!settle_attempt(request->budget, 0))
            return finish(result, CHAOS_NEXT_USE_ADMISSION_NOT_OPEN);
        result->loaded = 1;
        last_at = 0;
        return reject(result, CHAOS_NEXT_USE_SAFE_SCHEMA,
                      CHAOS_NEXT_USE_ADMISSION_SCHEMA);
    }
    result->loaded = 1;
    last_at = envelope.at;
    if (envelope.at > request->at_safe) {
        result->pending = 1;
        return finish(result, CHAOS_NEXT_USE_ADMISSION_NOT_OPEN);
    }
    fresh_after = request->budget && request->budget->next_use_count
        ? request->budget->next_use_terminal_seq : -1;
    if (!settle_attempt(request->budget, envelope.id))
        return finish(result, CHAOS_NEXT_USE_ADMISSION_NOT_OPEN);
    reasons = 0;
    if (envelope.at != request->at_safe)
        reasons |= CHAOS_NEXT_USE_SAFE_MISSED_INDEX;
    if (logical_run <= 0)
        reasons |= CHAOS_NEXT_USE_SAFE_IDENTITY;
    if (chaos_next_use_pack_level(request->level_dnum, request->level_dlevel) <= 0)
        reasons |= CHAOS_NEXT_USE_SAFE_LEVEL_INVALID;
    if (!request->budget || !chaos_state_valid(request->budget))
        reasons |= CHAOS_NEXT_USE_SAFE_BUDGET_STATE;
    memset(bound, 0, sizeof bound);
    reasons |= envelope_origin_reasons(&envelope, request, bound, &rebound, fresh_after);
    /* Recurrence repair: program 1 must declare 100 moves; programs 2-3 may
     * declare 100 (pre-repair rules) or 300 (repaired). */
    if (!CHAOS_NEXT_USE_LIFETIME_OK(chaos_next_use_program_ordinal(), envelope.ttl))
        reasons |= CHAOS_NEXT_USE_SAFE_SCHEMA;
    /* #196 (C3): a W program needs a qualifying companion on screen now.
     * Checked with the other cheap checks, before telegraph and charge.
     * A repaired program 2-3 is checked only at the whistle instead
     * (chaos_next_use_whistle_completed suppresses when none qualifies). */
    if (request->companion
        && !CHAOS_NEXT_USE_REPAIRED(chaos_next_use_program_ordinal(), envelope.ttl)) {
        int i, has_w = 0;
        for (i = 0; i < envelope.operation_count && i < 2; ++i)
            if (envelope.operations[i] == CHAOS_NEXT_USE_FAMILY_W) has_w = 1;
        if (has_w && !request->companion(request->companion_opaque))
            reasons |= CHAOS_NEXT_USE_SAFE_NO_COMPANION;
    }
    /* The sandboxed source check runs only when every cheaper check passed,
     * exactly as before; it draws no game RNG. */
    if (!reasons
        && chaos_lua_next_use_load(envelope.source, envelope.source_length) != 0)
        reasons |= CHAOS_NEXT_USE_SAFE_SOURCE;
    if (reasons)
        return reject(result, reasons, CHAOS_NEXT_USE_ADMISSION_SCHEMA);
    if (request->telegraph) recurrence_telegraph(request, &envelope);
    if (!request->telegraph
        || !request->telegraph(request->telegraph_opaque, envelope.telegraph))
        return reject(result, CHAOS_NEXT_USE_SAFE_TELEGRAPH,
                      CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT);
    result->telegraph_count = 1;
    if (!request->receipt)
        return reject(result, CHAOS_NEXT_USE_SAFE_RECEIPT,
                      CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT);
    memset(&source, 0, sizeof source);
    memset(&admitted, 0, sizeof admitted);
    source.budget_state = *request->budget;
    source.program.phase = CHAOS_ATTEMPT_OPEN;
    gate.phase = CHAOS_ATTEMPT_OPEN;
    gate.reason = 0;
    rc = chaos_next_use_admit_bound(&admitted, &source, &gate, &envelope, bound,
                                    canonical, written, request->sanity,
                                    request->at_move, 1, request->receipt,
                                    request->receipt_opaque);
    if (rc == CHAOS_NEXT_USE_ADMISSION_OK
        || rc == CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT) {
        *request->budget = admitted.budget_state;
        result->spent = admitted.budget_state.spent;
    }
    if (rc != CHAOS_NEXT_USE_ADMISSION_OK)
        return reject(result,
                      rc == CHAOS_NEXT_USE_ADMISSION_BUDGET
                          ? CHAOS_NEXT_USE_SAFE_BUDGET
                      : rc == CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT
                          ? CHAOS_NEXT_USE_SAFE_RECEIPT
                          : CHAOS_NEXT_USE_SAFE_INTERNAL,
                      rc);
    result->admitted = 1;
    result->rebound = rebound;
    {
        long origin_w = 0, origin_w_deadline = 0;
        long origin_f = 0, origin_f_deadline = 0;
        int i;

        for (i = 0; i < envelope.operation_count; ++i) {
            const struct chaos_next_use_origin_ref *ref = &bound[i];
            long ref_expiry = ref->move > 2147483547
                ? ref->move : ref->move + CHAOS_NEXT_USE_ORIGIN_LIFETIME;
            if (ref->family == CHAOS_NEXT_USE_FAMILY_W) {
                origin_w = ref->root;
                origin_w_deadline = ref_expiry;
            } else if (ref->family == CHAOS_NEXT_USE_FAMILY_F) {
                origin_f = ref->root;
                origin_f_deadline = ref_expiry;
            }
        }
        if (!chaos_next_use_runtime_install(&admitted, envelope.source,
                                            envelope.source_length,
                                            envelope.source_sha256,
                                            logical_run,
                                            chaos_next_use_pack_level(
                                                request->level_dnum,
                                                request->level_dlevel),
                                            origin_w, origin_w_deadline,
                                            origin_f, origin_f_deadline,
                                            envelope.variant, 0, 0))
            return reject(result, CHAOS_NEXT_USE_SAFE_INTERNAL,
                          CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT);
    }
    if (policy_state) {
        policy_state->next_use_terminal = 0;
        policy_state->next_use_terminal_seq = 0;
    }
    result->active = 1;
    return finish(result, CHAOS_NEXT_USE_ADMISSION_OK);
}
