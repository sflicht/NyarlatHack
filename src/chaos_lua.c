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

/* Curios share the movement VM's limits, but have a separate pure contract. */
enum curio_operation { CURIO_LOAD, CURIO_INSPECT, CURIO_APPLY };
struct curio_request {
    const char *source;
    size_t length;
    enum curio_operation operation;
    struct chaos_curio_lua_context context;
    char name[49];
    struct chaos_curio_lua_intent intent;
};

/* Check raw keys before field lookup: no extras, coercions or NUL aliases. */
static void curio_table(lua_State *L, int index, const char *const keys[3])
{
    unsigned fields = 0;
    index = lua_absindex(L, index);
    if (lua_type(L, index) != LUA_TTABLE) luaL_error(L, "table required");
    lua_pushnil(L);
    while (lua_next(L, index)) {
        size_t length;
        const char *key;
        int i;
        if (lua_type(L, -2) != LUA_TSTRING) luaL_error(L, "string key required");
        key = lua_tolstring(L, -2, &length);
        for (i = 0; i < 3; ++i)
            if (length == strlen(keys[i]) && !memcmp(key, keys[i], length)) break;
        if (i == 3 || (fields & (1U << i))) luaL_error(L, "unexpected field");
        fields |= 1U << i;
        lua_pop(L, 1);
    }
    if (fields != 7) luaL_error(L, "missing field");
}

static void curio_text(lua_State *L, int index, char *out, size_t maximum)
{
    size_t length, i;
    const unsigned char *text;
    int nonblank = 0;
    if (lua_type(L, index) != LUA_TSTRING) luaL_error(L, "string required");
    text = (const unsigned char *)lua_tolstring(L, index, &length);
    if (!length || length > maximum) luaL_error(L, "text length");
    for (i = 0; i < length; ++i) {
        if (text[i] < 32 || text[i] > 126) luaL_error(L, "printable ASCII required");
        if (text[i] != ' ') nonblank = 1;
    }
    if (!nonblank) luaL_error(L, "blank text");
    memcpy(out, text, length);
    out[length] = '\0';
}

static int curio_integer(lua_State *L, int index, int low, int high)
{
    lua_Integer value;
    if (!lua_isinteger(L, index)) luaL_error(L, "integer required");
    value = lua_tointeger(L, index);
    if (value < low || value > high) luaL_error(L, "integer bounds");
    return (int)value;
}

/* Source, copied input, calls, validation and extraction all remain protected.
 * Only this privileged C closure sees the request userdata, never candidate Lua.
 */
static int curio_invoke(lua_State *L)
{
    static const char *const root_keys[3] = {"name", "inspect", "apply"};
    static const char *const intent_keys[3] = {"text", "state", "sanity_delta"};
    struct curio_request *r = lua_touserdata(L, lua_upvalueindex(1));
    const struct chaos_curio_lua_context *c = &r->context;
    int i;
    if (luaL_loadbufferx(L, r->source, r->length, "curio", "t") != LUA_OK)
        return lua_error(L);
    lua_call(L, 0, LUA_MULTRET);
    if (lua_gettop(L) != 1) return luaL_error(L, "one root required");
    curio_table(L, 1, root_keys);
    lua_getfield(L, 1, "name");
    curio_text(L, -1, r->name, 48);
    lua_pop(L, 1);
    for (i = 1; i < 3; ++i) {
        lua_getfield(L, 1, root_keys[i]);
        if (lua_type(L, -1) != LUA_TFUNCTION) return luaL_error(L, "hook required");
        lua_pop(L, 1);
    }
    if (r->operation == CURIO_LOAD) return 0;
    lua_getfield(L, 1, r->operation == CURIO_INSPECT ? "inspect" : "apply");
    lua_createtable(L, 0, 4);
    number(L, "sanity", c->sanity);
    number(L, "insight", c->insight);
    number(L, "charges", c->charges);
    number(L, "state", c->state);
    lua_call(L, 1, LUA_MULTRET);
    if (lua_gettop(L) != 2) return luaL_error(L, "one hook result required");
    if (r->operation == CURIO_INSPECT) {
        curio_text(L, 2, r->intent.text, 160);
    } else {
        curio_table(L, 2, intent_keys);
        lua_getfield(L, 2, "text");
        curio_text(L, -1, r->intent.text, 160);
        lua_pop(L, 1);
        lua_getfield(L, 2, "state");
        r->intent.state = curio_integer(L, -1, 0, 255);
        lua_pop(L, 1);
        lua_getfield(L, 2, "sanity_delta");
        r->intent.sanity_delta = curio_integer(L, -1, -2, 2);
    }
    return 0;
}

/* A zero-upvalue C function needs no allocation before pcall. The extraspace
 * pointer bootstraps the hidden closure INSIDE that protection, so even closure
 * allocation failure cannot panic. Extraspace is not visible to candidate Lua.
 */
static int curio_setup(lua_State *L)
{
    struct curio_request *r;
    memcpy(&r, lua_getextraspace(L), sizeof r);
    lua_pushlightuserdata(L, r);
    lua_pushcclosure(L, curio_invoke, 1);
    lua_call(L, 0, 0);
    return 0;
}

static int curio_run(const char *source, size_t length,
                     const struct chaos_curio_lua_context *c,
                     enum curio_operation operation, struct curio_request *r)
{
    struct limits limits = {0, 0};
    lua_State *L;
    int status;
    if (!source || !length || length > CHAOS_LUA_SOURCE || memchr(source, 0, length))
        return 1;
    if (operation != CURIO_LOAD) {
        if (!c || c->sanity < 0 || c->sanity > 100 ||
            c->insight < 0 || c->insight > 1000000 ||
            c->charges < 0 || c->charges > 3 || c->state < 0 || c->state > 255)
            return 1;
        r->context = *c;
    }
    r->source = source;
    r->length = length;
    r->operation = operation;
    L = lua_newstate(limited_alloc, &limits);
    if (!L) return 2;
    /* No libraries, host functions or engine pointers are installed. */
    memcpy(lua_getextraspace(L), &r, sizeof r);
    lua_sethook(L, instruction_hook, LUA_MASKCOUNT, 100);
    lua_pushcfunction(L, curio_setup);
    status = lua_pcall(L, 0, 0, 0);
    lua_close(L);
    return status == LUA_OK ? 0 : 2;
}

int chaos_lua_curio_load(const char *source, size_t length, char name[49])
{
    struct curio_request r = {0};
    int status;
    if (!name) return 1;
    memset(name, 0, 49);
    status = curio_run(source, length, NULL, CURIO_LOAD, &r);
    if (!status) memcpy(name, r.name, 49);
    return status;
}

int chaos_lua_curio_inspect(const char *source, size_t length,
                          const struct chaos_curio_lua_context *c, char text[161])
{
    struct curio_request r = {0};
    int status;
    if (!text) return 1;
    memset(text, 0, 161);
    status = curio_run(source, length, c, CURIO_INSPECT, &r);
    if (!status) memcpy(text, r.intent.text, 161);
    return status;
}

int chaos_lua_curio_apply(const char *source, size_t length,
                        const struct chaos_curio_lua_context *c,
                        struct chaos_curio_lua_intent *intent)
{
    struct curio_request r = {0};
    int status;
    if (!intent) return 1;
    memset(intent, 0, sizeof *intent);
    status = curio_run(source, length, c, CURIO_APPLY, &r);
    if (!status) *intent = r.intent;
    return status;
}
