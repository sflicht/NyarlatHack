/* ENGINE-UNIT: real next-use Lua load/on_action; not gameplay. */
#include "chaos_lua.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const char *quiet_source =
    "return {\n"
    "  on_action = function(context)\n"
    "    return {next_use_intent_v=2, op=\"quiet\", state=context.state}\n"
    "  end\n"
    "}\n";

static void fill_context(struct chaos_next_use_context *c)
{
    memset(c, 0, sizeof *c);
    memset(c->source_sha256, 'a', 64);
    c->source_sha256[64] = '\0';
    c->trigger = CHAOS_NEXT_USE_FAMILY_W;
}

static void print_intent(int status, const struct chaos_next_use_intent *intent)
{
    printf("{\"status\":%d,\"op\":%d,\"state\":%d}\n", status, intent->op,
           intent->state);
}

int main(int argc, char **argv)
{
    struct chaos_next_use_context context;
    struct chaos_next_use_intent intent;
    char source[CHAOS_LUA_SOURCE + 2];
    size_t n;
    int status;
    if (argc < 2) return 2;
    fill_context(&context);
    memset(&intent, 0xa5, sizeof intent);
    if (!strcmp(argv[1], "load-quiet")) {
        status = chaos_lua_next_use_load(quiet_source, strlen(quiet_source));
        printf("{\"status\":%d}\n", status);
        return 0;
    }
    if (!strcmp(argv[1], "on-action-quiet")) {
        status = chaos_lua_next_use_on_action(quiet_source, strlen(quiet_source),
                                              &context, &intent);
        print_intent(status, &intent);
        return 0;
    }
    if (!strcmp(argv[1], "load-nul")) {
        memcpy(source, "return {on_action=function() end}", 33);
        source[6] = 0;
        status = chaos_lua_next_use_load(source, 33);
        printf("{\"status\":%d}\n", status);
        return 0;
    }
    if (!strcmp(argv[1], "load-oversize")) {
        memset(source, ' ', CHAOS_LUA_SOURCE + 1);
        memcpy(source, "return {on_action=function() end}", 33);
        status = chaos_lua_next_use_load(source, CHAOS_LUA_SOURCE + 1);
        printf("{\"status\":%d}\n", status);
        return 0;
    }
    if (!strcmp(argv[1], "extra-root")) {
        const char *s = "return {on_action=function(c) "
                        "return {next_use_intent_v=2, op=\"quiet\", state=0} end}, 1";
        status = chaos_lua_next_use_load(s, strlen(s));
        printf("{\"status\":%d}\n", status);
        return 0;
    }
    if (!strcmp(argv[1], "unknown-field")) {
        const char *s = "return {on_action=function(c) "
                        "return {next_use_intent_v=2, op=\"quiet\", state=0, extra=1} end}";
        status = chaos_lua_next_use_on_action(s, strlen(s), &context, &intent);
        print_intent(status, &intent);
        return 0;
    }
    if (!strcmp(argv[1], "bad-op")) {
        const char *s = "return {on_action=function(c) "
                        "return {next_use_intent_v=2, op=\"ward\", state=0} end}";
        status = chaos_lua_next_use_on_action(s, strlen(s), &context, &intent);
        print_intent(status, &intent);
        return 0;
    }
    if (!strcmp(argv[1], "state-high")) {
        const char *s = "return {on_action=function(c) "
                        "return {next_use_intent_v=2, op=\"quiet\", state=4} end}";
        status = chaos_lua_next_use_on_action(s, strlen(s), &context, &intent);
        print_intent(status, &intent);
        return 0;
    }
    if (!strcmp(argv[1], "two-returns")) {
        const char *s = "return {on_action=function(c) "
                        "return {next_use_intent_v=2, op=\"quiet\", state=0}, 1 end}";
        status = chaos_lua_next_use_on_action(s, strlen(s), &context, &intent);
        print_intent(status, &intent);
        return 0;
    }
    if (!strcmp(argv[1], "hidden-fate")) {
        const char *s = "return {on_action=function(c) "
                        "if c.fate ~= nil or c.rnd ~= nil or c.outcome ~= nil then "
                        "return {next_use_intent_v=2, op=\"delay\", state=0} end "
                        "return {next_use_intent_v=2, op=\"quiet\", state=0} end}";
        status = chaos_lua_next_use_on_action(s, strlen(s), &context, &intent);
        print_intent(status, &intent);
        return 0;
    }
    if (!strcmp(argv[1], "loop")) {
        const char *s = "return {on_action=function(c) while true do end end}";
        status = chaos_lua_next_use_on_action(s, strlen(s), &context, &intent);
        print_intent(status, &intent);
        status = chaos_lua_next_use_on_action(quiet_source, strlen(quiet_source),
                                              &context, &intent);
        printf("{\"recovery\":%d,\"op\":%d}\n", status, intent.op);
        return 0;
    }
    if (!strcmp(argv[1], "stdin-on-action")) {
        n = fread(source, 1, sizeof source, stdin);
        status = chaos_lua_next_use_on_action(source, n, &context, &intent);
        print_intent(status, &intent);
        return 0;
    }
    if (!strcmp(argv[1], "stdin-load")) {
        n = fread(source, 1, sizeof source, stdin);
        status = chaos_lua_next_use_load(source, n);
        printf("{\"status\":%d}\n", status);
        return 0;
    }
    if (!strcmp(argv[1], "upvalue-counter")) {
        const char *s = "local n=0 return {on_action=function(c) n=n+1 "
                        "return {next_use_intent_v=2, op=\"quiet\", state=n} end}";
        status = chaos_lua_next_use_on_action(s, strlen(s), &context, &intent);
        print_intent(status, &intent);
        status = chaos_lua_next_use_on_action(s, strlen(s), &context, &intent);
        print_intent(status, &intent);
        return 0;
    }
    if (!strcmp(argv[1], "returned-state")) {
        const char *s = "return {on_action=function(c) "
                        "return {next_use_intent_v=2, op=\"quiet\", "
                        "state=(c.state<3) and (c.state+1) or 3} end}";
        context.state = 0;
        status = chaos_lua_next_use_on_action(s, strlen(s), &context, &intent);
        print_intent(status, &intent);
        context.state = intent.state;
        status = chaos_lua_next_use_on_action(s, strlen(s), &context, &intent);
        print_intent(status, &intent);
        return 0;
    }
    if (!strcmp(argv[1], "branch-fixtures")) {
        const char *by_trigger =
            "return {on_action=function(c) "
            "if c.trigger==[[W]] then "
            "return {next_use_intent_v=2, op=[[quiet]], state=0} end "
            "return {next_use_intent_v=2, op=[[fountain_refresh]], state=0} end}";
        const char *by_state =
            "return {on_action=function(c) "
            "if c.state==0 then "
            "return {next_use_intent_v=2, op=[[whistle_attention]], state=0} end "
            "return {next_use_intent_v=2, op=[[quiet]], state=c.state} end}";
        context.trigger = CHAOS_NEXT_USE_FAMILY_W;
        context.state = 0;
        status = chaos_lua_next_use_on_action(by_trigger, strlen(by_trigger),
                                              &context, &intent);
        printf("{\"tag\":\"trigger_w\",\"status\":%d,\"op\":%d}\n", status, intent.op);
        context.trigger = CHAOS_NEXT_USE_FAMILY_F;
        status = chaos_lua_next_use_on_action(by_trigger, strlen(by_trigger),
                                              &context, &intent);
        printf("{\"tag\":\"trigger_f\",\"status\":%d,\"op\":%d}\n", status, intent.op);
        context.trigger = CHAOS_NEXT_USE_FAMILY_W;
        context.state = 0;
        status = chaos_lua_next_use_on_action(by_state, strlen(by_state),
                                              &context, &intent);
        printf("{\"tag\":\"state_0\",\"status\":%d,\"op\":%d}\n", status, intent.op);
        context.state = 2;
        status = chaos_lua_next_use_on_action(by_state, strlen(by_state),
                                              &context, &intent);
        printf("{\"tag\":\"state_2\",\"status\":%d,\"op\":%d}\n", status, intent.op);
        return status == 0 ? 0 : 1;
    }
    return 2;
}
