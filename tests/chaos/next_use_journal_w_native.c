/* NGPL. Real W journal through on_safe, dog_move and window expiry.
 * Controlled native fixture, not ordinary play or history-origin discovery. */
#include "hack.h"
#include "chaos.h"
#include "chaos_next_use_safe.h"
#include "chaos_next_use_runtime.h"
#include "wintty.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int journal_safe_try(const struct chaos_next_use_safe_request *, struct chaos_next_use_safe_result *);
static void journal_finalize(struct monst *, struct chaos_whistle_witness *);
#define chaos_next_use_safe_try journal_safe_try
#define chaos_whistle_witness_finalize journal_finalize
#define main historical_dogmove_main
#include "next_use_dogmove.c"
#undef main
#undef chaos_whistle_witness_finalize
#undef chaos_next_use_safe_try

static int journal_safe_try(const struct chaos_next_use_safe_request *r,
                            struct chaos_next_use_safe_result *out)
{
    int rc;
    chaos_next_use_safe_bind_run(r->run_hex);
    chaos_next_use_safe_bind_telegraph(r->telegraph, r->telegraph_opaque);
    /* The real safe wrapper owns admission and binds the production recorder. */
    rc = chaos_next_use_on_safe(r->dir, r->at_safe, r->sanity, &u.chaos,
                                r->level_dnum, r->level_dlevel);
    chaos_next_use_safe_last(out);
    return rc;
}
static void journal_finalize(struct monst *pet, struct chaos_whistle_witness *w)
{
    int blocked = getenv("JOURNAL_W_BLOCK") != NULL;
    int saved = 0, changed = blocked && WIN_MAP != WIN_ERR && wins[WIN_MAP];
    if (changed) {
        saved = wins[WIN_MAP]->flags;
        wins[WIN_MAP]->flags |= WIN_CANCELLED;
    }
    /* Deny only actual publication, after real movement and message delivery. */
    chaos_whistle_witness_finalize(pet, w);
    if (changed) wins[WIN_MAP]->flags = saved;
}
int main(int argc, char **argv)
{
    struct chaos_next_use_snapshot s;
    struct chaos_next_use_capture_status status;
    FILE *out;
    int rc = historical_dogmove_main(argc, argv);
    if (rc) return rc;
    assert(chaos_next_use_snapshot_export(&s));
    assert(s.attention_claimed && s.callback_ordinal == 1);
    monstermoves = s.activation_monstermoves + 10;
    chaos_next_use_identity_boundary(s.run_token, s.level_token);
    assert(chaos_next_use_snapshot_export(&s));
    chaos_next_use_capture_status(&status);
    out = fopen("journal-status.json", "w");
    assert(out);
    fprintf(out, "{\"phase\":%d,\"witnessed\":%d,\"attention_claimed\":%d,\"w_runtime\":%d,\"termination_emitted\":%d,\"spent\":%d,\"sink_connected\":%d,\"incomplete\":%d,\"transaction_open\":%d,\"acknowledged_cursor\":%lu}\n",
        s.phase, s.witnessed, s.attention_claimed, s.w_runtime,
        s.termination_emitted, u.chaos.spent, status.sink_connected,
        status.incomplete, status.transaction_open, status.acknowledged_cursor);
    assert(!fclose(out));
    return 0;
}
