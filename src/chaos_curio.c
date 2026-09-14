/* NetHack General Public License: validation only, no admission/effects/RNG. */
#include "chaos_curio.h"
#include "chaos_lua.h"
#include <string.h>

static int empty_bytes(const char *p, unsigned n)
{
    unsigned i;
    for (i = 0; i < n; ++i) if (p[i]) return 0;
    return 1;
}

int chaos_curio_valid(const struct chaos_curio_state *s)
{
    char name[49];
    if (!s || s->phase > CHAOS_CURIO_EXPIRED
        || s->charges < 0 || s->charges > 3
        || s->state < 0 || s->state > 255
        || s->disabled < 0 || s->disabled > 1)
        return 0;
    if (s->version != (s->phase == CHAOS_CURIO_VIRGIN
                       ? 0 : CHAOS_CURIO_VERSION)) return 0;
    if (!s->source_len) {
        return (s->phase == CHAOS_CURIO_VIRGIN
                || s->phase == CHAOS_CURIO_REJECTED
                || s->phase == CHAOS_CURIO_EXPIRED)
            && !s->owner && !s->charges && !s->state && !s->disabled
            && empty_bytes(s->name, sizeof s->name)
            && empty_bytes(s->source, sizeof s->source);
    }
    if (s->phase != CHAOS_CURIO_ADMITTED && s->phase != CHAOS_CURIO_PLACED
        && s->phase != CHAOS_CURIO_EXPIRED) return 0;
    if (s->source_len > CHAOS_CURIO_SOURCE
        || s->source[s->source_len] || memchr(s->source, 0, s->source_len)
        || !memchr(s->name, 0, sizeof s->name)) return 0;
    if (s->phase == CHAOS_CURIO_PLACED) {
        if (!s->owner) return 0;
    } else if (s->owner || s->charges != 3 || s->state || s->disabled) {
        return 0;
    }
    /* Reconstruct metadata in a fresh bounded VM, never trust saved text.
     * Failure is local; do not modify the caller or other saves/runtime state. */
    if (chaos_lua_curio_load(s->source, s->source_len, name)) return 0;
    return !strcmp(name, s->name)
        && empty_bytes(s->name + strlen(name), sizeof s->name - strlen(name));
}
