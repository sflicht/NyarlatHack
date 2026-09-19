/* ENGINE-UNIT: bounded next-use snapshot. Not save/restore wiring. */
#include "hack.h"
#include "chaos_next_use_admission.h"
#include "chaos_next_use_runtime.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

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
    if (write(fd, loc, num) != (ssize_t)num) abort();
}

void mread(int fd, genericptr_t loc, unsigned int num)
{
    if (read(fd, loc, num) != (ssize_t)num) abort();
}

static const char source_text[] = "return 0";
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

static int install_pending(void)
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
                                          1, 1, 10, 110, 0, 0, 0, 1, 0);
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

static void print_snap(const char *tag, int ok,
                       const struct chaos_next_use_snapshot *snap)
{
    printf("{\"tag\":\"%s\",\"ok\":%d,\"program_id\":%d,\"slot_w\":%d,"
           "\"slot_f\":%d,\"state\":%d,\"source_len\":%zu,\"sha\":\"%.16s\"}\n",
           tag, ok, snap ? snap->program_id : 0, snap ? snap->slot_w : -1,
           snap ? snap->slot_f : -1, snap ? snap->state : -1,
           snap ? snap->source_length : 0, snap ? snap->source_sha256 : "");
}

int main(int argc, char **argv)
{
    struct chaos_next_use_snapshot snap, live;
    int installed, exported, imported, validated;
    const char *mode;

    mode = argc > 1 ? argv[1] : "roundtrip";
    chaos_next_use_runtime_reset();
    installed = install_pending();
    exported = chaos_next_use_snapshot_export(&snap);
    print_snap("after_install", exported, &snap);
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
    return 2;
}
