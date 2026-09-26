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
    } else if (is_str(line, "detail", CHAOS_STATUS_REJECTED)
               || is_str(line, "detail", "source_rejected")
               || is_str(line, "detail", "shadow_failed")
               || is_str(line, "detail", "spawn_failed")) {
        ++r->rejected;
    }
}

void chaos_reveal_event_line(struct chaos_reveal *r, const char *line)
{
    long turn = 0;
    struct chaos_reveal_entry *e;
    (void)get_long(line, "turn", &turn);
    if (is_str(line, "event", CHAOS_EVENT_SESSION) && is_str(line, "detail", "new")) {
        /* A fresh game starts its own record; never inherit another game's rows. */
        r->count = r->overflow = r->rejected = 0;
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
    }
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
    return read_lines(r, dir, "events.jsonl", chaos_reveal_event_line) && ok;
}

static int delivered(const struct chaos_reveal_entry *e, const struct chaos_reveal_host *h)
{
    switch (e->kind) {
    case CHAOS_REVEAL_WHISPER: return e->mutation == CHAOS_AMBIENT;
    case CHAOS_REVEAL_CURIO: return e->uses > 0;
    case CHAOS_REVEAL_HAUNT: return e->steps > 0;
    case CHAOS_REVEAL_NEXT_USE: return h->next_use_delivered;
    }
    return 0;
}

void chaos_reveal_finish(struct chaos_reveal *r)
{
    struct chaos_reveal_entry tmp;
    int i, j;
    if (r->host.next_use)
        (void)add(r, CHAOS_REVEAL_NEXT_USE, r->host.next_use_turn);
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
    if (h->haunt_active && r->final_turn < h->haunt_until)
        out(emit, arg, "    Ended: still hunting when the game ended.");
    else
        out(emit, arg, "    Ended: its hunt was over by the end (due turn %ld).",
            h->haunt_until);
}

static void next_use_entry(const struct chaos_reveal_entry *e, const struct chaos_reveal_host *h,
                           chaos_reveal_emit emit, void *arg)
{
    out(emit, arg, "  Turn %ld, %s: a next-use program was admitted.", e->turn,
        h->next_use_origin[0] ? h->next_use_origin : "after an earlier action");
    out(emit, arg, "    Telegraph: \"%s\"", h->next_use_telegraph[0] ? h->next_use_telegraph : "(unknown)");
    out(emit, arg, "    Effect: %s", h->next_use_effect);
    out(emit, arg, "    Delivered: %s", h->next_use_delivered
        ? "yes, you saw your companion answer the whistle."
        : "no; no manifestation reached you.");
    out(emit, arg, "    Ended: %s", h->next_use_ended);
}

void chaos_reveal_render(const struct chaos_reveal *r, chaos_reveal_emit emit, void *arg)
{
    int i;
    if (!r->admitted) return;
    emit(arg, "The Crawling Chaos remembers.");
    for (i = 0; i < r->count; ++i) {
        const struct chaos_reveal_entry *e = &r->e[i];
        switch (e->kind) {
        case CHAOS_REVEAL_WHISPER: whisper(e, emit, arg); break;
        case CHAOS_REVEAL_CURIO: curio_entry(e, &r->host, emit, arg); break;
        case CHAOS_REVEAL_HAUNT: haunt_entry(e, r, emit, arg); break;
        case CHAOS_REVEAL_NEXT_USE: next_use_entry(e, &r->host, emit, arg); break;
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
