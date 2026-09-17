/* NetHack General Public License. Test the real Lua runtime. */
#include "chaos_lua.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef LUA_SANDBOX_WHITEBOX
#include <lua.h>
#include <lauxlib.h>
#include <stdarg.h>
#include <stdint.h>
static const char *target_stage = "none", *active_stage = "none";
static int stage_refused, table_calls, last_instructions, fail_realloc;
static size_t last_used;
static void observe_limits(void *ud);
static void *test_realloc(void *p, size_t n)
{
    if (fail_realloc) return NULL;
    return realloc(p, n);
}
/* Include production exactly once. Lua faults persist through retry at named
 * API stages, never guessed allocation ordinals. Never fail Lua shrinks. */
static lua_Alloc original_alloc, seen_alloc;
static void *original_ud;
static lua_Hook seen_hook;
static lua_CFunction seen_setup;
static int fault, armed, refused, depth, states, closes, hooks, loads, calls, bad;
static void *test_alloc(void *ud, void *ptr, size_t old, size_t size)
{
    void *result;
    if (fault && armed && size > (ptr ? old : 0)) {
        ++refused;
        if (!strcmp(active_stage, target_stage)) ++stage_refused;
        if (!depth && strcmp(active_stage, "init")) bad = 1;
        return NULL;
    }
    result = original_alloc(ud, ptr, old, size);
    if (size && !result) ++refused; /* Includes cap refusals before realloc. */
    return result;
}
static lua_State *test_newstate(lua_Alloc alloc, void *ud)
{
    lua_State *L;
    if (seen_alloc && seen_alloc != alloc) bad = 1;
    seen_alloc = original_alloc = alloc; original_ud = ud;
    active_stage = "init"; table_calls = 0;
    armed = !strcmp(target_stage, "init");
    L = lua_newstate(test_alloc, ud);
    if (L) ++states;
    else observe_limits(ud);
    active_stage = "entry";
    return L;
}
static void test_sethook(lua_State *L, lua_Hook hook, int mask, int count)
{
    if ((seen_hook && seen_hook != hook) || mask != LUA_MASKCOUNT || count != 100)
        bad = 1;
    seen_hook = hook; ++hooks;
    lua_sethook(L, hook, mask, count);
    if (!strcmp(target_stage, "none")) armed = 1;
}
static int test_pcallk(lua_State *L, int nargs, int results, int err,
                       lua_KContext ctx, lua_KFunction k)
{
    int status;
    lua_CFunction setup = lua_tocfunction(L, -(nargs + 1));
    if (seen_setup && seen_setup != setup) bad = 1;
    seen_setup = setup; ++calls; ++depth;
    status = lua_pcallk(L, nargs, results, err, ctx, k);
    --depth;
    return status;
}
static int test_loadbufferx(lua_State *L, const char *s, size_t n,
                            const char *name, const char *mode)
{
    if (!depth || !mode || strcmp(mode, "t")) bad = 1;
    ++loads;
    active_stage = "parser";
    if (!strcmp(target_stage, "parser")) armed = 1;
    return luaL_loadbufferx(L, s, n, name, mode);
}
static void test_createtable(lua_State *L, int a, int h)
{
    ++table_calls;
    active_stage = table_calls == 1 ? "context" : "history";
    if (!strcmp(target_stage, active_stage)) armed = 1;
    lua_createtable(L, a, h);
}
static int test_error(lua_State *L, const char *fmt, ...)
{
    char message[512]; va_list args;
    va_start(args, fmt); vsnprintf(message, sizeof message, fmt, args); va_end(args);
    active_stage = "diagnostic";
    if (!strcmp(target_stage, "diagnostic")) armed = 1;
    return luaL_error(L, "%s", message);
}
static void test_close(lua_State *L)
{
    ++closes; lua_close(L); observe_limits(original_ud);
}
static int inspect_arguments, current_op, haunt_arguments, curio_arguments, history_entries;
/* Read only the actual argument immediately before the real Lua call. No
 * inspection function, host pointer or replacement interpreter enters Lua. */
static void inspect_table(lua_State *L, int index, int level)
{
    int fields=0, expected=level==0 ? 4 : level==2 ? 2 : 8;
    index=lua_absindex(L,index);
    if (lua_type(L,index)!=LUA_TTABLE || level>2) { bad=1; return; }
    lua_pushnil(L);
    while (lua_next(L,index)) {
        int allowed=0, nested=0;
        ++fields;
        if (level==1) {
            allowed=lua_isinteger(L,-2) && lua_tointeger(L,-2)>=1 && lua_tointeger(L,-2)<=8;
            nested=1; ++history_entries;
        } else if (lua_type(L,-2)==LUA_TSTRING) {
            size_t n; const char *key=lua_tolstring(L,-2,&n);
            const char *const h[]={"mx","my","state","history"};
            const char *const c[]={"sanity","insight","charges","state"};
            const char *const point[]={"x","y"};
            const char *const *keys=level==2 ? point : current_op==0 ? h : c;
            int i;
            for (i=0;i<expected;++i)
                if (n==strlen(keys[i]) && !memcmp(key,keys[i],n)) { allowed=1; nested=level==0 && current_op==0 && i==3; }
        }
        if (!allowed) bad=1;
        if (nested) inspect_table(L,-1,level+1);
        else if (!lua_isinteger(L,-1)) bad=1;
        lua_pop(L,1);
    }
    if (fields!=expected) bad=1;
}
static void test_callk(lua_State *L, int nargs, int results, lua_KContext ctx, lua_KFunction k)
{
    if (inspect_arguments && nargs==1) {
        if (current_op==0) ++haunt_arguments; else ++curio_arguments;
        inspect_table(L,-1,0);
    }
    lua_callk(L,nargs,results,ctx,k);
}
static int raw_pcall(lua_State *L) { return lua_pcall(L,0,0,0); }
#define lua_callk test_callk
#define lua_newstate test_newstate
#define lua_sethook test_sethook
#define lua_pcallk test_pcallk
#define luaL_loadbufferx test_loadbufferx
#define lua_close test_close
#define lua_createtable test_createtable
#define luaL_error test_error
#define realloc test_realloc
#include "../../src/chaos_lua.c"
#undef realloc

static void observe_limits(void *ud)
{
    struct limits *l = ud;
    last_used = l->used; last_instructions = l->instructions;
    if (last_used) bad = 1;
}

static int zeroed(const void *p, size_t n)
{
    const unsigned char *s = p;
    while (n--) if (*s++) return 0;
    return 1;
}
static int allocator_unit(void)
{
    struct limits l = {0,0};
    unsigned char *p, *q, expected[16]; int checks = 0;
#define CHECK(c) do { ++checks; if (!(c)) bad = 1; } while (0)
    CHECK(!limited_alloc(&l,NULL,SIZE_MAX,0) && l.used == 0);
    p = limited_alloc(&l,NULL,SIZE_MAX,16);
    CHECK(p && l.used == 16); if (!p) return 1;
    memset(p,0x5a,16); memset(expected,0x5a,sizeof expected);
    q = limited_alloc(&l,p,16,32); CHECK(q && l.used == 32); if (!q) return 1; p=q;
    q = limited_alloc(&l,p,32,16); CHECK(q && l.used == 16); if (!q) return 1; p=q;
    fail_realloc=1;
    CHECK(!limited_alloc(&l,p,16,32) && l.used==16 && !memcmp(p,expected,16));
    /* Direct allocator unit ONLY: Lua requires shrinking to succeed. */
    CHECK(!limited_alloc(&l,p,16,8) && l.used==16 && !memcmp(p,expected,16));
    fail_realloc=0;
    q=limited_alloc(&l,p,16,8); CHECK(q && l.used==8 && q[7]==0x5a); if (!q) return 1; p=q;
    CHECK(!limited_alloc(&l,p,8,0) && l.used==0);
    p=limited_alloc(&l,NULL,LUA_TTABLE,MEMORY_LIMIT); CHECK(p && l.used==MEMORY_LIMIT); if (!p) return 1;
    CHECK(!limited_alloc(&l,p,MEMORY_LIMIT,MEMORY_LIMIT+1) && l.used==MEMORY_LIMIT);
    CHECK(!limited_alloc(&l,p,MEMORY_LIMIT,SIZE_MAX) && l.used==MEMORY_LIMIT);
    CHECK(!limited_alloc(&l,NULL,0,1) && l.used==MEMORY_LIMIT);
    CHECK(!limited_alloc(&l,p,MEMORY_LIMIT,0) && l.used==0);
    p=limited_alloc(&l,NULL,0,MEMORY_LIMIT-1); CHECK(p && l.used==MEMORY_LIMIT-1); if (!p) return 1;
    CHECK(!limited_alloc(&l,NULL,0,2) && l.used==MEMORY_LIMIT-1);
    CHECK(!limited_alloc(&l,NULL,0,SIZE_MAX) && l.used==MEMORY_LIMIT-1);
    CHECK(!limited_alloc(&l,p,MEMORY_LIMIT-1,0) && l.used==0);
    p=limited_alloc(&l,NULL,0,16); CHECK(p && l.used==16); if (!p) return 1;
    CHECK(!limited_alloc(&l,p,16,0) && l.used==0);
    printf("{\"checks\":%d,\"bad\":%d,\"used\":%zu}\n",checks,bad,l.used);
#undef CHECK
    return 0;
}
static const char *valid_source(int op)
{
    return op == 0 ? "return function(c) return {dx=0,dy=0,state=c.state} end" :
        "return {name='N',inspect=function(c) return 'Read.' end,"
        "apply=function(c) return {text='Used.',state=c.state,sanity_delta=0} end}";
}
static int invoke(int op, const char *source, int *clean)
{
    struct chaos_lua_context h = {0}, before;
    struct chaos_curio_lua_context c = {50,10,3,7}, c_before=c;
    union { struct chaos_lua_intent h; struct chaos_curio_lua_intent c; char text[161]; } out;
    size_t size; int status;
    h.count=inspect_arguments ? 8 : 2; h.state=7; h.history[0].x=3; before=h;
    memset(&out,0xa5,sizeof out);
    switch (op) {
    case 0: size=sizeof out.h; status=chaos_lua_step(source,strlen(source),&h,&out.h); break;
    case 1: size=49; status=chaos_lua_curio_load(source,strlen(source),out.text); break;
    case 2: size=161; status=chaos_lua_curio_inspect(source,strlen(source),&c,out.text); break;
    default: size=sizeof out.c; status=chaos_lua_curio_apply(source,strlen(source),&c,&out.c); break;
    }
    if (memcmp(&h,&before,sizeof h) || memcmp(&c,&c_before,sizeof c)) bad=1;
    if (inspect_arguments && !status) {
        if (op==0 && (out.h.dx!=0 || out.h.dy!=0 || out.h.state!=7)) bad=1;
        if ((op==1 || op==2) && strcmp(out.text,"Fresh")) bad=1;
        if (op==3 && (strcmp(out.c.text,"Fresh") || out.c.state!=7 || out.c.sanity_delta!=0)) bad=1;
    }
    *clean = !status || zeroed(&out,size);
    return status;
}
static int resource_case(int op, const char *stage, int from_stdin)
{
    char source[CHAOS_LUA_SOURCE+1]; size_t n;
    int status, clean, recovery, recovery_clean, saved_bad, saved_states, saved_closes;
    int saved_refused, saved_stage, saved_instructions; size_t saved_used;
    target_stage=stage; fault=strcmp(stage,"none") != 0;
    if (from_stdin) { n=fread(source,1,sizeof source-1,stdin); source[n]=0; }
    else if (!strcmp(stage,"diagnostic")) {
        const char *s = op==0 ? "return function() return 1 end" : op==1 ? "return {}" :
            "return {name='N',inspect=function() return {} end,apply=function() return {} end}";
        snprintf(source,sizeof source,"%s",s);
    } else snprintf(source,sizeof source,"%s",valid_source(op));
    status=invoke(op,source,&clean);
    saved_bad=bad; saved_states=states; saved_closes=closes;
    saved_refused=refused; saved_stage=stage_refused;
    saved_instructions=last_instructions; saved_used=last_used;
    fault=armed=0; target_stage="none";
    recovery=invoke(op,valid_source(op),&recovery_clean);
    if (states != saved_states+1 || closes != saved_closes+1 || refused != saved_refused)
        bad=1;
    printf("{\"status\":%d,\"clean\":%d,\"bad\":%d,\"states\":%d,\"closes\":%d,"
           "\"refused\":%d,\"stage_refused\":%d,\"instructions\":%d,\"used\":%zu,"
           "\"recovery\":%d,\"recovery_used\":%zu,\"recovery_clean\":%d}\n",
           status,clean,saved_bad || bad,saved_states,saved_closes,saved_refused,saved_stage,
           saved_instructions,saved_used,recovery,last_used,recovery_clean);
    return 0;
}
static int call_hook(lua_State *L) { instruction_hook(L,NULL); return 0; }
static int hook_unit(void)
{
    struct limits l={0,0}; lua_State *L=lua_newstate(limited_alloc,&l);
    int i, status, checks=0, clean, recovery;
    if (!L) return 1;
    for (i=1; i<=200; ++i) {
        lua_pushcfunction(L,call_hook);
        status=raw_pcall(L); ++checks;
        if (l.instructions != i*100 || status != (i==200 ? LUA_ERRRUN : LUA_OK)) bad=1;
        lua_settop(L,0);
    }
    lua_close(L);
    recovery=invoke(0,valid_source(0),&clean);
    printf("{\"checks\":%d,\"instructions\":%d,\"used\":%zu,\"bad\":%d,"
           "\"refused\":%d,\"recovery\":%d,\"recovery_used\":%zu}\n",
           checks,l.instructions,l.used,bad,refused,recovery,last_used);
    return 0;
}
static int isolation_case(void)
{
    const char *h="if marker~=nil or saved~=nil then return nil end; marker=1; local calls=0;"
        "return function(c) calls=calls+1; if calls~=1 or c.state~=7 or c.history[1].x~=3 then return nil end;"
        "saved=c;c.history[1].x=99;c.history[2].y=99;c.mx=99;c.state=99;return {dx=0,dy=0,state=7} end";
    const char *c="if marker~=nil or saved~=nil then return nil end; marker=1; local calls=0;"
        "local function touch(c) calls=calls+1;if calls~=1 or c.state~=7 or c.sanity~=50 or c.charges~=3 then return false end;"
        "saved=c;c.state=99;c.charges=99;return true end;"
        "return {name='Fresh',inspect=function(c) if not touch(c) then return nil end return 'Fresh' end,"
        "apply=function(c) if not touch(c) then return nil end return {text='Fresh',state=7,sanity_delta=0} end}";
    int cycle, i, clean, status, operations=0;
    const int order[]={0,1,2,3,0};
    inspect_arguments=1;
    /* Each failed mutation is followed by a different family/operation, then
     * all four are exercised afresh. Root and hook failures overlap names. */
    for (cycle=0;cycle<5;++cycle) for (i=0;i<5;++i) {
        current_op=order[i];
        if (cycle%2 && i<4) {
            char source[1024];
            if (cycle==1 || current_op==1)
                snprintf(source,sizeof source,"marker=77;saved={};while true do end;%s",current_op==0?h:c);
            else snprintf(source,sizeof source,"%s",current_op==0 ?
                "marker=77;return function(c) saved=c;c.history[1].x=99;while true do end end" :
                "marker=77;return {name='N',inspect=function(c) saved=c;c.state=99;while true do end end,apply=function(c) saved=c;c.state=99;while true do end end}");
            status=invoke(current_op,source,&clean);
            if (status!=2 || last_instructions!=20000) bad=1;
        } else {
            status=invoke(current_op,current_op==0?h:c,&clean);
            if (status!=0 || last_instructions>=20000) bad=1;
        }
        ++operations;
        if (!clean || last_used || states!=closes || refused) bad=1;
    }
    printf("{\"bad\":%d,\"operations\":%d,\"states\":%d,\"closes\":%d,\"used\":%zu,"
           "\"haunt_arguments\":%d,\"curio_arguments\":%d,\"history_entries\":%d}\n",
           bad,operations,states,closes,last_used,haunt_arguments,curio_arguments,history_entries);
    return 0;
}
int main(int argc, char **argv)
{
    if (argc>1 && !strcmp(argv[1],"isolation")) return isolation_case();
    if (argc>1 && !strcmp(argv[1],"hook-unit")) return hook_unit();
    if (argc>1 && !strcmp(argv[1],"allocator")) return allocator_unit();
    if (argc>3 && !strcmp(argv[1],"resource")) return resource_case(atoi(argv[2]),argv[3],0);
    if (argc>2 && !strcmp(argv[1],"execute")) return resource_case(atoi(argv[2]),"none",1);
    const char *haunt = "return function(c) return {dx=0,dy=0,state=c.state} end";
    const char *curio = "return {name='N',inspect=function(c) return 'Read.' end,"
                        "apply=function(c) return {text='Used.',state=c.state,sanity_delta=0} end}";
    struct chaos_lua_context h = {0};
    struct chaos_lua_intent hi;
    struct chaos_curio_lua_context c = {50,10,3,7};
    struct chaos_curio_lua_intent ci;
    char name[49], text[161];
    int status[4], clean = 1, i;
    fault = argc > 1 && !strcmp(argv[1], "setup-oom");
    memset(&hi, 0xa5, sizeof hi); memset(&ci, 0xa5, sizeof ci);
    memset(name, 0xa5, sizeof name); memset(text, 0xa5, sizeof text);
    status[0] = chaos_lua_step(haunt, strlen(haunt), &h, &hi);
    status[1] = chaos_lua_curio_load(curio, strlen(curio), name);
    status[2] = chaos_lua_curio_inspect(curio, strlen(curio), &c, text);
    status[3] = chaos_lua_curio_apply(curio, strlen(curio), &c, &ci);
    for (i=0;i<4;++i) if (status[i] != (fault ? 2 : 0)) bad = 1;
    if (fault) clean = zeroed(&hi,sizeof hi) && zeroed(&ci,sizeof ci)
                      && zeroed(name,sizeof name) && zeroed(text,sizeof text);
    printf("{\"bad\":%d,\"clean\":%d,\"states\":%d,\"closes\":%d,"
           "\"hooks\":%d,\"loads\":%d,\"calls\":%d,\"refused\":%d}\n",
           bad,clean,states,closes,hooks,loads,calls,refused);
    return 0;
}
#else
#include <lua.h>
#include <lauxlib.h>
#include <limits.h>
static int dump_writer(lua_State *L, const void *p, size_t n, void *ud)
{
 (void)L; (void)ud; return fwrite(p,1,n,stdout)!=n;
}
int main(int argc,char **argv) {
 char source[CHAOS_LUA_SOURCE+2]; size_t n=fread(source,1,sizeof source,stdin);
 struct chaos_lua_context c={0}, before; struct chaos_lua_intent r;
 if(argc>1 && !strcmp(argv[1],"dump")) {
   lua_State *L=luaL_newstate(); int status;
   if(!L) return 2;
   status=luaL_loadbufferx(L,source,n,"fixture","t");
   if(status==LUA_OK) status=lua_dump(L,dump_writer,NULL,0);
   lua_close(L); return status;
 }
 c.mx=4;c.my=4;c.state=7;c.count=1;c.history[0].x=5;c.history[0].y=4;
 if(argc>1 && !strncmp(argv[1],"context:",8)) {
   if(sscanf(argv[1],"context:%d:%d",&c.count,&c.state)!=2) return 2;
 }
 if(argc>1 && !strcmp(argv[1],"extremes")) {
   c.mx=INT_MIN;c.my=INT_MAX;c.history[0].x=INT_MIN;c.history[0].y=INT_MAX;
 }
 if(argc>1 && !strcmp(argv[1],"delay")){c.count=4;c.history[1].x=4;c.history[2].x=3;c.history[3].x=3;}
 before=c; memset(&r,0xa5,sizeof r);
 int status=chaos_lua_step(source,n,&c,&r);
 if(argc>1 && !strcmp(argv[1],"repeat"))status=chaos_lua_step(source,n,&c,&r);
 if(memcmp(&before,&c,sizeof c)) return 3;
 if(status) { const unsigned char *p=(const unsigned char *)&r; size_t i;
   for(i=0;i<sizeof r;++i) if(p[i]) return 4;
 }
 printf("{\"status\":%d,\"dx\":%d,\"dy\":%d,\"state\":%d}\n",status,r.dx,r.dy,r.state);
 return 0;
}
#endif
