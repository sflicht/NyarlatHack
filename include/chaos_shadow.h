/* NetHack General Public License. Fixed-size shadow report; no script callbacks. */
#ifndef CHAOS_SHADOW_H
#define CHAOS_SHADOW_H
struct chaos_shadow_report { int ok,steps,blocked,contacts,died,script_errors,sandboxed; };
int chaos_shadow_run(void (*)(void *,struct chaos_shadow_report *),void *,struct chaos_shadow_report *);
int chaos_shadow_active(void);
void chaos_shadow_death(void);
#endif
