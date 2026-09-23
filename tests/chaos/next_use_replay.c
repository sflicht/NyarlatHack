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
static const char quiet_lua[] =
    "return {on_action=function(c) return {next_use_intent_v=2, op=\"quiet\", state=0} end}";
static const char fountain_lua[] =
    "return {on_action=function(c) return {next_use_intent_v=2, op=\"fountain_refresh\", state=0} end}";
static const char wf_lua[] =
    "return {on_action=function(c) "
    "if c.trigger==[[W]] then "
    "return {next_use_intent_v=2, op=[[quiet]], state=0} end "
    "return {next_use_intent_v=2, op=[[fountain_refresh]], state=0} end}";
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

static int install_ops(const char *lua, const char *operations,
                       const char *origins, int cost, const char *telegraph,
                       long origin_w, long origin_f, int whistle_count,
                       int fountain_count)
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
        "{\"at\":7,\"cost\":%d,\"id\":1,\"next_use_program_v\":2,"
        "\"operations\":%s,\"origin_refs\":[%s],\"source\":\"%s\","
        "\"source_sha256\":\"%s\",\"telegraph\":\"%s\",\"ttl\":100,"
        "\"variant\":0}",
        cost, operations, origins, escaped, source_sha, telegraph);
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
                                          1, 1, origin_w,
                                          origin_w ? 110 : 0, origin_f,
                                          origin_f ? 110 : 0, 0,
                                          whistle_count, fountain_count);
}

static int copy_new_privates(int before, struct chaos_next_use_replay_input *record)
{
    int i, n;

    n = (int)chaos_next_use_runtime_private_count() - before;
    if (n < 1 || n > 4) return 0;
    record->private_count = n;
    for (i = 0; i < n; ++i)
        record->private_records[i] =
            *chaos_next_use_runtime_private_at((size_t)(before + i));
    record->seq = record->private_records[n - 1].seq;
    return 1;
}

static const char *intent_sha_from(const struct chaos_next_use_replay_input *record)
{
    int i;
    for (i = 0; i < record->private_count; ++i)
        if (record->private_records[i].kind == CHAOS_RUNTIME_PRIVATE_INTENT
            && record->private_records[i].data.intent.intent_sha256_present)
            return record->private_records[i].data.intent.intent_sha256;
    return "";
}

static int capture_action(struct chaos_next_use_replay_input *record, int family,
                          long root)
{
    struct chaos_next_use_snapshot snap;
    struct chaos_fountain_token token;
    int before, acted;

    memset(record, 0, sizeof *record);
    monstermoves = 40;
    if (!chaos_next_use_snapshot_export(&snap))
        return 0;
    before = (int)chaos_next_use_runtime_private_count();
    memset(&token, 0, sizeof token);
    acted = chaos_next_use_on_action(family, root, &token);
    record->operation = CHAOS_REPLAY_ACTION;
    record->family = family;
    record->root = root;
    memcpy(record->source_sha256, snap.source_sha256, 65);
    record->cursor = 1;
    record->at_move = monstermoves;
    record->w_runtime = snap.w_runtime;
    record->callback_ordinal = 1;
    record->state = 0;
    record->expected_token = token;
    if (family == CHAOS_NEXT_USE_FAMILY_W)
        record->slot_w = CHAOS_SLOT_W_CONSUMED_QUIET;
    else
        record->slot_w = snap.slot_w;
    if (family == CHAOS_NEXT_USE_FAMILY_F)
        record->slot_f = snap.slot_f;
    else
        record->slot_f = snap.slot_f;
    (void)acted;
    return copy_new_privates(before, record);
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
    if (!strcmp(mode, "save_replay")) {
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
        fill_replay(&record, &snap, 2);
        status = chaos_next_use_replay_record(&record);
        if (!chaos_next_use_snapshot_export(&live))
            return 1;
        printf("{\"tag\":\"save_replay\",\"restored\":%d,\"status\":%d,\"slot_w\":%d}\n",
               restored, status, live.slot_w);
        return installed && restored && status == CHAOS_REPLAY_BLOCKED_REPLAY
               && live.slot_w == CHAOS_SLOT_W_PENDING ? 0 : 1;
    }
    if (!strcmp(mode, "apply_w") || !strcmp(mode, "apply_w_save")
        || !strcmp(mode, "apply_f") || !strcmp(mode, "apply_wf")
        || !strcmp(mode, "apply_w_bad_intent")) {
        struct chaos_next_use_replay_input recorded;
        char origin_w[320], origin_f[320], origins[700];
        const char *sha;
        int restored = 1, second;
        FILE *fp;
        int fd;

        if (snprintf(origin_w, sizeof origin_w,
                "{\"end_seq\":12,\"fact\":\"ordinary_whistle\",\"family\":\"W\","
                "\"level_dlevel\":1,\"level_dnum\":0,\"move\":10,"
                "\"notice_seq\":11,\"root\":10,\"run\":\"%s\"}", run_hex) < 1)
            return 1;
        if (snprintf(origin_f, sizeof origin_f,
                "{\"end_seq\":22,\"fact\":\"water_refreshed\",\"family\":\"F\","
                "\"level_dlevel\":1,\"level_dnum\":0,\"move\":10,"
                "\"notice_seq\":21,\"root\":20,\"run\":\"%s\"}", run_hex) < 1)
            return 1;
        chaos_next_use_runtime_reset();
        if (!strcmp(mode, "apply_f")) {
            if (!install_ops(fountain_lua, "[\"F\"]", origin_f, 1,
                             "next-use-v2-F", 0, 20, 0, 1))
                return 1;
            if (!capture_action(&recorded, CHAOS_NEXT_USE_FAMILY_F, 20))
                return 1;
        } else if (!strcmp(mode, "apply_wf")) {
            if (snprintf(origins, sizeof origins, "%s,%s", origin_w, origin_f) < 1)
                return 1;
            if (!install_ops(wf_lua, "[\"W\",\"F\"]", origins, 2,
                             "next-use-v2-WF", 10, 20, 1, 1))
                return 1;
            if (!capture_action(&recorded, CHAOS_NEXT_USE_FAMILY_W, 10))
                return 1;
        } else {
            if (!install_ops(quiet_lua, "[\"W\"]", origin_w, 1,
                             "next-use-v2-W", 10, 0, 1, 0))
                return 1;
            if (!strcmp(mode, "apply_w_save")) {
                fp = tmpfile();
                if (!fp) return 1;
                fd = fileno(fp);
                chaos_next_use_save(fd);
                chaos_next_use_runtime_reset();
                if (fseek(fp, 0, SEEK_SET)) return 1;
                restored = chaos_next_use_restore(fd);
                if (!restored) return 1;
                if (!capture_action(&recorded, CHAOS_NEXT_USE_FAMILY_W, 10))
                    return 1;
                chaos_next_use_runtime_reset();
                if (fseek(fp, 0, SEEK_SET)) return 1;
                restored = chaos_next_use_restore(fd);
                fclose(fp);
                if (!restored) return 1;
            } else if (!capture_action(&recorded, CHAOS_NEXT_USE_FAMILY_W, 10))
                return 1;
        }
        sha = intent_sha_from(&recorded);
        if (!strcmp(mode, "apply_w") || !strcmp(mode, "apply_f")
            || !strcmp(mode, "apply_wf") || !strcmp(mode, "apply_w_bad_intent")) {
            chaos_next_use_runtime_reset();
            if (!strcmp(mode, "apply_f")) {
                if (!install_ops(fountain_lua, "[\"F\"]", origin_f, 1,
                                 "next-use-v2-F", 0, 20, 0, 1))
                    return 1;
            } else if (!strcmp(mode, "apply_wf")) {
                if (snprintf(origins, sizeof origins, "%s,%s", origin_w, origin_f) < 1)
                    return 1;
                if (!install_ops(wf_lua, "[\"W\",\"F\"]", origins, 2,
                                 "next-use-v2-WF", 10, 20, 1, 1))
                    return 1;
            } else if (!install_ops(quiet_lua, "[\"W\"]", origin_w, 1,
                                    "next-use-v2-W", 10, 0, 1, 0))
                return 1;
        }
        if (!strcmp(mode, "apply_w_bad_intent")
            && recorded.private_records[0].data.intent.intent_sha256_present) {
            recorded.private_records[0].data.intent.intent_sha256[0] =
                recorded.private_records[0].data.intent.intent_sha256[0] == '0'
                    ? '1' : '0';
        }
        monstermoves = 40;
        status = chaos_next_use_replay_record(&recorded);
        if (!chaos_next_use_snapshot_export(&live) && strcmp(mode, "apply_w_bad_intent"))
            return 1;
        second = chaos_next_use_replay_record(&recorded);
        printf("{\"tag\":\"%s\",\"status\":%d,\"second\":%d,\"slot_w\":%d,"
               "\"slot_f\":%d,\"restored\":%d,\"intent_sha\":\"%s\"}\n",
               mode, status, second, live.slot_w, live.slot_f, restored, sha);
        if (!strcmp(mode, "apply_w_bad_intent"))
            return status == CHAOS_REPLAY_BLOCKED_REPLAY
                   && second == CHAOS_REPLAY_BLOCKED_REPLAY ? 0 : 1;
        return status == CHAOS_REPLAY_APPLIED
               && second == CHAOS_REPLAY_BLOCKED_REPLAY
               && sha[0] ? 0 : 1;
    }
    return 2;
}
