/* ENGINE-UNIT producer using the production header, with scoped I/O faults. */
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

static const char *fault = "";
static int writes, reads;
static ssize_t note_write(int fd, const void *buf, size_t n)
{
    ++writes;
    if (!strcmp(fault, "eintr") && writes == 1) { errno = EINTR; return -1; }
    if (!strcmp(fault, "partial_fail") && writes > 1) { errno = EIO; return -1; }
    if ((!strcmp(fault, "short") || !strcmp(fault, "partial_fail")) && n > 3) n = 3;
    return write(fd, buf, n);
}
static ssize_t __attribute__((unused)) note_read(int fd, void *buf, size_t n)
{
    ++reads;
    if (!strcmp(fault, "read_eintr") && reads == 1) { errno = EINTR; return -1; }
    if (!strcmp(fault, "read_short") && n > 3) n = 3;
    return read(fd, buf, n);
}
static int note_fsync(int fd)
{
    if (!strcmp(fault, "sync_fail")) { errno = EIO; return -1; }
    return fsync(fd);
}
static int note_fstat(int fd, struct stat *st)
{
    int result = fstat(fd, st);
    if (!result && !strcmp(fault, "owner")) st->st_uid = getuid() + 1;
    return result;
}
#define write note_write
#define read note_read
#define fsync note_fsync
#define fstat note_fstat
#include "chaos_next_use_schedule.h"
#undef write
#undef read
#undef fsync
#undef fstat

int main(int argc, char **argv)
{
    int dir, status, lock = -1;
    const char *family = "W";
    int root = 10, notice = 11, end = 12;
    if (argc != 2 && argc != 3 && argc != 6) return 2;
    if (argc == 3) fault = argv[2];
    if (argc == 6) {
        family = argv[2]; root = atoi(argv[3]); notice = atoi(argv[4]); end = atoi(argv[5]);
    }
    dir = open(argv[1], O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (dir < 0) return 1;
    if (!strcmp(fault, "fifo") && mkfifoat(dir, "next_use-schedule.jsonl", 0600)) return 1;
    if (!strcmp(fault, "held_lock")) {
        lock = openat(dir, "next_use-schedule.jsonl", O_RDWR | O_CREAT, 0600);
        if (lock < 0 || flock(lock, LOCK_EX | LOCK_NB)) return 1;
    }
    status = chaos_next_use_note_origin(dir, family, 40, 0, 1, root, notice, end);
    printf("{\"status\":%d}\n", status);
    if (lock >= 0) close(lock);
    close(dir);
    return 0;
}
