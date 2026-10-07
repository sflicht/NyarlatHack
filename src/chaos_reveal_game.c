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

/* The reveal core mirrors the runtime's slot values; keep them in step. */
typedef char chaos_reveal_slot_mirror[
    ((int)CHAOS_REVEAL_W_PENDING == (int)CHAOS_SLOT_W_PENDING
     && (int)CHAOS_REVEAL_W_CONSUMED_ARMED == (int)CHAOS_SLOT_W_CONSUMED_ARMED
     && (int)CHAOS_REVEAL_W_CONSUMED_QUIET == (int)CHAOS_SLOT_W_CONSUMED_QUIET
     && (int)CHAOS_REVEAL_W_CONSUMED_DELAY == (int)CHAOS_SLOT_W_CONSUMED_DELAY
     && (int)CHAOS_REVEAL_W_CONSUMED_INVALID == (int)CHAOS_SLOT_W_CONSUMED_INVALID
     && (int)CHAOS_REVEAL_W_CONSUMED_SUPPRESSED == (int)CHAOS_SLOT_W_CONSUMED_SUPPRESSED
     && (int)CHAOS_REVEAL_W_TERMINATED_EXPIRY == (int)CHAOS_SLOT_W_TERMINATED_EXPIRY
     && (int)CHAOS_REVEAL_W_TERMINATED_LEVEL == (int)CHAOS_SLOT_W_TERMINATED_LEVEL
     && (int)CHAOS_REVEAL_W_TERMINATED_TRANSPORT == (int)CHAOS_SLOT_W_TERMINATED_TRANSPORT
     && (int)CHAOS_REVEAL_W_CONSUMED_RANG == (int)CHAOS_SLOT_W_CONSUMED_RANG
     && (int)CHAOS_REVEAL_F_PENDING == (int)CHAOS_SLOT_F_PENDING
     && (int)CHAOS_REVEAL_F_CONSUMED_APPLIED == (int)CHAOS_SLOT_F_CONSUMED_APPLIED
     && (int)CHAOS_REVEAL_F_CONSUMED_NONREMAPPABLE == (int)CHAOS_SLOT_F_CONSUMED_NONREMAPPABLE
     && (int)CHAOS_REVEAL_F_CONSUMED_QUIET == (int)CHAOS_SLOT_F_CONSUMED_QUIET
     && (int)CHAOS_REVEAL_F_CONSUMED_DELAY == (int)CHAOS_SLOT_F_CONSUMED_DELAY
     && (int)CHAOS_REVEAL_F_CONSUMED_INVALID == (int)CHAOS_SLOT_F_CONSUMED_INVALID
     && (int)CHAOS_REVEAL_F_CONSUMED_SUPPRESSED == (int)CHAOS_SLOT_F_CONSUMED_SUPPRESSED
     && (int)CHAOS_REVEAL_F_TERMINATED_EXPIRY == (int)CHAOS_SLOT_F_TERMINATED_EXPIRY
     && (int)CHAOS_REVEAL_F_TERMINATED_LEVEL == (int)CHAOS_SLOT_F_TERMINATED_LEVEL
     && (int)CHAOS_REVEAL_F_TERMINATED_TRANSPORT == (int)CHAOS_SLOT_F_TERMINATED_TRANSPORT)
    ? 1 : -1];

static int level_depth(long token)
{
    d_level lev;
    long dnum = token / 100000L - 1, dlevel = token % 100000L;
    if (token <= 0 || dnum < 0 || dnum >= MAXDUNGEON || dnum >= n_dgns || dlevel < 1 || dlevel > 200) return 0;
    lev.dnum = (xchar)dnum;
    lev.dlevel = (xchar)dlevel;
    return depth(&lev);
}

/* Next-use facts are the engine's own runtime snapshot values, copied as-is.
 * The origin roots are the bound origins (after any rebind); the published
 * ones come from the receipt row the core reads. */
static void copy_program(struct chaos_reveal_next_use *nu,
                         const struct chaos_next_use_snapshot *s, int ordinal)
{
    nu->present = 1;
    nu->terminated = s->phase == CHAOS_ATTEMPT_TERMINATED;
    nu->slot_w = s->slot_w;
    nu->slot_f = s->slot_f;
    nu->witnessed = s->witnessed != 0;
    nu->admission_move = s->admission_move;
    nu->origin_w = s->origin_w;
    nu->origin_f = s->origin_f;
    nu->depth = level_depth(s->level_token);
    nu->ordinal = ordinal;
    nu->broad_uses = s->broad_uses;
    nu->delivered = s->delivered;
    nu->ring = s->w_effect == CHAOS_NEXT_USE_W_EFFECT_RING;
}

static void next_use_facts(struct chaos_reveal_host *h)
{
    static struct chaos_next_use_snapshot s;
    struct chaos_next_use_safe_result last;
    const struct chaos_next_use_snapshot *closed;
    int k, ordinal = chaos_next_use_program_ordinal();
    if (chaos_next_use_safe_last(&last) && last.rejected) h->next_use_last_rejected = 1;
    /* Arc 1: earlier programs are the engine's saved closed snapshots. */
    for (k = 1; k < ordinal && k < CHAOS_REVEAL_PROGRAMS; ++k)
        if ((closed = chaos_next_use_closed_program(k))
            && closed->phase >= CHAOS_ATTEMPT_COMMITTED) {
            copy_program(&h->prior[k - 1], closed, k);
            h->prior_count = k;
        }
    if (!chaos_next_use_snapshot_export(&s) || s.phase < CHAOS_ATTEMPT_COMMITTED) return;
    copy_program(&h->nu, &s, ordinal > 0 ? ordinal : 1);
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
    chaos_reveal_curio_name(&reveal.host, u.curio.name, sizeof u.curio.name);
    next_use_facts(&reveal.host);
    chaos_reveal_finish(&reveal);
}

/* #188: the rendered section, for `chaos chronicle`. Written into the run
 * directory only after an admission, so stock and empty-mailbox runs gain no
 * file. Presentation only: failure is silent and changes nothing else. */
static void write_record(void)
{
    static char json[256 * 1024];
    struct stat st;
    size_t n;
    int dir, fd;
    if (!chaos_reveal_json(&reveal, json, sizeof json) || !json[0]) return;
    if ((dir = open_run()) < 0) return;
    fd = openat(dir, "reveal.json", O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW | O_CLOEXEC, 0600);
    (void)close(dir);
    if (fd < 0) return;
    n = strlen(json);
    if (!fstat(fd, &st) && S_ISREG(st.st_mode) && st.st_uid == getuid())
        if (write(fd, json, n) == (ssize_t)n) (void)fsync(fd);
    (void)close(fd);
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
    write_record();
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
