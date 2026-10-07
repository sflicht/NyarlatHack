/* NetHack General Public License. Player-only serializable haunting state. */
#ifndef CHAOS_HAUNT_H
#define CHAOS_HAUNT_H
#include "chaos_lua.h"
struct monst; struct nhcoord;
struct chaos_haunt_state {
 int checked,active,state,count,backtracks,echo_pending,echo_delivered,was_asleep;
 int dnum,dlevel,source_len;unsigned target;
 long last_turn,until;
 struct chaos_point history[CHAOS_TRAIL];
 char source[CHAOS_LUA_SOURCE+1];
};
#ifdef CHAOS
void chaos_haunt_tick(int);
int chaos_haunt_valid(const struct chaos_haunt_state *);
int chaos_haunt_pick(struct monst *,const struct nhcoord *,int);
void chaos_haunt_commit(struct monst *);
void tty_chaos_echo(const char *);
#else
#define chaos_haunt_tick(fd) ((void)0)
#define chaos_haunt_pick(m,p,n) (-2)
#define chaos_haunt_commit(m) ((void)0)
#endif
#endif
