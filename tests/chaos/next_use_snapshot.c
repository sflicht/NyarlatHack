/* ENGINE-UNIT: bounded next-use snapshot. Not save/restore wiring. */
#include "hack.h"
#include "chaos_next_use_admission.h"
#include "chaos_next_use_runtime.h"
#include "chaos_next_use_safe.h"

#include <stdarg.h>
#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>

#ifdef NYARL_TEST_NATIVE_READS
static int injected_interrupts, injected_short_reads;
ssize_t chaos_test_native_read(int fd, void *buf, size_t size)
{
    if (injected_interrupts) {
        --injected_interrupts;
        errno = EINTR;
        return -1;
    }
    if (injected_short_reads && size > 3) size = 3;
    return read(fd, buf, size);
}
#endif

long moves;
long monstermoves;
boolean panicking;

void panic(const char *str, ...)
{
    va_list args;
    va_start(args, str);
    fputs(" ERROR:  ", stderr);
    vfprintf(stderr, str, args);
    fputc('\n', stderr);
    va_end(args);
    abort();
}

void bwrite(int fd, genericptr_t loc, unsigned int num)
{
#if defined(NYARL_TEST_NATIVE_READS) && defined(ZEROCOMP)
    /* Valid literal zero-run encoding; only the reader is under test here. */
    unsigned char *p = loc;
    while (num--) {
        if (write(fd, p, 1) != 1) abort();
        if (!*p && write(fd, p, 1) != 1) abort();
        ++p;
    }
#else
    if (write(fd, loc, num) != (ssize_t)num) abort();
#endif
}

#ifndef NYARL_TEST_NATIVE_READS
int chaos_next_use_mread(int fd, void *loc, unsigned int num)
{
    return read(fd, loc, num) == (ssize_t)num;
}
void mread(int fd, genericptr_t loc, unsigned int num)
{
    if (read(fd, loc, num) != (ssize_t)num) abort();
}
#else
/* Cleanup/UI doubles must never be reached by checked snapshot reads. */
boolean restoring = TRUE;
void pline(const char *fmt, ...) { (void)fmt; }
int delete_savefile(void) { fputs("native reader deleted save\n", stderr); abort(); }
void error(const char *fmt, ...) { (void)fmt; abort(); }
#endif

static const char source_text[] = "return 0";
static const char quiet_lua[] =
    "return {on_action=function(c) return {next_use_intent_v=2, op=\"quiet\", state=0} end}";
static const char delay_lua[] =
    "return {on_action=function(c) return {next_use_intent_v=2, op=\"delay\", state=0} end}";
static const char attention_lua[] =
    "return {on_action=function(c) return {next_use_intent_v=2, op=\"whistle_attention\", state=0} end}";
static const char run_hex[] =
    "0000000000000000000000000000000000000000000000000000000000000000";

static void digest_hex(const unsigned char digest[32], char output[65])
{
    static const char hex[] = "0123456789abcdef";
    int i;
    for (i = 0; i < 32; ++i) {
        output[i * 2] = hex[digest[i] >> 4];
        output[i * 2 + 1] = hex[digest[i] & 15];
    }
    output[64] = '\0';
}

static int json_escape(const char *in, char *out, size_t cap)
{
    size_t n = 0;
    for (; *in; ++in) {
        if (*in == '"' || *in == '\\') {
            if (n + 2 >= cap) return 0;
            out[n++] = '\\';
            out[n++] = *in;
        } else {
            if (n + 1 >= cap) return 0;
            out[n++] = *in;
        }
    }
    out[n] = '\0';
    return 1;
}

static int receipt_ok(void *opaque, const struct chaos_next_use_private_record *record)
{
    (void)opaque;
    (void)record;
    return 1;
}

static int build_envelope(char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1],
                          size_t *canonical_length,
                          struct chaos_next_use_envelope *envelope)
{
    unsigned char digest[32];
    char source_sha[65], raw[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    int n;
    if (chaos_next_use_sha256(source_text, sizeof source_text - 1, digest)
        != CHAOS_NEXT_USE_OK)
        return 0;
    digest_hex(digest, source_sha);
    n = snprintf(raw, sizeof raw,
        "{\"at\":7,\"cost\":1,\"id\":1,\"next_use_program_v\":2,"
        "\"operations\":[\"W\"],\"origin_refs\":[{\"end_seq\":12,"
        "\"fact\":\"ordinary_whistle\",\"family\":\"W\",\"level_dlevel\":1,"
        "\"level_dnum\":0,\"move\":10,\"notice_seq\":11,\"root\":10,"
        "\"run\":\"%s\"}],\"source\":\"%s\",\"source_sha256\":\"%s\","
        "\"telegraph\":\"next-use-v2-W\",\"ttl\":100,\"variant\":0}",
        run_hex, source_text, source_sha);
    if (n < 1 || (size_t)n >= sizeof raw) return 0;
    if (chaos_next_use_jcs(raw, (size_t)n, canonical,
                           CHAOS_NEXT_USE_ENVELOPE_MAX + 1, canonical_length)
        != CHAOS_NEXT_USE_OK)
        return 0;
    return chaos_next_use_parse_envelope(canonical, *canonical_length, envelope)
        == CHAOS_NEXT_USE_OK;
}

static int install_pending_token(long run_token)
{
    struct chaos_next_use_envelope envelope;
    struct chaos_next_use_admission source, admitted;
    struct chaos_next_use_attempt_gate gate;
    char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    char source_sha[65];
    unsigned char digest[32];
    size_t canonical_length = 0;

    memset(&source, 0, sizeof source);
    memset(&admitted, 0, sizeof admitted);
    chaos_state_init(&source.budget_state);
    source.program.phase = CHAOS_ATTEMPT_OPEN;
    gate.phase = CHAOS_ATTEMPT_OPEN;
    gate.reason = 0;
    if (!build_envelope(canonical, &canonical_length, &envelope))
        return 0;
    if (chaos_next_use_admit(&admitted, &source, &gate, &envelope, canonical,
                             canonical_length, 0, 40, 1, receipt_ok, NULL)
        != CHAOS_NEXT_USE_ADMISSION_OK)
        return 0;
    if (chaos_next_use_sha256(source_text, sizeof source_text - 1, digest)
        != CHAOS_NEXT_USE_OK)
        return 0;
    digest_hex(digest, source_sha);
    return chaos_next_use_runtime_install(&admitted, source_text,
                                          sizeof source_text - 1, source_sha,
                                          run_token, 1, 10, 110, 0, 0, 0, 1, 0);
}

static int install_pending(void)
{
    return install_pending_token(1);
}

static int install_pending_f(void)
{
    struct chaos_next_use_envelope envelope;
    struct chaos_next_use_admission source, admitted;
    struct chaos_next_use_attempt_gate gate;
    char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    char source_sha[65], raw[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    unsigned char digest[32];
    size_t canonical_length = 0;
    int n;

    memset(&source, 0, sizeof source);
    memset(&admitted, 0, sizeof admitted);
    chaos_state_init(&source.budget_state);
    source.program.phase = CHAOS_ATTEMPT_OPEN;
    gate.phase = CHAOS_ATTEMPT_OPEN;
    gate.reason = 0;
    if (chaos_next_use_sha256(source_text, sizeof source_text - 1, digest)
        != CHAOS_NEXT_USE_OK)
        return 0;
    digest_hex(digest, source_sha);
    n = snprintf(raw, sizeof raw,
        "{\"at\":7,\"cost\":1,\"id\":1,\"next_use_program_v\":2,"
        "\"operations\":[\"F\"],\"origin_refs\":[{\"end_seq\":12,"
        "\"fact\":\"water_refreshed\",\"family\":\"F\",\"level_dlevel\":1,"
        "\"level_dnum\":0,\"move\":10,\"notice_seq\":11,\"root\":10,"
        "\"run\":\"%s\"}],\"source\":\"%s\",\"source_sha256\":\"%s\","
        "\"telegraph\":\"next-use-v2-F\",\"ttl\":100,\"variant\":0}",
        run_hex, source_text, source_sha);
    if (n < 1 || (size_t)n >= sizeof raw) return 0;
    if (chaos_next_use_jcs(raw, (size_t)n, canonical,
                           CHAOS_NEXT_USE_ENVELOPE_MAX + 1, &canonical_length)
        != CHAOS_NEXT_USE_OK)
        return 0;
    if (chaos_next_use_parse_envelope(canonical, canonical_length, &envelope)
        != CHAOS_NEXT_USE_OK)
        return 0;
    if (chaos_next_use_admit(&admitted, &source, &gate, &envelope, canonical,
                             canonical_length, 0, 40, 1, receipt_ok, NULL)
        != CHAOS_NEXT_USE_ADMISSION_OK)
        return 0;
    return chaos_next_use_runtime_install(&admitted, source_text,
                                          sizeof source_text - 1, source_sha,
                                          1, 1, 0, 0, 10, 110, 0, 0, 1);
}

static int install_wf(const char *lua)
{
    struct chaos_next_use_envelope envelope;
    struct chaos_next_use_admission source, admitted;
    struct chaos_next_use_attempt_gate gate;
    char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    char source_sha[65], raw[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    char escaped[CHAOS_NEXT_USE_SOURCE_MAX * 2];
    unsigned char digest[32];
    size_t canonical_length = 0, lua_len;
    int n;

    lua_len = strlen(lua);
    memset(&source, 0, sizeof source);
    memset(&admitted, 0, sizeof admitted);
    chaos_state_init(&source.budget_state);
    source.program.phase = CHAOS_ATTEMPT_OPEN;
    gate.phase = CHAOS_ATTEMPT_OPEN;
    gate.reason = 0;
    if (!json_escape(lua, escaped, sizeof escaped))
        return 0;
    if (chaos_next_use_sha256(lua, lua_len, digest) != CHAOS_NEXT_USE_OK)
        return 0;
    digest_hex(digest, source_sha);
    n = snprintf(raw, sizeof raw,
        "{\"at\":7,\"cost\":2,\"id\":1,\"next_use_program_v\":2,"
        "\"operations\":[\"W\",\"F\"],\"origin_refs\":["
        "{\"end_seq\":12,\"fact\":\"ordinary_whistle\",\"family\":\"W\","
        "\"level_dlevel\":1,\"level_dnum\":0,\"move\":10,"
        "\"notice_seq\":11,\"root\":10,\"run\":\"%s\"},"
        "{\"end_seq\":22,\"fact\":\"water_refreshed\",\"family\":\"F\","
        "\"level_dlevel\":1,\"level_dnum\":0,\"move\":10,"
        "\"notice_seq\":21,\"root\":20,\"run\":\"%s\"}],"
        "\"source\":\"%s\",\"source_sha256\":\"%s\","
        "\"telegraph\":\"next-use-v2-WF\",\"ttl\":100,\"variant\":0}",
        run_hex, run_hex, escaped, source_sha);
    if (n < 1 || (size_t)n >= sizeof raw) return 0;
    if (chaos_next_use_jcs(raw, (size_t)n, canonical,
                           CHAOS_NEXT_USE_ENVELOPE_MAX + 1, &canonical_length)
        != CHAOS_NEXT_USE_OK) return 0;
    if (chaos_next_use_parse_envelope(canonical, canonical_length, &envelope)
        != CHAOS_NEXT_USE_OK) return 0;
    if (chaos_next_use_admit(&admitted, &source, &gate, &envelope, canonical,
                             canonical_length, 0, 40, 1, receipt_ok, NULL)
        != CHAOS_NEXT_USE_ADMISSION_OK) return 0;
    return chaos_next_use_runtime_install(&admitted, lua, lua_len, source_sha,
                                          9, 4, 10, 110, 20, 120, 0, 1, 1);
}

static int install_lua(const char *lua)
{
    struct chaos_next_use_envelope envelope;
    struct chaos_next_use_admission source, admitted;
    struct chaos_next_use_attempt_gate gate;
    char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    char source_sha[65], raw[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    char escaped[CHAOS_NEXT_USE_SOURCE_MAX * 2];
    unsigned char digest[32];
    size_t canonical_length = 0, lua_len;
    int n;

    lua_len = strlen(lua);
    memset(&source, 0, sizeof source);
    memset(&admitted, 0, sizeof admitted);
    chaos_state_init(&source.budget_state);
    source.program.phase = CHAOS_ATTEMPT_OPEN;
    gate.phase = CHAOS_ATTEMPT_OPEN;
    gate.reason = 0;
    if (!json_escape(lua, escaped, sizeof escaped))
        return 0;
    if (chaos_next_use_sha256(lua, lua_len, digest) != CHAOS_NEXT_USE_OK)
        return 0;
    digest_hex(digest, source_sha);
    n = snprintf(raw, sizeof raw,
        "{\"at\":7,\"cost\":1,\"id\":1,\"next_use_program_v\":2,"
        "\"operations\":[\"W\"],\"origin_refs\":[{\"end_seq\":12,"
        "\"fact\":\"ordinary_whistle\",\"family\":\"W\",\"level_dlevel\":1,"
        "\"level_dnum\":0,\"move\":10,\"notice_seq\":11,\"root\":10,"
        "\"run\":\"%s\"}],\"source\":\"%s\",\"source_sha256\":\"%s\","
        "\"telegraph\":\"next-use-v2-W\",\"ttl\":100,\"variant\":0}",
        run_hex, escaped, source_sha);
    if (n < 1 || (size_t)n >= sizeof raw) return 0;
    if (chaos_next_use_jcs(raw, (size_t)n, canonical,
                           CHAOS_NEXT_USE_ENVELOPE_MAX + 1, &canonical_length)
        != CHAOS_NEXT_USE_OK)
        return 0;
    if (chaos_next_use_parse_envelope(canonical, canonical_length, &envelope)
        != CHAOS_NEXT_USE_OK)
        return 0;
    if (chaos_next_use_admit(&admitted, &source, &gate, &envelope, canonical,
                             canonical_length, 0, 40, 1, receipt_ok, NULL)
        != CHAOS_NEXT_USE_ADMISSION_OK)
        return 0;
    return chaos_next_use_runtime_install(&admitted, lua, lua_len, source_sha,
                                          1, 1, 10, 110, 0, 0, 0, 1, 0);
}

static void print_snap(const char *tag, int ok,
                       const struct chaos_next_use_snapshot *snap)
{
    printf("{\"tag\":\"%s\",\"ok\":%d,\"program_id\":%d,\"slot_w\":%d,"
           "\"slot_f\":%d,\"state\":%d,\"source_len\":%zu,\"sha\":\"%.16s\","
           "\"armed_m_id\":%u}\n",
           tag, ok, snap ? snap->program_id : 0, snap ? snap->slot_w : -1,
           snap ? snap->slot_f : -1, snap ? snap->state : -1,
           snap ? snap->source_length : 0, snap ? snap->source_sha256 : "",
           snap ? snap->armed_m_id : 0);
}

int main(int argc, char **argv)
{
    struct chaos_next_use_snapshot snap, live;
    int installed, exported, imported, validated;
    const char *mode;

    mode = argc > 1 ? argv[1] : "roundtrip";
    chaos_next_use_runtime_reset();
#ifdef NYARL_TEST_NATIVE_READS
    if (!strcmp(mode, "native_interrupted_short_reads")) {
        FILE *fp = tmpfile();
        if (!fp || !install_pending()
            || !chaos_next_use_snapshot_export(&snap)
            || !chaos_next_use_save(fileno(fp))) return 1;
        rewind(fp); minit();
        chaos_next_use_runtime_reset();
        injected_interrupts = 2;
        injected_short_reads = 1;
        if (!chaos_next_use_restore_bound(fileno(fp), 1, 1)
            || injected_interrupts
            || !chaos_next_use_snapshot_export(&live)
            || memcmp(&snap, &live, sizeof snap)) return 1;
        fclose(fp);
        printf("{\"interrupted_short_reads\":1}\n");
        return 0;
    }
    if (!strcmp(mode, "native_read_error")) {
        int fd = open("/dev/null", O_WRONLY), i;
        unsigned char byte = 0xa5;
        if (fd < 0 || !install_pending()
            || !chaos_next_use_snapshot_export(&snap)) return 1;
        minit();
        for (i = 0; i < 3; ++i) {
            if (chaos_next_use_mread(fd, &byte, 1) || byte != 0xa5
                || chaos_next_use_restore_bound(fd, 1, 1)
                || !chaos_next_use_snapshot_export(&live)
                || memcmp(&snap, &live, sizeof snap)) return 1;
        }
        /* Invalid descriptor must not be satisfied from residual decoder state. */
        close(fd);
        if (chaos_next_use_mread(-1, &byte, 1)) return 1;
        printf("{\"errors_rejected\":1,\"unchanged\":1}\n");
        return 0;
    }
    if (!strcmp(mode, "native_decoder_state")) {
        FILE *fp = tmpfile();
#ifdef ZEROCOMP
        unsigned char wire[] = {'A', 0, 5, 'B', 0, 0, 'C'};
#else
        unsigned char wire[] = {'A', 0, 0, 0, 0, 0, 0, 'B', 0, 'C'};
#endif
        unsigned char expected[] = {'A', 0, 0, 0, 0, 0, 0, 'B', 0, 'C'};
        unsigned char bytes[sizeof expected];
        if (!fp || write(fileno(fp), wire, sizeof wire) != sizeof wire) return 1;
        rewind(fp); minit();
        mread(fileno(fp), bytes, 2); /* leaves buffered bytes and a partial run */
        if (!chaos_next_use_mread(fileno(fp), bytes + 2, 3)) return 1;
        mread(fileno(fp), bytes + 5, 2);
        if (!chaos_next_use_mread(fileno(fp), bytes + 7, 3)
            || memcmp(bytes, expected, sizeof bytes)) return 1;
        if (chaos_next_use_mread(fileno(fp), bytes, 1)
            || chaos_next_use_mread(fileno(fp), bytes, 1)) return 1;
        /* A fresh stream after failed reads must not inherit EOF/run state. */
        rewind(fp); minit();
        if (!chaos_next_use_mread(fileno(fp), bytes, sizeof bytes)
            || memcmp(bytes, expected, sizeof bytes)) return 1;
        fclose(fp);
        printf("{\"shared_decoder\":1,\"fresh_stream\":1}\n");
        return 0;
    }
    if (!strcmp(mode, "native_truncation")) {
        FILE *original = tmpfile();
        unsigned char bytes[16384], retained[16384];
        long length, cut;
        int empty = argc > 2 && !strcmp(argv[2], "empty");
        if (!original || (!empty && !install_pending())) return 1;
        if (!chaos_next_use_save(fileno(original))) return 1;
        length = lseek(fileno(original), 0, SEEK_END);
        if (length <= 0 || length > (long)sizeof bytes
            || pread(fileno(original), bytes, length, 0) != length) return 1;
        /* Keep the complete source immutable; truncate only disposable copies.
         * Every physical byte boundary includes marker/header/hash/source and
         * (in ZEROCOMP) missing run counts, not just logical field boundaries. */
        for (cut = 0; cut <= length; ++cut) {
            FILE *copy = tmpfile();
            int restored, same;
            if (!copy || write(fileno(copy), bytes, cut) != cut) return 1;
            rewind(copy);
            minit();
            chaos_next_use_runtime_reset();
            if (!install_pending_token(2)
                || !chaos_next_use_snapshot_export(&snap)) return 1;
            restored = chaos_next_use_restore_bound(fileno(copy), 1, 1);
            exported = chaos_next_use_snapshot_export(&live);
            same = exported && !memcmp(&snap, &live, sizeof snap);
            if (cut < length && (restored || !same)) {
                fprintf(stderr, "accepted/published truncated save at %ld/%ld\n", cut, length);
                return 1;
            }
            if (cut == length && (!restored || (empty ? exported : !exported))) return 1;
            if (lseek(fileno(copy), 0, SEEK_END) != cut
                || pread(fileno(copy), retained, cut, 0) != cut
                || memcmp(retained, bytes, cut)) return 1;
            fclose(copy);
        }
        if (pread(fileno(original), retained, length, 0) != length
            || memcmp(retained, bytes, length)) return 1;
        fclose(original);
        printf("{\"truncated\":%ld,\"positive\":1,\"preserved\":1}\n", length);
        return 0;
    }
#endif
    if (!strcmp(mode, "legacy_no_invented_witness")) {
        /* Literal historical v2 layout: progress but no persisted witness.
         * The missing information is not recoverable from callback count. */
        int32_t header[26] = {2, 1, CHAOS_ATTEMPT_TERMINATED,
            CHAOS_SLOT_W_CONSUMED_QUIET, CHAOS_SLOT_F_UNDECLARED,
            CHAOS_W_RUNTIME_INACTIVE, 0, 0, 1, 40, 140, 0, 0,
            sizeof source_text - 1, 1, 0, 10, 0, 110, 0, 0, 0, 1, 1, 0, 0};
        FILE *fp = tmpfile();
        char hash[65];
        unsigned char digest[32];
        int read_ok;
        if (!fp) return 1;
        chaos_next_use_sha256(source_text, sizeof source_text - 1, digest);
        digest_hex(digest, hash);
        bwrite(fileno(fp), header, sizeof header);
        bwrite(fileno(fp), hash, sizeof hash);
        bwrite(fileno(fp), (void *)source_text, sizeof source_text - 1);
        rewind(fp);
        memset(&snap, 0x5a, sizeof snap);
        live = snap;
        read_ok = chaos_next_use_snapshot_read(fileno(fp), &snap);
        fclose(fp);
        printf("{\"tag\":\"legacy\",\"read\":%d,\"unchanged\":%d}\n",
               read_ok, !memcmp(&snap, &live, sizeof snap));
        return !read_ok && !memcmp(&snap, &live, sizeof snap) ? 0 : 1;
    }
    if (!strcmp(mode, "restore_error_is_atomic")) {
        FILE *fp = tmpfile();
        int present = -1, restored;
        if (!fp || !install_pending()) return 1;
        if (!chaos_next_use_snapshot_export(&snap)) return 1;
        bwrite(fileno(fp), (void *)"NUS1", 4);
        bwrite(fileno(fp), &present, sizeof present);
        rewind(fp);
        restored = chaos_next_use_restore(fileno(fp));
        fclose(fp);
        exported = chaos_next_use_snapshot_export(&live);
        printf("{\"tag\":\"atomic\",\"restored\":%d,\"exported\":%d,\"unchanged\":%d}\n",
               restored, exported, !memcmp(&snap, &live, sizeof snap));
        return !restored && exported && !memcmp(&snap, &live, sizeof snap) ? 0 : 1;
    }
    if (!strcmp(mode, "inflight_save_refuses_before_write")) {
        struct chaos_fountain_token token;
        FILE *fp = tmpfile();
        char bytes[8];
        if (!fp || !install_lua(attention_lua)) return 1;
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        if (!chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token)) return 1;
        bwrite(fileno(fp), (void *)"previous", 8);
        rewind(fp);
        chaos_next_use_save(fileno(fp));
        rewind(fp);
        mread(fileno(fp), bytes, sizeof bytes);
        fclose(fp);
        printf("{\"preserved\":%d}\n", !memcmp(bytes, "previous", 8));
        return !memcmp(bytes, "previous", 8) ? 0 : 1;
    }
    if (!strcmp(mode, "unbound_import_cannot_execute")) {
        struct chaos_fountain_token token;
        if (!install_lua(quiet_lua)) return 1;
        if (!chaos_next_use_snapshot_export(&snap)
            || !chaos_next_use_snapshot_import(&snap)) return 1;
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token);
        if (!chaos_next_use_snapshot_export(&live)) return 1;
        printf("{\"unchanged\":%d}\n", !memcmp(&snap, &live, sizeof snap));
        return !memcmp(&snap, &live, sizeof snap) ? 0 : 1;
    }
    if (!strcmp(mode, "wrong_trusted_restore_identity")) {
        FILE *fp = tmpfile();
        int restored;
        if (!fp || !install_pending()) return 1;
        if (!chaos_next_use_snapshot_export(&snap)
            || !chaos_next_use_save(fileno(fp))) return 1;
        rewind(fp);
        restored = chaos_next_use_restore_bound(fileno(fp), 999, 1);
        fclose(fp);
        if (!chaos_next_use_snapshot_export(&live)) return 1;
        printf("{\"rejected\":%d,\"unchanged\":%d}\n",
               !restored, !memcmp(&snap, &live, sizeof snap));
        return !restored && !memcmp(&snap, &live, sizeof snap) ? 0 : 1;
    }
    if (!strcmp(mode, "departure_roundtrip")) {
        struct chaos_fountain_token token;
        FILE *fp = tmpfile();
        int restored, rejected = 0, unchanged = 1, i;
        long wrong_runs[] = {0, -1, 10, 9};
        long wrong_levels[] = {5, 5, 5, 0};
        if (argc != 3 || !fp
            || !install_wf(!strcmp(argv[2], "armed") ? attention_lua : quiet_lua))
            return 1;
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        if (!strcmp(argv[2], "armed")) {
            if (!chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 30, &token)) return 1;
            chaos_next_use_capture_whistle(30, 7, 40);
        } else if (!strcmp(argv[2], "completed")) {
            chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 30, &token);
            chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_F, 40, &token);
        }
        chaos_next_use_runtime_boundary(9, 5, 1, 1, 1, 1);
        if (!chaos_next_use_snapshot_export(&snap)
            || snap.phase != CHAOS_ATTEMPT_TERMINATED
            || !chaos_next_use_save(fileno(fp))) return 1;
        /* Terminal history still requires positive, matching game identity. */
        for (i = 0; i < 4; ++i) {
            rewind(fp);
            rejected += !chaos_next_use_restore_bound(fileno(fp), wrong_runs[i], wrong_levels[i]);
            unchanged &= chaos_next_use_snapshot_export(&live)
                && !memcmp(&snap, &live, sizeof snap);
        }
        chaos_next_use_runtime_reset();
        rewind(fp);
        restored = chaos_next_use_restore_bound(fileno(fp), 9, 5);
        fclose(fp);
        exported = chaos_next_use_snapshot_export(&live);
        unchanged &= exported && !memcmp(&snap, &live, sizeof snap);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 50, &token);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_F, 60, &token);
        unchanged &= chaos_next_use_snapshot_export(&live)
            && !memcmp(&snap, &live, sizeof snap);
        printf("{\"restored\":%d,\"unchanged\":%d,\"identity_rejections\":%d,\"records\":%zu}\n",
               restored, unchanged, rejected, chaos_next_use_runtime_private_count());
        return restored && unchanged && rejected == 4
            && !chaos_next_use_whistle_decision_ready(7)
            && !chaos_next_use_runtime_private_count() ? 0 : 1;
    }
    if (!strcmp(mode, "active_foreign_level")) {
        FILE *fp = tmpfile();
        int restored;
        if (!fp || !install_pending()
            || !chaos_next_use_snapshot_export(&snap)
            || !chaos_next_use_save(fileno(fp))) return 1;
        rewind(fp);
        restored = chaos_next_use_restore_bound(fileno(fp), 1, 2);
        fclose(fp);
        exported = chaos_next_use_snapshot_export(&live);
        printf("{\"rejected\":%d,\"unchanged\":%d}\n", !restored,
               exported && !memcmp(&snap, &live, sizeof snap));
        return !restored && exported && !memcmp(&snap, &live, sizeof snap) ? 0 : 1;
    }
    if (!strcmp(mode, "capture_metadata")) {
        struct chaos_fountain_token token;
        struct chaos_next_use_snapshot corrupt;
        long root = 50;
        int reason, rejected = 0, total = 0, unchanged = 1;
        if (argc != 3 || !install_wf(attention_lua)) return 1;
        reason = atoi(argv[2]);
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        if (!chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 30, &token)) return 1;
        chaos_next_use_capture_whistle(30, 7, 40);
        if (reason) chaos_next_use_end_w((enum chaos_next_use_end_reason)reason,
            reason == CHAOS_END_INVALID_CALLBACK || reason == CHAOS_END_IDENTITY_UNSAFE
                ? &root : NULL);
        if (!chaos_next_use_snapshot_export(&snap)
            || !chaos_next_use_snapshot_import(&snap)) return 1;
#define REJECT_CAPTURE(field, value) do { \
            corrupt = snap; corrupt.field = (value); ++total; \
            validated = chaos_next_use_snapshot_validate(&corrupt); \
            imported = chaos_next_use_snapshot_import(&corrupt); \
            rejected += !validated && !imported; \
            unchanged &= chaos_next_use_snapshot_export(&live) \
                && !memcmp(&snap, &live, sizeof snap); \
            if (!chaos_next_use_snapshot_import(&snap)) return 1; \
        } while (0)
        REJECT_CAPTURE(w_runtime, CHAOS_W_RUNTIME_INACTIVE);
        REJECT_CAPTURE(armed_m_id, 0);
        REJECT_CAPTURE(armed_root, 0);
        REJECT_CAPTURE(activation_monstermoves, 39);
        REJECT_CAPTURE(activation_monstermoves, 140);
        REJECT_CAPTURE(slot_w, CHAOS_SLOT_W_CONSUMED_QUIET);
#undef REJECT_CAPTURE
        printf("{\"rejected\":%d,\"total\":%d,\"unchanged\":%d}\n", rejected, total, unchanged);
        return rejected == total && unchanged ? 0 : 1;
    }
    if (!strcmp(mode, "family_progress_cannot_swap")) {
        struct chaos_fountain_token token;
        int valid;
        if (!install_wf(quiet_lua)) return 1;
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token);
        if (!chaos_next_use_snapshot_export(&snap)) return 1;
        snap.slot_w = CHAOS_SLOT_W_PENDING;
        snap.slot_f = CHAOS_SLOT_F_CONSUMED_QUIET;
        valid = chaos_next_use_snapshot_validate(&snap);
        printf("{\"valid\":%d}\n", valid);
        return !valid ? 0 : 1;
    }
    if (!strcmp(mode, "sequence_continuation")) {
        struct chaos_fountain_token token;
        int before_seq, after_seq;
        size_t count;
        if (!install_wf(quiet_lua)) return 1;
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token);
        count = chaos_next_use_runtime_private_count();
        before_seq = chaos_next_use_runtime_private_at(count - 1)->seq;
        if (!chaos_next_use_snapshot_export(&snap)
            || !chaos_next_use_snapshot_import(&snap)) return 1;
        chaos_next_use_runtime_boundary(9, 4, 1, 1, 1, 1);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_F, 20, &token);
        after_seq = chaos_next_use_runtime_private_at(0)->seq;
        printf("{\"before_seq\":%d,\"after_seq\":%d}\n", before_seq, after_seq);
        return after_seq == before_seq + 1 ? 0 : 1;
    }
    if (!strcmp(mode, "claimed_roundtrip")) {
        struct chaos_fountain_token token;
        if (!install_lua(attention_lua)) return 1;
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        if (!chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token)) return 1;
        chaos_next_use_capture_whistle(10, 7, 40);
        monstermoves = 45;
        chaos_next_use_whistle_no_root(7);
        if (!chaos_next_use_snapshot_export(&snap)
            || !chaos_next_use_snapshot_import(&snap)) return 1;
        chaos_next_use_runtime_boundary(1, 1, 1, 0, 1, 0);
        printf("{\"claimed\":%d,\"ready\":%d,\"witnessed\":%d}\n",
               snap.attention_claimed, chaos_next_use_whistle_decision_ready(7),
               snap.witnessed);
        return snap.attention_claimed == 1 && !snap.witnessed
               && !chaos_next_use_whistle_decision_ready(7) ? 0 : 1;
    }
    installed = install_pending();
    exported = chaos_next_use_snapshot_export(&snap);
    print_snap("after_install", exported, &snap);
    if (!strcmp(mode, "binding_digest")) {
        printf("{\"binding_sha256\":\"%s\"}\n", snap.binding_sha256);
        return 0;
    }
    if (!strcmp(mode, "wide_identity_roundtrip")) {
        FILE *fp = tmpfile();
        int ok;
        if (!fp) return 1;
        chaos_next_use_runtime_reset();
        if (!install_pending_token(LONG_MAX - 17)
            || !chaos_next_use_snapshot_export(&snap)) return 1;
        ok = chaos_next_use_snapshot_write(fileno(fp), &snap);
        if (ok) {
            rewind(fp);
            ok = chaos_next_use_snapshot_read(fileno(fp), &live);
        }
        fclose(fp);
        printf("{\"wide_identity_preserved\":%d}\n", ok && live.run_token == snap.run_token);
        return ok && live.run_token == snap.run_token ? 0 : 1;
    }
    if (!strcmp(mode, "snapshot_change")) {
        struct chaos_next_use_snapshot changed;
        int matched = 0, unchanged;
        if (argc != 5) return 2;
        changed = snap;
#define CHANGE_FIELD(field) if (!strcmp(argv[2], #field)) { \
            changed.field = strtol(argv[3], NULL, 10); matched = 1; \
        }
        CHANGE_FIELD(phase)
        CHANGE_FIELD(origin_w_live)
        CHANGE_FIELD(origin_f_live)
        CHANGE_FIELD(run_token)
        CHANGE_FIELD(level_token)
        CHANGE_FIELD(program_expiry)
        CHANGE_FIELD(origin_w)
        CHANGE_FIELD(origin_w_deadline)
        CHANGE_FIELD(activation_monstermoves)
        CHANGE_FIELD(armed_root)
        CHANGE_FIELD(replay_cursor)
        CHANGE_FIELD(next_seq)
        CHANGE_FIELD(termination_emitted)
        CHANGE_FIELD(identity_unsafe)
        CHANGE_FIELD(last_root)
        CHANGE_FIELD(witnessed)
        CHANGE_FIELD(attention_claimed)
        CHANGE_FIELD(delay_until)
        CHANGE_FIELD(origin_f)
        CHANGE_FIELD(slot_w)
#undef CHANGE_FIELD
        if (!matched) return 2;
        /* Python supplies its independently recomputed binding for semantic
         * tests. Integrity tests deliberately retain the original binding. */
        if (strcmp(argv[4], "original")) {
            if (strlen(argv[4]) != 64) return 2;
            memcpy(changed.binding_sha256, argv[4], 65);
        }
        validated = chaos_next_use_snapshot_validate(&changed);
        imported = chaos_next_use_snapshot_import(&changed);
        unchanged = chaos_next_use_snapshot_export(&live)
            && !memcmp(&snap, &live, sizeof snap);
        printf("{\"validated\":%d,\"imported\":%d,\"unchanged\":%d}\n",
               validated, imported, unchanged);
        return 0;
    }
    if (!strcmp(mode, "roundtrip")) {
        chaos_next_use_runtime_reset();
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_reset", exported, &live);
        imported = chaos_next_use_snapshot_import(&snap);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_import", imported && exported, &live);
        return installed && imported && exported ? 0 : 1;
    }
    if (!strcmp(mode, "bad_version")) {
        snap.snapshot_v = 99;
        validated = chaos_next_use_snapshot_validate(&snap);
        imported = chaos_next_use_snapshot_import(&snap);
        exported = chaos_next_use_snapshot_export(&live);
        printf("{\"tag\":\"bad_version\",\"validated\":%d,\"imported\":%d,"
               "\"live_program\":%d}\n", validated, imported, live.program_id);
        return installed && !validated && !imported && exported
               && live.program_id == 1 ? 0 : 1;
    }
    if (!strcmp(mode, "digest_mismatch")) {
        if (snap.source_sha256[0] == '0')
            snap.source_sha256[0] = '1';
        else
            snap.source_sha256[0] = '0';
        validated = chaos_next_use_snapshot_validate(&snap);
        imported = chaos_next_use_snapshot_import(&snap);
        exported = chaos_next_use_snapshot_export(&live);
        printf("{\"tag\":\"digest_mismatch\",\"validated\":%d,\"imported\":%d,"
               "\"live_program\":%d}\n", validated, imported, live.program_id);
        return installed && !validated && !imported && exported
               && live.program_id == 1 ? 0 : 1;
    }
    if (!strcmp(mode, "consumed_invalid")) {
        struct chaos_fountain_token token;
        int acted;

        monstermoves = 40;
        memset(&token, 0, sizeof token);
        acted = chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token);
        exported = chaos_next_use_snapshot_export(&snap);
        print_snap("after_invalid", exported, &snap);
        chaos_next_use_runtime_reset();
        imported = chaos_next_use_snapshot_import(&snap);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("imported_invalid", imported && exported, &live);
        snap.slot_w = CHAOS_SLOT_W_PENDING;
        validated = chaos_next_use_snapshot_validate(&snap);
        printf("{\"tag\":\"resurrect\",\"validated\":%d,\"acted\":%d}\n",
               validated, acted);
        return installed && imported && exported
               && live.slot_w == CHAOS_SLOT_W_CONSUMED_INVALID
               && live.slot_w != CHAOS_SLOT_W_PENDING
               && !validated ? 0 : 1;
    }
    if (!strcmp(mode, "roundtrip_f")) {
        chaos_next_use_runtime_reset();
        installed = install_pending_f();
        exported = chaos_next_use_snapshot_export(&snap);
        print_snap("after_install_f", exported, &snap);
        chaos_next_use_runtime_reset();
        imported = chaos_next_use_snapshot_import(&snap);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_import_f", imported && exported, &live);
        return installed && imported && exported
               && live.slot_w == CHAOS_SLOT_W_UNDECLARED
               && live.slot_f == CHAOS_SLOT_F_PENDING ? 0 : 1;
    }
    if (!strcmp(mode, "file")) {
        FILE *fp;
        int fd, wrote, loaded;

        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        wrote = chaos_next_use_snapshot_write(fd, &snap);
        if (fseek(fp, 0, SEEK_SET)) return 1;
        loaded = chaos_next_use_snapshot_read(fd, &live);
        fclose(fp);
        chaos_next_use_runtime_reset();
        imported = chaos_next_use_snapshot_import(&live);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_file", wrote && loaded && imported && exported, &live);
        return installed && wrote && loaded && imported && exported
               && live.slot_w == snap.slot_w
               && live.program_id == snap.program_id ? 0 : 1;
    }
    if (!strcmp(mode, "quiet")) {
        struct chaos_fountain_token token;

        chaos_next_use_runtime_reset();
        installed = install_lua(quiet_lua);
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token);
        exported = chaos_next_use_snapshot_export(&snap);
        print_snap("after_quiet", exported, &snap);
        chaos_next_use_runtime_reset();
        imported = chaos_next_use_snapshot_import(&snap);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("imported_quiet", imported && exported, &live);
        return installed && imported && exported
               && live.slot_w == CHAOS_SLOT_W_CONSUMED_QUIET ? 0 : 1;
    }
    if (!strcmp(mode, "save_quiet")) {
        FILE *fp;
        int fd, restored;
        struct chaos_fountain_token token;

        chaos_next_use_runtime_reset();
        installed = install_lua(quiet_lua);
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token);
        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        chaos_next_use_save(fd);
        chaos_next_use_runtime_reset();
        if (fseek(fp, 0, SEEK_SET)) return 1;
        restored = chaos_next_use_restore(fd);
        fclose(fp);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_save_quiet", restored && exported, &live);
        return installed && restored && exported
               && live.slot_w == CHAOS_SLOT_W_CONSUMED_QUIET ? 0 : 1;
    }
    if (!strcmp(mode, "save_delay")) {
        FILE *fp;
        int fd, restored;
        struct chaos_fountain_token token;

        chaos_next_use_runtime_reset();
        installed = install_lua(delay_lua);
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token);
        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        chaos_next_use_save(fd);
        chaos_next_use_runtime_reset();
        if (fseek(fp, 0, SEEK_SET)) return 1;
        restored = chaos_next_use_restore(fd);
        fclose(fp);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_save_delay", restored && exported, &live);
        return installed && restored && exported
               && live.slot_w == CHAOS_SLOT_W_CONSUMED_DELAY ? 0 : 1;
    }
    if (!strcmp(mode, "delay")) {
        struct chaos_fountain_token token;

        chaos_next_use_runtime_reset();
        installed = install_lua(delay_lua);
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token);
        exported = chaos_next_use_snapshot_export(&snap);
        print_snap("after_delay", exported, &snap);
        chaos_next_use_runtime_reset();
        imported = chaos_next_use_snapshot_import(&snap);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("imported_delay", imported && exported, &live);
        return installed && imported && exported
               && live.slot_w == CHAOS_SLOT_W_CONSUMED_DELAY ? 0 : 1;
    }
    if (!strcmp(mode, "armed")) {
        struct chaos_fountain_token token;

        chaos_next_use_runtime_reset();
        installed = install_lua(attention_lua);
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token);
        chaos_next_use_capture_whistle(10, 7, 40);
        exported = chaos_next_use_snapshot_export(&snap);
        print_snap("after_armed", exported, &snap);
        chaos_next_use_runtime_reset();
        imported = chaos_next_use_snapshot_import(&snap);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("imported_armed", imported && exported, &live);
        return installed && imported && exported
               && live.slot_w == CHAOS_SLOT_W_CONSUMED_ARMED ? 0 : 1;
    }
    if (!strcmp(mode, "expired")) {
        chaos_next_use_expire(CHAOS_END_PROGRAM_EXPIRED);
        exported = chaos_next_use_snapshot_export(&snap);
        print_snap("after_expiry", exported, &snap);
        chaos_next_use_runtime_reset();
        imported = chaos_next_use_snapshot_import(&snap);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("imported_expiry", imported && exported, &live);
        return installed && imported && exported
               && live.slot_w == CHAOS_SLOT_W_TERMINATED_EXPIRY ? 0 : 1;
    }
    if (!strcmp(mode, "save_expiry")) {
        FILE *fp;
        int fd, restored;

        chaos_next_use_expire(CHAOS_END_PROGRAM_EXPIRED);
        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        chaos_next_use_save(fd);
        chaos_next_use_runtime_reset();
        if (fseek(fp, 0, SEEK_SET)) return 1;
        restored = chaos_next_use_restore(fd);
        fclose(fp);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_save_expiry", restored && exported, &live);
        return installed && restored && exported
               && live.slot_w == CHAOS_SLOT_W_TERMINATED_EXPIRY ? 0 : 1;
    }
    if (!strcmp(mode, "save_restore")) {
        FILE *fp;
        int fd, restored;

        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        chaos_next_use_save(fd);
        chaos_next_use_runtime_reset();
        if (fseek(fp, 0, SEEK_SET)) return 1;
        restored = chaos_next_use_restore(fd);
        fclose(fp);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_save_restore", restored && exported, &live);
        return installed && restored && exported
               && live.slot_w == CHAOS_SLOT_W_PENDING
               && live.program_id == snap.program_id ? 0 : 1;
    }
    if (!strcmp(mode, "save_restore_f")) {
        FILE *fp;
        int fd, restored;

        chaos_next_use_runtime_reset();
        installed = install_pending_f();
        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        chaos_next_use_save(fd);
        chaos_next_use_runtime_reset();
        if (fseek(fp, 0, SEEK_SET)) return 1;
        restored = chaos_next_use_restore(fd);
        fclose(fp);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_save_restore_f", restored && exported, &live);
        return installed && restored && exported
               && live.slot_f == CHAOS_SLOT_F_PENDING
               && live.slot_w == CHAOS_SLOT_W_UNDECLARED ? 0 : 1;
    }
    if (!strcmp(mode, "empty_save")) {
        FILE *fp;
        int fd, restored;

        chaos_next_use_runtime_reset();
        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        chaos_next_use_save(fd);
        if (fseek(fp, 0, SEEK_SET)) return 1;
        restored = chaos_next_use_restore(fd);
        fclose(fp);
        exported = chaos_next_use_snapshot_export(&live);
        printf("{\"tag\":\"empty_save\",\"restored\":%d,\"exported\":%d}\n",
               restored, exported);
        return restored && !exported ? 0 : 1;
    }
    if (!strcmp(mode, "restore_level")) {
        FILE *fp;
        int fd, restored;

        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        chaos_next_use_save(fd);
        chaos_next_use_runtime_reset();
        if (fseek(fp, 0, SEEK_SET)) return 1;
        restored = chaos_next_use_restore(fd);
        fclose(fp);
        chaos_next_use_runtime_boundary(1, 2, 1, 0, 1, 0);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_level", restored && exported, &live);
        return installed && restored && exported
               && live.slot_w == CHAOS_SLOT_W_TERMINATED_LEVEL ? 0 : 1;
    }
    if (!strcmp(mode, "restore_origin")) {
        FILE *fp;
        int fd, restored;

        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        chaos_next_use_save(fd);
        chaos_next_use_runtime_reset();
        if (fseek(fp, 0, SEEK_SET)) return 1;
        restored = chaos_next_use_restore(fd);
        fclose(fp);
        chaos_next_use_runtime_boundary(1, 1, 0, 0, 1, 0);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_origin", restored && exported, &live);
        return installed && restored && exported
               && live.slot_w == CHAOS_SLOT_W_TERMINATED_EXPIRY ? 0 : 1;
    }
    if (!strcmp(mode, "restore_run")) {
        FILE *fp;
        int fd, restored;

        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        chaos_next_use_save(fd);
        chaos_next_use_runtime_reset();
        if (fseek(fp, 0, SEEK_SET)) return 1;
        restored = chaos_next_use_restore(fd);
        fclose(fp);
        chaos_next_use_runtime_boundary(2, 1, 1, 0, 1, 0);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_run", restored && exported, &live);
        return installed && restored && exported
               && live.slot_w == CHAOS_SLOT_W_TERMINATED_EXPIRY ? 0 : 1;
    }
    if (!strcmp(mode, "restore_latch")) {
        FILE *fp;
        int fd, restored, admitted;
        struct chaos_state budget;
        struct chaos_next_use_safe_result last;

        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        chaos_next_use_save(fd);
        chaos_next_use_runtime_reset();
        if (fseek(fp, 0, SEEK_SET)) return 1;
        restored = chaos_next_use_restore(fd);
        fclose(fp);
        chaos_next_use_safe_mark_restored();
        chaos_state_init(&budget);
        admitted = chaos_next_use_on_safe(0, 40, 100, &budget, 0, 1);
        chaos_next_use_safe_last(&last);
        exported = chaos_next_use_snapshot_export(&live);
        printf("{\"tag\":\"restore_latch\",\"restored\":%d,\"admitted\":%d,"
               "\"safe_admitted\":%d,\"slot_w\":%d}\n",
               restored, admitted, last.admitted, live.slot_w);
        return restored && exported
               && admitted == CHAOS_NEXT_USE_ADMISSION_NOT_OPEN
               && !last.admitted
               && live.slot_w == CHAOS_SLOT_W_PENDING ? 0 : 1;
    }
    if (!strcmp(mode, "restore_armed")) {
        FILE *fp;
        int fd, restored;
        struct chaos_fountain_token token;

        chaos_next_use_runtime_reset();
        installed = install_lua(attention_lua);
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token);
        chaos_next_use_capture_whistle(10, 7, 40);
        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        chaos_next_use_save(fd);
        chaos_next_use_runtime_reset();
        if (fseek(fp, 0, SEEK_SET)) return 1;
        restored = chaos_next_use_restore(fd);
        fclose(fp);
        chaos_next_use_runtime_boundary(1, 1, 1, 0, 1, 0);
        chaos_next_use_capture_whistle(10, 8, 40);
        monstermoves = 45;
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_rebind", restored && exported, &live);
        printf("{\"tag\":\"armed_window\",\"ready\":%d,\"wrong\":%d,\"activation\":%ld}\n",
               chaos_next_use_whistle_decision_ready(7),
               chaos_next_use_whistle_decision_ready(8),
               live.activation_monstermoves);
        return installed && restored && exported
               && live.slot_w == CHAOS_SLOT_W_CONSUMED_ARMED
               && live.armed_m_id == 7
               && live.activation_monstermoves == 40
               && chaos_next_use_whistle_decision_ready(7)
               && !chaos_next_use_whistle_decision_ready(8) ? 0 : 1;
    }
    if (!strcmp(mode, "partial_wf")) {
        struct chaos_fountain_token token;
        FILE *fp;
        int fd, restored;

        chaos_next_use_runtime_reset();
        installed = install_wf(quiet_lua);
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token);
        exported = chaos_next_use_snapshot_export(&snap);
        print_snap("after_w_used", exported, &snap);
        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        chaos_next_use_save(fd);
        chaos_next_use_runtime_reset();
        if (fseek(fp, 0, SEEK_SET)) return 1;
        restored = chaos_next_use_restore(fd);
        fclose(fp);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_partial_restore", restored && exported, &live);
        printf("{\"tag\":\"partial_wf\",\"callback\":%d,\"run\":%ld,\"level\":%ld,"
               "\"whistles\":%d,\"fountains\":%d,\"attention\":%d}\n",
               live.callback_ordinal, live.run_token, live.level_token,
               live.whistle_count, live.fountain_count, live.attention_claimed);
        return installed && restored && exported
               && live.slot_w == CHAOS_SLOT_W_CONSUMED_QUIET
               && live.slot_f == CHAOS_SLOT_F_PENDING
               && live.callback_ordinal == 1
               && live.run_token == 9 && live.level_token == 4 ? 0 : 1;
    }
    if (!strcmp(mode, "partial_fw")) {
        struct chaos_fountain_token token;
        FILE *fp;
        int fd, restored;

        chaos_next_use_runtime_reset();
        installed = install_wf(quiet_lua);
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_F, 20, &token);
        exported = chaos_next_use_snapshot_export(&snap);
        print_snap("after_w_used", exported, &snap);
        fp = tmpfile();
        if (!fp) return 1;
        fd = fileno(fp);
        chaos_next_use_save(fd);
        chaos_next_use_runtime_reset();
        if (fseek(fp, 0, SEEK_SET)) return 1;
        restored = chaos_next_use_restore(fd);
        fclose(fp);
        exported = chaos_next_use_snapshot_export(&live);
        print_snap("after_partial_restore", restored && exported, &live);
        printf("{\"tag\":\"partial_fw\",\"callback\":%d,\"run\":%ld,\"level\":%ld,"
               "\"whistles\":%d,\"fountains\":%d,\"attention\":%d}\n",
               live.callback_ordinal, live.run_token, live.level_token,
               live.whistle_count, live.fountain_count, live.attention_claimed);
        return installed && restored && exported
               && live.slot_f == CHAOS_SLOT_F_CONSUMED_QUIET
               && live.slot_w == CHAOS_SLOT_W_PENDING
               && live.callback_ordinal == 1
               && live.run_token == 9 && live.level_token == 4 ? 0 : 1;
    }
    return 2;
}
