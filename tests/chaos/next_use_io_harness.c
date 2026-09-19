/* ENGINE-UNIT: load-only next_use.lua tick; wrap I/O, not gameplay. */
#define _GNU_SOURCE
#include "chaos_next_use_io.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

ssize_t __real_read(int, void *, size_t);
ssize_t __real_write(int, const void *, size_t);
int __real_fsync(int);
static int fail_read, fail_write, fail_sync, reads, writes, syncs;

ssize_t __wrap_read(int fd, void *buf, size_t n)
{
    ++reads;
    if (fail_read == 1 && reads == 1) {
        errno = EINTR;
        fail_read = 0;
        return -1;
    }
    if (fail_read == 2 && reads == 1 && n > 1)
        return __real_read(fd, buf, 1);
    return __real_read(fd, buf, n);
}

ssize_t __wrap_write(int fd, const void *buf, size_t n)
{
    ++writes;
    if (fail_write == 1 && writes == 1) {
        errno = EIO;
        return -1;
    }
    if (fail_write == 2 && writes == 1 && n > 1)
        return __real_write(fd, buf, 1);
    return __real_write(fd, buf, n);
}

int __wrap_fsync(int fd)
{
    ++syncs;
    if (fail_sync && syncs == fail_sync) {
        errno = EIO;
        return -1;
    }
    return __real_fsync(fd);
}

int main(int argc, char **argv)
{
    int dir, used;
    struct stat st;
    memset(&st, 0, sizeof st);
    if (argc != 3)
        return 2;
    dir = open(argv[1], O_RDONLY | O_DIRECTORY);
    if (dir < 0)
        return 3;
    if (!strcmp(argv[2], "eintr-read"))
        fail_read = 1;
    else if (!strcmp(argv[2], "short-read"))
        fail_read = 2;
    else if (!strcmp(argv[2], "write-fail"))
        fail_write = 1;
    else if (!strcmp(argv[2], "short-write"))
        fail_write = 2;
    else if (!strcmp(argv[2], "fsync-fail"))
        fail_sync = 1;
    chaos_next_use_candidate_tick(dir);
    chaos_next_use_candidate_tick(dir);
    used = !fstatat(dir, "next_use-used.lua", &st, AT_SYMLINK_NOFOLLOW);
    printf("{\"used\":%d,\"size\":%ld,\"reads\":%d,\"writes\":%d,\"syncs\":%d}\n",
           used, used ? (long)st.st_size : -1L, reads, writes, syncs);
    close(dir);
    return 0;
}
