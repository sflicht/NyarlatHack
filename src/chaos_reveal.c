/* NetHack General Public License. Post-mortem reveal core: bounded reads of
 * engine-owned records, no RNG, no game state. See include/chaos_reveal.h. */
#define _POSIX_C_SOURCE 200809L
#include "chaos_reveal.h"
#include "chaos_protocol.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

void chaos_reveal_init(struct chaos_reveal *r, long final_turn, int spent)
{
    memset(r, 0, sizeof *r);
    r->final_turn = final_turn;
    r->spent = spent;
}

/* ---- top-level JSON field lookup (engine rows are flat, fixed-format) ---- */
static const char *skip_string(const char *p)
{
    if (*p != '"') return 0;
    for (++p; *p; ++p) {
        if (*p == '\\') { if (!*++p) return 0; }
        else if (*p == '"') return p + 1;
    }
    return 0;
}
static const char *skip_value(const char *p)
{
    int depth = 0;
    if (*p == '"') return skip_string(p);
    for (; *p; ++p) {
        if (*p == '"') { p = skip_string(p); if (!p) return 0; --p; }
        else if (*p == '{' || *p == '[') ++depth;
        else if (*p == '}' || *p == ']') { if (!depth) return p; if (!--depth) return p + 1; }
        else if (*p == ',' && !depth) return p;
    }
    return depth ? 0 : p;
}
/* Value start for a top-level key, never a key nested in an object/string. */
static const char *field(const char *line, const char *key)
{
    const char *p = line, *k;
    size_t n = strlen(key);
    if (*p++ != '{') return 0;
    while (*p == '"') {
        k = p + 1;
        p = skip_string(p);
        if (!p || *p != ':') return 0;
        if ((size_t)(p - 1 - k) == n && !memcmp(k, key, n)) return p + 1;
        p = skip_value(p + 1);
        if (!p) return 0;
        if (*p == ',') ++p;
        else break;
    }
    return 0;
}
static int get_long(const char *line, const char *key, long *out)
{
    const char *v = field(line, key);
    char *end;
    long x;
    if (!v || (*v != '-' && (*v < '0' || *v > '9'))) return 0;
    errno = 0;
    x = strtol(v, &end, 10);
    if (errno || end == v || (*end != ',' && *end != '}')) return 0;
    *out = x;
    return 1;
}
static int get_int(const char *line, const char *key, int *out)
{
    long x;
    if (!get_long(line, key, &x) || x < INT_MIN || x > INT_MAX) return 0;
    *out = (int)x;
    return 1;
}
/* Exact match against a plain (escape-free) engine string value. */
static int is_str(const char *line, const char *key, const char *want)
{
    const char *v = field(line, key);
    size_t n = strlen(want);
    return v && *v == '"' && !strncmp(v + 1, want, n) && v[n + 1] == '"';
}
static int get_str(const char *line, const char *key, char *out, size_t cap)
{
    const char *v = field(line, key), *e;
    if (!v || *v != '"' || !(e = skip_string(v))) return 0;
    if ((size_t)(e - v - 2) >= cap || memchr(v + 1, '\\', (size_t)(e - v - 2))) return 0;
    memcpy(out, v + 1, (size_t)(e - v - 2));
    out[e - v - 2] = 0;
    return 1;
}
static int mutation_kind(const char *line)
{
#define KIND(id, name, ...) if (is_str(line, "mutation", name)) return id;
    CHAOS_MUTATION_ROWS(KIND)
#undef KIND
    return -1;
}

static struct chaos_reveal_entry *add(struct chaos_reveal *r, int kind, long turn)
{
    struct chaos_reveal_entry *e;
    if (r->count >= CHAOS_REVEAL_MAX) { ++r->overflow; return 0; }
    e = &r->e[r->count++];
    memset(e, 0, sizeof *e);
    e->kind = kind;
    e->turn = turn;
    return e;
}
static struct chaos_reveal_entry *latest(struct chaos_reveal *r, int kind)
{
    int i;
    for (i = r->count - 1; i >= 0; --i)
        if (r->e[i].kind == kind) return &r->e[i];
    return 0;
}

/* whispers.jsonl: written before the telegraph, so it is NOT admission alone. */
void chaos_reveal_journal_line(struct chaos_reveal *r, const char *line)
{
    int id, kind;
    long turn, safe;
    if (!is_str(line, "status", CHAOS_STATUS_ADMITTED) || !get_int(line, "id", &id)
        || !get_long(line, "turn", &turn) || !get_long(line, "safe", &safe)
        || (kind = mutation_kind(line)) < 0 || r->journal_count >= CHAOS_REVEAL_JOURNAL)
        return;
    r->journal[r->journal_count].id = id;
    r->journal[r->journal_count].mutation = kind;
    r->journal[r->journal_count].turn = turn;
    r->journal[r->journal_count].safe = safe;
    ++r->journal_count;
}

/* The acknowledgement shares its journal row's turn and safe-point index. */
static int journaled(const struct chaos_reveal *r, int id, int kind, long turn, long safe)
{
    int i;
    for (i = 0; i < r->journal_count; ++i)
        if (r->journal[i].id == id && r->journal[i].mutation == kind
            && r->journal[i].turn == turn && r->journal[i].safe == safe) return 1;
    return 0;
}

static void ack(struct chaos_reveal *r, const char *line, long turn)
{
    struct chaos_reveal_entry *e;
    int id, kind;
    long expires = 0, safe = -1;
    if (!is_str(line, "status", CHAOS_STATUS_ACCEPTED)) {
        /* The same mailbox file re-read at a later safe point is acknowledged
         * as a duplicate of an admitted whisper: not another candidate. */
        if (is_str(line, "detail", "duplicate") && get_int(line, "id", &id)) {
            int i;
            for (i = 0; i < r->count; ++i)
                if (r->e[i].kind == CHAOS_REVEAL_WHISPER && r->e[i].id == id) return;
        }
        ++r->rejected;
        return;
    }
    /* Final engine acknowledgement, bound to the admitted journal row. */
    if (!get_int(line, "id", &id) || (kind = mutation_kind(line)) < 0
        || !get_long(line, "safe", &safe) || !journaled(r, id, kind, turn, safe)) {
        ++r->rejected;
        return;
    }
    if (!(e = add(r, CHAOS_REVEAL_WHISPER, turn))) return;
    e->id = id;
    e->mutation = kind;
    (void)get_int(line, "value", &e->value);
    (void)get_int(line, "duration", &e->duration);
    (void)get_int(line, "telegraph", &e->telegraph);
    (void)get_int(line, "cost", &e->cost);
    (void)get_long(line, "expires", &expires);
    e->expires = expires;
    memcpy(e->why, r->last_why, sizeof e->why);
}

static void expiry(struct chaos_reveal *r, const char *line, long turn)
{
    int i;
    for (i = r->count - 1; i >= 0; --i) {
        struct chaos_reveal_entry *e = &r->e[i];
        if (e->kind == CHAOS_REVEAL_WHISPER && !e->ended
            && e->mutation >= 0 && e->mutation < CHAOS_KINDS
            && is_str(line, "detail", chaos_name(e->mutation))) {
            e->ended = 1;
            e->end_turn = turn;
            return;
        }
    }
}

static void curio(struct chaos_reveal *r, const char *line, long turn)
{
    struct chaos_reveal_entry *e = latest(r, CHAOS_REVEAL_CURIO);
    char detail[80];
    int requested, actual;
    if (!get_str(line, "detail", detail, sizeof detail)) return;
    if (!strcmp(detail, CHAOS_STATUS_ADMITTED)) { (void)add(r, CHAOS_REVEAL_CURIO, turn); return; }
    if (!strcmp(detail, CHAOS_STATUS_REJECTED)) { ++r->rejected; return; }
    if (!e) return;  /* expiry of a never-admitted opportunity is not a fact to narrate */
    if (!strcmp(detail, "placed") && e->placement == CHAOS_REVEAL_UNPLACED) {
        e->placement = CHAOS_REVEAL_PLACED; e->placed_turn = turn;
    } else if (!strcmp(detail, "placement_unavailable") && e->placement == CHAOS_REVEAL_UNPLACED) {
        e->placement = CHAOS_REVEAL_NO_ROOM;
    } else if (!strcmp(detail, "placement_failed") && e->placement != CHAOS_REVEAL_PLACED) {
        e->placement = CHAOS_REVEAL_PLACE_FAILED; e->ended = 1; e->end_turn = turn;
    } else if (!strcmp(detail, "expired") && e->placement != CHAOS_REVEAL_PLACED && !e->ended) {
        e->ended = 1; e->end_turn = turn;
    } else if (sscanf(detail, "applied requested=%d actual=%d", &requested, &actual) == 2
               && e->placement == CHAOS_REVEAL_PLACED) {
        ++e->uses; e->actual += actual;
    }
}

static void haunting(struct chaos_reveal *r, const char *line, long turn)
{
    struct chaos_reveal_entry *e;
    if (is_str(line, "detail", CHAOS_STATUS_ACCEPTED)) {
        if ((e = add(r, CHAOS_REVEAL_HAUNT, turn))) e->cost = CHAOS_COST_HAUNT;
        /* A budget refusal is not final: nothing is consumed, so the same
         * candidate may be admitted once the budget grows. Then it was not
         * refused after all. */
        if (r->haunt_budget_seen == 1) { --r->rejected; r->haunt_budget_seen = 2; }
    } else if (is_str(line, "detail", CHAOS_STATUS_REJECTED)
               || is_str(line, "detail", "source_rejected")
               || is_str(line, "detail", "shadow_failed")
               || is_str(line, "detail", "spawn_failed")) {
        ++r->rejected;
    } else if (is_str(line, "detail", "budget")) {
        /* #165: a candidate refused because another spender was admitted
         * first; a count, never a narrated haunting. The engine's once-only
         * guard is per process, so each restore may log it again: it is
         * still the same one candidate. */
        if (!r->haunt_budget_seen) {
            r->haunt_budget_seen = 1;
            ++r->rejected;
        }
    } else if (is_str(line, "detail", "expired")) {
        /* #165: the engine's lifecycle end (timeout or leaving the level)
         * closes the latest still-open admitted haunt; nothing else. */
        if ((e = latest(r, CHAOS_REVEAL_HAUNT)) && !e->ended) {
            e->ended = 1;
            e->end_turn = turn;
        }
    }
}

/* A "started" observation row is the root every next-use origin names. */
static void observation(struct chaos_reveal *r, const char *line, long turn)
{
    const char *o = field(line, "observation");
    long seq;
    int fountain;
    if (!o || *o != '{' || !get_long(line, "seq", &seq) || !is_str(o, "stage", "started"))
        return;
    if (is_str(o, "operation", "whistling")) fountain = 0;
    else if (is_str(o, "operation", "fountain_drink")) fountain = 1;
    else return;
    if (r->origin_count >= CHAOS_REVEAL_ORIGINS) {
        /* Keep the most recent roots: origins are bounded in lifetime. */
        memmove(&r->origin[0], &r->origin[1], sizeof r->origin[0] * (CHAOS_REVEAL_ORIGINS - 1));
        --r->origin_count;
    }
    r->origin[r->origin_count].seq = seq;
    r->origin[r->origin_count].turn = turn;
    r->origin[r->origin_count].fountain = fountain;
    ++r->origin_count;
}

void chaos_reveal_event_line(struct chaos_reveal *r, const char *line)
{
    long turn = 0;
    struct chaos_reveal_entry *e;
    (void)get_long(line, "turn", &turn);
    if (is_str(line, "event", CHAOS_EVENT_SESSION) && is_str(line, "detail", "new")) {
        /* A fresh game starts its own record; never inherit another game's rows. */
        r->count = r->overflow = r->rejected = 0;
        r->origin_count = 0;
        r->haunt_budget_seen = 0;
        r->last_why[0] = 0;
    } else if (is_str(line, "event", CHAOS_EVENT_SAFE_POINT)) {
        if (!get_str(line, "detail", r->last_why, sizeof r->last_why)) r->last_why[0] = 0;
    } else if (is_str(line, "event", CHAOS_EVENT_ACK)) {
        ack(r, line, turn);
    } else if (is_str(line, "event", CHAOS_EVENT_EXPIRY)) {
        expiry(r, line, turn);
    } else if (is_str(line, "event", CHAOS_EVENT_CURIO)) {
        curio(r, line, turn);
    } else if (is_str(line, "event", CHAOS_EVENT_HAUNTING)) {
        haunting(r, line, turn);
    } else if (is_str(line, "event", CHAOS_EVENT_HAUNT_STEP)) {
        /* Emitted only for a committed scripted step the player could see. */
        if ((e = latest(r, CHAOS_REVEAL_HAUNT))) ++e->steps;
    } else if (is_str(line, "event", "observation")) {
        observation(r, line, turn);
    }
}

/* next_use-receipt.jsonl: kind 2 is the engine's admission receipt. Its
 * "origins" list (when present) names the published and bound origin root
 * per family; a decision row records a refused next-use candidate. */
void chaos_reveal_receipt_line(struct chaos_reveal *r, const char *line)
{
    const char *o, *p;
    int kind, n = 0, ordinal = 0;
    long published, bound;
    if (is_str(line, "decision", "rejected")) { ++r->receipt_rejected; return; }
    if (!get_int(line, "kind", &kind) || kind != 2) return;
    r->receipt_ops = 0;
    if (get_int(line, "program_ordinal", &ordinal)
        && (ordinal < 1 || ordinal > CHAOS_REVEAL_PROGRAMS)) ordinal = 0;
    r->receipt_by_ops[ordinal] = 0;
    if (!(o = field(line, "origins")) || *o != '[') return;
    for (p = o + 1; *p == '{' && n < 2; ++n) {
        const char *end = skip_value(p);
        int fountain;
        if (!end) return;
        if (is_str(p, "family", "W")) fountain = 0;
        else if (is_str(p, "family", "F")) fountain = 1;
        else return;
        if (!get_long(p, "published", &published) || !get_long(p, "bound", &bound)) return;
        r->receipt[n].fountain = fountain;
        r->receipt[n].published = published;
        r->receipt[n].bound = bound;
        r->receipt_by[ordinal][n].fountain = fountain;
        r->receipt_by[ordinal][n].published = published;
        r->receipt_by[ordinal][n].bound = bound;
        p = end;
        if (*p == ',') ++p;
    }
    r->receipt_ops = n;
    r->receipt_by_ops[ordinal] = n;
}

/* Same ownership/no-follow rule as chaos_io.c; bounded bytes and line size. */
static int read_lines(struct chaos_reveal *r, int dir, const char *name,
                      void (*fn)(struct chaos_reveal *, const char *))
{
    char buf[4096], line[CHAOS_REVEAL_LINE];
    size_t used = 0;
    long total = 0;
    int fd, skipping = 0;
    ssize_t n, i;
    struct stat st;
    fd = openat(dir, name, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0) return errno == ENOENT;
    if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_uid != getuid() || st.st_nlink != 1) {
        close(fd);
        return 0;
    }
    for (;;) {
        n = read(fd, buf, sizeof buf);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) break;
        if ((total += n) > CHAOS_REVEAL_BYTES_MAX) { r->truncated = 1; break; }
        for (i = 0; i < n; ++i) {
            if (buf[i] == '\n') {
                if (!skipping) { line[used] = 0; fn(r, line); }
                used = 0; skipping = 0;
            } else if (skipping) {
                continue;
            } else if (used + 1 >= sizeof line || !buf[i]) {
                skipping = 1;  /* never a row the engine writes; ignore */
            } else {
                line[used++] = buf[i];
            }
        }
    }
    close(fd);
    return n >= 0;
}

int chaos_reveal_read(struct chaos_reveal *r, int dir)
{
    int ok;
    if (dir < 0) return 0;
    ok = read_lines(r, dir, "whispers.jsonl", chaos_reveal_journal_line);
    ok = read_lines(r, dir, "events.jsonl", chaos_reveal_event_line) && ok;
    return read_lines(r, dir, "next_use-receipt.jsonl", chaos_reveal_receipt_line) && ok;
}

/* The program an entry describes: the live one, or a closed earlier one. */
static const struct chaos_reveal_next_use *program_of(const struct chaos_reveal_entry *e,
                                                      const struct chaos_reveal_host *h)
{
    return e->program > 0 && e->program <= h->prior_count ? &h->prior[e->program - 1]
                                                          : &h->nu;
}

static int nu_w(const struct chaos_reveal_next_use *nu)
{
    return nu->slot_w != CHAOS_REVEAL_W_UNDECLARED;
}
static int nu_f(const struct chaos_reveal_next_use *nu)
{
    return nu->slot_f != CHAOS_REVEAL_F_UNDECLARED;
}
static int nu_felt_w(const struct chaos_reveal_next_use *nu) { return nu->witnessed != 0; }
static int nu_felt_f(const struct chaos_reveal_next_use *nu)
{
    return nu->slot_f == CHAOS_REVEAL_F_CONSUMED_APPLIED;
}

static int delivered(const struct chaos_reveal_entry *e, const struct chaos_reveal_host *h)
{
    const struct chaos_reveal_next_use *nu;
    switch (e->kind) {
    case CHAOS_REVEAL_WHISPER: return e->mutation == CHAOS_AMBIENT;
    case CHAOS_REVEAL_CURIO: return e->uses > 0;
    case CHAOS_REVEAL_HAUNT: return e->steps > 0;
    case CHAOS_REVEAL_NEXT_USE:
        nu = program_of(e, h);
        return nu_felt_w(nu) || nu_felt_f(nu);
    }
    return 0;
}

void chaos_reveal_finish(struct chaos_reveal *r)
{
    struct chaos_reveal_entry tmp, *e;
    int i, j;
    if (r->host.prior_count < 0) r->host.prior_count = 0;
    if (r->host.prior_count > CHAOS_REVEAL_PROGRAMS - 1)
        r->host.prior_count = CHAOS_REVEAL_PROGRAMS - 1;
    for (i = 0; i < r->host.prior_count; ++i)
        if (r->host.prior[i].present
            && (e = add(r, CHAOS_REVEAL_NEXT_USE, r->host.prior[i].admission_move)))
            e->program = i + 1;
    if (r->host.nu.present)
        (void)add(r, CHAOS_REVEAL_NEXT_USE, r->host.nu.admission_move);
    /* A refused next-use candidate is one count: the receipt's recorded
     * decision rows when present, otherwise the engine's last attempt. */
    r->rejected += r->receipt_rejected ? r->receipt_rejected
                                       : r->host.next_use_last_rejected != 0;
    for (i = 1; i < r->count; ++i)  /* stable chronological order */
        for (j = i; j > 0 && r->e[j - 1].turn > r->e[j].turn; --j) {
            tmp = r->e[j]; r->e[j] = r->e[j - 1]; r->e[j - 1] = tmp;
        }
    r->admitted = r->count + r->overflow;
    r->delivered = 0;
    for (i = 0; i < r->count; ++i)
        r->delivered += delivered(&r->e[i], &r->host);
}

/* ---- rendering: engine wording only; nothing proposed is narrated ---- */
static const char *signal_text(int telegraph)
{
#define TEXT(id, text) if (telegraph == id) return text;
    CHAOS_SIGNAL_ROWS(TEXT)
#undef TEXT
    return 0;
}
static const char *ambient_text(int value)
{
#define TEXT(id, text) if (value == id) return text;
    CHAOS_AMBIENT_MESSAGE_ROWS(TEXT)
#undef TEXT
    return 0;
}
static const char *why_text(const char *why)
{
    if (!strcmp(why, "level_enter")) return "as you arrived on a level";
    if (!strcmp(why, "pray")) return "as you prayed";
    if (!strcmp(why, "sleep")) return "as you slept";
    if (!strcmp(why, "sanity_threshold")) return "as your Sanity crossed a threshold";
    return "at a safe point";
}

static void out(chaos_reveal_emit emit, void *arg, const char *fmt, ...)
    __attribute__((format(printf, 3, 4)));
static void out(chaos_reveal_emit emit, void *arg, const char *fmt, ...)
{
    char line[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    emit(arg, line);
}

static void whisper(const struct chaos_reveal_entry *e, chaos_reveal_emit emit, void *arg)
{
    const char *signal = signal_text(e->telegraph), *ambient = ambient_text(e->value);
    out(emit, arg, "  Turn %ld, %s: whisper %d (%s) was admitted.",
        e->turn, why_text(e->why), e->id, chaos_name(e->mutation));
    out(emit, arg, "    Telegraph: \"%s\"", signal ? signal : "(unknown)");
    if (e->mutation == CHAOS_AMBIENT) {
        out(emit, arg, "    Effect: an omen only; no rule changed.");
        out(emit, arg, "    Delivered: yes, \"%s\" was shown with the telegraph.",
            ambient ? ambient : "(unknown)");
        out(emit, arg, "    Spent at once.");
        return;
    }
    if (e->mutation == CHAOS_WARD)
        out(emit, arg, "    Effect: your wards counted for half, for %d turns.", e->duration);
    else if (e->mutation == CHAOS_DOOR)
        out(emit, arg, "    Effect: closed doors resisted you more often, for %d turns.", e->duration);
    else
        out(emit, arg, "    Effect: you grew hungry twice as fast, for %d turns.", e->duration);
    out(emit, arg, "    Delivered: no; a rule change has no separate manifestation.");
    if (e->ended)
        out(emit, arg, "    Ended: expired on turn %ld.", e->end_turn);
    else
        out(emit, arg, "    Ended: still in force when the game ended (due turn %ld).",
            e->expires);
}

static void curio_entry(const struct chaos_reveal_entry *e, const struct chaos_reveal_host *h,
                        chaos_reveal_emit emit, void *arg)
{
    out(emit, arg, "  Turn %ld: a curio was admitted.", e->turn);
    out(emit, arg, "    Telegraph: \"An uncanny curio may appear on a later floor.\"");
    switch (e->placement) {
    case CHAOS_REVEAL_PLACED:
        out(emit, arg, "    Effect: a curio whistle was placed on a new level on turn %ld.",
            e->placed_turn);
        break;
    case CHAOS_REVEAL_NO_ROOM:
        out(emit, arg, "    Effect: no level had room for it.");
        break;
    case CHAOS_REVEAL_PLACE_FAILED:
        out(emit, arg, "    Effect: placement failed; nothing appeared.");
        break;
    default:
        out(emit, arg, "    Effect: it was never placed.");
    }
    if (e->uses)
        out(emit, arg, "    Delivered: yes, you applied it %d time%s (Sanity %+d in total).",
            e->uses, e->uses == 1 ? "" : "s", e->actual);
    else
        out(emit, arg, "    Delivered: no; you never applied it.");
    if (e->ended)
        out(emit, arg, "    Ended: retired unplaced on turn %ld.", e->end_turn);
    else if (e->placement == CHAOS_REVEAL_PLACED && h->curio_placed)
        out(emit, arg, "    Ended: %d use%s left when the game ended.",
            h->curio_charges, h->curio_charges == 1 ? "" : "s");
    else
        out(emit, arg, "    Ended: still pending when the game ended.");
}

static void haunt_entry(const struct chaos_reveal_entry *e, const struct chaos_reveal *r,
                        chaos_reveal_emit emit, void *arg)
{
    const struct chaos_reveal_host *h = &r->host;
    out(emit, arg, "  Turn %ld, after you doubled back: a haunting was admitted.", e->turn);
    out(emit, arg, "    Telegraph: \"Something has learned the rhythm of your footsteps.\"");
    out(emit, arg, "    Effect: an echo hound was set to follow your trail.");
    if (e->steps)
        out(emit, arg, "    Delivered: yes, you saw it follow your trail %d time%s.",
            e->steps, e->steps == 1 ? "" : "s");
    else
        out(emit, arg, "    Delivered: no; you never saw it follow your trail.");
    if (e->ended)
        out(emit, arg, "    Ended: its hunt ended on turn %ld.", e->end_turn);
    else if (h->haunt_active && r->final_turn < h->haunt_until)
        out(emit, arg, "    Ended: still hunting when the game ended.");
    else
        out(emit, arg, "    Ended: its hunt was over by the end (due turn %ld).",
            h->haunt_until);
}

static const char *w_outcome(int slot)
{
    switch (slot) {
    case CHAOS_REVEAL_W_PENDING: return "it was still waiting for your next whistle";
    case CHAOS_REVEAL_W_CONSUMED_ARMED: return "your next whistle armed it";
    case CHAOS_REVEAL_W_CONSUMED_QUIET: return "at your next whistle it chose to stay quiet";
    case CHAOS_REVEAL_W_CONSUMED_DELAY: return "at your next whistle it chose to wait";
    case CHAOS_REVEAL_W_CONSUMED_INVALID: return "its program failed at your next whistle; nothing changed";
    case CHAOS_REVEAL_W_CONSUMED_SUPPRESSED: return "a guard suppressed it at your next whistle; nothing changed";
    case CHAOS_REVEAL_W_TERMINATED_EXPIRY: return "it expired before you whistled again";
    case CHAOS_REVEAL_W_TERMINATED_LEVEL: return "it ended when you left the level";
    case CHAOS_REVEAL_W_TERMINATED_TRANSPORT: return "it ended when its record could not be written";
    }
    return 0;
}

static const char *f_outcome(int slot)
{
    switch (slot) {
    case CHAOS_REVEAL_F_PENDING: return "it was still waiting for your next fountain drink";
    case CHAOS_REVEAL_F_CONSUMED_APPLIED: return "your next fountain drink was turned into a refreshing one";
    case CHAOS_REVEAL_F_CONSUMED_NONREMAPPABLE: return "your next fountain drink took its native course";
    case CHAOS_REVEAL_F_CONSUMED_QUIET: return "at your next fountain drink it chose to stay quiet";
    case CHAOS_REVEAL_F_CONSUMED_DELAY: return "at your next fountain drink it chose to wait";
    case CHAOS_REVEAL_F_CONSUMED_INVALID: return "its program failed at your next fountain drink; nothing changed";
    case CHAOS_REVEAL_F_CONSUMED_SUPPRESSED: return "a guard suppressed it at your next fountain drink; nothing changed";
    case CHAOS_REVEAL_F_TERMINATED_EXPIRY: return "it expired before you drank again";
    case CHAOS_REVEAL_F_TERMINATED_LEVEL: return "it ended when you left the level";
    case CHAOS_REVEAL_F_TERMINATED_TRANSPORT: return "it ended when its record could not be written";
    }
    return 0;
}

/* The engine's "started" row for an origin root, or 0. */
static int origin_turn(const struct chaos_reveal *r, long root, int fountain, long *turn)
{
    int i;
    for (i = r->origin_count - 1; i >= 0; --i)
        if (r->origin[i].seq == root && r->origin[i].fountain == fountain) {
            *turn = r->origin[i].turn;
            return 1;
        }
    return 0;
}

static void origin_line(const struct chaos_reveal *r, const struct chaos_reveal_next_use *nu,
                        int fountain, long root, chaos_reveal_emit emit, void *arg)
{
    const char *act = fountain ? "you drank from a fountain" : "you whistled";
    char where[24];
    long turn, published = 0;
    int i, rebound = 0, k = nu->ordinal;
    if (nu->depth > 0) snprintf(where, sizeof where, " on DL%d", nu->depth);
    else where[0] = 0;
    if (k >= 1 && k <= CHAOS_REVEAL_PROGRAMS && r->receipt_by_ops[k]) {
        for (i = 0; i < r->receipt_by_ops[k]; ++i)
            if (r->receipt_by[k][i].fountain == fountain && r->receipt_by[k][i].bound == root
                && r->receipt_by[k][i].published != root) {
                rebound = 1;
                published = r->receipt_by[k][i].published;
            }
    } else if (k <= 1 || !r->host.prior_count) {
        for (i = 0; i < r->receipt_ops; ++i)
            if (r->receipt[i].fountain == fountain && r->receipt[i].bound == root
                && r->receipt[i].published != root) {
                rebound = 1;
                published = r->receipt[i].published;
            }
    }
    if (origin_turn(r, root, fountain, &turn))
        out(emit, arg, "    Origin: %s%s on turn %ld.", act, where, turn);
    else
        out(emit, arg, "    Origin: %s%s (record %ld).", act, where, root);
    if (rebound) {
        /* #177: the model wrote about the published origin; the engine bound
         * the program to a newer one. Both are engine records. */
        if (origin_turn(r, published, fountain, &turn))
            out(emit, arg, "    Rebound: first written about an earlier one (turn %ld).", turn);
        else
            out(emit, arg, "    Rebound: first written about an earlier one.");
    }
}

/* Arc 1, mirroring the engine's admission rule: the recurrence line fired for
 * program k when an earlier closed program of the game delivered that family. */
static int felt_before(const struct chaos_reveal_host *h, int program, int fountain)
{
    int k, last = program > 0 ? program - 1 : h->prior_count;
    for (k = 0; k < last && k < h->prior_count; ++k)
        if (h->prior[k].present
            && (fountain ? nu_felt_f(&h->prior[k]) : nu_felt_w(&h->prior[k])))
            return 1;
    return 0;
}

static void next_use_entry(const struct chaos_reveal_entry *e, const struct chaos_reveal *r,
                           chaos_reveal_emit emit, void *arg)
{
    const struct chaos_reveal_next_use *nu = program_of(e, &r->host);
    const char *w = nu_w(nu) ? w_outcome(nu->slot_w) : 0;
    const char *f = nu_f(nu) ? f_outcome(nu->slot_f) : 0;
    const char *telegraph = w && f ? "The next whistle or fountain drink may not behave as usual."
                            : w ? "The next whistle may call unusual attention."
                            : f ? "The next fountain drink may take a different course."
                            : 0;
    if (r->host.prior_count)
        out(emit, arg, "  Turn %ld: next-use program %d was admitted.", e->turn,
            e->program ? e->program : r->host.prior_count + 1);
    else
        out(emit, arg, "  Turn %ld: a next-use program was admitted.", e->turn);
    if (w && nu->origin_w > 0) origin_line(r, nu, 0, nu->origin_w, emit, arg);
    if (f && nu->origin_f > 0) origin_line(r, nu, 1, nu->origin_f, emit, arg);
    if (w && felt_before(&r->host, e->program, 0))
        out(emit, arg, "    Recurrence: \"%s\"", signal_text(5));
    if (f && felt_before(&r->host, e->program, 1))
        out(emit, arg, "    Recurrence: \"%s\"", signal_text(6));
    out(emit, arg, "    Telegraph: \"%s\"", telegraph ? telegraph : "(unknown)");
    out(emit, arg, "    Effect: %s%s%s.", w ? w : "", w && f ? "; " : "",
        f ? f : (w ? "" : "(unknown)"));
    /* Delivery needs the engine's own record: a published W witness, or the
     * F slot the native fountain path marks as applied. */
    if (nu->witnessed && nu->slot_f == CHAOS_REVEAL_F_CONSUMED_APPLIED)
        out(emit, arg, "    Delivered: yes, you saw your companion answer the whistle,"
            " and you drank the changed water.");
    else if (nu->witnessed)
        out(emit, arg, "    Delivered: yes, you saw your companion answer the whistle.");
    else if (nu->slot_f == CHAOS_REVEAL_F_CONSUMED_APPLIED)
        out(emit, arg, "    Delivered: yes, you drank the changed water.");
    else
        out(emit, arg, "    Delivered: no; no manifestation reached you.");
    out(emit, arg, "    Ended: %s", nu->terminated
        ? "consumed or ended before the game ended."
        : "still pending when the game ended.");
}

/* Arc 1 motif: a program's family is its first declared operation (W before
 * F, the engine's order); 0 whistle, 1 fountain. */
static int motif_of(const struct chaos_reveal_entry *e, const struct chaos_reveal_host *h)
{
    return nu_w(program_of(e, h)) ? 0 : 1;
}

/* Programs of one game, grouped by motif in first-appearance order. Only
 * when the game had more than one program; one program renders as before. */
static void next_use_motifs(const struct chaos_reveal *r, chaos_reveal_emit emit, void *arg)
{
    int order[2], n = 0, m, i, programs, felt;
    for (i = 0; i < r->count; ++i)
        if (r->e[i].kind == CHAOS_REVEAL_NEXT_USE) {
            int motif = motif_of(&r->e[i], &r->host);
            if (!n || (n == 1 && order[0] != motif)) order[n++] = motif;
        }
    for (m = 0; m < n; ++m) {
        programs = felt = 0;
        for (i = 0; i < r->count; ++i)
            if (r->e[i].kind == CHAOS_REVEAL_NEXT_USE && motif_of(&r->e[i], &r->host) == order[m]) {
                ++programs;
                felt += delivered(&r->e[i], &r->host);
            }
        out(emit, arg, "  Motif: the %s, %d program%s, felt %d time%s.",
            order[m] ? "fountain" : "whistle", programs, programs == 1 ? "" : "s",
            felt, felt == 1 ? "" : "s");
        for (i = 0; i < r->count; ++i)
            if (r->e[i].kind == CHAOS_REVEAL_NEXT_USE && motif_of(&r->e[i], &r->host) == order[m])
                next_use_entry(&r->e[i], r, emit, arg);
    }
}

void chaos_reveal_render(const struct chaos_reveal *r, chaos_reveal_emit emit, void *arg)
{
    int i, grouped = r->host.prior_count > 0, motifs_done = 0;
    if (!r->admitted) return;
    emit(arg, "The Crawling Chaos remembers.");
    for (i = 0; i < r->count; ++i) {
        const struct chaos_reveal_entry *e = &r->e[i];
        switch (e->kind) {
        case CHAOS_REVEAL_WHISPER: whisper(e, emit, arg); break;
        case CHAOS_REVEAL_CURIO: curio_entry(e, &r->host, emit, arg); break;
        case CHAOS_REVEAL_HAUNT: haunt_entry(e, r, emit, arg); break;
        case CHAOS_REVEAL_NEXT_USE:
            if (!grouped) next_use_entry(e, r, emit, arg);
            else if (!motifs_done) { next_use_motifs(r, emit, arg); motifs_done = 1; }
            break;
        }
    }
    if (r->overflow)
        out(emit, arg, "  (%d later admitted whisper%s not listed.)",
            r->overflow, r->overflow == 1 ? "" : "s");
    if (r->truncated)
        emit(arg, "  (The record was too long to read in full.)");
    out(emit, arg, "  Admitted %d, delivered %d; cruelty spent %d.",
        r->admitted, r->delivered, r->spent);
    if (r->rejected)
        out(emit, arg, "  %d other candidate%s refused; none took effect.",
            r->rejected, r->rejected == 1 ? " was" : "s were");
    emit(arg, "");
}

struct json_buf { char *p; size_t cap, n; int bad, first; };

static void json_raw(struct json_buf *b, const char *s)
{
    size_t k = strlen(s);
    if (b->bad || b->n + k >= b->cap) { b->bad = 1; return; }
    memcpy(b->p + b->n, s, k);
    b->n += k;
    b->p[b->n] = 0;
}

static void json_string(struct json_buf *b, const char *s)
{
    char esc[8];
    json_raw(b, "\"");
    for (; *s && !b->bad; ++s) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\') { esc[0] = '\\'; esc[1] = (char)c; esc[2] = 0; json_raw(b, esc); }
        else if (c < 0x20 || c == 0x7f) { snprintf(esc, sizeof esc, "\\u%04x", c); json_raw(b, esc); }
        else { esc[0] = (char)c; esc[1] = 0; json_raw(b, esc); }
    }
    json_raw(b, "\"");
}

static void json_line(void *arg, const char *line)
{
    struct json_buf *b = arg;
    if (!b->first) json_raw(b, ",");
    b->first = 0;
    json_string(b, line);
}

int chaos_reveal_json(const struct chaos_reveal *r, char *buf, size_t cap)
{
    struct json_buf b;
    char head[256];
    if (!cap) return 0;
    buf[0] = 0;
    if (!r || !r->admitted) return 1;
    b.p = buf; b.cap = cap; b.n = 0; b.bad = 0; b.first = 1;
    snprintf(head, sizeof head,
             "{\"reveal_v\":%d,\"final_turn\":%ld,\"admitted\":%d,\"delivered\":%d,"
             "\"spent\":%d,\"rejected\":%d,\"lines\":[",
             CHAOS_REVEAL_JSON_VERSION, r->final_turn, r->admitted, r->delivered, r->spent,
             r->rejected);
    json_raw(&b, head);
    chaos_reveal_render(r, json_line, &b);
    json_raw(&b, "]}\n");
    if (b.bad) { buf[0] = 0; return 0; }
    return 1;
}

int chaos_reveal_xlog_fields(const struct chaos_reveal *r, char *buf, size_t cap)
{
    int n;
    if (!cap) return 0;
    buf[0] = 0;
    if (!r || !r->admitted) return 1;
    n = snprintf(buf, cap, ":chaos_admitted=%d:chaos_delivered=%d:chaos_spent=%d",
                 r->admitted, r->delivered, r->spent);
    if (n < 0 || (size_t)n >= cap) { buf[0] = 0; return 0; }
    return 1;
}
