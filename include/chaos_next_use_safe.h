/* NetHack General Public License. Opt-in next-use safe-point admission. */
#ifndef CHAOS_NEXT_USE_SAFE_H
#define CHAOS_NEXT_USE_SAFE_H

#include <stddef.h>
#include "chaos_next_use_admission.h"

/* Native moves an engine-observed origin stays admissible after its notice
 * (#177). The origin deadline is the bound origin's move plus this value. */
#ifndef CHAOS_NEXT_USE_ORIGIN_LIFETIME
#define CHAOS_NEXT_USE_ORIGIN_LIFETIME 100
#endif

struct chaos_next_use_safe_request {
    int dir;
    int enabled;
    int at_safe;
    int at_move;
    int level_dnum;
    int level_dlevel;
    int sanity;
    const char *run_hex;
    struct chaos_state *budget;
    chaos_next_use_receipt_fn receipt;
    void *receipt_opaque;
    int (*telegraph)(void *, const char *);
    void *telegraph_opaque;
};

/* Recorded admission decision (#177). Every failing check is a bit; the
 * rejection row in next_use-receipt.jsonl lists them in this fixed order. */
enum chaos_next_use_safe_reason {
    CHAOS_NEXT_USE_SAFE_SCHEMA = 1 << 0,
    CHAOS_NEXT_USE_SAFE_IDENTITY = 1 << 1,
    CHAOS_NEXT_USE_SAFE_RUN_UNAVAILABLE = 1 << 2,
    CHAOS_NEXT_USE_SAFE_LEVEL_INVALID = 1 << 3,
    CHAOS_NEXT_USE_SAFE_BUDGET_STATE = 1 << 4,
    CHAOS_NEXT_USE_SAFE_MISSED_INDEX = 1 << 5,
    CHAOS_NEXT_USE_SAFE_RUN_MISMATCH = 1 << 6,
    CHAOS_NEXT_USE_SAFE_LEVEL_MISMATCH = 1 << 7,
    CHAOS_NEXT_USE_SAFE_ORIGIN_EXPIRED = 1 << 8,
    CHAOS_NEXT_USE_SAFE_ORIGIN_UNBOUND = 1 << 9,
    CHAOS_NEXT_USE_SAFE_ORIGIN_SUPERSEDED = 1 << 10,
    CHAOS_NEXT_USE_SAFE_SOURCE = 1 << 11,
    CHAOS_NEXT_USE_SAFE_TELEGRAPH = 1 << 12,
    CHAOS_NEXT_USE_SAFE_BUDGET = 1 << 13,
    CHAOS_NEXT_USE_SAFE_RECEIPT = 1 << 14,
    /* Carrier reservation or runtime install failed: defensive only, not
     * reachable from envelope, clock or budget inputs. */
    CHAOS_NEXT_USE_SAFE_INTERNAL = 1 << 15
};

struct chaos_next_use_safe_result {
    int loaded;
    int rejected;
    int admitted;
    int active;
    int pending;
    int telegraph_count;
    int spent;
    int reasons;
    /* Bit per operation index: the engine bound a newer origin (#177). */
    int rebound;
};

int chaos_next_use_safe_try(const struct chaos_next_use_safe_request *,
                            struct chaos_next_use_safe_result *);
int chaos_next_use_on_safe(int dir, long at_safe, int sanity,
                           struct chaos_state *budget, int dnum, int dlevel);
void chaos_next_use_safe_reset_for_test(void);
void chaos_next_use_safe_bind_run(const char *);
void chaos_next_use_safe_bind_logical(long run_token);
void chaos_next_use_safe_bind_telegraph(int (*)(void *, const char *), void *);
void chaos_next_use_safe_bind_receipt(chaos_next_use_receipt_fn, void *);
void chaos_next_use_safe_bind_origin(const struct chaos_next_use_origin_ref *,
                                    int qualifying);
void chaos_next_use_safe_mark_restored(void);
int chaos_next_use_safe_attempted(void);
int chaos_next_use_safe_restore_attempted(int attempted);
/* Startup only: resolve the restored recorder before observation boundaries. */
void chaos_next_use_safe_resume(int dir);
int chaos_next_use_safe_last(struct chaos_next_use_safe_result *);
/* Formats the admission receipt row (with newline): identity plus the
 * published and bound origin root per operation (#177). 0 on failure. */
int chaos_next_use_safe_receipt_row(const struct chaos_next_use_private_record *,
                                    char *out, size_t cap);
/* Formats the recorded rejection row (with newline); 0 when there is none:
 * not rejected, unparsed envelope (at < 1) or a transport the game does not own. */
int chaos_next_use_safe_decision_row(const struct chaos_next_use_safe_result *,
                                     int at, long at_safe, long at_move,
                                     char *out, size_t cap);

#endif
