/* ENGINE-UNIT: real next-use admission and runtime install clocks.
 * Host globals satisfy hack.h; this is not linked-game gameplay. */
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

static int origin_json(char *out, size_t cap, int root, const char *family,
                       const char *fact)
{
    return snprintf(out, cap,
        "{\"end_seq\":%d,\"fact\":\"%s\",\"family\":\"%s\",\"level_dlevel\":1,"
        "\"level_dnum\":0,\"move\":10,\"notice_seq\":%d,\"root\":%d,"
        "\"run\":\"%s\"}",
        root + 2, fact, family, root + 1, root, run_hex);
}

static int build_envelope_kind(int at_safe, int origin_w, int origin_f, int ttl,
                               const char *kind,
                               char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1],
                               size_t *canonical_length,
                               struct chaos_next_use_envelope *envelope)
{
    unsigned char digest[32];
    char source_sha[65], raw[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    char o1[320], o2[320];
    const char *ops, *telegraph;
    int n, cost;
    if (chaos_next_use_sha256(source_text, sizeof source_text - 1, digest)
        != CHAOS_NEXT_USE_OK)
        return 0;
    digest_hex(digest, source_sha);
    if (!strcmp(kind, "F")) {
        cost = 1;
        ops = "[\"F\"]";
        telegraph = "next-use-v2-F";
        if (origin_json(o1, sizeof o1, origin_f, "F", "water_refreshed") < 1)
            return 0;
        n = snprintf(raw, sizeof raw,
            "{\"at\":%d,\"cost\":%d,\"id\":1,\"next_use_program_v\":2,"
            "\"operations\":%s,\"origin_refs\":[%s],\"source\":\"%s\","
            "\"source_sha256\":\"%s\",\"telegraph\":\"%s\",\"ttl\":%d,"
            "\"variant\":0}",
            at_safe, cost, ops, o1, source_text, source_sha, telegraph, ttl);
    } else if (!strcmp(kind, "WF")) {
        cost = 2;
        ops = "[\"W\",\"F\"]";
        telegraph = "next-use-v2-WF";
        if (origin_json(o1, sizeof o1, origin_w, "W", "ordinary_whistle") < 1
            || origin_json(o2, sizeof o2, origin_f, "F", "water_refreshed") < 1)
            return 0;
        n = snprintf(raw, sizeof raw,
            "{\"at\":%d,\"cost\":%d,\"id\":1,\"next_use_program_v\":2,"
            "\"operations\":%s,\"origin_refs\":[%s,%s],\"source\":\"%s\","
            "\"source_sha256\":\"%s\",\"telegraph\":\"%s\",\"ttl\":%d,"
            "\"variant\":0}",
            at_safe, cost, ops, o1, o2, source_text, source_sha, telegraph, ttl);
    } else {
        cost = 1;
        ops = "[\"W\"]";
        telegraph = "next-use-v2-W";
        if (origin_json(o1, sizeof o1, origin_w, "W", "ordinary_whistle") < 1)
            return 0;
        n = snprintf(raw, sizeof raw,
            "{\"at\":%d,\"cost\":%d,\"id\":1,\"next_use_program_v\":2,"
            "\"operations\":%s,\"origin_refs\":[%s],\"source\":\"%s\","
            "\"source_sha256\":\"%s\",\"telegraph\":\"%s\",\"ttl\":%d,"
            "\"variant\":0}",
            at_safe, cost, ops, o1, source_text, source_sha, telegraph, ttl);
    }
    if (n < 1 || (size_t)n >= sizeof raw) return 0;
    if (chaos_next_use_jcs(raw, (size_t)n, canonical,
                           CHAOS_NEXT_USE_ENVELOPE_MAX + 1, canonical_length)
        != CHAOS_NEXT_USE_OK)
        return 0;
    return chaos_next_use_parse_envelope(canonical, *canonical_length, envelope)
        == CHAOS_NEXT_USE_OK;
}

static int build_envelope(int at_safe, int origin_root, int ttl,
                          char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1],
                          size_t *canonical_length,
                          struct chaos_next_use_envelope *envelope)
{
    return build_envelope_kind(at_safe, origin_root, 0, ttl, "W", canonical,
                               canonical_length, envelope);
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

static int admit_kind(const char *kind, int origin_w, int origin_f,
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
    if (!build_envelope_kind(7, origin_w, origin_f, 100, kind, canonical,
                             canonical_length, &envelope))
        return CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    return chaos_next_use_admit(out, &source, &gate, &envelope, canonical,
                                *canonical_length, 0, 40, 1, deliver, NULL);
}

static int install_kind(const struct chaos_next_use_admission *admission,
                        int origin_w, int origin_f)
{
    char source_sha[65];
    unsigned char digest[32];
    long w_dead = origin_w ? 100000 : 0;
    long f_dead = origin_f ? 100000 : 0;
    if (chaos_next_use_sha256(source_text, sizeof source_text - 1, digest)
        != CHAOS_NEXT_USE_OK)
        return 0;
    digest_hex(digest, source_sha);
    return chaos_next_use_runtime_install(admission, source_text,
                                          sizeof source_text - 1, source_sha, 1,
                                          1, origin_w, w_dead, origin_f, f_dead,
                                          0, origin_w ? 1 : 0,
                                          origin_f ? 1 : 0);
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
    if (argc >= 2 && !strcmp(argv[1], "f-ok")) {
        memset(&first, 0, sizeof first);
        chaos_next_use_runtime_reset();
        admit_rc = admit_kind("F", 0, 50, &first, canonical, &canonical_length,
                              receipt_ok);
        installed = install_kind(&first, 0, 50);
        printf("{\"admit\":%d,\"spent\":%d,\"cost\":%d,\"install\":%d,"
               "\"slot_w\":%d,\"slot_f\":%d,\"phase\":%d,\"private\":%zu}\n",
               admit_rc, first.budget_state.spent,
               first.carrier.records[1].data.admission.cost, installed,
               first.program.slot_w, first.program.slot_f, first.program.phase,
               chaos_next_use_runtime_private_count());
        return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "wf-ok")) {
        memset(&first, 0, sizeof first);
        chaos_next_use_runtime_reset();
        admit_rc = admit_kind("WF", 10, 20, &first, canonical, &canonical_length,
                              receipt_ok);
        installed = install_kind(&first, 10, 20);
        printf("{\"admit\":%d,\"spent\":%d,\"cost\":%d,\"install\":%d,"
               "\"slot_w\":%d,\"slot_f\":%d,\"ops\":%d,\"phase\":%d}\n",
               admit_rc, first.budget_state.spent,
               first.carrier.records[1].data.admission.cost, installed,
               first.program.slot_w, first.program.slot_f,
               first.carrier.records[1].data.admission.operation_count,
               first.program.phase);
        return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "install-fail")) {
        memset(&first, 0, sizeof first);
        chaos_next_use_runtime_reset();
        admit_rc = admit_kind("W", 123, 0, &first, canonical, &canonical_length,
                              receipt_ok);
        first.carrier.records[1].data.admission.at_safe = 99;
        installed = install_kind(&first, 123, 0);
        printf("{\"admit\":%d,\"spent\":%d,\"install\":%d,\"phase\":%d,"
               "\"seq\":%d,\"private\":%zu}\n",
               admit_rc, first.budget_state.spent, installed, first.program.phase,
               first.program.next_private_seq,
               chaos_next_use_runtime_private_count());
        return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "preserve-runtime")) {
        size_t before;
        int first_install, second_install, second_admit;
        memset(&first, 0, sizeof first);
        memset(&second, 0, sizeof second);
        chaos_next_use_runtime_reset();
        admit_rc = admit_kind("W", 123, 0, &first, canonical, &canonical_length,
                              receipt_ok);
        first_install = install_kind(&first, 123, 0);
        before = chaos_next_use_runtime_private_count();
        second_admit = admit_kind("F", 0, 50, &second, canonical,
                                  &canonical_length, receipt_ok);
        second.carrier.records[1].data.admission.at_safe = 99;
        second_install = install_kind(&second, 0, 50);
        printf("{\"first_admit\":%d,\"first_install\":%d,\"second_admit\":%d,"
               "\"second_install\":%d,\"private_before\":%zu,\"private_after\":%zu,"
               "\"first_spent\":%d,\"second_spent\":%d}\n",
               admit_rc, first_install, second_admit, second_install, before,
               chaos_next_use_runtime_private_count(), first.budget_state.spent,
               second.budget_state.spent);
        return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "carrier")) {
        struct chaos_next_use_admission source, out;
        struct chaos_next_use_envelope envelope;
        struct chaos_next_use_attempt_gate g;
        memset(&source, 0, sizeof source);
        memset(&out, 0, sizeof out);
        chaos_state_init(&source.budget_state);
        source.program.phase = CHAOS_ATTEMPT_OPEN;
        source.carrier.capacity_records = 2;
        source.carrier.capacity_bytes = CHAOS_NEXT_USE_CARRIER_BYTES;
        g.phase = CHAOS_ATTEMPT_OPEN;
        if (!build_envelope(7, 123, 100, canonical, &canonical_length, &envelope))
            return 1;
        admit_rc = chaos_next_use_admit(&out, &source, &g, &envelope, canonical,
                                        canonical_length, 0, 40, 1, receipt_ok,
                                        NULL);
        printf("{\"admit\":%d,\"spent\":%d,\"out_spent\":%d,\"count\":%d}\n",
               admit_rc, source.budget_state.spent, out.budget_state.spent,
               source.carrier.count);
        return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "parse-dup")) {
        struct chaos_next_use_envelope envelope;
        char raw[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
        unsigned char digest[32];
        char source_sha[65];
        int n, rc;
        if (chaos_next_use_sha256(source_text, sizeof source_text - 1, digest)
            != CHAOS_NEXT_USE_OK)
            return 1;
        digest_hex(digest, source_sha);
        n = snprintf(raw, sizeof raw,
            "{\"at\":7,\"cost\":2,\"id\":1,\"next_use_program_v\":2,"
            "\"operations\":[\"W\",\"W\"],\"origin_refs\":["
            "{\"end_seq\":12,\"fact\":\"ordinary_whistle\",\"family\":\"W\","
            "\"level_dlevel\":1,\"level_dnum\":0,\"move\":10,\"notice_seq\":11,"
            "\"root\":10,\"run\":\"%s\"},"
            "{\"end_seq\":22,\"fact\":\"ordinary_whistle\",\"family\":\"W\","
            "\"level_dlevel\":1,\"level_dnum\":0,\"move\":10,\"notice_seq\":21,"
            "\"root\":20,\"run\":\"%s\"}],\"source\":\"%s\","
            "\"source_sha256\":\"%s\",\"telegraph\":\"next-use-v2-WF\","
            "\"ttl\":100,\"variant\":0}",
            run_hex, run_hex, source_text, source_sha);
        rc = chaos_next_use_parse_envelope(raw, (size_t)n, &envelope);
        printf("{\"parse\":%d}\n", rc);
        return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "parse-malformed")) {
        struct chaos_next_use_envelope envelope;
        char raw[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
        unsigned char digest[32];
        char source_sha[65];
        int n, rc;
        if (chaos_next_use_sha256(source_text, sizeof source_text - 1, digest)
            != CHAOS_NEXT_USE_OK)
            return 1;
        digest_hex(digest, source_sha);
        n = snprintf(raw, sizeof raw,
            "{\"at\":7,\"cost\":1,\"id\":1,\"next_use_program_v\":2,"
            "\"operations\":[\"W\"],\"origin_refs\":["
            "{\"end_seq\":10,\"fact\":\"ordinary_whistle\",\"family\":\"W\","
            "\"level_dlevel\":1,\"level_dnum\":0,\"move\":10,\"notice_seq\":11,"
            "\"root\":10,\"run\":\"%s\"}],\"source\":\"%s\","
            "\"source_sha256\":\"%s\",\"telegraph\":\"next-use-v2-W\","
            "\"ttl\":100,\"variant\":0}",
            run_hex, source_text, source_sha);
        rc = chaos_next_use_parse_envelope(raw, (size_t)n, &envelope);
        printf("{\"parse\":%d}\n", rc);
        return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "public-bound")) {
        struct chaos_whistle_witness witness;
        memset(&first, 0, sizeof first);
        chaos_next_use_runtime_reset();
        admit_rc = admit_kind("W", 123, 0, &first, canonical, &canonical_length,
                              receipt_ok);
        installed = install_kind(&first, 123, 0);
        memset(&witness, 0, sizeof witness);
        witness.root = 10;
        witness.notice_seq = 11;
        witness.manifestation_delivered = 1;
        witness.displaced = 1;
        chaos_next_use_on_manifestation(&witness, 12);
        chaos_next_use_on_manifestation(&witness, 12);
        printf("{\"admit\":%d,\"install\":%d,\"public\":%zu,\"private\":%zu}\n",
               admit_rc, installed, chaos_next_use_runtime_public_count(),
               chaos_next_use_runtime_private_count());
        return 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "delay-twice")) {
        static const char delay_src[] =
            "return {on_action=function(c) return {next_use_intent_v=2, op=[[delay]], state=0} end}";
        struct chaos_next_use_envelope envelope;
        struct chaos_next_use_admission source, admitted;
        struct chaos_next_use_attempt_gate gate;
        struct chaos_fountain_token token;
        unsigned char digest[32];
        char source_sha[65], origin[320], raw[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
        int n, first_act, second_act, second_ready, installed;

        memset(&source, 0, sizeof source);
        memset(&admitted, 0, sizeof admitted);
        chaos_next_use_runtime_reset();
        chaos_state_init(&source.budget_state);
        source.program.phase = CHAOS_ATTEMPT_OPEN;
        gate.phase = CHAOS_ATTEMPT_OPEN;
        gate.reason = 0;
        if (chaos_next_use_sha256(delay_src, sizeof delay_src - 1, digest)
            != CHAOS_NEXT_USE_OK)
            return 1;
        digest_hex(digest, source_sha);
        if (origin_json(origin, sizeof origin, 123, "W", "ordinary_whistle") < 1)
            return 1;
        n = snprintf(raw, sizeof raw,
            "{\"at\":7,\"cost\":1,\"id\":1,\"next_use_program_v\":2,"
            "\"operations\":[\"W\"],\"origin_refs\":[%s],\"source\":\"%s\","
            "\"source_sha256\":\"%s\",\"telegraph\":\"next-use-v2-W\",\"ttl\":100,"
            "\"variant\":0}",
            origin, delay_src, source_sha);
        if (n < 1 || (size_t)n >= sizeof raw)
            return 1;
        if (chaos_next_use_jcs(raw, (size_t)n, canonical, sizeof canonical,
                               &canonical_length) != CHAOS_NEXT_USE_OK)
            return 1;
        if (chaos_next_use_parse_envelope(canonical, canonical_length, &envelope)
            != CHAOS_NEXT_USE_OK)
            return 1;
        admit_rc = chaos_next_use_admit(&admitted, &source, &gate, &envelope,
                                        canonical, canonical_length, 0, 40, 1,
                                        receipt_ok, NULL);
        installed = chaos_next_use_runtime_install(
            &admitted, delay_src, sizeof delay_src - 1, source_sha, 1, 1, 123,
            100000, 0, 0, 0, 1, 0);
        monstermoves = 40;
        memset(&token, 0, sizeof token);
        first_act = chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 123, &token);
        second_ready = chaos_next_use_action_preflight(CHAOS_NEXT_USE_FAMILY_W, 123);
        memset(&token, 0, sizeof token);
        second_act = chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 123, &token);
        printf("{\"admit\":%d,\"install\":%d,\"first\":%d,\"second_ready\":%d,\"second\":%d}\n",
               admit_rc, installed, first_act, second_ready, second_act);
        return 0;
    }
    if (argc < 6) return 2;
    if (argc > 6) tamper = argv[6];
    return run_install(atoi(argv[1]), atoi(argv[2]), atoi(argv[3]), atoi(argv[4]),
                       atoi(argv[5]), tamper);
}
