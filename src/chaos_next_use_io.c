/* NetHack General Public License. Consume next_use.lua once; not admission. */
#define _GNU_SOURCE
#include "chaos_lua.h"
#include "chaos_next_use.h"
#include "chaos_next_use_io.h"
#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

/*
 * Process-local `checked` is not durable evidence. It latches after this
 * process opens a private next_use.lua, including invalid Lua, so a failed
 * candidate is not retried every turn. Absent/unreadable files do not latch;
 * polling stays nonblocking. next_use-used.lua is proof of a complete
 * load/copy only, never admission or permission to run a mechanic.
 */

static int private_file(int dir, const char *name, int flags)
{
    struct stat st;
    int fd;

    fd = openat(dir, name, flags | O_NOFOLLOW | O_NONBLOCK, 0600);
    if (fd < 0)
        return -1;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != getuid()
        || st.st_nlink != 1 || (st.st_mode & 077)) {
        close(fd);
        return -1;
    }
    return fd;
}

static ssize_t full_read(int fd, char *buf, size_t cap)
{
    size_t pos = 0;
    while (pos < cap) {
        ssize_t n = read(fd, buf + pos, cap - pos);
        if (n < 0 && errno == EINTR)
            continue;
        if (n < 0)
            return -1;
        if (n == 0)
            return (ssize_t)pos;
        pos += (size_t)n;
    }
    return (ssize_t)pos;
}

static int full_write(int fd, const char *buf, size_t len)
{
    size_t pos = 0;
    while (pos < len) {
        ssize_t n = write(fd, buf + pos, len - pos);
        if (n < 0 && errno == EINTR)
            continue;
        if (n <= 0)
            return 0;
        pos += (size_t)n;
    }
    return 1;
}

void chaos_next_use_candidate_tick(int dir)
{
    static int checked;
    char source[CHAOS_LUA_SOURCE + 1];
    ssize_t n;
    int fd, used;

    if (checked || dir < 0)
        return;
    fd = private_file(dir, "next_use.lua", O_RDONLY);
    if (fd < 0)
        return;
    checked = 1;
    n = full_read(fd, source, CHAOS_LUA_SOURCE + 1);
    close(fd);
    if (n < 1 || n > CHAOS_LUA_SOURCE || memchr(source, 0, (size_t)n))
        return;
    if (chaos_lua_next_use_load(source, (size_t)n) != 0)
        return;
    used = private_file(dir, "next_use-used.lua",
                        O_WRONLY | O_CREAT | O_EXCL);
    if (used < 0)
        return;
    if (!full_write(used, source, (size_t)n) || fsync(used)) {
        close(used);
        unlinkat(dir, "next_use-used.lua", 0);
        return;
    }
    if (close(used) || fsync(dir)) {
        unlinkat(dir, "next_use-used.lua", 0);
        return;
    }
}

int chaos_next_use_envelope_load(int dir, struct chaos_next_use_envelope *out)
{
    char buf[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    ssize_t n;
    int fd;

    if (!out)
        return CHAOS_NEXT_USE_NULL_ARGUMENT;
    memset(out, 0, sizeof *out);
    if (dir < 0)
        return CHAOS_NEXT_USE_OUTPUT;
    fd = private_file(dir, "next_use-envelope.json", O_RDONLY);
    if (fd < 0)
        return CHAOS_NEXT_USE_OUTPUT;
    n = full_read(fd, buf, sizeof buf);
    close(fd);
    if (n < 1 || n > CHAOS_NEXT_USE_ENVELOPE_MAX)
        return CHAOS_NEXT_USE_LIMIT;
    if (memchr(buf, 0, (size_t)n))
        return CHAOS_NEXT_USE_UTF8;
    return chaos_next_use_parse_envelope(buf, (size_t)n, out);
}

int chaos_next_use_envelope_read(int dir, char *buf, size_t cap, size_t *written)
{
    ssize_t n;
    int fd;

    if (!buf || !written)
        return CHAOS_NEXT_USE_NULL_ARGUMENT;
    *written = 0;
    if (dir < 0 || cap < 1)
        return CHAOS_NEXT_USE_OUTPUT;
    fd = private_file(dir, "next_use-envelope.json", O_RDONLY);
    if (fd < 0)
        return CHAOS_NEXT_USE_OUTPUT;
    n = full_read(fd, buf, cap);
    close(fd);
    if (n < 1 || (size_t)n >= cap)
        return CHAOS_NEXT_USE_LIMIT;
    if (memchr(buf, 0, (size_t)n))
        return CHAOS_NEXT_USE_UTF8;
    buf[n] = '\0';
    *written = (size_t)n;
    return CHAOS_NEXT_USE_OK;
}
