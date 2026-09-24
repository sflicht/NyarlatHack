/* NGPL. Real admission and drinkfountain; fault injection is link-time only. */
#define main fountain_fixture_main
#include "next_use_fountain.c"
#undef main
#include <errno.h>

ssize_t __real_write(int, const void *, size_t);
int __real_fsync(int);
int __real_close(int);
static int journal_fd(int fd)
{
    char path[64], target[4096];
    ssize_t n;
    snprintf(path, sizeof path, "/proc/self/fd/%d", fd);
    n = readlink(path, target, sizeof target - 1);
    if (n < 0) return 0;
    target[n] = 0;
    return strstr(target, "/next_use-journal.jsonl") != 0;
}
ssize_t __wrap_write(int fd, const void *buf, size_t n)
{
    static int interrupted, calls;
    const char *fault = getenv("JOURNAL_TEST_FAULT");
    if (fault && journal_fd(fd)) {
        ++calls;
        if (!strcmp(fault, "short")) {
            if (!interrupted++) { errno = EINTR; return -1; }
            if (n > 7) n = 7;
        }
        if (!strcmp(fault, "sync4-persistent") && calls >= 5) { errno = EIO; return -1; }
        if (!strcmp(fault, "write") && calls == 3) { errno = EIO; return -1; }
        if (!strcmp(fault, "zero") && calls == 3) return 0;
    }
    return __real_write(fd, buf, n);
}
int __wrap_fsync(int fd)
{
    static int count, interrupted;
    const char *fault = getenv("JOURNAL_TEST_FAULT");
    if (journal_fd(fd)) {
        if (fault && !strcmp(fault, "short") && !interrupted++) {
            errno = EINTR; return -1;
        }
        ++count;
        if (fault && !strncmp(fault, "sync", 4)
            && (count == atoi(fault + 4)
                || (!strcmp(fault, "sync4-persistent") && count >= 4))) {
            errno = EIO; return -1;
        }
    }
    return __real_fsync(fd);
}
int __wrap_close(int fd)
{
    const char *fault = getenv("JOURNAL_TEST_FAULT");
    if (fault && !strcmp(fault, "close") && journal_fd(fd)) {
        /* Linux close can release the descriptor and still report failure. */
        (void)__real_close(fd);
        errno = EIO;
        return -1;
    }
    return __real_close(fd);
}
int main(int argc, char **argv)
{
    int dir, admitted, hunger_before, contacted, telegraphs = 0;
    const char *mode = getenv("JOURNAL_TEST_MODE");
    char run[65];
    struct chaos_fountain_token token;
    struct chaos_next_use_capture_status status;
    struct chaos_next_use_safe_result result;
    long obs, root;
    FILE *out;
    if (argc != 2) return 2;
    setenv("NYARLATHACK_RUN_DIR", argv[1], 1);
    setenv("NYARLATHACK_OBSERVATIONS", "1", 1);
    setup_tty(&argc, argv);
    setup_level();
    chaos_start();
    dir = open(argv[1], O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (dir < 0 || dir_run_hex(dir, run)) return 3;
    /* Same approved origin fixture and real safe wrapper, not a supplied capture. */
    chaos_next_use_safe_reset_for_test();
    bind_origin(run);
    chaos_next_use_safe_bind_logical(u.chaos_game_token);
    chaos_next_use_safe_bind_run(run);
    chaos_next_use_safe_bind_telegraph(telegraph_ok, &telegraphs);
    /* Keep approved origin move/source unchanged; advance only the live clock. */
    if (mode && !strcmp(mode, "deadline")) monstermoves = 140;
    if (mode && !strcmp(mode, "deadline-late")) monstermoves = 141;
    admitted = chaos_next_use_on_safe(dir, 7, 50, &u.chaos, 0, 1);
    chaos_next_use_safe_last(&result);
    close(dir);
    hunger_before = u.uhunger;
    memset(&token, 0, sizeof token);
    if (mode && !strcmp(mode, "deadline-late")) {
        struct chaos_next_use_snapshot absent;
        if (!result.rejected || result.active || result.admitted
            || telegraphs || u.chaos.spent
            || chaos_next_use_snapshot_export(&absent)) return 6;
        goto report; /* Rejected admission must never call native effects. */
    }
    if (admitted || !result.active) return 4;
    reseed_period = INT_MAX;
    reseed_count = 0;
    /* Preselected controlled native seed, shared with the capture fixture.
     * Never search/retry seeds to manufacture a passing manifestation. */
    srandom(123u);
    if (mode && !strcmp(mode, "expire")) {
        struct chaos_next_use_snapshot initial;
        assert(chaos_next_use_snapshot_export(&initial));
        monstermoves = initial.program_expiry;
        chaos_next_use_identity_boundary(initial.run_token, initial.level_token);
    } else {
    root = chaos_next_use_fountain_completed_root();
    contacted = chaos_next_use_fountain_contact(root, &token);
    chaos_bind_drinkfountain_token(contacted ? &token : 0);
    obs = chaos_observation_begin(CHAOS_OBS_OP_FOUNTAIN_DRINK);
    drinkfountain();
    chaos_observation_end(obs);
    chaos_bind_drinkfountain_token(0);
    }
report:
    chaos_next_use_capture_status(&status);
    out = fopen("result.json", "w");
    if (!out) return 5;
    fprintf(out, "{\"admitted\":%d,\"rejected\":%d,\"spent\":%d,\"hunger_delta\":%d,\"consumed\":%d,\"incomplete\":%d,\"cursor\":%lu}\n",
            result.admitted, result.rejected, u.chaos.spent,
            u.uhunger - hunger_before, token.consumed,
            status.incomplete, status.acknowledged_cursor);
    fclose(out);
    return 0;
}
