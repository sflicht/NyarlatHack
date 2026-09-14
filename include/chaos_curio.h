/* NetHack General Public License: pointer-free, player-owned curio save record. */
#ifndef CHAOS_CURIO_H
#define CHAOS_CURIO_H

#define CHAOS_CURIO_VERSION 1
#define CHAOS_CURIO_SOURCE 4096

enum chaos_curio_phase {
    CHAOS_CURIO_VIRGIN = 0,
    CHAOS_CURIO_REJECTED,
    CHAOS_CURIO_ADMITTED,
    CHAOS_CURIO_PLACED,
    CHAOS_CURIO_EXPIRED
};
enum chaos_curio_tag {
    CHAOS_CURIO_ORDINARY = 0,
    CHAOS_CURIO_GENERATED,
    CHAOS_CURIO_INERT_REMNANT
};

/* VIRGIN is all-zero fields (including unused text); other phases use version 1.
 * REJECTED has no source/name/owner/charges/state/disabled.
 * ADMITTED has source+canonical name, owner 0, charges 3, state/disabled 0.
 * PLACED has source+name and nonzero owner, charges 0..3, state 0..255,
 * disabled 0..1. Ownership need not be loaded or in inventory on restore.
 * EXPIRED permanently retires an unplaced opportunity: either no-source empty
 * fields or the unchanged admitted record. Never convert it back to ADMITTED.
 * No pointers or Lua VM state; source_len excludes the terminating NUL.
 */
struct chaos_curio_state {
    unsigned version;
    unsigned phase;
    unsigned source_len;
    unsigned owner;
    int charges;
    int state;
    int disabled;
    char name[49];
    char source[CHAOS_CURIO_SOURCE + 1];
};
int chaos_curio_valid(const struct chaos_curio_state *);
/* Engine safe-point adapter supplies a healthy dir only after actual advance.
 * A negative dir services unplaced expiry only, without transport. */
struct obj;
#ifdef CHAOS
/* Recognition is deliberately independent of identity and execution binding. */
int chaos_curio_tagged(const struct obj *);
int chaos_curio_matches(const struct obj *);
const char *chaos_curio_name(const struct obj *);
void chaos_curio_inspect(const struct obj *, char text[161]);
/* Every nonzero tag is handled, even when execution is forbidden. */
int chaos_curio_apply(struct obj *, int *move_result);
void chaos_curio_safe(int dir);
/* Transient generation capability: capture original ledger flags at remake. */
void chaos_curio_prepare(unsigned ledger_flags);
void chaos_curio_begin(void);
void chaos_curio_ordinary(void);
void chaos_curio_finish(int generated);
#else
#define chaos_curio_tagged(obj) 0
#define chaos_curio_apply(obj, move_result) 0
#define chaos_curio_safe(dir) ((void)0)
#define chaos_curio_prepare(flags) ((void)0)
#define chaos_curio_begin() ((void)0)
#define chaos_curio_ordinary() ((void)0)
#define chaos_curio_finish(generated) ((void)0)
#endif
#endif
