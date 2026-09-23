/* NetHack General Public License. Bounded origin schedule for the director.
 * Not an observation-event field and not a general event database.
 * Header implementation so existing engine object sets keep linking. */
#ifndef CHAOS_NEXT_USE_SCHEDULE_H
#define CHAOS_NEXT_USE_SCHEDULE_H
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>

static inline int chaos_next_use_note_origin(int dir, const char *family,
                                             int move, int dnum, int dlevel,
                                             int root, int notice, int end)
{
    char line[256], chunk[1024];
    struct stat st;
    int fd, n, records = 0, width = 0, interrupts = 0;
    size_t pos = 0, i;
    off_t left;
    ssize_t amount;

    if (dir < 0 || !family) return 0;
    if (strcmp(family, "W") && strcmp(family, "F")) return 0;
    if (move < 0 || move > 2147483547 || dnum < 0 || dnum > 255
        || dlevel < 0 || dlevel > 255 || root < 1 || notice <= root
        || end <= notice || end > 2147483647)
        return 0;
    n = snprintf(line, sizeof line,
                 "{\"next_use_schedule_v\":1,\"family\":\"%s\",\"move\":%d,"
                 "\"level_dnum\":%d,\"level_dlevel\":%d,\"root\":%d,"
                 "\"notice_seq\":%d,\"end_seq\":%d}\n",
                 family, move, dnum, dlevel, root, notice, end);
    if (n < 1 || (size_t)n >= sizeof line) return 0;
    fd = openat(dir, "next_use-schedule.jsonl",
                O_RDWR | O_CREAT | O_APPEND | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC,
                0600);
    if (fd < 0) return 0;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_nlink != 1
        || st.st_uid != getuid() || (st.st_mode & 077)
        || flock(fd, LOCK_EX | LOCK_NB)) goto fail;
    /* Recheck size under the cooperating writer lock. No append past total cap. */
    if (fstat(fd, &st) || st.st_size < 0 || st.st_size > 16384 - n) goto fail;
    left = st.st_size;
    while (left) {
        amount = read(fd, chunk, left < (off_t)sizeof chunk ? (size_t)left : sizeof chunk);
        if (amount < 0 && errno == EINTR && ++interrupts <= 8) continue;
        if (amount <= 0) goto fail;
        left -= amount;
        for (i = 0; i < (size_t)amount; ++i) {
            if (++width > 256) goto fail;
            if (chunk[i] == '\n') {
                if (++records >= 32) goto fail;
                width = 0;
            }
        }
    }
    /* Never append onto someone else's incomplete record or repair old bytes. */
    if (width) goto fail;
    while (pos < (size_t)n) {
        amount = write(fd, line + pos, (size_t)n - pos);
        if (amount < 0 && errno == EINTR && ++interrupts <= 8) continue;
        if (amount <= 0) goto rollback;
        pos += (size_t)amount;
    }
    while (fsync(fd)) {
        if (errno == EINTR && ++interrupts <= 8) continue;
        goto rollback;
    }
    /* Sync file creation too. This is not an atomic append transaction: crash,
     * close or rollback failure can leave ambiguous bytes. Caller must latch
     * failure and MUST NOT mark the origin ready on any failure return. */
    while (fsync(dir)) {
        if (errno == EINTR && ++interrupts <= 8) continue;
        goto rollback;
    }
    return close(fd) == 0;
rollback:
    /* Only bytes added by this locked call; preserve the entire old prefix. */
    if (ftruncate(fd, st.st_size) == 0) (void)fsync(fd);
fail:
    (void)close(fd);
    return 0;
}
#endif
