/* NetHack General Public License. Consume next_use.lua once; not admission. */
#include "hack.h"
#include "chaos_lua.h"
#include "chaos_next_use_io.h"
#include <fcntl.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

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
    n = read(fd, source, CHAOS_LUA_SOURCE + 1);
    close(fd);
    if (n < 1 || n > CHAOS_LUA_SOURCE || memchr(source, 0, (size_t) n))
        return;
    source[n] = 0;
    if (chaos_lua_next_use_load(source, (size_t) n) != 0)
        return;
    used = private_file(dir, "next_use-used.lua", O_WRONLY | O_CREAT | O_EXCL);
    if (used < 0)
        return;
    if (write(used, source, n) != n || fsync(used)) {
        close(used);
        return;
    }
    close(used);
}
