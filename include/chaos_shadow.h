/* NetHack General Public License. Fixed-size shadow report; no script callbacks. */
#ifndef CHAOS_SHADOW_H
#define CHAOS_SHADOW_H
/* min_dist/median_dist: Chebyshev distance hound-player after each hound
 * action (median: lower median over the steps taken); -1 when no step ran. */
struct chaos_shadow_report { int ok,steps,blocked,contacts,died,script_errors,sandboxed,moved,escaped,max_damage,min_dist,median_dist; };
int chaos_shadow_run(void (*)(void *,struct chaos_shadow_report *),void *,struct chaos_shadow_report *);
int chaos_shadow_active(void);
void chaos_shadow_end(int);
#endif
