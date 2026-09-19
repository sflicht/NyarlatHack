/* NetHack General Public License. Opt-in next-use admission at a safe point. */
#define _GNU_SOURCE
#include "hack.h"
#include "chaos_lua.h"
#include "chaos_next_use.h"
#include "chaos_next_use_io.h"
#include "chaos_next_use_runtime.h"
#include "chaos_next_use_safe.h"

#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static int settled;
static char owned_run[65];
static int owned_run_set;
static int (*owned_warn)(void *, const char *);
static void *owned_warn_opaque;
static chaos_next_use_receipt_fn owned_receipt;
static void *owned_receipt_opaque;
static int origin_bound;
static int origin_qualifying;
static struct chaos_next_use_origin_ref origin_evidence;
static struct chaos_next_use_safe_result last_result;

void chaos_next_use_safe_reset_for_test(void)
{
    settled = 0;
    owned_run_set = 0;
    owned_run[0] = '\0';
    owned_warn = 0;
    owned_warn_opaque = 0;
    owned_receipt = 0;
    owned_receipt_opaque = 0;
    origin_bound = 0;
    origin_qualifying = 0;
    memset(&origin_evidence, 0, sizeof origin_evidence);
    memset(&last_result, 0, sizeof last_result);
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

void chaos_next_use_safe_bind_receipt(chaos_next_use_receipt_fn fn, void *opaque)
{
    owned_receipt = fn;
    owned_receipt_opaque = opaque;
}

void chaos_next_use_safe_bind_origin(const struct chaos_next_use_origin_ref *origin,
                                    int qualifying)
{
    origin_bound = 0;
    origin_qualifying = 0;
    memset(&origin_evidence, 0, sizeof origin_evidence);
    if (!origin) return;
    origin_evidence = *origin;
    origin_bound = 1;
    origin_qualifying = qualifying ? 1 : 0;
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

static int origin_evidence_ok(const struct chaos_next_use_origin_ref *origin)
{
    if (!origin_bound || !origin_qualifying || !origin)
        return 0;
    if (origin_evidence.root != origin->root
        || origin_evidence.notice_seq != origin->notice_seq
        || origin_evidence.end_seq != origin->end_seq
        || origin_evidence.family != origin->family
        || origin_evidence.level_dnum != origin->level_dnum
        || origin_evidence.level_dlevel != origin->level_dlevel
        || origin_evidence.move != origin->move)
        return 0;
    if (strcmp(origin_evidence.fact, origin->fact)
        || strcmp(origin_evidence.run, origin->run))
        return 0;
    return 1;
}

static int production_receipt(void *opaque,
                              const struct chaos_next_use_private_record *record)
{
    char line[256];
    int dir, fd, n;
    ssize_t wrote;

    if (!record) return 0;
    dir = (int)(intptr_t)opaque;
    if (dir < 0) return 0;
    n = snprintf(line, sizeof line,
                 "{\"next_use_private_v\":%d,\"kind\":%d,\"seq\":%d}\n",
                 record->next_use_private_v, record->kind, record->seq);
    if (n < 1 || (size_t)n >= sizeof line) return 0;
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

static int finish(struct chaos_next_use_safe_result *result, int rc)
{
    last_result = *result;
    return rc;
}

int chaos_next_use_on_safe(int dir, long at_safe, int sanity,
                           struct chaos_state *budget, int dnum, int dlevel)
{
    struct chaos_next_use_safe_request req;
    struct chaos_next_use_safe_result res;
    memset(&req, 0, sizeof req);
    req.dir = dir;
    req.enabled = 1;
    req.at_safe = at_safe > 2147483647L ? 2147483647 : (int)at_safe;
    req.at_move = monstermoves > 2147483547L ? 2147483547
                  : monstermoves < 0L ? 0 : (int)monstermoves;
    req.level_dnum = dnum;
    req.level_dlevel = dlevel;
    req.sanity = sanity;
    req.budget = budget;
    if (owned_run_set)
        req.run_hex = owned_run;
    req.telegraph = owned_warn;
    req.telegraph_opaque = owned_warn_opaque;
    if (owned_receipt) {
        req.receipt = owned_receipt;
        req.receipt_opaque = owned_receipt_opaque;
    } else {
        req.receipt = production_receipt;
        req.receipt_opaque = (void *)(intptr_t)dir;
    }
    return chaos_next_use_safe_try(&req, &res);
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
    size_t n = 0, written = 0;
    int rc, expiry;

    if (!result)
        return CHAOS_NEXT_USE_ADMISSION_SCHEMA;
    memset(result, 0, sizeof *result);
    if (!request || !request->enabled || request->dir < 0 || settled)
        return finish(result, CHAOS_NEXT_USE_ADMISSION_NOT_OPEN);
    if (chaos_next_use_envelope_read(request->dir, raw, sizeof raw, &n)
        != CHAOS_NEXT_USE_OK)
        return finish(result, CHAOS_NEXT_USE_ADMISSION_SCHEMA);
    if (chaos_next_use_parse_envelope(raw, n, &envelope) != CHAOS_NEXT_USE_OK
        || chaos_next_use_jcs(raw, n, canonical, sizeof canonical, &written)
           != CHAOS_NEXT_USE_OK) {
        settled = 1;
        result->loaded = 1;
        result->rejected = 1;
        return finish(result, CHAOS_NEXT_USE_ADMISSION_SCHEMA);
    }
    result->loaded = 1;
    if (envelope.at > request->at_safe) {
        result->pending = 1;
        return finish(result, CHAOS_NEXT_USE_ADMISSION_NOT_OPEN);
    }
    settled = 1;
    origin = &envelope.origin_refs[0];
    expiry = origin->move > 2147483547 ? origin->move : origin->move + 100;
    if (envelope.at != request->at_safe
        || !request->budget
        || !chaos_state_valid(request->budget)
        || !hex64(request->run_hex)
        || strcmp(origin->run, request->run_hex)
        || origin->level_dnum != request->level_dnum
        || origin->level_dlevel != request->level_dlevel
        || request->at_move < 0
        || request->at_move > expiry
        || !origin_evidence_ok(origin)
        || chaos_lua_next_use_load(envelope.source, envelope.source_length) != 0) {
        result->rejected = 1;
        return finish(result, CHAOS_NEXT_USE_ADMISSION_SCHEMA);
    }
    if (!request->telegraph
        || !request->telegraph(request->telegraph_opaque, envelope.telegraph)) {
        result->rejected = 1;
        return finish(result, CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT);
    }
    result->telegraph_count = 1;
    if (!request->receipt) {
        result->rejected = 1;
        return finish(result, CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT);
    }
    memset(&source, 0, sizeof source);
    memset(&admitted, 0, sizeof admitted);
    source.budget_state = *request->budget;
    source.program.phase = CHAOS_ATTEMPT_OPEN;
    gate.phase = CHAOS_ATTEMPT_OPEN;
    gate.reason = 0;
    rc = chaos_next_use_admit(&admitted, &source, &gate, &envelope,
                              canonical, written, request->sanity,
                              request->at_move, 1, request->receipt,
                              request->receipt_opaque);
    if (rc == CHAOS_NEXT_USE_ADMISSION_OK
        || rc == CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT) {
        *request->budget = admitted.budget_state;
        result->spent = admitted.budget_state.spent;
    }
    if (rc != CHAOS_NEXT_USE_ADMISSION_OK) {
        result->rejected = 1;
        return finish(result, rc);
    }
    result->admitted = 1;
    {
        long origin_w = 0, origin_w_deadline = 0;
        long origin_f = 0, origin_f_deadline = 0;
        int i;

        for (i = 0; i < envelope.operation_count; ++i) {
            const struct chaos_next_use_origin_ref *ref = &envelope.origin_refs[i];
            long ref_expiry = ref->move > 2147483547 ? ref->move : ref->move + 100;
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
                                            envelope.source_sha256, 1, 1,
                                            origin_w, origin_w_deadline,
                                            origin_f, origin_f_deadline,
                                            envelope.variant, 0, 0)) {
            result->rejected = 1;
            return finish(result, CHAOS_NEXT_USE_ADMISSION_RECEIPT_TRANSPORT);
        }
    }
    result->active = 1;
    return finish(result, CHAOS_NEXT_USE_ADMISSION_OK);
}
