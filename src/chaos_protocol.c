/* NetHack General Public License; no allocations, RNG, engine globals or I/O.
 * Deliberately implements only the documented flat JSON sublanguage, not JSON
 * substring matching. Every byte and every token must be consumed and typed.
 */
#include "chaos_protocol.h"
#include <limits.h>
#include <string.h>

#if INT_MAX < CHAOS_MAX_INT
#error int cannot represent protocol integers
#endif
#define OBS_FAMILY(id, blocked, name) {id, blocked, name},
static const struct chaos_obs_family_info obs_families[] = { CHAOS_OBS_FAMILY_ROWS(OBS_FAMILY) };
#undef OBS_FAMILY
#define OBS_FACT(id, op, channel, blocked, name) {id, op, channel, blocked, name},
static const struct chaos_obs_fact_info obs_facts[] = { CHAOS_OBS_FACT_ROWS(OBS_FACT) };
#undef OBS_FACT
#define OBS_STAGE(id, role, name, phase) {id, role, name, phase},
static const struct chaos_obs_stage_info obs_stages[] = { CHAOS_OBS_STAGE_ROWS(OBS_STAGE) };
#undef OBS_STAGE
const struct chaos_obs_family_info *chaos_obs_family(int op) {
    size_t i;
    for (i = 0; i < sizeof obs_families / sizeof *obs_families; ++i)
        if (obs_families[i].id == op) return &obs_families[i];
    return 0;
}
const struct chaos_obs_fact_info *chaos_obs_fact(int op, int fact) {
    size_t i;
    for (i = 0; i < sizeof obs_facts / sizeof *obs_facts; ++i)
        if (obs_facts[i].id == fact && obs_facts[i].operation == op) return &obs_facts[i];
    return 0;
}
const struct chaos_obs_stage_info *chaos_obs_stage(int stage) {
    size_t i;
    for (i = 0; i < sizeof obs_stages / sizeof *obs_stages; ++i)
        if (obs_stages[i].id == stage) return &obs_stages[i];
    return 0;
}
const char *chaos_obs_operation_name(int op) {
    const struct chaos_obs_family_info *f = chaos_obs_family(op);
    return op == CHAOS_OBS_OP_NONE ? "none" : f ? f->name : 0;
}
const char *chaos_obs_fact_name(int fact) {
    size_t i;
    if (fact == CHAOS_OBS_FACT_NONE) return "none";
    for (i = 0; i < sizeof obs_facts / sizeof *obs_facts; ++i)
        if (obs_facts[i].id == fact) return obs_facts[i].name;
    return 0;
}
/* Row-local grammar only: engine/projector own root lifetime and chronology. */
int chaos_obs_row_valid(int op, int stage, long seq, long root, int fact) {
    const struct chaos_obs_family_info *f = chaos_obs_family(op);
    const struct chaos_obs_stage_info *s = chaos_obs_stage(stage);
    if (!s || seq <= 0 || seq > CHAOS_MAX_COUNTER || root < 0 || root > CHAOS_MAX_COUNTER) return 0;
    if (s->role == CHAOS_OBS_ROLE_ENABLE)
        return op == CHAOS_OBS_OP_NONE && !root && fact == CHAOS_OBS_FACT_NONE;
    if (!f) return 0;
    if (s->role == CHAOS_OBS_ROLE_START) return !root && fact == CHAOS_OBS_FACT_NONE;
    if (!root || root >= seq) return 0;
    if (s->role == CHAOS_OBS_ROLE_NOTICE) return chaos_obs_fact(op, fact) != 0;
    return fact == CHAOS_OBS_FACT_NONE && (s->role == CHAOS_OBS_ROLE_COMPLETE
        || (s->role == CHAOS_OBS_ROLE_BLOCK && f->allow_blocked));
}
struct mutation {
    const char *name;
    int cost, low, high, duration_low, duration_high, telegraph;
    int sanity_max, ordinary_food, persistent, rule;
};
#define MUTATION(k, name, cost, lo, hi, dlo, dhi, signal, sanity, food, active, rule) \
    {name, cost, lo, hi, dlo, dhi, signal, sanity, food, active, rule},
static const struct mutation mutations[] = { CHAOS_MUTATION_ROWS(MUTATION) };
#undef MUTATION
#define REASON(k, name, ack) name,
static const char *const reasons[] = { CHAOS_RESULT_ROWS(REASON) };
#undef REASON
const char *chaos_name(int k) { return k >= 0 && k < CHAOS_KINDS ? mutations[k].name : ""; }
const char *chaos_reason(int r) { return r >= 0 && r <= CHAOS_FUTURE ? reasons[r] : "schema"; }
int chaos_cost(int k) { return k >= 0 && k < CHAOS_KINDS ? mutations[k].cost : 0; }
struct cursor { const unsigned char *p, *end; };
static void ws(struct cursor *c) {
    while(c->p < c->end && (*c->p == ' ' || *c->p == '\r' || *c->p == '\n' || *c->p == '\t')) ++c->p;
}
static int take(struct cursor *c, int ch) {
    ws(c); if(c->p == c->end || *c->p != ch) return 0;
    ++c->p; return 1;
}
static int string(struct cursor *c, char *out, size_t cap) {
    size_t n = 0;
    if(!take(c, '"')) return 0;
    while(c->p < c->end && *c->p != '"') {
        unsigned char ch = *c->p++;
        if(!((ch >= 'a' && ch <= 'z') || ch == '_') || n + 1 >= cap) return 0;
        out[n++] = (char)ch;
    }
    if(c->p == c->end) return 0;
    ++c->p; out[n] = 0; return 1;
}
static int integer(struct cursor *c, int *out) {
    unsigned long n = 0;
    ws(c);
    if(c->p == c->end || *c->p < '0' || *c->p > '9') return 0;
    if(*c->p == '0' && c->p + 1 < c->end && c->p[1] >= '0' && c->p[1] <= '9') return 0;
    while(c->p < c->end && *c->p >= '0' && *c->p <= '9') {
        unsigned int d = *c->p++ - '0';
        if(n > ((unsigned long)CHAOS_MAX_INT - d) / 10) return 0;
        n = n * 10 + d;
    }
    *out = (int)n; return 1;
}
static int request_valid(const struct chaos_request *r) {
    const struct mutation *m;
    CHAOS_VALIDATE_FIELDS(r)
    if(r->kind < 0 || r->kind >= CHAOS_KINDS) return 0;
    m = &mutations[r->kind];
    return r->value >= m->low && r->value <= m->high &&
        r->duration >= m->duration_low && r->duration <= m->duration_high &&
        r->telegraph == m->telegraph;
}
int chaos_parse(const char *data, size_t n, struct chaos_request *r) {
    static const char *const keys[] = {CHAOS_FIELD_NAMES};
    struct cursor c;
    int fields[CHAOS_FIELD_COUNT] = {0}, i, seen = 0, k;
    char key[CHAOS_REQUEST_STRING_BUFFER], value[CHAOS_REQUEST_STRING_BUFFER];
    memset(r, 0, sizeof *r); r->kind = -1;
    if(n > CHAOS_MAX_REQUEST) return CHAOS_OVERSIZE;
    if(!n || memchr(data, 0, n)) return CHAOS_SCHEMA;
    c.p = (const unsigned char *)data; c.end = c.p + n;
    if(!take(&c, '{')) return CHAOS_SCHEMA;
    for(k = 0; k < CHAOS_FIELD_COUNT; ++k) {
        if(k && !take(&c, ',')) return CHAOS_SCHEMA;
        if(!string(&c,key,sizeof key) || !take(&c, ':')) return CHAOS_SCHEMA;
        for(i = 0; i < CHAOS_FIELD_COUNT && strcmp(key,keys[i]); ++i) {}
        if(i == CHAOS_FIELD_COUNT || (seen & (1 << i))) return CHAOS_SCHEMA;
        seen |= 1 << i;
        if(i == CHAOS_MUTATION_FIELD) {
            if(!string(&c,value,sizeof value)) return CHAOS_SCHEMA;
            for(fields[i] = 0; fields[i] < CHAOS_KINDS && strcmp(value,mutations[fields[i]].name); ++fields[i]) {}
        } else if(!integer(&c, &fields[i])) return CHAOS_SCHEMA;
    }
    if(seen != CHAOS_FIELD_MASK || !take(&c, '}')) return CHAOS_SCHEMA;
    ws(&c); if(c.p != c.end) return CHAOS_SCHEMA;
    CHAOS_ASSIGN_FIELDS(r, fields)
    if(!request_valid(r)) { memset(r, 0, sizeof *r); r->kind = -1; return CHAOS_SCHEMA; }
    return CHAOS_OK;
}
/* Byte-safe JSON output. Valid UTF-8 bytes are retained; engine call sites use
 * ASCII constants, test callers may supply UTF-8. Controls are always escaped. */
int chaos_quote(char *out, size_t cap, const char *src, size_t n) {
    static const char hex[] = "0123456789abcdef";
    size_t i, pos = 0;
    if(cap < 3) return 0;
    out[pos++] = '"';
    for(i = 0; i < n; ++i) {
        unsigned char ch = (unsigned char)src[i];
        size_t need = ch < 32 || ch == 127 ? 6 : ch == '"' || ch == '\\' ? 2 : 1;
        if(pos + need + 2 > cap) return 0;
        if(need == 6) {
            out[pos++] = '\\'; out[pos++] = 'u'; out[pos++] = '0'; out[pos++] = '0';
            out[pos++] = hex[ch >> 4]; out[pos++] = hex[ch & 15];
        } else {
            if(need == 2) out[pos++] = '\\';
            out[pos++] = (char)ch;
        }
    }
    out[pos++] = '"'; out[pos] = 0; return 1;
}
void chaos_state_init(struct chaos_state *s) { memset(s, 0, sizeof *s); s->version = CHAOS_STATE_VERSION; }
int chaos_state_valid(const struct chaos_state *s) {
    int i, reserved = 0;
    if(s->version != CHAOS_STATE_VERSION || s->spent < 0 || s->spent > CHAOS_BUDGET_CEILING ||
       s->last_id < 0 || s->safe < 0 || s->safe > CHAOS_MAX_COUNTER ||
       s->seq < 0 || s->seq > CHAOS_MAX_COUNTER) return 0;
    for(i = 0; i < CHAOS_KINDS; ++i) {
        const struct chaos_effect *e = &s->effects[i];
        if(e->value) {
            if(!mutations[i].persistent || e->value < mutations[i].low || e->value > mutations[i].high ||
               e->cost != chaos_cost(i) || e->expires < 1) return 0;
            reserved += e->cost;
        } else if(e->cost || e->expires) return 0;
    }
    return reserved == s->reserved && reserved <= s->spent;
}
int chaos_budget(const struct chaos_state *s, int sanity) {
    int n;
    if(sanity < CHAOS_BUDGET_SANITY_MIN) sanity = CHAOS_BUDGET_SANITY_MIN;
    if(sanity > CHAOS_BUDGET_SANITY_MAX) sanity = CHAOS_BUDGET_SANITY_MAX;
    n = CHAOS_BUDGET_BASE + (CHAOS_BUDGET_SANITY_MAX - sanity) / CHAOS_BUDGET_STEP - s->spent;
    return n > 0 ? n : 0;
}
int chaos_spend_non_effect(struct chaos_state *s, int sanity, int spender) {
    int cost;
    if(!s || !chaos_state_valid(s)) return CHAOS_SCHEMA;
    switch(spender) {
    case CHAOS_SPEND_CURIO: cost = CHAOS_COST_CURIO; break;
    case CHAOS_SPEND_HAUNT: cost = CHAOS_COST_HAUNT; break;
    default: return CHAOS_SCHEMA;
    }
    if(cost <= 0 || cost > CHAOS_BUDGET_CEILING) return CHAOS_SCHEMA;
    if(cost > chaos_budget(s, sanity) || cost > CHAOS_BUDGET_CEILING - s->spent)
        return CHAOS_BUDGET;
    s->spent += cost;
    return CHAOS_OK;
}
void chaos_expire(struct chaos_state *s, long turn) {
    int i;
    for(i = 1; i < CHAOS_KINDS; ++i) {
        struct chaos_effect *e = &s->effects[i];
        if(e->value && turn >= e->expires) {
            s->reserved -= e->cost; memset(e, 0, sizeof *e);
        }
    }
}
int chaos_admit(struct chaos_state *s, const struct chaos_request *r, long turn, int sanity, int eligible) {
    int cost;
    if(!request_valid(r)) return CHAOS_SCHEMA;
    if(r->id <= s->last_id) return CHAOS_DUPLICATE;
    if(r->at > s->safe) return CHAOS_FUTURE;
    s->last_id = r->id;
    if(r->at != s->safe) return CHAOS_SCHEDULE;
    chaos_expire(s,turn);
    if(!eligible || turn < 0 || turn > LONG_MAX - CHAOS_TURN_HEADROOM ||
       (mutations[r->kind].sanity_max >= 0 && sanity > mutations[r->kind].sanity_max) ||
       (mutations[r->kind].ordinary_food && eligible != 1)) return CHAOS_INELIGIBLE;
    if(s->effects[r->kind].value) return CHAOS_ACTIVE;
    cost = chaos_cost(r->kind);
    if(cost > chaos_budget(s,sanity)) return CHAOS_BUDGET;
    s->spent += cost;
    if(mutations[r->kind].persistent) {
        s->reserved += cost;
        s->effects[r->kind].value = r->value;
        s->effects[r->kind].cost = cost;
        s->effects[r->kind].expires = turn + r->duration;
    }
    return CHAOS_OK;
}
int chaos_rule(const struct chaos_state *s, int kind, long turn, int base) {
    const struct chaos_effect *e;
    if(kind < 0 || kind >= CHAOS_KINDS || !mutations[kind].persistent) return base;
    e = &s->effects[kind];
    if(!e->value || turn >= e->expires || base < 0) return base;
    if(mutations[kind].rule == CHAOS_RULE_HALVE) return base / 2;
    if(mutations[kind].rule == CHAOS_RULE_DOUBLE && base <= INT_MAX / 2) return base * 2;
    return base;
}
