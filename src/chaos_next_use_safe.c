/* NetHack General Public License. Opt-in next-use admission at a safe point. */
#define _GNU_SOURCE
#include "hack.h"
#include "chaos_lua.h"
#include "chaos_next_use.h"
#include "chaos_next_use_io.h"
#include "chaos_next_use_runtime.h"
#include "chaos_next_use_safe.h"

#include <string.h>

static int settled;

void chaos_next_use_safe_reset_for_test(void)
{
    settled = 0;
    chaos_next_use_runtime_reset();
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

static int receipt_ok(void *opaque, const struct chaos_next_use_private_record *record)
{
    (void)opaque;
    (void)record;
    return 1;
}

int chaos_next_use_safe_try(const struct chaos_next_use_safe_request *request,
                            struct chaos_next_use_safe_result *result)
{
    char raw[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    char canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    struct chaos_next_use_envelope envelope;
    struct chaos_next_use_admission source, admitted;
    struct chaos_next_use_attempt_gate gate;
    struct chaos_next_use_origin_ref *origin;
    chaos_next_use_receipt_fn deliver;
    size_t n = 0, written = 0;
    int rc, expiry;

    if (!result)
        return CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    memset(result, 0, sizeof *result);
    if (!request || !request->enabled || request->dir < 0 || settled)
        return CHAOS_NEXT_USE_ADMISSION_NOT_OPEN;
    if (chaos_next_use_envelope_read(request->dir, raw, sizeof raw, &n)
        != CHAOS_NEXT_USE_OK)
        return CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    if (chaos_next_use_parse_envelope(raw, n, &envelope) != CHAOS_NEXT_USE_OK
        || chaos_next_use_jcs(raw, n, canonical, sizeof canonical, &written)
           != CHAOS_NEXT_USE_OK) {
        settled = 1;
        result->loaded = 1;
        result->rejected = 1;
        return CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    }
    result->loaded = 1;
    if (envelope.at > request->at_safe) {
        result->pending = 1;
        return CHAOS_NEXT_USE_ADMISSION_NOT_OPEN;
    }
    settled = 1;
    origin = &envelope.origin_refs[0];
    expiry = origin->move > 2147483547 ? origin->move : origin->move + 100;
    if (envelope.at != request->at_safe
        || !request->budget
        || !hex64(request->run_hex)
        || strcmp(origin->run, request->run_hex)
        || origin->level_dnum != request->level_dnum
        || origin->level_dlevel != request->level_dlevel
        || request->at_move < 0
        || request->at_move > expiry
        || chaos_lua_next_use_load(envelope.source, envelope.source_length) != 0) {
        result->rejected = 1;
        return CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    }
    if (request->telegraph) {
        if (!request->telegraph(request->telegraph_opaque, envelope.telegraph)) {
            result->rejected = 1;
            return CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT;
        }
        result->telegraph_count = 1;
    }
    memset(&source, 0, sizeof source);
    memset(&admitted, 0, sizeof admitted);
    source.budget_state = *request->budget;
    if (!chaos_state_valid(&source.budget_state))
        chaos_state_init(&source.budget_state);
    source.program.phase = CHAOS_ATTEMPT_OPEN;
    gate.phase = CHAOS_ATTEMPT_OPEN;
    gate.reason = 0;
    deliver = request->receipt ? request->receipt : receipt_ok;
    rc = chaos_next_use_admit(&admitted, &source, &gate, &envelope,
                              canonical, written, request->sanity,
                              request->at_move, 1, deliver,
                              request->receipt_opaque);
    result->spent = admitted.budget_state.spent;
    if (rc != CHAOS_NEXT_USE_ADMISSION_OK) {
        result->rejected = 1;
        return rc;
    }
    result->admitted = 1;
    if (!chaos_next_use_runtime_install(&admitted, envelope.source,
                                        envelope.source_length,
                                        envelope.source_sha256, 1, 1,
                                        origin->root, expiry, 0, 0,
                                        envelope.variant, 0, 0)) {
        result->rejected = 1;
        return CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT;
    }
    result->active = 1;
    return CHAOS_NEXT_USE_ADMISSION_OK;
}
