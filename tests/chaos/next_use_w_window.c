/* ENGINE-UNIT: W capture window after real admit/install. Not dog_move. */
#include "hack.h"
#include "chaos_next_use_runtime.h"
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
    (void)opaque;
    return text && text[0];
}

int main(int argc, char **argv)
{
    struct chaos_next_use_safe_request req;
    struct chaos_next_use_safe_result admitted;
    struct chaos_state budget;
    unsigned m_id = 7;
    int dir, at_move, ready_early, ready, attention, again, wrong, late;

    if (argc != 5) return 2;
    dir = open(argv[1], O_RDONLY | O_DIRECTORY);
    if (dir < 0) return 2;
    at_move = atoi(argv[2]);
    chaos_next_use_safe_reset_for_test();
    chaos_state_init(&budget);
    memset(&req, 0, sizeof req);
    req.dir = dir;
    req.enabled = 1;
    req.at_safe = atoi(argv[3]);
    req.at_move = at_move;
    req.level_dnum = 0;
    req.level_dlevel = 1;
    req.run_hex = argv[4];
    req.sanity = 50;
    req.budget = &budget;
    req.telegraph = telegraph_ok;
    chaos_next_use_safe_try(&req, &admitted);
    monstermoves = at_move;
    if (!admitted.active
        || !chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 10, 0)) {
        printf("{\"admitted\":%d,\"on_action\":0}\n", admitted.active);
        close(dir);
        return 0;
    }
    chaos_next_use_capture_whistle(10, m_id, at_move);
    monstermoves = at_move + 4;
    ready_early = chaos_next_use_whistle_decision_ready(m_id);
    monstermoves = at_move + 5;
    ready = chaos_next_use_whistle_decision_ready(m_id);
    attention = chaos_next_use_whistle_attention(m_id, 99);
    again = chaos_next_use_whistle_attention(m_id, 100);
    wrong = chaos_next_use_whistle_attention(8, 101);
    monstermoves = at_move + 10;
    late = chaos_next_use_whistle_decision_ready(m_id);
    close(dir);
    printf("{\"admitted\":1,\"on_action\":1,\"ready_early\":%d,\"ready\":%d,"
           "\"attention\":%d,\"again\":%d,\"wrong\":%d,\"late\":%d}\n",
           ready_early, ready, attention, again, wrong, late);
    return 0;
}
