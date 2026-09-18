/* NetHack General Public License. Load next_use.lua; not admission. */
#ifndef CHAOS_NEXT_USE_IO_H
#define CHAOS_NEXT_USE_IO_H
#ifdef CHAOS
void chaos_next_use_candidate_tick(int);
#else
#define chaos_next_use_candidate_tick(fd) ((void)0)
#endif
#endif
