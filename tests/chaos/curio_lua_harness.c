/* NetHack General Public License. Exercise the actual bounded Lua interpreter. */
#include "chaos_lua.h"
#include <lua.h>
#include <lauxlib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int zeroed(const void *p, size_t n)
{
    const unsigned char *bytes = p;
    size_t i;
    for (i = 0; i < n; ++i)
        if (bytes[i]) return 0;
    return 1;
}

/* Hex avoids trusting candidate text as JSON or terminal output. */
static void hex_text(const char *text, size_t capacity)
{
    size_t i;
    for (i = 0; i < capacity && text[i]; ++i)
        printf("%02x", (unsigned char)text[i]);
}

/* Produce genuine bytecode for rejection tests, not a truncated magic header. */
static int dump_writer(lua_State *L, const void *p, size_t n, void *ud)
{
    (void)L;
    (void)ud;
    return fwrite(p, 1, n, stdout) != n;
}

int main(int argc, char **argv)
{
    char source[CHAOS_LUA_SOURCE + 2], name[49], text[161];
    size_t n = fread(source, 1, sizeof source, stdin);
    struct chaos_curio_lua_context c = {50, 10, 3, 7}, before;
    struct chaos_curio_lua_intent intent;
    const char *input = source, *mode = argc > 2 ? argv[2] : "normal";
    const struct chaos_curio_lua_context *context = &c;
    int status = -1, i, repeats = 1, clean = 0;
    const char *output = "";
    size_t capacity = 1;

    if (argc < 2) return 2;
    if (!strcmp(argv[1], "dump")) {
        lua_State *L = luaL_newstate();
        if (!L) return 2;
        status = luaL_loadbufferx(L, source, n, "fixture", "t");
        if (status == LUA_OK) status = lua_dump(L, dump_writer, NULL, 0);
        lua_close(L);
        return status;
    }
    if (argc == 7) {
        c.sanity = atoi(argv[3]); c.insight = atoi(argv[4]);
        c.charges = atoi(argv[5]); c.state = atoi(argv[6]);
    }
    before = c;
    if (!strcmp(mode, "null-source")) input = NULL;
    if (!strcmp(mode, "null-context")) context = NULL;
    if (!strcmp(mode, "repeat")) repeats = 20;
    for (i = 0; i < repeats; ++i) {
        int null_output = !strcmp(mode, "null-output");
        memset(name, 0xa5, sizeof name);
        memset(text, 0xa5, sizeof text);
        memset(&intent, 0xa5, sizeof intent);
        if (!strcmp(argv[1], "load")) {
            status = chaos_lua_curio_load(input, n, null_output ? NULL : name);
            clean = zeroed(name, sizeof name);
            output = name; capacity = sizeof name;
        } else if (!strcmp(argv[1], "inspect")) {
            status = chaos_lua_curio_inspect(input, n, context,
                                            null_output ? NULL : text);
            clean = zeroed(text, sizeof text);
            output = text; capacity = sizeof text;
        } else if (!strcmp(argv[1], "apply")) {
            status = chaos_lua_curio_apply(input, n, context,
                                          null_output ? NULL : &intent);
            clean = zeroed(&intent, sizeof intent);
            output = intent.text; capacity = sizeof intent.text;
        } else return 2;
        if (status && repeats > 1) return 3;
    }
    printf("{\"status\":%d,\"cleared\":%d,\"unchanged\":%d,\"hex\":\"",
           status, clean, memcmp(&before, &c, sizeof c) == 0);
    hex_text(output, capacity);
    printf("\",\"state\":%d,\"sanity_delta\":%d}\n",
           !strcmp(argv[1], "apply") ? intent.state : 0,
           !strcmp(argv[1], "apply") ? intent.sanity_delta : 0);
    return 0;
}
