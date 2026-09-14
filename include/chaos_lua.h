/* NetHack General Public License: copied input, typed output, no engine pointers. */
#ifndef CHAOS_LUA_H
#define CHAOS_LUA_H
#include <stddef.h>
#define CHAOS_LUA_SOURCE 4096
#define CHAOS_TRAIL 8
struct chaos_point { int x,y; };
struct chaos_lua_context { int mx,my,state,count; struct chaos_point history[CHAOS_TRAIL]; };
struct chaos_lua_intent { int dx,dy,state; };
int chaos_lua_step(const char *,size_t,const struct chaos_lua_context *,struct chaos_lua_intent *);
#endif
