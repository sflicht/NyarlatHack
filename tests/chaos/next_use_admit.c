/* ENGINE-UNIT: real next-use admission and runtime install clocks.
 * Host globals satisfy hack.h; this is not linked-game gameplay. */
#include "hack.h"
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

static int receipt_fail(void *opaque, const struct chaos_next_use_private_record *record)
{
    (void)opaque;
    (void)record;
    return 0;
}

static int build_envelope(int at_safe, int origin_root, int ttl,
                          char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1],
                          size_t *canonical_length,
                          struct chaos_next_use_envelope *envelope)
{
    unsigned char digest[32];
    char source_sha[65], raw[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    int n, notice, end;
    if (chaos_next_use_sha256(source_text, sizeof source_text - 1, digest)
        != CHAOS_NEXT_USE_OK)
        return 0;
    digest_hex(digest, source_sha);
    notice = origin_root + 1;
    end = origin_root + 2;
    n = snprintf(raw, sizeof raw,
        "{\"at\":%d,\"cost\":1,\"id\":1,\"next_use_program_v\":2,"
        "\"operations\":[\"W\"],\"origin_refs\":[{\"end_seq\":%d,"
        "\"fact\":\"ordinary_whistle\",\"family\":\"W\",\"level_dlevel\":1,"
        "\"level_dnum\":0,\"move\":10,\"notice_seq\":%d,\"root\":%d,"
        "\"run\":\"%s\"}],\"source\":\"%s\",\"source_sha256\":\"%s\","
        "\"telegraph\":\"next-use-v2-W\",\"ttl\":%d,\"variant\":0}",
        at_safe, end, notice, origin_root, run_hex, source_text, source_sha,
        ttl);
    if (n < 1 || (size_t)n >= sizeof raw) return 0;
    if (chaos_next_use_jcs(raw, (size_t)n, canonical,
                           CHAOS_NEXT_USE_ENVELOPE_MAX + 1, canonical_length)
        != CHAOS_NEXT_USE_OK)
        return 0;
    return chaos_next_use_parse_envelope(canonical, *canonical_length, envelope)
        == CHAOS_NEXT_USE_OK;
}

static int admit_program(int at_safe, int at_move, int origin_root, int ttl,
                         struct chaos_next_use_admission *out,
                         char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1],
                         size_t *canonical_length,
                         chaos_next_use_receipt_fn deliver)
{
    struct chaos_next_use_envelope envelope;
    struct chaos_next_use_admission source;
    struct chaos_next_use_attempt_gate gate;
    memset(&source, 0, sizeof source);
    chaos_state_init(&source.budget_state);
    source.program.phase = CHAOS_ATTEMPT_OPEN;
    gate.phase = CHAOS_ATTEMPT_OPEN;
    gate.reason = 0;
    if (!build_envelope(at_safe, origin_root, ttl, canonical, canonical_length,
                        &envelope))
        return CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    return chaos_next_use_admit(out, &source, &gate, &envelope, canonical,
                                *canonical_length, 0, at_move, 1, deliver,
                                NULL);
}

static int install_program(const struct chaos_next_use_admission *admission,
                           int origin_root)
{
    char source_sha[65];
    unsigned char digest[32];
    if (chaos_next_use_sha256(source_text, sizeof source_text - 1, digest)
        != CHAOS_NEXT_USE_OK)
        return 0;
    digest_hex(digest, source_sha);
    return chaos_next_use_runtime_install(admission, source_text,
                                          sizeof source_text - 1, source_sha, 1,
                                          1, origin_root, 100000, 0, 0, 0, 1, 0);
}

static void print_runtime(int install, int preflight)
{
    const struct chaos_next_use_runtime_private_record *record =
        chaos_next_use_runtime_private_at(1);
    printf("{\"install\":%d,\"preflight\":%d,\"private\":%zu,"
           "\"at_move\":%d,\"at_safe\":%d,\"expiry\":%d}\n",
           install, preflight, chaos_next_use_runtime_private_count(),
           record ? record->at_move : -1,
           record ? record->data.admission.at_safe : -1,
           record ? record->data.admission.program_expiry : -1);
}

static int run_install(int at_safe, int at_move, int origin_root, int ttl,
                       int probe_move, const char *tamper)
{
    struct chaos_next_use_admission admitted;
    char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    size_t canonical_length = 0;
    int admit_rc, installed, preflight;
    memset(&admitted, 0, sizeof admitted);
    chaos_next_use_runtime_reset();
    admit_rc = admit_program(at_safe, at_move, origin_root, ttl, &admitted,
                             canonical, &canonical_length, receipt_ok);
    printf("{\"admit\":%d}\n", admit_rc);
    if (admit_rc != CHAOS_NEXT_USE_ADMISSION_OK) {
        print_runtime(0, 0);
        return admit_rc == CHAOS_NEXT_USE_ADMISSION_SCHEMA ? 0 : 1;
    }
    if (tamper && !strcmp(tamper, "safe-index"))
        admitted.carrier.records[1].data.admission.at_safe = at_safe + 1;
    else if (tamper && !strcmp(tamper, "attempt-move"))
        admitted.carrier.records[0].at_move = at_move + 1;
    else if (tamper && !strcmp(tamper, "expiry"))
        admitted.program.program_expiry = at_move + 50;
    installed = install_program(&admitted, origin_root);
    monstermoves = probe_move;
    preflight = chaos_next_use_action_preflight(CHAOS_NEXT_USE_FAMILY_W,
                                                origin_root);
    print_runtime(installed, preflight);
    return 0;
}

int main(int argc, char **argv)
{
    struct chaos_next_use_admission first, second;
    struct chaos_next_use_attempt_gate gate;
    char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    size_t canonical_length = 0;
    int admit_rc, second_rc, installed;
    const char *tamper = "";
    if (argc >= 2 && argv[1][0] && argv[1][0] < '0')
        return 2;
    if (argc >= 2 && !strcmp(argv[1], "ok")) {
        memset(&first, 0, sizeof first);
        chaos_next_use_runtime_reset();
        admit_rc = admit_program(7, 40, 123, 100, &first, canonical,
                                 &canonical_length, receipt_ok);
        installed = install_program(&first, 123);
        printf("{\"admit\":%d,\"spent\":%d,\"phase\":%d,\"install\":%d,"
               "\"cost\":1}\n",
               admit_rc, first.budget_state.spent, first.program.phase,
               installed);
        return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "receipt-fail")) {
        memset(&first, 0, sizeof first);
        chaos_next_use_runtime_reset();
        admit_rc = admit_program(7, 40, 123, 100, &first, canonical,
                                 &canonical_length, receipt_fail);
        installed = install_program(&first, 123);
        printf("{\"admit\":%d,\"spent\":%d,\"phase\":%d,\"install\":%d}\n",
               admit_rc, first.budget_state.spent, first.program.phase,
               installed);
        return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "second-call")) {
        struct chaos_next_use_envelope envelope;
        memset(&first, 0, sizeof first);
        memset(&second, 0, sizeof second);
        chaos_next_use_runtime_reset();
        admit_rc = admit_program(7, 40, 123, 100, &first, canonical,
                                 &canonical_length, receipt_ok);
        gate.phase = CHAOS_ATTEMPT_OPEN;
        gate.reason = 0;
        if (!build_envelope(7, 123, 100, canonical, &canonical_length, &envelope))
            return 1;
        second_rc = chaos_next_use_admit(&second, &first, &gate, &envelope,
                                         canonical, canonical_length, 0, 40, 10,
                                         receipt_ok, NULL);
        printf("{\"first\":%d,\"second\":%d,\"spent\":%d,\"phase\":%d}\n",
               admit_rc, second_rc, first.budget_state.spent, first.program.phase);
        return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "budget")) {
        struct chaos_next_use_admission source, out;
        struct chaos_next_use_envelope envelope;
        struct chaos_next_use_attempt_gate g;
        memset(&source, 0, sizeof source);
        memset(&out, 0, sizeof out);
        chaos_state_init(&source.budget_state);
        source.budget_state.spent = 12;
        source.program.phase = CHAOS_ATTEMPT_OPEN;
        g.phase = CHAOS_ATTEMPT_OPEN;
        if (!build_envelope(7, 123, 100, canonical, &canonical_length, &envelope))
            return 1;
        admit_rc = chaos_next_use_admit(&out, &source, &g, &envelope, canonical,
                                        canonical_length, 0, 40, 1, receipt_ok,
                                        NULL);
        printf("{\"admit\":%d,\"spent\":%d,\"out_spent\":%d}\n", admit_rc,
               source.budget_state.spent, out.budget_state.spent);
        return 0;
    }
    if (argc < 6) return 2;
    if (argc > 6) tamper = argv[6];
    return run_install(atoi(argv[1]), atoi(argv[2]), atoi(argv[3]), atoi(argv[4]),
                       atoi(argv[5]), tamper);
}
