/* NetHack General Public License - synchronous bounded mailbox transport. */
#ifndef CHAOS_IO_H
#define CHAOS_IO_H
#include "chaos_protocol.h"
struct chaos_io { int dir, events, journal, busy, failed; };
struct chaos_context { long turn; int sanity, insight, eligible;
    int hp, hp_max, power, power_max; /* player-known status-line values */
};
typedef int (*chaos_telegraph_fn)(void *, int, int);
int chaos_io_open(struct chaos_io *, const char *);
void chaos_io_close(struct chaos_io *);
int chaos_io_event(struct chaos_io *, struct chaos_state *, const struct chaos_context *,
                   const char *, const char *, const char *);
void chaos_io_expire(struct chaos_io *, struct chaos_state *, const struct chaos_context *);
void chaos_io_safe(struct chaos_io *, struct chaos_state *, const struct chaos_context *,
                   const char *, chaos_telegraph_fn, void *);
#endif
