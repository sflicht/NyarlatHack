/* NetHack General Public License. Bounded origin schedule for the director.
 * Not an observation-event field and not a general event database.
 * Header implementation so existing engine object sets keep linking. */
#ifndef CHAOS_NEXT_USE_SCHEDULE_H
#define CHAOS_NEXT_USE_SCHEDULE_H
#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static inline int chaos_next_use_note_origin(int dir, const char *family,
                                             int move, int dnum, int dlevel,
                                             int root, int notice, int end)
{
    char line[256];
    int fd, n;
    ssize_t wrote;

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
                O_WRONLY | O_CREAT | O_APPEND | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (fd < 0) return 0;
    wrote = write(fd, line, (size_t)n);
    if (wrote != n || fsync(fd)) {
        close(fd);
        return 0;
    }
    return close(fd) == 0;
}
#endif
