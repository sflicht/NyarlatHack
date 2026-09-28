/* NGPL: drive the post-mortem reveal core over a real run directory. */
#define _POSIX_C_SOURCE 200809L
#include "chaos_reveal.h"
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static void emit(void *unused, const char *line)
{
    (void)unused;
    printf("%s\n", line);
}

/* argv: DIR [host-fact ...]; host facts stand in for values the game host
 * copies from the engine's runtime snapshot and u.haunt/u.curio.
 *   nu=W,F,witnessed,terminated,move,origin_w,origin_f,depth
 *   next_use_rejected | haunt_active | curio_placed */
int main(int argc, char **argv)
{
    static struct chaos_reveal r;
    char xlog[128];
    int dir, i, ok;
    if (argc < 2) return 2;
    dir = open(argv[1], O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    chaos_reveal_init(&r, 1000, 3);
    ok = chaos_reveal_read(&r, dir);
    for (i = 2; i < argc; ++i) {
        struct chaos_reveal_next_use *nu = &r.host.nu;
        if (!strncmp(argv[i], "nu=", 3)) {
            if (sscanf(argv[i] + 3, "%d,%d,%d,%d,%ld,%ld,%ld,%d", &nu->slot_w, &nu->slot_f,
                       &nu->witnessed, &nu->terminated, &nu->admission_move,
                       &nu->origin_w, &nu->origin_f, &nu->depth) != 8)
                return 2;
            nu->present = 1;
        } else if (!strcmp(argv[i], "next_use_rejected")) {
            r.host.next_use_last_rejected = 1;
        } else if (!strcmp(argv[i], "haunt_active")) {
            r.host.haunt_active = 1;
            r.host.haunt_until = 2000;
        } else if (!strcmp(argv[i], "curio_placed")) {
            r.host.curio_placed = 1;
            r.host.curio_charges = 2;
        } else {
            return 2;
        }
    }
    chaos_reveal_finish(&r);
    chaos_reveal_render(&r, emit, 0);
    if (!chaos_reveal_xlog_fields(&r, xlog, sizeof xlog)) return 3;
    printf("XLOG[%s]\n", xlog);
    printf("READ[%d]\n", ok);
    if (dir >= 0) close(dir);
    return 0;
}
