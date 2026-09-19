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

static void fill_replay(struct chaos_next_use_replay_input *record,
                        const struct chaos_next_use_snapshot *snap,
                        unsigned long cursor)
{
    memset(record, 0, sizeof *record);
    record->operation = CHAOS_REPLAY_ACTION;
    record->family = CHAOS_NEXT_USE_FAMILY_W;
    record->root = 10;
    memcpy(record->source_sha256, snap->source_sha256, 65);
    record->cursor = cursor;
    record->at_move = monstermoves;
    record->slot_w = snap->slot_w;
    record->slot_f = snap->slot_f;
    record->w_runtime = snap->w_runtime;
}

int main(int argc, char **argv)
{
    struct chaos_next_use_snapshot snap, live;
    struct chaos_next_use_replay_input record;
    int installed, status;
    const char *mode;

    mode = argc > 1 ? argv[1] : "skip";
    chaos_next_use_runtime_reset();
    installed = install_pending();
    if (!chaos_next_use_snapshot_export(&snap))
        return 1;
    if (!strcmp(mode, "skip")) {
        fill_replay(&record, &snap, 2);
        status = chaos_next_use_replay_record(&record);
        if (!chaos_next_use_snapshot_export(&live))
            return 1;
        printf("{\"tag\":\"skip\",\"installed\":%d,\"status\":%d,\"slot_w\":%d}\n",
               installed, status, live.slot_w);
        return installed && status == CHAOS_REPLAY_BLOCKED_REPLAY
               && live.slot_w == CHAOS_SLOT_W_PENDING ? 0 : 1;
    }
    if (!strcmp(mode, "bad_sha")) {
        fill_replay(&record, &snap, 1);
        record.source_sha256[0] =
            record.source_sha256[0] == '0' ? '1' : '0';
        status = chaos_next_use_replay_record(&record);
        if (!chaos_next_use_snapshot_export(&live))
            return 1;
        printf("{\"tag\":\"bad_sha\",\"status\":%d,\"slot_w\":%d}\n",
               status, live.slot_w);
        return installed && status == CHAOS_REPLAY_BLOCKED_REPLAY
               && live.slot_w == CHAOS_SLOT_W_PENDING ? 0 : 1;
    }
    if (!strcmp(mode, "wrong_clock")) {
        fill_replay(&record, &snap, 1);
        record.at_move = monstermoves + 1;
        status = chaos_next_use_replay_record(&record);
        if (!chaos_next_use_snapshot_export(&live))
            return 1;
        printf("{\"tag\":\"wrong_clock\",\"status\":%d,\"slot_w\":%d}\n",
               status, live.slot_w);
        return installed && status == CHAOS_REPLAY_BLOCKED_REPLAY
               && live.slot_w == CHAOS_SLOT_W_PENDING ? 0 : 1;
    }
    if (!strcmp(mode, "after_expire")) {
        chaos_next_use_expire(CHAOS_END_PROGRAM_EXPIRED);
        fill_replay(&record, &snap, 1);
        status = chaos_next_use_replay_record(&record);
        printf("{\"tag\":\"after_expire\",\"status\":%d}\n", status);
        return installed && status == CHAOS_REPLAY_BLOCKED_REPLAY ? 0 : 1;
    }
    return 2;
}
