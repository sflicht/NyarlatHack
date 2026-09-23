/* ENGINE-UNIT: opt-in safe-point admission. Not linked-game gameplay. */
#include "hack.h"
#include "chaos_next_use_safe.h"
#include "chaos_next_use_runtime.h"
#include "chaos_next_use.h"

#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

long moves;
long monstermoves;
boolean panicking;

void panic(const char *str, ...)
{
    va_list args;
    va_start(args, str);
    fputs(" ERROR:  ", stderr);
    vfprintf(stderr, str, args);
    fputc('\n', stderr);
    va_end(args);
    abort();
}

static struct chaos_state *budget_watch;
static int spent_at_telegraph = -1;

static int telegraph_ok(void *opaque, const char *text)
{
    int *count = opaque;
    if (!text || !text[0]) return 0;
    if (budget_watch) spent_at_telegraph = budget_watch->spent;
    if (count) ++*count;
    return 1;
}

static int telegraph_fail(void *opaque, const char *text)
{
    (void)opaque;
    (void)text;
    if (budget_watch) spent_at_telegraph = budget_watch->spent;
    return 0;
}

static int receipt_ok(void *opaque, const struct chaos_next_use_private_record *record)
{
    (void)opaque;
    (void)record;
    return 1;
}

static int receipt_fail(void *opaque, const struct chaos_next_use_private_record *record)
{
    (void)opaque;
    (void)record;
    return 0;
}

static void bind_origin(const char *run, int qualifying, const char *fact,
                        int root, int dlevel, int origin_move, int family,
                        int notice, int end)
{
    struct chaos_next_use_origin_ref origin;
    memset(&origin, 0, sizeof origin);
    origin.end_seq = end;
    strncpy(origin.fact, fact, sizeof origin.fact - 1);
    origin.family = family;
    origin.level_dlevel = dlevel;
    origin.level_dnum = 0;
    origin.move = origin_move;
    origin.notice_seq = notice;
    origin.root = root;
    strncpy(origin.run, run && strcmp(run, "none") ? run : "",
            CHAOS_NEXT_USE_RUN_HEX);
    origin.run[CHAOS_NEXT_USE_RUN_HEX] = '\0';
    chaos_next_use_safe_bind_origin(&origin, qualifying);
}

int main(int argc, char **argv)
{
    struct chaos_next_use_safe_request req;
    struct chaos_next_use_safe_result first, second;
    struct chaos_state budget;
    const char *wrapper, *telegraph_mode, *budget_mode, *receipt_mode;
    const char *evidence_mode, *run, *clock_mode;
    int dir, polls, telegraphs = 0, before, second_caller;
    int at_safe, at_move, dnum, dlevel, on_safe, origin_move;

    if (argc < 9) return 2;
    dir = open(argv[1], O_RDONLY | O_DIRECTORY);
    if (dir < 0) return 2;
    chaos_next_use_safe_reset_for_test();
    chaos_state_init(&budget);
    at_safe = atoi(argv[2]);
    at_move = atoi(argv[3]);
    dnum = atoi(argv[4]);
    dlevel = atoi(argv[5]);
    run = argv[6];
    polls = atoi(argv[7]);
    wrapper = argc > 9 ? argv[9] : "try";
    telegraph_mode = argc > 10 ? argv[10] : "ok";
    budget_mode = argc > 11 ? argv[11] : "valid";
    receipt_mode = argc > 12 ? argv[12] : "ok";
    evidence_mode = argc > 13 ? argv[13] : "valid";
    clock_mode = argc > 14 ? argv[14] : "native";
    on_safe = !strcmp(wrapper, "on_safe");
    moves = 1;
    monstermoves = at_move;
    if (!strcmp(clock_mode, "negative"))
        monstermoves = -5;
    else if (!strcmp(clock_mode, "overflow"))
        monstermoves = 3000000000L;
    origin_move = !strcmp(clock_mode, "overflow") ? 2147483497 : 40;
    budget_watch = &budget;
    spent_at_telegraph = -1;
    if (!strcmp(budget_mode, "invalid"))
        budget.spent = 100;
    else if (!strcmp(budget_mode, "empty"))
        budget.spent = 12;
    else if (!strcmp(budget_mode, "shared")) {
        budget.effects[CHAOS_HUNGER].value = 2;
        budget.effects[CHAOS_HUNGER].cost = 3;
        budget.effects[CHAOS_HUNGER].expires = 100;
        budget.reserved = 3;
        budget.spent = 3;
    }
    if (!strcmp(evidence_mode, "valid"))
        bind_origin(run, 1, "ordinary_whistle", 10, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_W, 11, 12);
    else if (!strcmp(evidence_mode, "missing"))
        ; /* leave unbound */
    else if (!strcmp(evidence_mode, "incomplete"))
        bind_origin(run, 0, "ordinary_whistle", 10, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_W, 11, 12);
    else if (!strcmp(evidence_mode, "stale"))
        bind_origin(run, 1, "ordinary_whistle", 9, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_W, 11, 12);
    else if (!strcmp(evidence_mode, "wrong_run"))
        bind_origin("cd", 1, "ordinary_whistle", 10, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_W, 11, 12);
    else if (!strcmp(evidence_mode, "wrong_level"))
        bind_origin(run, 1, "ordinary_whistle", 10, 2, origin_move,
                    CHAOS_NEXT_USE_FAMILY_W, 11, 12);
    else if (!strcmp(evidence_mode, "wrong_fact"))
        bind_origin(run, 1, "water_refreshed", 10, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_W, 11, 12);
    else if (!strcmp(evidence_mode, "valid_f"))
        bind_origin(run, 1, "water_refreshed", 10, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_F, 11, 12);
    else if (!strcmp(evidence_mode, "wf")) {
        bind_origin(run, 1, "ordinary_whistle", 10, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_W, 11, 12);
        bind_origin(run, 1, "water_refreshed", 13, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_F, 14, 15);
    } else if (!strcmp(evidence_mode, "fw")) {
        bind_origin(run, 1, "water_refreshed", 13, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_F, 14, 15);
        bind_origin(run, 1, "ordinary_whistle", 10, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_W, 11, 12);
    } else if (!strcmp(evidence_mode, "wf_wrong_f")) {
        bind_origin(run, 1, "ordinary_whistle", 10, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_W, 11, 12);
        bind_origin(run, 1, "water_refreshed", 20, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_F, 21, 22);
    }
    if (on_safe) {
        chaos_next_use_safe_bind_logical(argc > 15 ? strtol(argv[15], NULL, 10)
                                             : 1750000001L);
        if (strcmp(run, "none"))
            chaos_next_use_safe_bind_run(run);
        if (!strcmp(telegraph_mode, "ok"))
            chaos_next_use_safe_bind_telegraph(telegraph_ok, &telegraphs);
        else if (!strcmp(telegraph_mode, "fail"))
            chaos_next_use_safe_bind_telegraph(telegraph_fail, &telegraphs);
        /* receipt=ok leaves the production writer; fail injects transport loss. */
        if (!strcmp(receipt_mode, "fail"))
            chaos_next_use_safe_bind_receipt(receipt_fail, NULL);
    }
    memset(&req, 0, sizeof req);
    req.dir = dir;
    req.enabled = atoi(argv[8]);
    req.at_safe = at_safe;
    req.at_move = at_move;
    req.level_dnum = dnum;
    req.level_dlevel = dlevel;
    req.run_hex = strcmp(run, "none") ? run : NULL;
    req.sanity = 50;
    req.budget = &budget;
    chaos_next_use_safe_bind_logical(argc > 15 ? strtol(argv[15], NULL, 10)
                                             : 1750000001L);
    if (!strcmp(telegraph_mode, "ok")) {
        req.telegraph = telegraph_ok;
        req.telegraph_opaque = &telegraphs;
    } else if (!strcmp(telegraph_mode, "fail")) {
        req.telegraph = telegraph_fail;
        req.telegraph_opaque = &telegraphs;
    }
    if (!strcmp(receipt_mode, "ok"))
        req.receipt = receipt_ok;
    else if (!strcmp(receipt_mode, "fail"))
        req.receipt = receipt_fail;
    memset(&first, 0, sizeof first);
    memset(&second, 0, sizeof second);
    before = budget.spent;
    if (on_safe)
        chaos_next_use_on_safe(dir, at_safe, 50, &budget, dnum, dlevel);
    else
        chaos_next_use_safe_try(&req, &first);
    if (on_safe)
        chaos_next_use_safe_last(&first);
    second_caller = budget.spent;
    if (polls > 1) {
        if (on_safe)
            chaos_next_use_on_safe(dir, at_safe, 50, &budget, dnum, dlevel);
        else
            chaos_next_use_safe_try(&req, &second);
        if (on_safe)
            chaos_next_use_safe_last(&second);
        second_caller = budget.spent;
    }
    close(dir);
    printf("{\"loaded\":%d,\"rejected\":%d,\"admitted\":%d,\"active\":%d,"
           "\"pending\":%d,\"telegraph\":%d,\"spent\":%d,"
           "\"second_admitted\":%d,\"second_telegraph\":%d,\"second_spent\":%d,"
           "\"caller_spent_before\":%d,\"caller_spent\":%d,"
           "\"second_caller_spent\":%d,\"telegraph_spent\":%d,"
           "\"budget_valid\":%d,\"reserved\":%d,\"hunger_value\":%d,"
           "\"hunger_cost\":%d,\"hunger_expires\":%ld,\"run_token\":%ld,"
           "\"level_token\":%ld}\n",
           first.loaded, first.rejected, first.admitted, first.active,
           first.pending, first.telegraph_count, first.spent,
           second.admitted, second.telegraph_count, second.spent,
           before, budget.spent, second_caller, spent_at_telegraph,
           chaos_state_valid(&budget), budget.reserved,
           budget.effects[CHAOS_HUNGER].value,
           budget.effects[CHAOS_HUNGER].cost,
           budget.effects[CHAOS_HUNGER].expires,
           chaos_next_use_runtime_run_token(),
           chaos_next_use_pack_level(dnum, dlevel));
    return 0;
}
