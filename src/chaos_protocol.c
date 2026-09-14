/* NetHack General Public License; no allocations, RNG, engine globals or I/O.
 * Deliberately implements only the documented flat JSON sublanguage, not JSON
 * substring matching. Every byte and every token must be consumed and typed.
 */
#include "chaos_protocol.h"
#include <limits.h>
#include <string.h>

static const char *const names[] = {"ambient", "ward_efficacy", "hunger_rate"};
static const char *const reasons[] = {"ok", "schema", "oversize", "duplicate",
    "schedule", "budget", "active", "ineligible", "log_failure", "future"};
const char *chaos_name(int k) { return k >= 0 && k < CHAOS_KINDS ? names[k] : ""; }
const char *chaos_reason(int r) { return r >= 0 && r <= CHAOS_FUTURE ? reasons[r] : "schema"; }
int chaos_cost(int k) { return k == CHAOS_AMBIENT ? 1 : k == CHAOS_WARD ? 4 : k == CHAOS_HUNGER ? 3 : 0; }
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
        if(n > (2147483647UL - d) / 10) return 0;
        n = n * 10 + d;
    }
    *out = (int)n; return 1;
}
static int request_valid(const struct chaos_request *r) {
    if(r->v != 1 || r->id < 1 || r->at < 1 || r->kind < 0 || r->kind >= CHAOS_KINDS) return 0;
    if(r->kind == CHAOS_AMBIENT)
        return r->value >= 1 && r->value <= 3 && r->duration == 0 && r->telegraph == 1;
    return r->duration >= 1 && r->duration <= 50 &&
        (r->kind == CHAOS_WARD ? r->value == 50 && r->telegraph == 2 : r->value == 2 && r->telegraph == 3);
}
int chaos_parse(const char *data, size_t n, struct chaos_request *r) {
    static const char *const keys[] = {"v","id","mutation","value","duration","telegraph","at"};
    struct cursor c;
    int fields[7] = {0}, i, seen = 0, k;
    char key[24], value[24];
    memset(r, 0, sizeof *r); r->kind = -1;
    if(n > CHAOS_MAX_REQUEST) return CHAOS_OVERSIZE;
    if(!n || memchr(data, 0, n)) return CHAOS_SCHEMA;
    c.p = (const unsigned char *)data; c.end = c.p + n;
    if(!take(&c, '{')) return CHAOS_SCHEMA;
    for(k = 0; k < 7; ++k) {
        if(k && !take(&c, ',')) return CHAOS_SCHEMA;
        if(!string(&c,key,sizeof key) || !take(&c, ':')) return CHAOS_SCHEMA;
        for(i = 0; i < 7 && strcmp(key,keys[i]); ++i) {}
        if(i == 7 || (seen & (1 << i))) return CHAOS_SCHEMA;
        seen |= 1 << i;
        if(i == 2) {
            if(!string(&c,value,sizeof value)) return CHAOS_SCHEMA;
            for(fields[i] = 0; fields[i] < CHAOS_KINDS && strcmp(value,names[fields[i]]); ++fields[i]) {}
        } else if(!integer(&c, &fields[i])) return CHAOS_SCHEMA;
    }
    if(seen != 127 || !take(&c, '}')) return CHAOS_SCHEMA;
    ws(&c); if(c.p != c.end) return CHAOS_SCHEMA;
    r->v = fields[0]; r->id = fields[1]; r->kind = fields[2]; r->value = fields[3];
    r->duration = fields[4]; r->telegraph = fields[5]; r->at = fields[6];
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
    if(s->version != CHAOS_STATE_VERSION || s->spent < 0 || s->spent > 12 ||
       s->last_id < 0 || s->safe < 0 || s->safe > CHAOS_MAX_COUNTER ||
       s->seq < 0 || s->seq > CHAOS_MAX_COUNTER) return 0;
    for(i = 0; i < CHAOS_KINDS; ++i) {
        const struct chaos_effect *e = &s->effects[i];
        if(e->value) {
            if(i == CHAOS_AMBIENT || e->value != (i == CHAOS_WARD ? 50 : 2) ||
               e->cost != chaos_cost(i) || e->expires < 1) return 0;
            reserved += e->cost;
        } else if(e->cost || e->expires) return 0;
    }
    return reserved == s->reserved && reserved <= s->spent;
}
int chaos_budget(const struct chaos_state *s, int sanity) {
    int n;
    if(sanity < 0) sanity = 0;
    if(sanity > 100) sanity = 100;
    n = 2 + (100 - sanity) / 10 - s->spent;
    return n > 0 ? n : 0;
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
    if(!eligible || turn < 0 || turn > LONG_MAX - 50 ||
       (r->kind == CHAOS_WARD && sanity > 80) ||
       (r->kind == CHAOS_HUNGER && (sanity > 90 || eligible != 1))) return CHAOS_INELIGIBLE;
    if(s->effects[r->kind].value) return CHAOS_ACTIVE;
    cost = chaos_cost(r->kind);
    if(cost > chaos_budget(s,sanity)) return CHAOS_BUDGET;
    s->spent += cost;
    if(r->kind != CHAOS_AMBIENT) {
        s->reserved += cost;
        s->effects[r->kind].value = r->value;
        s->effects[r->kind].cost = cost;
        s->effects[r->kind].expires = turn + r->duration;
    }
    return CHAOS_OK;
}
int chaos_rule(const struct chaos_state *s, int kind, long turn, int base) {
    const struct chaos_effect *e;
    if(kind <= CHAOS_AMBIENT || kind >= CHAOS_KINDS) return base;
    e = &s->effects[kind];
    if(!e->value || turn >= e->expires || base < 0) return base;
    if(kind == CHAOS_WARD) return base / 2;
    return base <= INT_MAX / 2 ? base * 2 : base;
}
