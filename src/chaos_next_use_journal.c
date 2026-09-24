/* NetHack General Public License. No raw structs, VM or executable state. */
#define _GNU_SOURCE
#include "hack.h"
#include "chaos_next_use_runtime.h"
#include "chaos_next_use_journal.h"
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

/* One bounded buffer and one owned descriptor, not a database. */
static struct {
    int fd, started, failed, ended;
    unsigned long cursor;
    size_t bytes, used;
    int bad;
    char previous[65], source_sha256[65];
    char line[CHAOS_JOURNAL_LINE_MAX];
} journal = { .fd = -1 };

static void put(const char *fmt, ...)
{
    int n;
    va_list ap;
    if (journal.bad) return;
    va_start(ap, fmt);
    n = vsnprintf(journal.line + journal.used,
                  sizeof journal.line - journal.used, fmt, ap);
    va_end(ap);
    if (n < 0 || (size_t)n >= sizeof journal.line - journal.used) {
        journal.bad = 1;
        return;
    }
    journal.used += (size_t)n;
}
#define N(p, field) put("\"" #field "\":%lld,", (long long)(p)->field)
/* All string fields except source are validated ASCII identifiers/base64.
 * Source is always length-delimited hex, including UTF-8/control bytes. */
static void text(const char *key, const char *value, size_t cap)
{
    size_t i, n = strnlen(value, cap);
    if (n == cap) { journal.bad = 1; return; }
    for (i = 0; i < n; ++i) {
        unsigned char c = (unsigned char)value[i];
        if (!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')
              || (c >= '0' && c <= '9') || c == '+' || c == '/'
              || c == '=' || c == '-' || c == '_')) {
            journal.bad = 1;
            return;
        }
    }
    put("\"%s\":\"%s\",", key, value);
}
#define T(p, field) text(#field, (p)->field, sizeof (p)->field)
static void end_object(void)
{
    if (!journal.bad && journal.used && journal.line[journal.used - 1] == ',')
        --journal.used;
    put("}");
}
static void token(const struct chaos_fountain_token *p)
{
    put("{"); N(p, root); N(p, active); N(p, remap); N(p, consumed); end_object();
}
static void snapshot(const struct chaos_next_use_snapshot *p)
{
    size_t i;
    put("{");
    N(p, snapshot_v); N(p, program_id); N(p, phase);
    N(p, slot_w); N(p, slot_f); N(p, w_runtime);
    N(p, state); N(p, delay_used); N(p, callback_ordinal);
    N(p, witnessed); N(p, attention_claimed); N(p, whistle_count); N(p, fountain_count);
    N(p, next_seq); N(p, termination_emitted); N(p, identity_unsafe);
    N(p, callback_w); N(p, callback_f); N(p, last_root);
    N(p, admission_move); N(p, program_expiry); N(p, delay_until); N(p, variant);
    N(p, origin_w_live); N(p, origin_f_live); N(p, armed_m_id); N(p, replay_cursor);
    N(p, origin_w); N(p, origin_f); N(p, origin_w_deadline); N(p, origin_f_deadline);
    N(p, run_token); N(p, level_token); N(p, activation_monstermoves); N(p, armed_root);
    N(p, journal_state); N(p, journal_bytes); T(p, journal_sha256);
    N(p, capture_incomplete);
    N(p, source_length); T(p, source_sha256); T(p, binding_sha256);
    if (p->source_length > CHAOS_NEXT_USE_SOURCE_MAX) journal.bad = 1;
    put("\"source_hex\":\"");
    for (i = 0; !journal.bad && i < p->source_length; ++i)
        put("%02x", (unsigned char)p->source[i]);
    put("\""); end_object();
}
static void poststate(const struct chaos_next_use_replay_poststate *p)
{
    put("{");
    N(p, phase); N(p, delay_used); N(p, delay_until); N(p, termination_emitted);
    N(p, identity_unsafe); N(p, pending_w_capture); N(p, f_inflight);
    N(p, witnessed); N(p, attention_claimed); N(p, callback_w); N(p, callback_f);
    N(p, whistle_count); N(p, fountain_count); N(p, origin_w_live); N(p, origin_f_live);
    N(p, manifest_success); N(p, armed_m_id); N(p, expected_manifest_m_id);
    N(p, activation_monstermoves); N(p, armed_root); N(p, pending_w_root); N(p, f_root);
    N(p, current_run_token); N(p, current_level_token);
    N(p, expected_manifest_root); N(p, expected_notice_seq); N(p, expected_end_seq);
    end_object();
}
static void private_record(const struct chaos_next_use_runtime_private_record *p)
{
    int i;
    put("{"); N(p, next_use_private_v); N(p, kind); N(p, seq);
    N(p, at_move); N(p, program_id); T(p, source_sha256);
    put("\"data\":{");
    switch (p->kind) {
    case CHAOS_RUNTIME_PRIVATE_ATTEMPT:
        N((&p->data.attempt), outcome); N((&p->data.attempt), reason);
        N((&p->data.attempt), reason_present);
        break;
    case CHAOS_RUNTIME_PRIVATE_ADMISSION:
        N((&p->data.admission), at_safe); N((&p->data.admission), cost);
        N((&p->data.admission), operation_count); N((&p->data.admission), program_expiry);
        T((&p->data.admission), envelope_b64); T((&p->data.admission), envelope_sha256);
        if (p->data.admission.operation_count < 1 || p->data.admission.operation_count > 2)
            journal.bad = 1;
        put("\"operations\":[");
        for (i = 0; !journal.bad && i < p->data.admission.operation_count; ++i)
            put("%s%d", i ? "," : "", p->data.admission.operations[i]);
        put("],\"origin_roots\":[");
        for (i = 0; !journal.bad && i < p->data.admission.operation_count; ++i)
            put("%s%ld", i ? "," : "", p->data.admission.origin_roots[i]);
        put("],");
        break;
    case CHAOS_RUNTIME_PRIVATE_INTENT:
        N((&p->data.intent), callback_ordinal); N((&p->data.intent), trigger);
        N((&p->data.intent), validation); N((&p->data.intent), failure_code);
        N((&p->data.intent), root); N((&p->data.intent), state_before);
        N((&p->data.intent), state_after); N((&p->data.intent), delay_used_after);
        T((&p->data.intent), context_sha256); N((&p->data.intent), intent_present);
        T((&p->data.intent), intent_sha256); N((&p->data.intent), intent_sha256_present);
        N((&p->data.intent), failure_code_present);
        put("\"intent\":{"); N((&p->data.intent.intent), op); N((&p->data.intent.intent), state);
        end_object(); put(",");
        break;
    case CHAOS_RUNTIME_PRIVATE_EFFECT:
        N((&p->data.effect), family); N((&p->data.effect), outcome);
        N((&p->data.effect), root); N((&p->data.effect), activation_monstermoves);
        N((&p->data.effect), m_id);
        break;
    case CHAOS_RUNTIME_PRIVATE_TERMINATION:
        N((&p->data.termination), failure_code); N((&p->data.termination), reason);
        N((&p->data.termination), slot_f); N((&p->data.termination), slot_w);
        N((&p->data.termination), w_runtime);
        break;
    default: journal.bad = 1;
    }
    end_object(); end_object();
}
static void public_record(const struct chaos_next_use_public_record *p)
{
    put("{"); N(p, next_use_public_v); N(p, family); N(p, phase);
    N(p, root); N(p, notice_seq); N(p, end_seq); end_object();
}
static void transition(const struct chaos_next_use_replay_input *p)
{
    int i;
    put("{"); N(p, replay_input_v);
    N(p, expected_last_root); N(p, activation_move); N(p, notice_root); N(p, witness_notice_seq);
    N(p, token_present); N(p, root_present); N(p, expected_result); N(p, published); N(p, pre_public);
    N(p, operation); N(p, family); N(p, root); T(p, source_sha256);
    N(p, callback_ordinal); N(p, state); N(p, seq); N(p, slot_w); N(p, slot_f); N(p, w_runtime);
    N(p, m_id); N(p, at_move); N(p, fountain_outcome); N(p, run_token); N(p, level_token);
    N(p, origin_w_live); N(p, origin_f_live); N(p, whistle_count); N(p, fountain_count);
    N(p, end_reason); N(p, expected_attention); N(p, decision_root); N(p, cursor);
    N(p, manifest_root); N(p, notice_seq); N(p, end_seq);
    N(p, manifestation_delivered); N(p, displaced); N(p, invalid);
    put("\"expected_token\":"); token(&p->expected_token);
    put(",\"post\":"); poststate(&p->post);
    put(","); N(p, private_count); N(p, public_count);
    put("\"private_records\":[");
    for (i = 0; i < p->private_count; ++i) {
        if (i) put(",");
        private_record(&p->private_records[i]);
    }
    put("],\"public_records\":[");
    for (i = 0; i < p->public_count; ++i) {
        if (i) put(",");
        public_record(&p->public_records[i]);
    }
    put("]"); end_object();
}
#undef N
#undef T

static int write_all(int fd, const char *buf, size_t len)
{
    while (len) {
        ssize_t n = write(fd, buf, len);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return 0;
        buf += n; len -= (size_t)n;
    }
    return 1;
}
static int sync_all(int fd)
{
    int rc;
    do { rc = fsync(fd); } while (rc && errno == EINTR);
    return rc == 0;
}
static void fail(void)
{
    static const char marker[] = "{\"journal_failed\":1}\n";
    journal.failed = 1;
    chaos_next_use_capture_journal_fail();
    /* Best effort negative evidence, never overwrite/delete the original prefix.
     * A footer CAN survive failed fsync/close even when this marker cannot land.
     * File completeness is NOT capture acknowledgement: the caller must consult
     * capture_status.incomplete/cursor. Reader never infers it from bytes alone.
     * A marker after a footer is invalid trailing data, not successful capture. */
    if (journal.fd >= 0) {
        (void)write_all(journal.fd, marker, sizeof marker - 1);
        (void)sync_all(journal.fd);
        (void)close(journal.fd);
        journal.fd = -1;
    }
}
static void start_line(const char *kind, unsigned long cursor)
{
    journal.used = 0; journal.bad = 0;
    put("{\"payload\":{\"v\":1,\"kind\":\"%s\",\"cursor\":%lu,\"prev\":\"%s\",\"data\":",
        kind, cursor, journal.previous);
}
static int finish_line(void)
{
    unsigned char raw[32];
    char digest[65];
    int i;
    put("}"); /* payload */
    if (journal.bad || journal.used < 12
        || chaos_next_use_sha256(journal.line + 11, journal.used - 11, raw))
        return 0;
    for (i = 0; i < 32; ++i) sprintf(digest + i * 2, "%02x", raw[i]);
    put(",\"sha256\":\"%s\"}\n", digest);
    /* Reserve an extra line for footer/failure, never silently truncate. */
    if (journal.bad || journal.bytes + journal.used > CHAOS_JOURNAL_BYTES_MAX - CHAOS_JOURNAL_LINE_MAX
        || !write_all(journal.fd, journal.line, journal.used)
        || !sync_all(journal.fd))
        return 0;
    journal.bytes += journal.used;
    memcpy(journal.previous, digest, sizeof digest);
    return 1;
}
static int sink(void *opaque, const struct chaos_next_use_replay_input *p)
{
    int i, terminal = 0;
    (void)opaque;
    if (!p || journal.failed || journal.ended || journal.fd < 0) return 0;
    if (p->replay_input_v != 1 || p->cursor != journal.cursor + 1
        || p->cursor > CHAOS_JOURNAL_RECORDS_MAX
        || p->private_count < 0 || p->private_count > 4
        || p->public_count < 0 || p->public_count > 1
        || strcmp(p->source_sha256, journal.source_sha256)) {
        fail(); return 0;
    }
    for (i = 0; i < p->private_count; ++i)
        if (p->private_records[i].kind == CHAOS_RUNTIME_PRIVATE_TERMINATION)
            terminal = 1;
    start_line("transition", p->cursor); transition(p);
    if (!finish_line()) { fail(); return 0; }
    if (terminal && p->post.phase == CHAOS_ATTEMPT_TERMINATED
        && p->post.termination_emitted && !p->post.pending_w_capture && !p->post.f_inflight
        && p->slot_w != CHAOS_SLOT_W_PENDING && p->slot_f != CHAOS_SLOT_F_PENDING
        && p->w_runtime != CHAOS_W_RUNTIME_ARMED) {
        start_line("end", p->cursor);
        put("{\"status\":\"complete\",\"terminal_seq\":%d}", p->seq);
        if (!finish_line()) { fail(); return 0; }
        /* close errors also deny acknowledgement. Keep fd for negative evidence
         * until the close; POSIX close must not be retried after EINTR. */
        if (close(journal.fd)) { journal.fd = -1; fail(); return 0; }
        journal.fd = -1;
        journal.ended = 1;
    }
    chaos_next_use_capture_journal_ack(
        journal.ended ? CHAOS_JOURNAL_COMPLETE : CHAOS_JOURNAL_OPEN,
        (unsigned long)journal.bytes, journal.previous);
    journal.cursor = p->cursor;
    return 1;
}
void chaos_next_use_journal_reset(void)
{
    if (journal.fd >= 0) (void)close(journal.fd);
    memset(&journal, 0, sizeof journal);
    journal.fd = -1;
    chaos_next_use_capture_set_sink(NULL, NULL);
}
/* This is a writer-framing scanner, not a second semantic JSON interpreter.
 * The trusted save tip authenticates every payload in the original prefix. */
static int take(const char **p, const char *literal)
{
    size_t n = strlen(literal);
    if (strncmp(*p, literal, n)) return 0;
    *p += n;
    return 1;
}
static int number(const char **p, const char *key, long *value)
{
    char prefix[80], canonical[40], *end;
    const char *start;
    long v;
    snprintf(prefix, sizeof prefix, "\"%s\":", key);
    if (!take(p, prefix)) return 0;
    start = *p;
    errno = 0;
    v = strtol(start, &end, 10);
    if (errno || end == start || *end != ',') return 0;
    snprintf(canonical, sizeof canonical, "%ld", v);
    if ((size_t)(end - start) != strlen(canonical)
        || strncmp(start, canonical, (size_t)(end - start))) return 0;
    *value = v; *p = end + 1;
    return 1;
}
static int header_binding(const char *p, const struct chaos_next_use_snapshot *s)
{
    static const char *fields[] = {
        "snapshot_v", "program_id", "phase", "slot_w", "slot_f", "w_runtime",
        "state", "delay_used", "callback_ordinal", "witnessed", "attention_claimed",
        "whistle_count", "fountain_count", "next_seq", "termination_emitted",
        "identity_unsafe", "callback_w", "callback_f", "last_root", "admission_move",
        "program_expiry", "delay_until", "variant", "origin_w_live", "origin_f_live",
        "armed_m_id", "replay_cursor", "origin_w", "origin_f", "origin_w_deadline",
        "origin_f_deadline", "run_token", "level_token", "activation_monstermoves",
        "armed_root", "journal_state", "journal_bytes"
    };
    size_t i;
    long v;
    char tail[256], hex[3];
    if (!take(&p, "{\"snapshot\":{")) return 0;
    for (i = 0; i < sizeof fields / sizeof fields[0]; ++i) {
        if (!number(&p, fields[i], &v)) return 0;
        if ((!i && v != CHAOS_NEXT_USE_SNAPSHOT_V)
            || ((!strcmp(fields[i], "replay_cursor")
                 || !strcmp(fields[i], "journal_state")
                 || !strcmp(fields[i], "journal_bytes")) && v)) return 0;
    }
    snprintf(tail, sizeof tail,
        "\"journal_sha256\":\"\",\"capture_incomplete\":0,\"source_length\":%lu,"
        "\"source_sha256\":\"%s\",\"binding_sha256\":\"%s\",\"source_hex\":\"",
        (unsigned long)s->source_length, s->source_sha256, s->binding_sha256);
    if (!take(&p, tail)) return 0;
    for (i = 0; i < s->source_length; ++i) {
        snprintf(hex, sizeof hex, "%02x", (unsigned char)s->source[i]);
        if (!take(&p, hex)) return 0;
    }
    return take(&p, "\"},\"private_records\":[");
}
static int inner_cursor(const char *p, unsigned long cursor, long *seq)
{
    static const char *before[] = {
        "replay_input_v", "expected_last_root", "activation_move", "notice_root",
        "witness_notice_seq", "token_present", "root_present", "expected_result",
        "published", "pre_public", "operation", "family", "root"
    };
    static const char *after[] = {
        "callback_ordinal", "state", "seq", "slot_w", "slot_f", "w_runtime", "m_id",
        "at_move", "fountain_outcome", "run_token", "level_token", "origin_w_live",
        "origin_f_live", "whistle_count", "fountain_count", "end_reason",
        "expected_attention", "decision_root", "cursor"
    };
    size_t i;
    long v;
    char source[96];
    if (!take(&p, "{")) return 0;
    for (i = 0; i < sizeof before / sizeof before[0]; ++i)
        if (!number(&p, before[i], &v) || (!i && v != 1)) return 0;
    snprintf(source, sizeof source, "\"source_sha256\":\"%s\",", journal.source_sha256);
    if (!take(&p, source)) return 0;
    for (i = 0; i < sizeof after / sizeof after[0]; ++i) {
        if (!number(&p, after[i], &v)) return 0;
        if (i == 2) *seq = v;
    }
    return v >= 0 && (unsigned long)v == cursor;
}
int chaos_next_use_journal_resume(int dir)
{
    struct chaos_next_use_snapshot saved;
    struct chaos_next_use_capture_status status;
    struct stat before, after;
    FILE *input = NULL;
    int fd = -1, copy = -1, ok = 0, ended = 0, lines = 0;
    unsigned long cursor = 0;
    size_t total = 0, n, payload_length;
    long seq = 0;
    char previous[65], digest[65], framing[256], footer[128];
    const char *kind, *data;
    if (!chaos_next_use_capture_journal_enter(&status)) return 0;
    /* Never reset an existing writer, including a closed terminal writer. */
    if (journal.started) goto done;
    if (!chaos_next_use_snapshot_export(&saved)) { ok = 1; goto done; }
    if (saved.journal_state == CHAOS_JOURNAL_NONE) { ok = 1; goto done; }
    journal.started = 1;
    if (saved.journal_state == CHAOS_JOURNAL_FAILED || status.incomplete
        || status.transaction_open || dir < 0
        || fstat(dir, &before) || !S_ISDIR(before.st_mode)
        || before.st_uid != getuid() || (before.st_mode & 077)) goto rejected;
    fd = openat(dir, "next_use-journal.jsonl",
                (saved.journal_state == CHAOS_JOURNAL_COMPLETE ? O_RDONLY : O_RDWR)
                | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0 || fstat(fd, &before) || !S_ISREG(before.st_mode)
        || before.st_uid != getuid() || before.st_nlink != 1
        || (before.st_mode & 077) || before.st_size < 1
        || (unsigned long)before.st_size != saved.journal_bytes
        || saved.journal_bytes > CHAOS_JOURNAL_BYTES_MAX) goto rejected;
    copy = dup(fd);
    if (copy < 0) goto rejected;
    input = fdopen(copy, "r");
    if (!input) { close(copy); goto rejected; }
    memset(previous, '0', 64); previous[64] = 0;
    memcpy(journal.source_sha256, saved.source_sha256, 65);
    while (fgets(journal.line, sizeof journal.line, input)) {
        n = strlen(journal.line);
        if (ended || n < 100 || n >= CHAOS_JOURNAL_LINE_MAX
            || journal.line[n - 1] != '\n'
            || ++lines > CHAOS_JOURNAL_RECORDS_MAX + 2
            || total + n > saved.journal_bytes) goto rejected;
        total += n;
        /* Fixed suffix, including the exact payload closing brace and LF. */
        payload_length = n - 11 - (sizeof(",\"sha256\":\"") - 1) - 64 - 3;
        if (journal.line[11 + payload_length - 1] != '}') goto rejected;
        {
            unsigned char raw[32];
            int i;
            if (chaos_next_use_sha256(journal.line + 11, payload_length, raw))
                goto rejected;
            for (i = 0; i < 32; ++i) sprintf(digest + i * 2, "%02x", raw[i]);
        }
        snprintf(framing, sizeof framing, ",\"sha256\":\"%s\"}\n", digest);
        if (strcmp(journal.line + 11 + payload_length, framing)) goto rejected;
        if (lines == 1) kind = "header";
        else if (!strncmp(journal.line, "{\"payload\":{\"v\":1,\"kind\":\"end\",",
                          sizeof("{\"payload\":{\"v\":1,\"kind\":\"end\",") - 1)) {
            kind = "end"; ended = 1;
        } else { kind = "transition"; ++cursor; }
        if (cursor > CHAOS_JOURNAL_RECORDS_MAX) goto rejected;
        snprintf(framing, sizeof framing,
            "{\"payload\":{\"v\":1,\"kind\":\"%s\",\"cursor\":%lu,\"prev\":\"%s\",\"data\":",
            kind, cursor, previous);
        data = journal.line;
        if (!take(&data, framing)) goto rejected;
        if (lines == 1) {
            if (!header_binding(data, &saved)) goto rejected;
        } else if (ended) {
            snprintf(footer, sizeof footer,
                "{\"status\":\"complete\",\"terminal_seq\":%ld}}", seq);
            if (!cursor || (size_t)(journal.line + 11 + payload_length - data) != strlen(footer)
                || strncmp(data, footer, strlen(footer))) goto rejected;
        } else if (!inner_cursor(data, cursor, &seq)) goto rejected;
        memcpy(previous, digest, 65);
    }
    if (ferror(input) || !lines || total != saved.journal_bytes
        || cursor != saved.replay_cursor || strcmp(previous, saved.journal_sha256)
        || ended != (saved.journal_state == CHAOS_JOURNAL_COMPLETE)) goto rejected;
    if (fclose(input)) { input = NULL; goto rejected; }
    input = NULL;
    if (fstat(fd, &after) || before.st_dev != after.st_dev
        || before.st_ino != after.st_ino || before.st_size != after.st_size
        || before.st_mode != after.st_mode || before.st_uid != after.st_uid
        || after.st_nlink != 1
        || before.st_mtim.tv_sec != after.st_mtim.tv_sec
        || before.st_mtim.tv_nsec != after.st_mtim.tv_nsec
        || before.st_ctim.tv_sec != after.st_ctim.tv_sec
        || before.st_ctim.tv_nsec != after.st_ctim.tv_nsec) goto rejected;
    if (ended) {
        int rc = close(fd);
        fd = -1;
        if (rc) goto rejected;
    } else if (fcntl(fd, F_SETFL, O_APPEND | O_NONBLOCK) < 0) goto rejected;
    journal.fd = fd; fd = -1;
    journal.cursor = cursor; journal.bytes = total; journal.ended = ended;
    memcpy(journal.previous, previous, 65);
    /* Closed COMPLETE retains its status subscriber, never a writable fd. */
    chaos_next_use_capture_set_sink(sink, NULL);
    ok = 1;
    goto done;
rejected:
    if (input) fclose(input);
    if (fd >= 0) close(fd);
    journal.failed = 1;
    /* Unlike fail(), rejection must never touch the untrusted input bytes. */
    chaos_next_use_capture_journal_fail();
done:
    chaos_next_use_capture_journal_leave();
    return ok;
}
int chaos_next_use_journal_begin(int dir)
{
    struct stat st;
    struct chaos_next_use_snapshot initial;
    const struct chaos_next_use_runtime_private_record *a, *b;
    struct chaos_next_use_capture_status status;
    int result = 0;
    /* Reentrant callers neither reset the writer nor release the outer guard. */
    if (!chaos_next_use_capture_journal_enter(&status)) return 0;
    if (journal.started) { chaos_next_use_capture_fail(); goto done; }
    journal.started = 1;
    chaos_next_use_capture_set_sink(sink, NULL);
    if (status.incomplete || status.transaction_open || status.acknowledged_cursor
        || !chaos_next_use_snapshot_export(&initial) || initial.replay_cursor
        || initial.phase != CHAOS_ATTEMPT_COMMITTED
        || initial.journal_state != CHAOS_JOURNAL_NONE
        || initial.capture_incomplete
        || chaos_next_use_runtime_private_count() != 2
        || fstat(dir, &st) || !S_ISDIR(st.st_mode) || st.st_uid != getuid()
        || (st.st_mode & 077)) goto failed;
    a = chaos_next_use_runtime_private_at(0);
    b = chaos_next_use_runtime_private_at(1);
    if (!a || !b || a->kind != CHAOS_RUNTIME_PRIVATE_ATTEMPT
        || b->kind != CHAOS_RUNTIME_PRIVATE_ADMISSION) goto failed;
    journal.fd = openat(dir, "next_use-journal.jsonl",
                        O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC, 0600);
    if (journal.fd < 0) goto failed;
    if (fstat(journal.fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != getuid()
        || st.st_nlink != 1 || (st.st_mode & 077) || st.st_size != 0) {
        /* Never write to an unverified descriptor, including a failure marker. */
        (void)close(journal.fd); journal.fd = -1; goto failed;
    }
    memset(journal.previous, '0', 64); journal.previous[64] = 0;
    memcpy(journal.source_sha256, initial.source_sha256, 65);
    start_line("header", 0);
    put("{\"snapshot\":"); snapshot(&initial);
    put(",\"private_records\":["); private_record(a); put(","); private_record(b);
    put("]}");
    if (!finish_line() || !sync_all(dir)) goto failed;
    chaos_next_use_capture_journal_ack(CHAOS_JOURNAL_OPEN,
        (unsigned long)journal.bytes, journal.previous);
    result = 1;
    goto done;
failed:
    fail();
done:
    chaos_next_use_capture_journal_leave();
    return result;
}
