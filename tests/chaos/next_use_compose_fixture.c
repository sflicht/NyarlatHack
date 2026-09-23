/* ENGINE-UNIT: two handwritten next-use programs, same native adapters.
 * Not a story-specific engine edit and not ordinary play. */
#include "hack.h"
#include "chaos.h"
#include "chaos_next_use_admission.h"
#include "chaos_next_use_runtime.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

static const char run_hex[] =
    "0000000000000000000000000000000000000000000000000000000000000000";
static const char state_lua[] =
    "return {on_action=function(c) "
    "if c.trigger==[[W]] then "
    "return {next_use_intent_v=2, op=[[whistle_attention]], state=1} end "
    "if c.state==0 then "
    "return {next_use_intent_v=2, op=[[fountain_refresh]], state=0} end "
    "return {next_use_intent_v=2, op=[[quiet]], state=c.state} end}";
static const char witness_lua[] =
    "return {on_action=function(c) "
    "if c.trigger==[[W]] then "
    "return {next_use_intent_v=2, op=[[whistle_attention]], state=0} end "
    "if c.own_witnessed==[[W]] then "
    "return {next_use_intent_v=2, op=[[fountain_refresh]], state=1} end "
    "return {next_use_intent_v=2, op=[[quiet]], state=0} end}";

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

static int receipt_ok(void *opaque,
                      const struct chaos_next_use_private_record *record)
{
    (void)opaque;
    (void)record;
    return 1;
}

static int install_wf(const char *lua)
{
    struct chaos_next_use_envelope envelope;
    struct chaos_next_use_admission source, admitted;
    struct chaos_next_use_attempt_gate gate;
    char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    char source_sha[65], raw[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    unsigned char digest[32];
    size_t canonical_length = 0, lua_len;
    int n;

    lua_len = strlen(lua);
    memset(&source, 0, sizeof source);
    memset(&admitted, 0, sizeof admitted);
    chaos_next_use_runtime_reset();
    chaos_state_init(&source.budget_state);
    source.program.phase = CHAOS_ATTEMPT_OPEN;
    gate.phase = CHAOS_ATTEMPT_OPEN;
    gate.reason = 0;
    if (chaos_next_use_sha256(lua, lua_len, digest) != CHAOS_NEXT_USE_OK)
        return 0;
    digest_hex(digest, source_sha);
    n = snprintf(raw, sizeof raw,
        "{\"at\":7,\"cost\":2,\"id\":1,\"next_use_program_v\":2,"
        "\"operations\":[\"W\",\"F\"],\"origin_refs\":["
        "{\"end_seq\":12,\"fact\":\"ordinary_whistle\",\"family\":\"W\","
        "\"level_dlevel\":1,\"level_dnum\":0,\"move\":10,\"notice_seq\":11,"
        "\"root\":10,\"run\":\"%s\"},"
        "{\"end_seq\":22,\"fact\":\"water_refreshed\",\"family\":\"F\","
        "\"level_dlevel\":1,\"level_dnum\":0,\"move\":10,\"notice_seq\":21,"
        "\"root\":20,\"run\":\"%s\"}],"
        "\"source\":\"%s\",\"source_sha256\":\"%s\","
        "\"telegraph\":\"next-use-v2-WF\",\"ttl\":100,\"variant\":0}",
        run_hex, run_hex, lua, source_sha);
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
                                          1, 1, 10, 110, 20, 110, 0, 1, 1);
}

static int arm_w(void)
{
    struct chaos_fountain_token token;
    monstermoves = 40;
    memset(&token, 0, sizeof token);
    if (!chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, &token))
        return 0;
    chaos_next_use_capture_whistle(10, 7, 40);
    return 1;
}

static int deliver_witness(void)
{
    struct chaos_whistle_witness witness;
    const struct chaos_next_use_public_record *pub;
    monstermoves = 45;
    if (!chaos_next_use_whistle_attention(7, 30)) return 0;
    if (!chaos_next_use_manifestation_begin(7, 40)) return 0;
    chaos_next_use_manifestation_notice(40, 41);
    chaos_next_use_manifestation_end(40, 41, 42, 1);
    memset(&witness, 0, sizeof witness);
    witness.root = 40;
    witness.notice_seq = 41;
    witness.manifestation_delivered = 1;
    witness.displaced = 1;
    chaos_next_use_on_manifestation(&witness, 42);
    if (chaos_next_use_runtime_public_count() != 1) return 0;
    pub = chaos_next_use_runtime_public_at(0);
    return pub && pub->phase == CHAOS_PUBLIC_WITNESSED;
}

static void print_f(const char *tag, int installed)
{
    struct chaos_next_use_snapshot snap;
    struct chaos_fountain_token token;
    const struct chaos_next_use_runtime_private_record *rec;
    int acted, i, n, effect = 0, exported;
    memset(&token, 0, sizeof token);
    acted = chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_F, 20, &token);
    if (acted && token.remap) {
        token.consumed = 1;
        chaos_next_use_fountain_result(&token, CHAOS_FOUNTAIN_REMAPPED);
    }
    n = (int)chaos_next_use_runtime_private_count();
    for (i = 0; i < n; ++i) {
        rec = chaos_next_use_runtime_private_at((size_t)i);
        if (rec->kind == CHAOS_RUNTIME_PRIVATE_EFFECT
            && rec->data.effect.family == CHAOS_NEXT_USE_FAMILY_F)
            effect = rec->data.effect.outcome;
    }
    exported = chaos_next_use_snapshot_export(&snap);
    printf("{\"tag\":\"%s\",\"installed\":%d,\"acted\":%d,\"remap\":%d,"
           "\"active\":%d,\"effect\":%d,\"public\":%d,"
           "\"state\":%d,\"slot_w\":%d,\"slot_f\":%d,\"w_runtime\":%d}\n",
           tag, installed, acted, token.remap, token.active, effect,
           (int)chaos_next_use_runtime_public_count(),
           exported ? snap.state : -1,
           exported ? snap.slot_w : -1,
           exported ? snap.slot_f : -1,
           exported ? snap.w_runtime : -1);
}

int main(int argc, char **argv)
{
    const char *mode = argc > 1 ? argv[1] : "";
    int installed;
    if (!strcmp(mode, "state_f_first")) {
        installed = install_wf(state_lua);
        monstermoves = 40;
        print_f(mode, installed);
        return installed ? 0 : 1;
    }
    if (!strcmp(mode, "state_after_w")) {
        installed = install_wf(state_lua) && arm_w();
        print_f(mode, installed);
        return installed ? 0 : 1;
    }
    if (!strcmp(mode, "witness_delivered")) {
        installed = install_wf(witness_lua) && arm_w() && deliver_witness();
        print_f(mode, installed);
        return installed ? 0 : 1;
    }
    if (!strcmp(mode, "witness_undelivered")) {
        installed = install_wf(witness_lua) && arm_w();
        print_f(mode, installed);
        return installed ? 0 : 1;
    }
    return 2;
}
