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
        } else if (!strncmp(argv[i], "prior=", 6)) {
            /* Arc 1: an earlier closed program, same fields as nu=, oldest
             * first; the live nu= program then becomes the next ordinal. */
            struct chaos_reveal_next_use *p;
            if (r.host.prior_count >= CHAOS_REVEAL_PROGRAMS - 1) return 2;
            p = &r.host.prior[r.host.prior_count];
            if (sscanf(argv[i] + 6, "%d,%d,%d,%d,%ld,%ld,%ld,%d", &p->slot_w, &p->slot_f,
                       &p->witnessed, &p->terminated, &p->admission_move,
                       &p->origin_w, &p->origin_f, &p->depth) != 8)
                return 2;
            p->present = 1;
            p->ordinal = ++r.host.prior_count;
            nu->ordinal = r.host.prior_count + 1;
        } else if (!strncmp(argv[i], "broad=", 6)) {
            /* C: the live program is broad: broad=uses,delivered */
            if (sscanf(argv[i] + 6, "%d,%d", &nu->broad_uses, &nu->delivered) != 2)
                return 2;
        } else if (!strcmp(argv[i], "ring")) {
            /* Ring: the live program's W effect is ring. */
            nu->ring = 1;
        } else if (!strcmp(argv[i], "next_use_rejected")) {
            r.host.next_use_last_rejected = 1;
        } else if (!strcmp(argv[i], "haunt_active")) {
            r.host.haunt_active = 1;
            r.host.haunt_until = 2000;
        } else if (!strcmp(argv[i], "curio_placed")) {
            r.host.curio_placed = 1;
            r.host.curio_charges = 2;
        } else if (!strncmp(argv[i], "curio_name=", 11)) {
            /* The engine-held u.curio.name, through the same filter. */
            char name[49];
            memset(name, 0, sizeof name);
            strncpy(name, argv[i] + 11, sizeof name - 1);
            if (strlen(argv[i] + 11) > 48) name[48] = 'x'; /* unterminated: refused */
            chaos_reveal_curio_name(&r.host, name, sizeof name);
        } else {
            return 2;
        }
    }
    chaos_reveal_finish(&r);
    chaos_reveal_render(&r, emit, 0);
    if (!chaos_reveal_xlog_fields(&r, xlog, sizeof xlog)) return 3;
    printf("XLOG[%s]\n", xlog);
    printf("READ[%d]\n", ok);
    {
        static char json[256 * 1024];
        size_t n;
        if (!chaos_reveal_json(&r, json, sizeof json)) return 4;
        n = strlen(json);
        if (n && json[n - 1] == '\n') json[n - 1] = 0;
        printf("JSON[%s]\n", json);
    }
    if (dir >= 0) close(dir);
    return 0;
}
