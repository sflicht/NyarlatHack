/* NetHack General Public License: small upstream-facing hook surface. */
#ifndef CHAOS_H
#define CHAOS_H
#include "chaos_protocol.h"
#ifdef CHAOS
#include "chaos_shadow.h"
void chaos_start(void);
void chaos_observe(void);
void chaos_event(const char *, const char *, const char *);
int chaos_event_checked(const char *, const char *, const char *);
void chaos_safe(const char *);
int chaos_ward_count(int);
int chaos_food(int);
long chaos_observation_begin(int);
void chaos_observation_end(long);
void chaos_observation_arm(int, int);
void chaos_observation_disarm(void);
int chaos_observation_take_message(void);
void chaos_observation_delivered(int);
void chaos_observation_map_delivered(void);
void chaos_observation_blocked(void);
#else
#define chaos_shadow_active() (0)
#define chaos_shadow_end(died) ((void)0)
#define chaos_start() ((void)0)
#define chaos_observe() ((void)0)
#define chaos_event(a,b,c) ((void)0)
#define chaos_safe(a) ((void)0)
#define chaos_ward_count(n) (n)
#define chaos_food(n) (n)
#define chaos_observation_begin(operation) (0L)
#define chaos_observation_end(root) ((void)0)
#define chaos_observation_arm(operation,fact) ((void)0)
#define chaos_observation_disarm() ((void)0)
#define chaos_observation_take_message() (0)
#define chaos_observation_delivered(fact) ((void)0)
#define chaos_observation_map_delivered() ((void)0)
#define chaos_observation_blocked() ((void)0)
#endif
#endif
