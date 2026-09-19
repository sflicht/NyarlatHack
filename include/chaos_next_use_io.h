/* NetHack General Public License. Load next_use.lua; not admission. */
#ifndef CHAOS_NEXT_USE_IO_H
#define CHAOS_NEXT_USE_IO_H
#include "chaos_next_use.h"
#ifdef CHAOS
void chaos_next_use_candidate_tick(int);
int chaos_next_use_envelope_load(int, struct chaos_next_use_envelope *);
int chaos_next_use_envelope_read(int, char *, size_t, size_t *);
#else
#define chaos_next_use_candidate_tick(fd) ((void)0)
#define chaos_next_use_envelope_load(fd, out) (CHAOS_NEXT_USE_OUTPUT)
#define chaos_next_use_envelope_read(fd, buf, cap, n) (CHAOS_NEXT_USE_OUTPUT)
#endif
#endif
