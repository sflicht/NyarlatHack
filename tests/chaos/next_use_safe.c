/* ENGINE-UNIT: opt-in safe-point admission. Not linked-game gameplay. */
#include "hack.h"
#include "chaos_next_use_safe.h"

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

static int telegraph_ok(void *opaque, const char *text)
{
    int *count = opaque;
    if (!text || !text[0]) return 0;
    if (count) ++*count;
    return 1;
}

int main(int argc, char **argv)
{
    struct chaos_next_use_safe_request req;
    struct chaos_next_use_safe_result first, second;
    struct chaos_state budget;
    int dir, polls, telegraphs = 0;

    if (argc != 9) return 2;
    dir = open(argv[1], O_RDONLY | O_DIRECTORY);
    if (dir < 0) return 2;
    chaos_next_use_safe_reset_for_test();
    chaos_state_init(&budget);
    memset(&req, 0, sizeof req);
    req.dir = dir;
    req.enabled = atoi(argv[8]);
    req.at_safe = atoi(argv[2]);
    req.at_move = atoi(argv[3]);
    req.level_dnum = atoi(argv[4]);
    req.level_dlevel = atoi(argv[5]);
    req.run_hex = argv[6];
    req.sanity = 50;
    req.budget = &budget;
    req.telegraph = telegraph_ok;
    req.telegraph_opaque = &telegraphs;
    polls = atoi(argv[7]);
    memset(&first, 0, sizeof first);
    memset(&second, 0, sizeof second);
    chaos_next_use_safe_try(&req, &first);
    if (polls > 1)
        chaos_next_use_safe_try(&req, &second);
    close(dir);
    printf("{\"loaded\":%d,\"rejected\":%d,\"admitted\":%d,\"active\":%d,"
           "\"pending\":%d,\"telegraph\":%d,\"spent\":%d,"
           "\"second_admitted\":%d,\"second_telegraph\":%d,\"second_spent\":%d}\n",
           first.loaded, first.rejected, first.admitted, first.active,
           first.pending, first.telegraph_count, first.spent,
           second.admitted, second.telegraph_count, second.spent);
    return 0;
}
