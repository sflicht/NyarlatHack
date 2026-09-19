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

/* Closed private dispatch, not an adapter registration or capability API. */
enum sandbox_operation { HAUNT_STEP, CURIO_LOAD, CURIO_INSPECT, CURIO_APPLY };
struct sandbox_request {
    const char *source;
    size_t length;
    enum sandbox_operation operation;
    int validation_status;
    struct chaos_lua_context movement;
    struct chaos_lua_intent movement_intent;
    struct chaos_curio_lua_context context;
    char name[49];
    struct chaos_curio_lua_intent intent;
};

static int sandbox_source_valid(const char *source, size_t length)
{
    return source && length && length <= CHAOS_LUA_SOURCE &&
           !memchr(source, 0, length);
}

/* Raw exact keys: no coercions, metamethod enumeration or NUL aliases.
 * Checked readers return explicit schema failure; Lua/OOM errors instead unwind
 * to the outer pcall and always map to status 2, even during extraction. */
static int sandbox_keys3(lua_State *L, int index, const char *const keys[3])
{
    unsigned fields = 0;
    index = lua_absindex(L, index);
    if (lua_type(L, index) != LUA_TTABLE) return 0;
    lua_pushnil(L);
    while (lua_next(L, index)) {
        size_t length;
        const char *key;
        int i;
        if (lua_type(L, -2) != LUA_TSTRING) { lua_pop(L, 2); return 0; }
        key = lua_tolstring(L, -2, &length);
        for (i = 0; i < 3; ++i)
            if (length == strlen(keys[i]) && !memcmp(key, keys[i], length)) break;
        if (i == 3 || (fields & (1U << i))) { lua_pop(L, 2); return 0; }
        fields |= 1U << i;
        lua_pop(L, 1);
    }
    return fields == 7;
}

static int sandbox_text(lua_State *L, int index, char *out, size_t maximum)
{
    size_t length, i;
    const unsigned char *text;
    int nonblank = 0;
    if (lua_type(L, index) != LUA_TSTRING) return 0;
    text = (const unsigned char *)lua_tolstring(L, index, &length);
    if (!length || length > maximum) return 0;
    for (i = 0; i < length; ++i) {
        if (text[i] < 32 || text[i] > 126) return 0;
        if (text[i] != ' ') nonblank = 1;
    }
    if (!nonblank) return 0;
    memcpy(out, text, length);
    out[length] = '\0';
    return 1;
}

static int sandbox_integer(lua_State *L, int index, int low, int high, int *out)
{
    lua_Integer value;
    if (!lua_isinteger(L, index)) return 0;
    value = lua_tointeger(L, index);
    if (value < low || value > high) return 0;
    *out = (int)value;
    return 1;
}

static int haunt_invoke(lua_State *L, struct sandbox_request *r)
{
    static const char *const keys[3] = {"dx", "dy", "state"};
    const struct chaos_lua_context *c = &r->movement;
    int i, valid;
    if (luaL_loadbufferx(L, r->source, r->length, "haunting", "t") != LUA_OK)
        return lua_error(L);
    /* Movement deliberately discards extra root AND handler results. */
    lua_call(L, 0, 1);
    if (!lua_isfunction(L, -1)) return luaL_error(L, "function required");
    lua_createtable(L, 0, 4);
    number(L, "mx", c->mx); number(L, "my", c->my); number(L, "state", c->state);
    lua_createtable(L, c->count, 0);
    for (i = 0; i < c->count; ++i) {
        lua_createtable(L, 0, 2);
        number(L, "x", c->history[i].x); number(L, "y", c->history[i].y);
        lua_rawseti(L, -2, i + 1);
    }
    lua_setfield(L, -2, "history");
    lua_call(L, 1, 1);
    if (!lua_istable(L, -1)) return luaL_error(L, "table required");
    if (!sandbox_keys3(L, 1, keys)) { r->validation_status = 3; return 0; }
    lua_getfield(L, 1, "dx");
    valid = sandbox_integer(L, -1, -1, 1, &r->movement_intent.dx);
    lua_pop(L, 1);
    lua_getfield(L, 1, "dy");
    valid = sandbox_integer(L, -1, -1, 1, &r->movement_intent.dy) && valid;
    lua_pop(L, 1);
    lua_getfield(L, 1, "state");
    valid = sandbox_integer(L, -1, 0, 1000000, &r->movement_intent.state) && valid;
    if (!valid) r->validation_status = 3;
    return 0;
}

/* Curios retain their own schema, exact arities and narrower state bounds. */
static int curio_invoke(lua_State *L, struct sandbox_request *r)
{
    static const char *const root_keys[3] = {"name", "inspect", "apply"};
    static const char *const intent_keys[3] = {"text", "state", "sanity_delta"};
    const struct chaos_curio_lua_context *c = &r->context;
    int i;
    if (luaL_loadbufferx(L, r->source, r->length, "curio", "t") != LUA_OK)
        return lua_error(L);
    lua_call(L, 0, LUA_MULTRET);
    if (lua_gettop(L) != 1) return luaL_error(L, "one root required");
    if (!sandbox_keys3(L, 1, root_keys)) return luaL_error(L, "root fields");
    lua_getfield(L, 1, "name");
    if (!sandbox_text(L, -1, r->name, 48)) return luaL_error(L, "name required");
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
        if (!sandbox_text(L, 2, r->intent.text, 160)) return luaL_error(L, "text required");
    } else {
        if (!sandbox_keys3(L, 2, intent_keys)) return luaL_error(L, "intent fields");
        lua_getfield(L, 2, "text");
        if (!sandbox_text(L, -1, r->intent.text, 160)) return luaL_error(L, "text required");
        lua_pop(L, 1);
        lua_getfield(L, 2, "state");
        if (!sandbox_integer(L, -1, 0, 255, &r->intent.state))
            return luaL_error(L, "state bounds");
        lua_pop(L, 1);
        lua_getfield(L, 2, "sanity_delta");
        if (!sandbox_integer(L, -1, -2, 2, &r->intent.sanity_delta))
            return luaL_error(L, "sanity bounds");
    }
    return 0;
}

/* Zero upvalues means no closure allocation before protection. The private
 * request lives only in extraspace/C, never in a candidate-visible Lua value.
 * Parser, copied context, calls, extraction and diagnostics all run protected. */
static int sandbox_setup(lua_State *L)
{
    struct sandbox_request *r;
    memcpy(&r, lua_getextraspace(L), sizeof r);
    switch (r->operation) {
    case HAUNT_STEP: return haunt_invoke(L, r);
    case CURIO_LOAD:
    case CURIO_INSPECT:
    case CURIO_APPLY: return curio_invoke(L, r);
    }
    return luaL_error(L, "invalid operation");
}

static int sandbox_run(struct sandbox_request *r)
{
    struct limits limits = {0, 0};
    lua_State *L;
    int status;
    if (!sandbox_source_valid(r->source, r->length)) return 1;
    L = lua_newstate(limited_alloc, &limits);
    if (!L) return 2;
    /* No libraries, host functions or engine pointers are installed. No fuel
     * reset between root and handler: only a fresh public call starts over. */
    memcpy(lua_getextraspace(L), &r, sizeof r);
    lua_sethook(L, instruction_hook, LUA_MASKCOUNT, 100);
    lua_pushcfunction(L, sandbox_setup);
    status = lua_pcall(L, 0, 0, 0);
    lua_close(L);
    return status == LUA_OK ? r->validation_status : 2;
}

int chaos_lua_step(const char *source, size_t length,
                   const struct chaos_lua_context *c, struct chaos_lua_intent *result)
{
    struct sandbox_request r = {0};
    int status;
    /* The movement API retains its native caller's non-NULL c/result contract. */
    memset(result, 0, sizeof *result);
    if (c->count < 0 || c->count > CHAOS_TRAIL || c->state < 0 || c->state > 1000000)
        return 1;
    r.source = source; r.length = length; r.operation = HAUNT_STEP; r.movement = *c;
    status = sandbox_run(&r);
    if (!status) *result = r.movement_intent;
    return status;
}

/* Family preflight only; the common runner owns the entire VM lifecycle. */
static int curio_run(const char *source, size_t length,
                     const struct chaos_curio_lua_context *c,
                     enum sandbox_operation operation, struct sandbox_request *r)
{
    if (operation != CURIO_LOAD) {
        if (!c || c->sanity < 0 || c->sanity > 100 ||
            c->insight < 0 || c->insight > 1000000 ||
            c->charges < 0 || c->charges > 3 || c->state < 0 || c->state > 255)
            return 1;
        r->context = *c;
    }
    r->source = source; r->length = length; r->operation = operation;
    return sandbox_run(r);
}

int chaos_lua_curio_load(const char *source, size_t length, char name[49])
{
    struct sandbox_request r = {0};
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
    struct sandbox_request r = {0};
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
    struct sandbox_request r = {0};
    int status;
    if (!intent) return 1;
    memset(intent, 0, sizeof *intent);
    status = curio_run(source, length, c, CURIO_APPLY, &r);
    if (!status) *intent = r.intent;
    return status;
}

/* Next-use schema stays family-specific; VM containment uses the shared
 * allocator, instruction hook, and source bound. */
struct next_lua_request {
    const char *source;
    size_t length;
    const struct chaos_next_use_context *context;
    struct chaos_next_use_intent intent;
    int call_handler;
    int valid;
    int failure_code;
};

static int next_hex64(const char *text);
static int next_hex64(const char *text)
{
    size_t index;
    if (!text) return 0;
    for (index = 0; index < 64; ++index)
        if (!((text[index] >= '0' && text[index] <= '9') ||
              (text[index] >= 'a' && text[index] <= 'f'))) return 0;
    return text[64] == '\0';
}

static int next_root_exact(lua_State *);
static int next_root_exact(lua_State *L)
{
    int fields = 0;
    if (lua_gettop(L) != 1 || lua_type(L, 1) != LUA_TTABLE) return 0;
    lua_pushnil(L);
    while (lua_next(L, 1)) {
        size_t length = 0;
        const char *key;
        if (lua_type(L, -2) != LUA_TSTRING) return 0;
        key = lua_tolstring(L, -2, &length);
        if (!key || length != 9 || memcmp(key, "on_action", 9) ||
            lua_type(L, -1) != LUA_TFUNCTION || fields) return 0;
        fields = 1;
        lua_settop(L, -2);
    }
    return fields == 1;
}

static int next_lua_failure(lua_State *, int);
static int next_lua_failure(lua_State *L, int status)
{
    const char *message;
    size_t length = 0;
    if (status == LUA_ERRMEM) return CHAOS_LUA_NEXT_USE_SANDBOX_MEMORY;
    message = lua_tolstring(L, -1, &length);
    if (message && length >= 17
        && !memcmp(message, "instruction limit", 17))
        return CHAOS_LUA_NEXT_USE_SANDBOX_INSTRUCTION;
    return CHAOS_LUA_NEXT_USE_SANDBOX_RUNTIME;
}

static int next_root_load(lua_State *, const char *, size_t,
                          struct next_lua_request *);
static int next_root_load(lua_State *L, const char *source, size_t length,
                          struct next_lua_request *request)
{
    int status = luaL_loadbufferx(L, source, length, "next-use", "t");
    if (status != LUA_OK) {
        request->failure_code = next_lua_failure(L, status);
        return 0;
    }
    status = lua_pcall(L, 0, LUA_MULTRET, 0);
    if (status != LUA_OK) {
        request->failure_code = next_lua_failure(L, status);
        return 0;
    }
    if (!next_root_exact(L)) {
        request->failure_code = CHAOS_LUA_NEXT_USE_OUTPUT_COPY;
        return 0;
    }
    return 1;
}

static void next_set_integer(lua_State *, const char *, int);
static void next_set_integer(lua_State *L, const char *key, int value)
{
    lua_pushinteger(L, value);
    lua_setfield(L, -2, key);
}

static void next_set_text(lua_State *, const char *, const char *);
static void next_set_text(lua_State *L, const char *key, const char *value)
{
    lua_pushlstring(L, value, strlen(value));
    lua_setfield(L, -2, key);
}

static void next_push_context(lua_State *, const struct chaos_next_use_context *);
static void next_push_context(lua_State *L,
                              const struct chaos_next_use_context *context)
{
    lua_createtable(L, 0, 9);
    next_set_integer(L, "age", context->age);
    next_set_integer(L, "fountain_count", context->fountain_count);
    next_set_integer(L, "next_use_context_v", 2);
    next_set_text(L, "own_witnessed", context->own_witnessed ? "W" : "none");
    next_set_text(L, "source_sha256", context->source_sha256);
    next_set_integer(L, "state", context->state);
    next_set_text(L, "trigger",
                  context->trigger == CHAOS_NEXT_USE_FAMILY_W ? "W" : "F");
    next_set_integer(L, "variant", context->variant);
    next_set_integer(L, "whistle_count", context->whistle_count);
}

static int next_result_keys(lua_State *, int);
static int next_result_keys(lua_State *L, int index)
{
    int fields = 0;
    index = index < 0 ? lua_gettop(L) + index + 1 : index;
    if (lua_type(L, index) != LUA_TTABLE) return 0;
    lua_pushnil(L);
    while (lua_next(L, index)) {
        size_t length = 0;
        const char *key;
        int bit = 0;
        if (lua_type(L, -2) != LUA_TSTRING) return 0;
        key = lua_tolstring(L, -2, &length);
        if (key && length == 17 && !memcmp(key, "next_use_intent_v", 17)) bit = 1;
        else if (key && length == 2 && !memcmp(key, "op", 2)) bit = 2;
        else if (key && length == 5 && !memcmp(key, "state", 5)) bit = 4;
        if (!bit || (fields & bit)) return 0;
        fields |= bit;
        lua_settop(L, -2);
    }
    return fields == 7;
}

static void next_raw_field(lua_State *, int, const char *);
static void next_raw_field(lua_State *L, int index, const char *key)
{
    index = index < 0 ? lua_gettop(L) + index + 1 : index;
    lua_pushlstring(L, key, strlen(key));
    lua_rawget(L, index);
}

static int next_integer_field(lua_State *, int, const char *, int, int, int *);
static int next_integer_field(lua_State *L, int index, const char *key,
                              int low, int high, int *result)
{
    lua_Integer value;
    int integer_status = 0;
    next_raw_field(L, index, key);
    if (!lua_isinteger(L, -1)) { lua_settop(L, -2); return 0; }
    value = lua_tointegerx(L, -1, &integer_status);
    lua_settop(L, -2);
    if (!integer_status || value < low || value > high) return 0;
    *result = (int)value; return 1;
}

static int next_intent_extract(lua_State *, int, struct chaos_next_use_intent *);
static int next_intent_extract(lua_State *L, int index,
                               struct chaos_next_use_intent *intent)
{
    size_t length = 0;
    const char *op_text;
    int version;
    index = index < 0 ? lua_gettop(L) + index + 1 : index;
    if (!next_result_keys(L, index) ||
        !next_integer_field(L, index, "next_use_intent_v", 2, 2, &version) ||
        !next_integer_field(L, index, "state", 0, 3, &intent->state)) return 0;
    next_raw_field(L, index, "op");
    if (lua_type(L, -1) != LUA_TSTRING) { lua_settop(L, -2); return 0; }
    op_text = lua_tolstring(L, -1, &length);
    if (length == 5 && !memcmp(op_text, "quiet", 5))
        intent->op = CHAOS_NEXT_USE_INTENT_QUIET;
    else if (length == 5 && !memcmp(op_text, "delay", 5))
        intent->op = CHAOS_NEXT_USE_INTENT_DELAY;
    else if (length == 17 && !memcmp(op_text, "whistle_attention", 17))
        intent->op = CHAOS_NEXT_USE_INTENT_WHISTLE_ATTENTION;
    else if (length == 16 && !memcmp(op_text, "fountain_refresh", 16))
        intent->op = CHAOS_NEXT_USE_INTENT_FOUNTAIN_REFRESH;
    else { lua_settop(L, -2); return 0; }
    lua_settop(L, -2); return 1;
}

static int next_protected_call(lua_State *);
static int next_protected_call(lua_State *L)
{
    struct next_lua_request *request = NULL;
    int status;
    memcpy(&request, lua_getextraspace(L), sizeof request);
    if (!request || !next_root_load(L, request->source, request->length, request)) return 0;
    if (!request->call_handler) {
        request->valid = 1;
        return 0;
    }
    lua_getfield(L, 1, "on_action");
    next_push_context(L, request->context);
    status = lua_pcall(L, 1, LUA_MULTRET, 0);
    if (status != LUA_OK) {
        request->failure_code = next_lua_failure(L, status);
    } else if (lua_gettop(L) != 2
               || !next_intent_extract(L, -1, &request->intent)) {
        request->failure_code = CHAOS_LUA_NEXT_USE_OUTPUT_COPY;
    } else {
        request->valid = 1;
    }
    return 0;
}

static int next_use_vm(struct next_lua_request *request)
{
    struct limits limits = {0, 0};
    struct next_lua_request *request_pointer = request;
    lua_State *L;
    int status;
    if (!sandbox_source_valid(request->source, request->length)) return 1;
    L = lua_newstate(limited_alloc, &limits);
    if (!L) return CHAOS_LUA_NEXT_USE_SANDBOX_MEMORY;
    memcpy(lua_getextraspace(L), &request_pointer, sizeof request_pointer);
    lua_sethook(L, instruction_hook, LUA_MASKCOUNT, 100);
    lua_pushcclosure(L, next_protected_call, 0);
    status = lua_pcall(L, 0, 0, 0);
    if (status != LUA_OK && !request->failure_code)
        request->failure_code = next_lua_failure(L, status);
    if (status == LUA_OK && request->valid) {
        lua_close(L);
        return 0;
    }
    status = request->failure_code ? request->failure_code
                                   : CHAOS_LUA_NEXT_USE_OUTPUT_COPY;
    lua_close(L);
    return status;
}

int chaos_lua_next_use_load(const char *, size_t);
int chaos_lua_next_use_load(const char *source, size_t length)
{
    struct next_lua_request request;
    memset(&request, 0, sizeof request);
    request.source = source; request.length = length;
    return next_use_vm(&request);
}

int chaos_lua_next_use_on_action(const char *, size_t,
                                 const struct chaos_next_use_context *,
                                 struct chaos_next_use_intent *);
int chaos_lua_next_use_on_action(const char *source, size_t length,
                                 const struct chaos_next_use_context *context,
                                 struct chaos_next_use_intent *intent)
{
    struct next_lua_request request;
    int status;
    if (!intent) return 1;
    memset(intent, 0, sizeof *intent);
    memset(&request, 0, sizeof request);
    if (!context ||
        context->age < 0 || context->age > 99 ||
        context->fountain_count < 0 || context->fountain_count > 3 ||
        context->own_witnessed < 0 || context->own_witnessed > 1 ||
        context->state < 0 || context->state > 3 ||
        (context->trigger != CHAOS_NEXT_USE_FAMILY_W &&
         context->trigger != CHAOS_NEXT_USE_FAMILY_F) ||
        context->variant < 0 || context->variant > 2 ||
        context->whistle_count < 0 || context->whistle_count > 3 ||
        !next_hex64(context->source_sha256)) return 1;
    request.source = source; request.length = length;
    request.context = context; request.call_handler = 1;
    status = next_use_vm(&request);
    if (!status) {
        *intent = request.intent;
        return 0;
    }
    memset(intent, 0, sizeof *intent);
    return status;
}
