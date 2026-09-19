/* NetHack General Public License. Opt-in next-use safe-point admission. */
#ifndef CHAOS_NEXT_USE_SAFE_H
#define CHAOS_NEXT_USE_SAFE_H

#include "chaos_next_use_admission.h"

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

struct chaos_next_use_safe_result {
    int loaded;
    int rejected;
    int admitted;
    int active;
    int pending;
    int telegraph_count;
    int spent;
};

int chaos_next_use_safe_try(const struct chaos_next_use_safe_request *,
                            struct chaos_next_use_safe_result *);
int chaos_next_use_on_safe(int dir, long at_safe, int sanity,
                           struct chaos_state *budget, int dnum, int dlevel);
void chaos_next_use_safe_reset_for_test(void);

#endif
