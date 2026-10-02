/* ENGINE-UNIT: opt-in safe-point admission. Not linked-game gameplay. */
#include "hack.h"
#include "chaos_next_use_safe.h"
#include "chaos_next_use_runtime.h"
#include "chaos_next_use.h"

#include <fcntl.h>
#include <assert.h>
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

static int recurrence_lines;  /* Arc 1: "again" telegraphs shown */
static int telegraph_ok(void *opaque, const char *text)
{
    int *count = opaque;
    if (!text || !text[0]) return 0;
    if (!strncmp(text, "next-use-again-", 15)) {
        ++recurrence_lines;  /* not a program telegraph; never counted as one */
        return 1;
    }
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

/* #196 (C3): NYARLATHACK_TEST_COMPANION=absent|present binds a fixed
 * companion answer; unset leaves the check unbound, as before. */
static int companion_calls;
static int companion_fixed(void *opaque)
{
    ++companion_calls;
    return opaque != NULL;
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

void bwrite(int fd, genericptr_t loc, unsigned int num)
{
    assert(write(fd, loc, num) == (ssize_t)num);
}
int chaos_next_use_mread(int fd, void *loc, unsigned int num)
{
    return read(fd, loc, num) == (ssize_t)num;
}

static void series_restore(int dir, struct chaos_state *budget, int *telegraphs)
{
    FILE *save = tmpfile();
    assert(save && chaos_next_use_save(fileno(save)));
    rewind(save);
    chaos_next_use_safe_reset_for_test();
    assert(chaos_next_use_restore_bound(fileno(save), 1750000001L,
                                        chaos_next_use_pack_level(0, 1)));
    assert(chaos_next_use_safe_restore_state(budget, 1));
    chaos_next_use_safe_resume(dir);
    chaos_next_use_safe_bind_logical(1750000001L);
    chaos_next_use_safe_bind_run("abababababababababababababababababababababababababababababababab");
    chaos_next_use_safe_bind_telegraph(telegraph_ok, telegraphs);
    fclose(save);
}

static void series_codec(int dir, int ordinal, const char *phase)
{
    char name[64];
    struct chaos_next_use_snapshot snap;
    int fd;
    snprintf(name, sizeof name, "program-%d-%s.codec", ordinal, phase);
    fd = openat(dir, name, O_WRONLY | O_CREAT | O_EXCL, 0600);
    assert(fd >= 0 && chaos_next_use_snapshot_export(&snap));
    assert(chaos_next_use_snapshot_write(fd, &snap));
    assert(!close(fd));
}

static int series_checks(const char *path)
{
    struct chaos_state budget;
    struct chaos_next_use_safe_result result;
    struct chaos_next_use_snapshot snap;
    const char *run = "abababababababababababababababababababababababababababababababab";
    int dir = open(path, O_RDONLY | O_DIRECTORY), k, telegraphs = 0;
    assert(dir >= 0);
    chaos_next_use_safe_reset_for_test();
    chaos_state_init(&budget);
    chaos_next_use_safe_bind_logical(1750000001L);
    chaos_next_use_safe_bind_run(run);
    chaos_next_use_safe_bind_telegraph(telegraph_ok, &telegraphs);
    for (k = 1; k <= 3; ++k) {
        int root = 10 + (k - 1) * 30;
        monstermoves = 40 + (k - 1) * 400;
        budget.seq = root + 2;
        bind_origin(run, 1, "ordinary_whistle", root, 1, monstermoves,
                    CHAOS_NEXT_USE_FAMILY_W, root + 1, root + 2);
        {
            int rc = chaos_next_use_on_safe(dir, 6 + k, 0, &budget, 0, 1);
            chaos_next_use_safe_last(&result);
            fprintf(stderr, "program %d rc %d reasons %d\n", k, rc, result.reasons);
            assert(rc == CHAOS_NEXT_USE_ADMISSION_OK);
        }
        assert(budget.next_use_count == k && !budget.next_use_terminal);
        series_codec(dir, k, "initial");
        if (getenv("SERIES_RESTORE")) {
            series_restore(dir, &budget, &telegraphs);
            bind_origin(run, 1, "ordinary_whistle", root, 1, monstermoves,
                        CHAOS_NEXT_USE_FAMILY_W, root + 1, root + 2);
        }
        assert(chaos_next_use_on_safe(dir, 7 + k, 0, &budget, 0, 1)
               == CHAOS_NEXT_USE_ADMISSION_NOT_OPEN);
        budget.seq = root + 10;
        monstermoves += k == 1 ? CHAOS_NEXT_USE_LIFETIME_FIRST
                               : CHAOS_NEXT_USE_LIFETIME_LATER;
        chaos_next_use_identity_boundary(1750000001L, chaos_next_use_pack_level(0, 1));
        assert(chaos_next_use_snapshot_export(&snap));
        assert(snap.journal_state == CHAOS_JOURNAL_COMPLETE);
        series_codec(dir, k, "terminal");
        assert(chaos_next_use_on_safe(dir, 7 + k, 0, &budget, 0, 1)
               == CHAOS_NEXT_USE_ADMISSION_NOT_OPEN); /* old origin */
        assert(chaos_next_use_safe_last(&result) && !result.loaded);
        assert(budget.next_use_count == k);
        if (getenv("SERIES_RESTORE")) series_restore(dir, &budget, &telegraphs);
    }
    close(dir);
    assert(telegraphs == 3);
    /* Arc 1: no program in this series delivered (nothing witnessed or
     * applied), so programs 2 and 3 carry no recurrence line. */
    assert(recurrence_lines == 0);
    for (k = 1; k <= 2; ++k) {
        const struct chaos_next_use_snapshot *closed = chaos_next_use_closed_program(k);
        assert(closed && !closed->witnessed);
    }
    puts("{\"programs\":3,\"recurrence_lines\":0}");
    return 0;
}

/* Recurrence repair: program 1 (companion in view) closes, then program 2
 * meets the safe point with NO companion in view. A repaired envelope (ttl
 * 300) is admitted without asking about a companion; a pre-repair envelope
 * (ttl 100) keeps the #196 admission check and is rejected. */
static int repair_checks(const char *path)
{
    struct chaos_state budget;
    struct chaos_next_use_safe_result result;
    struct chaos_next_use_snapshot snap;
    const char *run = "abababababababababababababababababababababababababababababababab";
    int dir = open(path, O_RDONLY | O_DIRECTORY), k, telegraphs = 0, rc = 0;
    long lifetime = 0;
    assert(dir >= 0);
    chaos_next_use_safe_reset_for_test();
    chaos_state_init(&budget);
    chaos_next_use_safe_bind_logical(1750000001L);
    chaos_next_use_safe_bind_run(run);
    chaos_next_use_safe_bind_telegraph(telegraph_ok, &telegraphs);
    companion_calls = 0;
    memset(&result, 0, sizeof result);
    for (k = 1; k <= 2; ++k) {
        int root = 10 + (k - 1) * 30;
        monstermoves = 40 + (k - 1) * 400;
        budget.seq = root + 2;
        bind_origin(run, 1, "ordinary_whistle", root, 1, monstermoves,
                    CHAOS_NEXT_USE_FAMILY_W, root + 1, root + 2);
        chaos_next_use_safe_bind_companion(companion_fixed,
                                           k == 1 ? (void *)&companion_calls : NULL);
        rc = chaos_next_use_on_safe(dir, 6 + k, 0, &budget, 0, 1);
        chaos_next_use_safe_last(&result);
        if (k == 1) {
            assert(rc == CHAOS_NEXT_USE_ADMISSION_OK && companion_calls == 1);
            budget.seq = root + 10;
            monstermoves += CHAOS_NEXT_USE_LIFETIME_FIRST;
            chaos_next_use_identity_boundary(1750000001L,
                                             chaos_next_use_pack_level(0, 1));
            assert(chaos_next_use_snapshot_export(&snap));
            assert(snap.journal_state == CHAOS_JOURNAL_COMPLETE);
        } else if (rc == CHAOS_NEXT_USE_ADMISSION_OK) {
            assert(chaos_next_use_snapshot_export(&snap));
            lifetime = (long)snap.program_expiry - snap.admission_move;
        }
    }
    close(dir);
    printf("{\"admitted\":%d,\"reasons\":%d,\"companion_calls\":%d,"
           "\"lifetime\":%ld,\"telegraphs\":%d,\"count\":%d}\n",
           rc == CHAOS_NEXT_USE_ADMISSION_OK, result.reasons, companion_calls,
           lifetime, telegraphs, budget.next_use_count);
    return 0;
}

/* Arc 1: the felt rule over closed program snapshots, as the engine applies
 * it at admission. Only a witnessed W or an applied F counts; a declared,
 * armed, quiet or native-course program is not felt. */
static int felt_checks(void)
{
    struct chaos_next_use_snapshot w, f, quiet;
    const struct chaos_next_use_snapshot *list[3];
    memset(&w, 0, sizeof w);
    memset(&f, 0, sizeof f);
    memset(&quiet, 0, sizeof quiet);
    w.slot_w = CHAOS_SLOT_W_CONSUMED_ARMED;
    w.witnessed = 1;
    f.slot_f = CHAOS_SLOT_F_CONSUMED_APPLIED;
    quiet.slot_w = CHAOS_SLOT_W_CONSUMED_ARMED;  /* armed, never seen */
    quiet.slot_f = CHAOS_SLOT_F_CONSUMED_NONREMAPPABLE;
    assert(!chaos_next_use_felt_in(NULL, 0, CHAOS_NEXT_USE_FAMILY_W));
    list[0] = &quiet;
    assert(!chaos_next_use_felt_in(list, 1, CHAOS_NEXT_USE_FAMILY_W));
    assert(!chaos_next_use_felt_in(list, 1, CHAOS_NEXT_USE_FAMILY_F));
    list[1] = &w;
    assert(chaos_next_use_felt_in(list, 2, CHAOS_NEXT_USE_FAMILY_W));
    assert(!chaos_next_use_felt_in(list, 2, CHAOS_NEXT_USE_FAMILY_F));
    list[1] = NULL;  /* a rejected attempt has no snapshot */
    list[2] = &f;
    assert(!chaos_next_use_felt_in(list, 3, CHAOS_NEXT_USE_FAMILY_W));
    assert(chaos_next_use_felt_in(list, 3, CHAOS_NEXT_USE_FAMILY_F));
    assert(!chaos_next_use_felt_in(list, 2, CHAOS_NEXT_USE_FAMILY_F)); /* bounded */
    assert(!strcmp(chaos_next_use_player_warning(CHAOS_NEXT_USE_AGAIN_W),
                   "Again, the whistle carries farther than it should."));
    assert(!strcmp(chaos_next_use_player_warning(CHAOS_NEXT_USE_AGAIN_F),
                   "Again, the fountain's water may not run true."));
    puts("{\"felt_checks\":1}");
    return 0;
}

static int policy_checks(void)
{
    struct chaos_state s, saved;
    struct chaos_next_use_safe_request req;
    struct chaos_next_use_safe_result result;
    chaos_next_use_safe_reset_for_test();
    chaos_state_init(&s);
    s.seq = 40;
    assert(chaos_next_use_safe_opportunity(&s, 40));
    s.next_use_count = s.next_use_ordinal = 1;
    s.next_use_id = 7;
    assert(!chaos_next_use_safe_opportunity(&s, 40)); /* still active */
    s.next_use_terminal = 1;
    s.next_use_terminal_seq = 30;
    assert(!chaos_next_use_safe_opportunity(&s, 30)); /* same origin/boundary */
    assert(!chaos_next_use_safe_opportunity(&s, 29));
    assert(!chaos_next_use_safe_opportunity(&s, 41)); /* not yet observed */
    assert(chaos_next_use_safe_opportunity(&s, 31)); /* rejected, no journal */
    saved = s;
    chaos_next_use_safe_reset_for_test();
    assert(!chaos_next_use_safe_restore_state(&saved, 1)); /* mismatched carrier */
    assert(chaos_next_use_set_ordinal(1));
    assert(chaos_next_use_safe_restore_state(&saved, 1));
    assert(chaos_next_use_safe_attempted());
    assert(!chaos_next_use_safe_restore_state(&saved, 0));
    memset(&req, 0, sizeof req);
    req.dir = 0; req.enabled = 1; req.budget = &saved;
    assert(chaos_next_use_safe_try(&req, &result) == CHAOS_NEXT_USE_ADMISSION_NOT_OPEN);
    assert(!result.loaded); /* resume validation is required before polling */
    assert(saved.next_use_count == 1);
    saved.next_use_count = saved.next_use_ordinal = CHAOS_NEXT_USE_PROGRAM_CAP;
    assert(chaos_state_valid(&saved));
    assert(!chaos_next_use_safe_opportunity(&saved, 40));
    assert(chaos_next_use_set_ordinal(2));
    assert(chaos_next_use_set_ordinal(3));
    assert(chaos_next_use_safe_restore_state(&saved, 1));
    assert(chaos_next_use_safe_try(&req, &result) == CHAOS_NEXT_USE_ADMISSION_NOT_OPEN);
    assert(saved.next_use_count == CHAOS_NEXT_USE_PROGRAM_CAP && !result.loaded);
    ++saved.next_use_count;
    assert(!chaos_state_valid(&saved));
    assert(!chaos_next_use_safe_restore_state(&saved, 1));
    saved = s;
    saved.next_use_ordinal = 2;
    assert(!chaos_state_valid(&saved));
    saved = s;
    saved.next_use_terminal_seq = 41;
    assert(!chaos_state_valid(&saved));
    saved = s; saved.version = 4;
    assert(!chaos_state_valid(&saved)); /* refuse, never migrate */
    puts("{\"policy_checks\":1}");
    return 0;
}

int main(int argc, char **argv)
{
    struct chaos_next_use_safe_request req;
    struct chaos_next_use_safe_result first, second;
    struct chaos_state budget;
    const char *wrapper, *telegraph_mode, *budget_mode, *receipt_mode;
    const char *evidence_mode, *run, *clock_mode;
    int dir, polls, telegraphs = 0, before, second_caller;
    int future_open = -1, terminal_seq = -1;
    int at_safe, at_move, dnum, dlevel, on_safe, origin_move;

    if (argc == 3 && !strcmp(argv[1], "series")) return series_checks(argv[2]);
    if (argc == 3 && !strcmp(argv[1], "repair")) return repair_checks(argv[2]);
    if (argc == 2 && !strcmp(argv[1], "policy")) return policy_checks();
    if (argc == 2 && !strcmp(argv[1], "felt")) return felt_checks();
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
    else if (!strcmp(budget_mode, "null"))
        budget_watch = NULL;
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
    else if (!strcmp(evidence_mode, "schedule_fff"))
        bind_origin(run, 1, "water_refreshed", 11, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_F, 12, 13);
    else if (!strcmp(evidence_mode, "schedule_ww"))
        bind_origin(run, 1, "ordinary_whistle", 8, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_W, 9, 10);
    else if (!strcmp(evidence_mode, "schedule_wf")) {
        bind_origin(run, 1, "ordinary_whistle", 5, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_W, 6, 7);
        bind_origin(run, 1, "water_refreshed", 8, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_F, 9, 10);
    }
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
    } else if (!strcmp(evidence_mode, "rebind_w")) {
        /* #177: a newer engine-observed W origin, 5 moves later, same level. */
        bind_origin(run, 1, "ordinary_whistle", 20, 1, origin_move + 5,
                    CHAOS_NEXT_USE_FAMILY_W, 21, 22);
    } else if (!strcmp(evidence_mode, "rebind_other_level")) {
        bind_origin(run, 1, "ordinary_whistle", 20, 2, origin_move + 5,
                    CHAOS_NEXT_USE_FAMILY_W, 21, 22);
    } else if (!strcmp(evidence_mode, "rebind_not_delivered")) {
        bind_origin(run, 0, "ordinary_whistle", 20, 1, origin_move + 5,
                    CHAOS_NEXT_USE_FAMILY_W, 21, 22);
    } else if (!strcmp(evidence_mode, "rebind_wrong_family")) {
        /* Only the other family is newer; the W slot holds an older origin. */
        bind_origin(run, 1, "ordinary_whistle", 9, 1, origin_move,
                    CHAOS_NEXT_USE_FAMILY_W, 11, 12);
        bind_origin(run, 1, "water_refreshed", 20, 1, origin_move + 5,
                    CHAOS_NEXT_USE_FAMILY_F, 21, 22);
    } else if (!strcmp(evidence_mode, "rebind_wrong_fact")) {
        bind_origin(run, 1, "water_refreshed", 20, 1, origin_move + 5,
                    CHAOS_NEXT_USE_FAMILY_W, 21, 22);
    } else if (!strcmp(evidence_mode, "rebind_wrong_run")) {
        bind_origin("cd", 1, "ordinary_whistle", 20, 1, origin_move + 5,
                    CHAOS_NEXT_USE_FAMILY_W, 21, 22);
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
        if (getenv("NYARLATHACK_TEST_COMPANION"))
            chaos_next_use_safe_bind_companion(companion_fixed,
                !strcmp(getenv("NYARLATHACK_TEST_COMPANION"), "present")
                    ? (void *)&companion_calls : NULL);
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
    req.budget = strcmp(budget_mode, "null") ? &budget : NULL;
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
    if (getenv("NYARLATHACK_TEST_COMPANION")) {
        req.companion = companion_fixed;
        req.companion_opaque =
            !strcmp(getenv("NYARLATHACK_TEST_COMPANION"), "present")
                ? (void *)&companion_calls : NULL;
    }
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
    if (polls == 3) {
        budget.seq = 20;
        assert(!chaos_next_use_safe_opportunity(&budget, 20));
        chaos_next_use_expire(CHAOS_END_PROGRAM_EXPIRED);
        terminal_seq = budget.next_use_terminal_seq;
        assert(terminal_seq == 20);
        assert(!chaos_next_use_safe_opportunity(&budget, 20));
        budget.seq = 21;
        future_open = chaos_next_use_safe_opportunity(&budget, 21);
    }
    close(dir);
    printf("{\"count\":%d,\"ordinal\":%d,\"last_program_id\":%d,"
           "\"future_open\":%d,\"terminal_seq\":%d,",
           budget.next_use_count, budget.next_use_ordinal, budget.next_use_id,
           future_open, terminal_seq);
    printf("\"loaded\":%d,\"rejected\":%d,\"admitted\":%d,\"active\":%d,"
           "\"pending\":%d,\"telegraph\":%d,\"spent\":%d,"
           "\"second_admitted\":%d,\"second_telegraph\":%d,\"second_spent\":%d,"
           "\"caller_spent_before\":%d,\"caller_spent\":%d,"
           "\"second_caller_spent\":%d,\"telegraph_spent\":%d,"
           "\"budget_valid\":%d,\"reserved\":%d,\"hunger_value\":%d,"
           "\"hunger_cost\":%d,\"hunger_expires\":%ld,\"run_token\":%ld,"
           "\"level_token\":%ld,\"reasons\":%d,\"rebound\":%d,"
           "\"companion_calls\":%d}\n",
           first.loaded, first.rejected, first.admitted, first.active,
           first.pending, first.telegraph_count, first.spent,
           second.admitted, second.telegraph_count, second.spent,
           before, budget.spent, second_caller, spent_at_telegraph,
           chaos_state_valid(&budget), budget.reserved,
           budget.effects[CHAOS_HUNGER].value,
           budget.effects[CHAOS_HUNGER].cost,
           budget.effects[CHAOS_HUNGER].expires,
           chaos_next_use_runtime_run_token(),
           chaos_next_use_pack_level(dnum, dlevel), first.reasons, first.rebound,
           companion_calls);
    return 0;
}
