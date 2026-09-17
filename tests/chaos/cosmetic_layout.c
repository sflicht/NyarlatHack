/* Independent ctypes allocation proof; no game build. */
#include "chaos_protocol.h"
#include <stddef.h>
size_t cosmetic_layout(int field) {
    if (!field) return sizeof(struct chaos_state);
#if CHAOS_STATE_VERSION >= 2
    if (field == 1) return offsetof(struct chaos_state, cosmetic_seen);
    if (field == 2) return offsetof(struct chaos_state, cosmetic_last_turn);
#endif
    return 0;
}
