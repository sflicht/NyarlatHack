/* NetHack General Public License: copied input, typed output, no engine pointers. */
#ifndef CHAOS_LUA_H
#define CHAOS_LUA_H
#include <stddef.h>
#include "chaos_next_use.h"
#define CHAOS_LUA_SOURCE 4096
#define CHAOS_TRAIL 8
struct chaos_point { int x,y; };
struct chaos_lua_context { int mx,my,state,count; struct chaos_point history[CHAOS_TRAIL]; };
struct chaos_lua_intent { int dx,dy,state; };
int chaos_lua_step(const char *,size_t,const struct chaos_lua_context *,struct chaos_lua_intent *);

/* Pure curio hooks: copied observations in, bounded intent out. No native effects. */
struct chaos_curio_lua_context { int sanity, insight, charges, state; };
struct chaos_curio_lua_intent { char text[161]; int state, sanity_delta; };
/* Zero means success. Each call evaluates source in a fresh bounded VM.
 * Non-NULL outputs are entirely zeroed on failure; NULL outputs are rejected.
 * Source is 1..4096 text bytes without NUL. Context bounds are Sanity 0..100,
 * Insight 0..1000000, charges 0..3 (not consumed here), state 0..255.
 * Name/text are nonblank printable ASCII, at most 48/160 bytes respectively.
 * Apply returns state 0..255 and an integer Sanity delta -2..2, not an effect.
 */
int chaos_lua_curio_load(const char *, size_t, char name[49]);
int chaos_lua_curio_inspect(const char *, size_t,
                          const struct chaos_curio_lua_context *, char text[161]);
int chaos_lua_curio_apply(const char *, size_t,
                        const struct chaos_curio_lua_context *,
                        struct chaos_curio_lua_intent *);

enum chaos_lua_next_use_failure {
    CHAOS_LUA_NEXT_USE_INVALID_OUTPUT = 1,
    CHAOS_LUA_NEXT_USE_SANDBOX_INSTRUCTION = 2,
    CHAOS_LUA_NEXT_USE_SANDBOX_MEMORY = 3,
    CHAOS_LUA_NEXT_USE_SANDBOX_RUNTIME = 4,
    CHAOS_LUA_NEXT_USE_OUTPUT_COPY = 5,
    CHAOS_LUA_NEXT_USE_REENTRANCY = 6
};

/* Next-use Lua receives copied public context and returns a bounded intent. */
int chaos_lua_next_use_load(const char *, size_t);
int chaos_lua_next_use_on_action(const char *, size_t,
                                 const struct chaos_next_use_context *,
                                 struct chaos_next_use_intent *);
#endif
