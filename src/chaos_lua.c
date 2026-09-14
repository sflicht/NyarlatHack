/* NetHack General Public License. Lua without libraries; new VM each decision. */
#include "chaos_lua.h"
#include <lua.h>
#include <lauxlib.h>
#include <stdlib.h>
#include <string.h>
#define MEMORY_LIMIT (256*1024)
#define INSTRUCTION_LIMIT 20000
struct limits { size_t used; int instructions; };
static void *limited_alloc(void *ud,void *ptr,size_t old,size_t size) {
    struct limits *l=ud; void *next;
    if(!ptr) old=0; /* Lua encodes object type in old size for new allocations. */
    if(!size) { free(ptr); l->used-=old; return NULL; }
    if(size>MEMORY_LIMIT || l->used-old>MEMORY_LIMIT-size) return NULL;
    next=realloc(ptr,size);
    if(next) l->used=l->used-old+size;
    return next;
}
static void instruction_hook(lua_State *L,lua_Debug *ar) {
    void *ud; struct limits *l; (void)ar;
    (void)lua_getallocf(L,&ud); l=ud;
    l->instructions+=100;
    if(l->instructions>=INSTRUCTION_LIMIT) luaL_error(L,"instruction limit");
}
static void number(lua_State *L,const char *key,int value) {
    lua_pushinteger(L,value);lua_setfield(L,-2,key);
}
/* All allocating setup runs protected too, including creation of copied input. */
static int invoke(lua_State *L) {
    const struct chaos_lua_context *c=lua_touserdata(L,lua_upvalueindex(1));
    const char *source=lua_touserdata(L,lua_upvalueindex(2));
    size_t n=(size_t)lua_tointeger(L,lua_upvalueindex(3));
    int i;
    if(luaL_loadbufferx(L,source,n,"haunting","t")!=LUA_OK) return lua_error(L);
    lua_call(L,0,1);
    if(!lua_isfunction(L,-1)) return luaL_error(L,"function required");
    lua_createtable(L,0,4);number(L,"mx",c->mx);number(L,"my",c->my);number(L,"state",c->state);
    lua_createtable(L,c->count,0);
    for(i=0;i<c->count;++i) {
        lua_createtable(L,0,2);number(L,"x",c->history[i].x);number(L,"y",c->history[i].y);
        lua_rawseti(L,-2,i+1);
    }
    lua_setfield(L,-2,"history");lua_call(L,1,1);
    return 1;
}
int chaos_lua_step(const char *source,size_t n,const struct chaos_lua_context *c,struct chaos_lua_intent *result) {
    struct limits limits={0,0};struct chaos_lua_intent out={0,0,0};
    lua_State *L;int status,fields=0;
    memset(result,0,sizeof *result);
    if(!source || !n || n>CHAOS_LUA_SOURCE || memchr(source,0,n) ||
       c->count<0 || c->count>CHAOS_TRAIL || c->state<0 || c->state>1000000) return 1;
    L=lua_newstate(limited_alloc,&limits);if(!L) return 2;
    /* Deliberately do NOT luaL_openlibs. Even pcall/debug/load are unavailable. */
    lua_sethook(L,instruction_hook,LUA_MASKCOUNT,100);
    lua_pushlightuserdata(L,(void*)c);lua_pushlightuserdata(L,(void*)source);lua_pushinteger(L,(lua_Integer)n);
    lua_pushcclosure(L,invoke,3);
    status=lua_pcall(L,0,1,0);
    if(status!=LUA_OK || !lua_istable(L,-1)) { lua_close(L);return 2; }
    lua_pushnil(L);
    while(lua_next(L,-2)) {
        int bit=0;const char *key;
        if(lua_type(L,-2)!=LUA_TSTRING || !lua_isinteger(L,-1)) {status=3;break;}
        { size_t length; key=lua_tolstring(L,-2,&length);
          if(memchr(key,0,length)){status=3;break;} }
        lua_Integer value=lua_tointeger(L,-1);
        if(!strcmp(key,"dx")) {bit=1;if(value < -1 || value>1){status=3;break;}out.dx=(int)value;}
        else if(!strcmp(key,"dy")) {bit=2;if(value < -1 || value>1){status=3;break;}out.dy=(int)value;}
        else if(!strcmp(key,"state")) {bit=4;if(value<0 || value>1000000){status=3;break;}out.state=(int)value;}
        else {status=3;break;}
        if(fields&bit){status=3;break;}fields|=bit;lua_pop(L,1);
    }
    if(fields!=7)status=3;
    if(!status)*result=out;
    lua_close(L);return status;
}
