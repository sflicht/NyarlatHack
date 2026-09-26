/* NetHack General Public License. Post-mortem reveal host: runs once after the
 * final state is fixed. No RNG, no game-state writes, no save/bones impact. */
#include "hack.h"
#include "chaos.h"
#include "chaos_reveal.h"
#include "chaos_next_use_runtime.h"
#include "chaos_next_use_safe.h"
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

extern int n_dgns;          /* dungeon.c: dungeon count, no header */
#ifdef DUMP_LOG
extern FILE *dump_fp;       /* end.c: open only while the dumplog is written */
#endif

static struct chaos_reveal reveal;
static int computed;

static const char *w_outcome(int slot)
{
    switch (slot) {
    case CHAOS_SLOT_W_PENDING: return "it was still waiting for your next whistle";
    case CHAOS_SLOT_W_CONSUMED_ARMED: return "your next whistle armed it";
    case CHAOS_SLOT_W_CONSUMED_QUIET: return "at your next whistle it chose to stay quiet";
    case CHAOS_SLOT_W_CONSUMED_DELAY: return "at your next whistle it chose to wait";
    case CHAOS_SLOT_W_CONSUMED_INVALID: return "its program failed at your next whistle; nothing changed";
    case CHAOS_SLOT_W_CONSUMED_SUPPRESSED: return "a guard suppressed it at your next whistle; nothing changed";
    case CHAOS_SLOT_W_TERMINATED_EXPIRY: return "it expired before you whistled again";
    case CHAOS_SLOT_W_TERMINATED_LEVEL: return "it ended when you left the level";
    case CHAOS_SLOT_W_TERMINATED_TRANSPORT: return "it ended when its record could not be written";
    }
    return 0;
}

static const char *f_outcome(int slot)
{
    switch (slot) {
    case CHAOS_SLOT_F_PENDING: return "it was still waiting for your next fountain drink";
    case CHAOS_SLOT_F_CONSUMED_APPLIED: return "your next fountain drink was turned into a refreshing one";
    case CHAOS_SLOT_F_CONSUMED_NONREMAPPABLE: return "your next fountain drink took its native course";
    case CHAOS_SLOT_F_CONSUMED_QUIET: return "at your next fountain drink it chose to stay quiet";
    case CHAOS_SLOT_F_CONSUMED_DELAY: return "at your next fountain drink it chose to wait";
    case CHAOS_SLOT_F_CONSUMED_INVALID: return "its program failed at your next fountain drink; nothing changed";
    case CHAOS_SLOT_F_CONSUMED_SUPPRESSED: return "a guard suppressed it at your next fountain drink; nothing changed";
    case CHAOS_SLOT_F_TERMINATED_EXPIRY: return "it expired before you drank again";
    case CHAOS_SLOT_F_TERMINATED_LEVEL: return "it ended when you left the level";
    case CHAOS_SLOT_F_TERMINATED_TRANSPORT: return "it ended when its record could not be written";
    }
    return 0;
}

static int level_depth(long token)
{
    d_level lev;
    long dnum = token / 100000L - 1, dlevel = token % 100000L;
    if (token <= 0 || dnum < 0 || dnum >= MAXDUNGEON || dnum >= n_dgns || dlevel < 1 || dlevel > 200) return 0;
    lev.dnum = (xchar)dnum;
    lev.dlevel = (xchar)dlevel;
    return depth(&lev);
}

/* Next-use facts come from the engine's own saved runtime snapshot. */
static void next_use_facts(struct chaos_reveal_host *h)
{
    static struct chaos_next_use_snapshot s;
    struct chaos_next_use_safe_result last;
    const char *w, *f, *id;
    char where[40];
    int dl;
    if (chaos_next_use_safe_last(&last) && last.rejected) ++reveal.rejected;
    if (!chaos_next_use_snapshot_export(&s) || s.phase < CHAOS_ATTEMPT_COMMITTED) return;
    h->next_use = 1;
    h->next_use_turn = s.admission_move;
    h->next_use_delivered = s.witnessed != 0;
    w = s.slot_w != CHAOS_SLOT_W_UNDECLARED ? w_outcome(s.slot_w) : 0;
    f = s.slot_f != CHAOS_SLOT_F_UNDECLARED ? f_outcome(s.slot_f) : 0;
    id = w && f ? "next-use-v2-WF" : w ? "next-use-v2-W" : "next-use-v2-F";
    Strcpy(h->next_use_telegraph, chaos_next_use_player_warning(id)
           ? chaos_next_use_player_warning(id) : "");
    dl = level_depth(s.level_token);
    if (dl) Sprintf(where, " on DL%d", dl);
    else where[0] = 0;
    if (w && s.origin_w > 0 && s.origin_w_deadline >= 100)
        Sprintf(h->next_use_origin, "after you whistled%s on turn %ld",
                where, s.origin_w_deadline - 100);
    else if (f && s.origin_f > 0 && s.origin_f_deadline >= 100)
        Sprintf(h->next_use_origin, "after you drank from a fountain%s on turn %ld",
                where, s.origin_f_deadline - 100);
    Sprintf(h->next_use_effect, "%s%s%s.", w ? w : "", w && f ? "; " : "", f ? f : "");
    Strcpy(h->next_use_ended, s.phase == CHAOS_ATTEMPT_TERMINATED
           ? "consumed or ended before the game ended."
           : "still pending when the game ended.");
}

/* Read-only reopen of this process's run directory, with the ownership and
 * no-follow rules chaos_io_open applies. Never creates or repairs a file. */
static int open_run(void)
{
    const char *path = getenv("NYARLATHACK_RUN_DIR");
    struct stat st;
    int fd;
    if (!path || path[0] != '/' || u.chaos.version == 0) return -1;
    fd = open(path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    if (fd < 0) return -1;
    if (fstat(fd, &st) || st.st_uid != getuid() || (st.st_mode & 077)) {
        close(fd);
        return -1;
    }
    return fd;
}

static void compute(void)
{
    int dir;
    if (computed) return;
    computed = 1;
    chaos_reveal_init(&reveal, moves, u.chaos.spent);
    dir = open_run();
    /* Without a run directory nothing can have been admitted: stay silent. */
    if (dir < 0) return;
    (void)chaos_reveal_read(&reveal, dir);
    (void)close(dir);
    reveal.host.haunt_active = u.haunt.active;
    reveal.host.haunt_until = u.haunt.until;
    reveal.host.curio_placed = u.curio.phase == CHAOS_CURIO_PLACED;
    reveal.host.curio_charges = u.curio.charges;
    next_use_facts(&reveal.host);
    chaos_reveal_finish(&reveal);
}

static void to_dump(void *unused, const char *line)
{
    (void)unused;
#ifdef DUMP_LOG
    dump("", (char *)line);
#else
    (void)line;
#endif
}

static void to_window(void *win, const char *line)
{
    putstr(*(winid *)win, 0, line);
}

/* Settled policy: default n, asked only after at least one admission. The
 * dumplog section is written whatever the answer. */
void chaos_reveal_end(int how)
{
    winid win;
    char c;
    if (chaos_shadow_active()) return;
    compute();
    if (!reveal.admitted) return;
    if (iflags.window_inited && !program_state.stopprint && how != PANICKED
        && strcmp(flags.end_disclose, "none")) {
        c = yn_function("Do you want to know what watched you?", ynqchars, 'n');
        if (c == 'y') {
            win = create_nhwindow(NHW_TEXT);
            chaos_reveal_render(&reveal, to_window, &win);
            display_nhwindow(win, TRUE);
            destroy_nhwindow(win);
        } else if (c == 'q') {
            program_state.stopprint++;
        }
    }
#ifdef DUMP_LOG
    if (dump_fp) chaos_reveal_render(&reveal, to_dump, 0);
#endif
}

void chaos_reveal_xlog(FILE *rfile)
{
    char buf[128];
    if (!computed || !rfile || !chaos_reveal_xlog_fields(&reveal, buf, sizeof buf)) return;
    if (buf[0]) (void)fputs(buf, rfile);
}
