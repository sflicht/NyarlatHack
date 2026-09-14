/* NetHack General Public License - bounded, engine-independent protocol v1. */
#ifndef CHAOS_PROTOCOL_H
#define CHAOS_PROTOCOL_H
#include <stddef.h>
#define CHAOS_MAX_REQUEST 512
#define CHAOS_STATE_VERSION 1
#define CHAOS_MAX_COUNTER 2147483647L
enum chaos_kind { CHAOS_AMBIENT, CHAOS_WARD, CHAOS_HUNGER, CHAOS_KINDS };
enum chaos_result { CHAOS_OK, CHAOS_SCHEMA, CHAOS_OVERSIZE, CHAOS_DUPLICATE,
    CHAOS_SCHEDULE, CHAOS_BUDGET, CHAOS_ACTIVE, CHAOS_INELIGIBLE,
    CHAOS_LOG_FAILURE, CHAOS_FUTURE };
struct chaos_request { int v, id, kind, value, duration, telegraph, at; };
struct chaos_effect { int value, cost; long expires; };
struct chaos_state {
    int version, spent, reserved, last_id;
    long seq, safe;
    struct chaos_effect effects[CHAOS_KINDS];
};
int chaos_parse(const char *, size_t, struct chaos_request *);
const char *chaos_reason(int);
const char *chaos_name(int);
int chaos_cost(int);
int chaos_quote(char *, size_t, const char *, size_t);
void chaos_state_init(struct chaos_state *);
int chaos_state_valid(const struct chaos_state *);
int chaos_budget(const struct chaos_state *, int);
void chaos_expire(struct chaos_state *, long);
/* eligibility: 0 unconscious/dead, 1 ordinary food, 2 conscious non-food. */
int chaos_admit(struct chaos_state *, const struct chaos_request *, long, int, int);
int chaos_rule(const struct chaos_state *, int, long, int);
#endif
