/* Actual linked dog_move subscriber; reuse the frozen fixture verbatim. */
#include "hack.h"
#include "chaos.h"
#include "chaos_next_use_runtime.h"
#include "chaos_next_use_safe.h"
#include "wintty.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static void capture_finalize(struct monst *, struct chaos_whistle_witness *);
static void capture_reset(void);
#define chaos_next_use_safe_reset_for_test capture_reset
#define chaos_whistle_witness_finalize capture_finalize
#define main historical_dogmove_main
#include "next_use_dogmove.c"
#undef main
#undef chaos_whistle_witness_finalize
#undef chaos_next_use_safe_reset_for_test

static int transitions, manifests, intents, pubs, delivered, displaced;
static int publications, rejection_seen;
static int native_sink(void *opaque, const struct chaos_next_use_replay_input *r)
{
    struct chaos_next_use_replay_input bad;
    int i;
    assert(opaque == &transitions);
    assert(r->replay_input_v == CHAOS_NEXT_USE_REPLAY_INPUT_V);
    assert(strlen(r->source_sha256) == 64);
    for (i = 0; i < r->private_count; ++i) {
        const struct chaos_next_use_runtime_private_record *p = &r->private_records[i];
        assert(!strcmp(p->source_sha256, r->source_sha256));
        if (p->kind == CHAOS_RUNTIME_PRIVATE_INTENT) {
            ++intents;
            assert(strlen(p->data.intent.context_sha256) == 64);
            assert(strlen(p->data.intent.intent_sha256) == 64);
        }
    }
    if (r->operation == CHAOS_REPLAY_W_MANIFEST) {
        ++manifests;
        publications += r->published;
        delivered += r->manifestation_delivered;
        displaced += r->displaced;
        pubs += r->public_count;
        bad = *r;
        bad.published = !r->published;
        assert(chaos_next_use_replay_record(&bad) == CHAOS_REPLAY_BLOCKED_REPLAY);
        ++rejection_seen;
    }
    assert(chaos_next_use_replay_record(r) == CHAOS_REPLAY_APPLIED);
    ++transitions;
    return 1;
}

static void capture_reset(void)
{
    /* Fixture reset now disconnects recorder state. Subscribe AFTER that reset
     * and before installation/actions; do not weaken capture completeness. */
    chaos_next_use_safe_reset_for_test();
    chaos_next_use_capture_set_sink(native_sink, &transitions);
}

static void capture_finalize(struct monst *pet, struct chaos_whistle_witness *witness)
{
    /* Real map publication denied AFTER native movement and message delivery.
     * Do not set witness outcomes: the production finalizer derives them. */
    if (getenv("NYARL_CAPTURE_BLOCK_PUBLICATION") && WIN_MAP != WIN_ERR && wins[WIN_MAP])
        wins[WIN_MAP]->flags |= WIN_CANCELLED;
    chaos_whistle_witness_finalize(pet, witness);
}

int main(int argc, char **argv)
{
    struct chaos_next_use_capture_status status;
    FILE *out;
    int rc;
    rc = historical_dogmove_main(argc, argv);
    if (rc) return rc;
    chaos_next_use_capture_status(&status);
    assert(!status.incomplete && !status.transaction_open);
    assert(status.acknowledged_cursor == (unsigned long)transitions);
    out = fopen("capture.json", "w");
    assert(out);
    fprintf(out, "{\"transitions\":%d,\"intents\":%d,\"manifests\":%d,"
                 "\"published\":%d,\"public\":%d,\"delivered\":%d,"
                 "\"displaced\":%d,\"tamper_rejected\":%d}\n",
            transitions, intents, manifests, publications, pubs, delivered,
            displaced, rejection_seen);
    fclose(out);
    return 0;
}
