/* NetHack General Public License: small upstream-facing hook surface. */
#ifndef CHAOS_H
#define CHAOS_H
#ifdef CHAOS
#include "chaos_shadow.h"
void chaos_start(void);
void chaos_observe(void);
void chaos_event(const char *, const char *, const char *);
int chaos_event_checked(const char *, const char *, const char *);
void chaos_safe(const char *);
int chaos_ward_count(int);
int chaos_food(int);
#else
#define chaos_shadow_active() (0)
#define chaos_shadow_end(died) ((void)0)
#define chaos_start() ((void)0)
#define chaos_observe() ((void)0)
#define chaos_event(a,b,c) ((void)0)
#define chaos_safe(a) ((void)0)
#define chaos_ward_count(n) (n)
#define chaos_food(n) (n)
#endif
#endif
