/* ENGINE-UNIT only: real current engine/transport, not native gameplay delivery.
 * These host stubs satisfy unrelated game dependencies using real declarations.
 * Commands simulate delivery flags; they never execute putstr or display hooks. */
#include "hack.h"
#include "chaos.h"
#include "chaos_curio.h"
#include <errno.h>
#include <unistd.h>

struct you u;
struct monst youmonst;
struct permonst mons[NUMMONS];
struct Race urace;
struct sinfo program_state;
long moves = 1;
long monstermoves = 1;
int multi;
static int shadow, write_count, sync_count, fail_write, fail_sync;
int chaos_shadow_active(void) { return shadow; }
void chaos_curio_safe(int dir) { (void)dir; }
#include <stdarg.h>

void pline(const char *fmt, ...) {
    va_list args;
    va_start(args, fmt);
    fputs("message: ", stdout);
    vprintf(fmt, args);
    putchar('\n');
    va_end(args);
}

/* Missing APIs produce behavioral RED (missing records), not link failure. */
extern long chaos_observation_begin(int) __attribute__((weak));
extern void chaos_observation_end(long) __attribute__((weak));
extern void chaos_observation_arm(int, int) __attribute__((weak));
extern void chaos_observation_disarm(void) __attribute__((weak));
extern struct chaos_observation_token chaos_observation_take_message(void) __attribute__((weak));
extern struct chaos_observation_token chaos_observation_take_map(void) __attribute__((weak));
extern void chaos_observation_delivered(struct chaos_observation_token) __attribute__((weak));
extern void chaos_observation_map_delivered(struct chaos_observation_token) __attribute__((weak));
extern void chaos_observation_blocked(void) __attribute__((weak));
ssize_t __real_write(int, const void *, size_t);
int __real_fsync(int);
ssize_t __wrap_write(int fd, const void *buf, size_t n) {
    if (++write_count == fail_write) { errno = EIO; return -1; }
    return __real_write(fd, buf, n);
}
int __wrap_fsync(int fd) {
    if (++sync_count == fail_sync) { errno = EIO; return -1; }
    return __real_fsync(fd);
}
int main(void) {
    char cmd[80], text[80];
    int a, b;
    struct chaos_observation_token token = {0L, CHAOS_OBS_FACT_NONE};
    struct chaos_observation_token saved_token = {0L, CHAOS_OBS_FACT_NONE}, swap;
    const struct chaos_observation_token empty = {0L, CHAOS_OBS_FACT_NONE};
    long root = 0, oldroot = 0;
    struct you before;
    u.usanity = 60; u.uinsight = 4;
    u.uhp = 7; u.uhpmax = 20; u.uen = 2; u.uenmax = 10;
    urace.malenum = PM_HUMAN;
    while (scanf("%79s", cmd) == 1) {
        before = u;
        if (!strcmp(cmd, "food")) mons[PM_HUMAN].mflagst = MT_CARNIVORE;
        else if (!strcmp(cmd, "start")) chaos_start();
        else if (!strcmp(cmd, "restore")) {
            chaos_state_init(&u.chaos); u.chaos.seq = 20;
            u.chaos.safe = 7; u.chaos.spent = 1; u.chaos.last_id = 3;
        } else if (!strcmp(cmd, "env")) {
            if (scanf("%79s", text) != 1) return 2;
            setenv("NYARLATHACK_OBSERVATIONS", text, 1);
        } else if (!strcmp(cmd, "event")) {
            if (scanf("%79s", text) != 1) return 2;
            chaos_event(text, "result", "");
        } else if (!strcmp(cmd, "turn")) ++moves;
        else if (!strcmp(cmd, "shadow")) shadow = !shadow;
        else if (!strcmp(cmd, "dead")) program_state.gameover = !program_state.gameover;
        else if (!strcmp(cmd, "multi")) multi = -1;
        else if (!strcmp(cmd, "nonfood")) urace.malenum = PM_INCANTIFIER;
        else if (!strcmp(cmd, "poly")) {
            u.umonnum = 1; u.mh = -2; u.mhmax = 30; youmonst.data = &mons[PM_HUMAN];
        } else if (!strcmp(cmd, "overflow")) u.chaos.seq = CHAOS_MAX_COUNTER;
        else if (!strcmp(cmd, "fault")) {
            if (scanf("%d%d", &a, &b) != 2) return 2;
            fail_write = a ? write_count + a : 0;
            fail_sync = b ? sync_count + b : 0;
        } else {
            if (!strcmp(cmd, "begin")) {
                if (scanf("%d", &a) != 1) return 2;
                oldroot = root;
                root = chaos_observation_begin ? chaos_observation_begin(a) : 0;
            } else if (!strcmp(cmd, "arm")) {
                if (scanf("%d%d", &a, &b) != 2) return 2;
                if (chaos_observation_arm) chaos_observation_arm(a, b);
            } else if (!strcmp(cmd, "take")) {
                token = chaos_observation_take_message ? chaos_observation_take_message() : empty;
            } else if (!strcmp(cmd, "save_token")) {
                saved_token = token;
            } else if (!strcmp(cmd, "swap_token")) {
                swap = token; token = saved_token; saved_token = swap;
            } else if (!strcmp(cmd, "take_map")) {
                token = chaos_observation_take_map ? chaos_observation_take_map() : empty;
            } else if (!strcmp(cmd, "token")) {
                if (scanf("%ld%d", &token.root, &token.fact) != 2) return 2;
            } else if (!strcmp(cmd, "empty_token")) {
                if (token.root || token.fact != CHAOS_OBS_FACT_NONE) return 5;
            } else if (!strcmp(cmd, "deliver")) {
                if (chaos_observation_delivered) chaos_observation_delivered(token);
            } else if (!strcmp(cmd, "fake")) {
                if (scanf("%d", &a) != 1) return 2;
                swap.root = root; swap.fact = a;
                if (chaos_observation_delivered) chaos_observation_delivered(swap);
            } else if (!strcmp(cmd, "map")) {
                if (chaos_observation_map_delivered) chaos_observation_map_delivered(token);
            } else if (!strcmp(cmd, "disarm")) {
                if (chaos_observation_disarm) chaos_observation_disarm();
            } else if (!strcmp(cmd, "block")) {
                if (chaos_observation_blocked) chaos_observation_blocked();
            } else if (!strcmp(cmd, "end")) {
                if (chaos_observation_end) chaos_observation_end(root);
            } else if (!strcmp(cmd, "oldend")) {
                if (chaos_observation_end) chaos_observation_end(oldroot);
            } else return 3;
            /* Observations may advance only the actual record sequence. */
            before.chaos.seq = u.chaos.seq;
            if (memcmp(&before, &u, sizeof u)) return 4;
        }
        printf("%s %ld %ld %ld %d %d %d %d\n", cmd, root, u.chaos.seq,
               u.chaos.safe, u.chaos.spent, u.chaos.reserved, u.chaos.last_id, token.fact);
    }
    return 0;
}
