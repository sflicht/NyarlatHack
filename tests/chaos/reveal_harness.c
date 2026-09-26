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

/* argv: DIR [host-fact ...]; host facts stand in for copied engine state. */
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
        if (!strcmp(argv[i], "next_use_undelivered") || !strcmp(argv[i], "next_use_delivered")) {
            r.host.next_use = 1;
            r.host.next_use_turn = 40;
            r.host.next_use_delivered = !strcmp(argv[i], "next_use_delivered");
            strcpy(r.host.next_use_origin, "after you whistled on DL3 on turn 30");
            strcpy(r.host.next_use_telegraph, "The next whistle may call unusual attention.");
            strcpy(r.host.next_use_effect, "your next whistle armed it.");
            strcpy(r.host.next_use_ended, "consumed or ended before the game ended.");
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
