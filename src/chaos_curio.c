/* NetHack General Public License: bounded admission, no native effects/RNG. */
#define _POSIX_C_SOURCE 200809L
#ifdef CHAOS
#include "hack.h"
#include "chaos.h"
#include "mkroom.h"
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#endif
#include "chaos_curio.h"
#include "chaos_lua.h"
#include <string.h>

static int empty_bytes(const char *p, unsigned n)
{
    unsigned i;
    for (i = 0; i < n; ++i) if (p[i]) return 0;
    return 1;
}

int chaos_curio_valid(const struct chaos_curio_state *s)
{
    char name[49];
    if (!s || s->phase > CHAOS_CURIO_EXPIRED
        || s->charges < 0 || s->charges > 3
        || s->state < 0 || s->state > 255
        || s->disabled < 0 || s->disabled > 1)
        return 0;
    if (s->version != (s->phase == CHAOS_CURIO_VIRGIN
                       ? 0 : CHAOS_CURIO_VERSION)) return 0;
    if (!s->source_len) {
        return (s->phase == CHAOS_CURIO_VIRGIN
                || s->phase == CHAOS_CURIO_REJECTED
                || s->phase == CHAOS_CURIO_EXPIRED)
            && !s->owner && !s->charges && !s->state && !s->disabled
            && empty_bytes(s->name, sizeof s->name)
            && empty_bytes(s->source, sizeof s->source);
    }
    if (s->phase != CHAOS_CURIO_ADMITTED && s->phase != CHAOS_CURIO_PLACED
        && s->phase != CHAOS_CURIO_EXPIRED) return 0;
    if (s->source_len > CHAOS_CURIO_SOURCE
        || s->source[s->source_len] || memchr(s->source, 0, s->source_len)
        || !memchr(s->name, 0, sizeof s->name)) return 0;
    if (s->phase == CHAOS_CURIO_PLACED) {
        if (!s->owner) return 0;
    } else if (s->owner || s->charges != 3 || s->state || s->disabled) {
        return 0;
    }
    /* Reconstruct metadata in a fresh bounded VM, never trust saved text.
     * Failure is local; do not modify the caller or other saves/runtime state. */
    if (chaos_lua_curio_load(s->source, s->source_len, name)) return 0;
    return !strcmp(name, s->name)
        && empty_bytes(s->name + strlen(name), sizeof s->name - strlen(name));
}

#ifdef CHAOS
int chaos_curio_tagged(const struct obj *obj)
{
    return obj && obj->curio_tag != CHAOS_CURIO_ORDINARY;
}

/* Cached printable identity only: no VM, ownership search, or mutable state. */
int chaos_curio_matches(const struct obj *obj)
{
    unsigned i;
    int nonblank = 0;
    if (!chaos_curio_tagged(obj) || obj->curio_tag != CHAOS_CURIO_GENERATED
        || obj->otyp != WHISTLE || obj->quan != 1L
        || u.curio.phase != CHAOS_CURIO_PLACED || !u.curio.owner
        || obj->o_id != u.curio.owner) return 0;
    for (i = 0; i < sizeof u.curio.name; ++i) {
        unsigned char c = (unsigned char) u.curio.name[i];
        if (!c) return nonblank;
        if (c < 32 || c > 126) return 0;
        if (c != ' ') nonblank = 1;
    }
    return 0;
}

const char *chaos_curio_name(const struct obj *obj)
{
    return chaos_curio_matches(obj) ? u.curio.name : "inert curio";
}

void chaos_curio_inspect(const struct obj *obj, char text[161])
{
    const struct obj *held;
    struct chaos_curio_lua_context c;
    char result[161];
    strcpy(text, "This curio is inert.");
    if (!chaos_curio_matches(obj) || u.curio.disabled) return;
    /* where alone can be stale or forged; require actual chain membership. */
    for (held = invent; held && held != obj; held = held->nobj) ;
    if (!held || obj->where != OBJ_INVENT || !chaos_curio_valid(&u.curio)) return;
    c.sanity = u.usanity; c.insight = u.uinsight;
    c.charges = u.curio.charges; c.state = u.curio.state;
    if (!chaos_lua_curio_inspect(u.curio.source, u.curio.source_len, &c, result))
        strcpy(text, result);
}

/* Local execution is independent of admission transport and placement. */
int chaos_curio_apply(struct obj *obj, int *move_result)
{
    const struct obj *held;
    struct chaos_curio_lua_context c;
    struct chaos_curio_lua_intent intent;
    int starting_sanity;
    char receipt[80];
    if (!chaos_curio_tagged(obj)) return 0;
    *move_result = MOVE_CANCELLED;
    /* Structural/binding failures are inert, not a reason to disable a
     * different legitimate owner or silently repair a corrupted record. */
    if (!chaos_curio_matches(obj) || u.curio.disabled
        || u.curio.charges <= 0 || obj->where != OBJ_INVENT) goto inert;
    for (held = invent; held && held != obj; held = held->nobj) ;
    if (!held || !chaos_curio_valid(&u.curio)) goto inert;
    c.sanity = u.usanity; c.insight = u.uinsight;
    c.charges = u.curio.charges; c.state = u.curio.state;
    /* The bounded pure API validates the ENTIRE intent before returning.
     * Runtime program failure disables only the established executable owner. */
    if (chaos_lua_curio_apply(u.curio.source, u.curio.source_len, &c, &intent)) {
        u.curio.disabled = 1;
        goto inert;
    }
    pline("The curio requests a Sanity change of %+d; native limits may reduce it. This spends one use.",
          intent.sanity_delta);
    pline("%s", intent.text);
    --u.curio.charges;
    u.curio.state = intent.state;
    starting_sanity = u.usanity;
    /* FALSE suppresses the extra acute-madness check, not native glyphs or
     * health/energy recalculation (nor all possible native consequences). */
    change_usanity(intent.sanity_delta, FALSE);
    Sprintf(receipt, "applied requested=%d actual=%d",
            intent.sanity_delta, u.usanity - starting_sanity);
    /* A failed final receipt must never refund or reopen this use. */
    chaos_event("curio", "result", receipt);
    *move_result = MOVE_STANDARD;
    return 1;
inert:
    pline("This curio is inert.");
    return 1;
}

/* Not saved: a capability for this one mklev invocation, never for restore.
 * Nested/duplicate begin or prepare invalidates the outer capability too. */
static struct {
    int prepared, active, eligible, ordinary;
    d_level level;
} placement;

void chaos_curio_prepare(unsigned ledger_flags)
{
    int conflict = placement.prepared || placement.active;
    placement.prepared = 1;
    placement.eligible = !conflict && !chaos_shadow_active()
        && !(ledger_flags & (LFILE_EXISTS | VISITED | FORGOTTEN));
    placement.ordinary = 0;
    placement.level = u.uz;
}

void chaos_curio_begin(void)
{
    placement.eligible = placement.prepared && !placement.active
        && placement.eligible && on_level(&placement.level, &u.uz)
        && !chaos_shadow_active() && u.curio.phase == CHAOS_CURIO_ADMITTED
        && u.uz.dnum == 0 && u.uz.dlevel >= 2 && u.uz.dlevel <= 3;
    placement.prepared = 0;
    placement.active = 1;
    placement.ordinary = 0;
}

void chaos_curio_ordinary(void)
{
    if (placement.active && placement.eligible && !Is_rogue_level(&u.uz))
        placement.ordinary = 1;
}

/* SPECIALIZATION leaves ordinary rectangular roomno unset. Irregular rooms
 * require topology membership; rectangular rooms explicitly exclude subrooms
 * and their borders, matching native somexy rather than inside_room alone. */
static int curio_room_cell(struct mkroom *r, int x, int y)
{
    int i;
    if (r->rtype != OROOM || x < r->lx || x > r->hx
        || y < r->ly || y > r->hy || levl[x][y].edge) return 0;
    if (r->irregular && levl[x][y].roomno != (r - rooms) + ROOMOFFSET)
        return 0;
    for (i = 0; i < r->nsubrooms; ++i)
        if (inside_room(r->sbrooms[i], x, y)) return 0;
    return 1;
}

void chaos_curio_finish(int generated)
{
    int eligible = placement.active && placement.eligible && placement.ordinary
        && generated && on_level(&placement.level, &u.uz);
    int x, y, r, bestx = 0, besty = 0, best = COLNO * ROWNO * 4;
    struct obj *obj;
    memset(&placement, 0, sizeof placement); /* consume even bones/failure */
    if (!eligible || chaos_shadow_active() || u.curio.phase != CHAOS_CURIO_ADMITTED
        || u.uz.dnum != 0 || u.uz.dlevel < 2 || u.uz.dlevel > 3
        || Is_special(&u.uz) || Is_rogue_level(&u.uz)
        || dungeons[u.uz.dnum].proto[0] || level.flags.is_maze_lev) return;
    /* One fixed-size scan; upstairs room first, then distance, stable ties.
     * ROOM excludes stairs, doors, water, altars and other reserved furniture. */
    for (x = 1; x < COLNO; ++x) for (y = 0; y < ROWNO; ++y) {
        if (levl[x][y].typ != ROOM || t_at(x,y) || m_at(x,y)
            || level.objects[x][y] || *in_rooms(x,y,SHOPBASE)) continue;
        for (r = 0; r < nroom; ++r) if (curio_room_cell(&rooms[r],x,y)) {
            int score = (&rooms[r] == upstairs_room ? 0 : COLNO * ROWNO)
                + distmin(x,y,xupstair,yupstair);
            if (score < best) { best = score; bestx = x; besty = y; }
            break;
        }
    }
    if (!bestx) { chaos_event("curio", "result", "placement_unavailable"); return; }
    obj = mksobj(WHISTLE, MKOBJ_NOINIT); /* one attempt, no reroll/repair */
    if (!obj) {
        u.curio.phase = CHAOS_CURIO_EXPIRED;
        chaos_event("curio", "result", "placement_failed");
        return;
    }
    obj->quan = 1L;
    obj->nomerge = 1;
    obj->curio_tag = CHAOS_CURIO_GENERATED;
    place_object(obj, bestx, besty);
    u.curio.owner = obj->o_id;
    u.curio.phase = CHAOS_CURIO_PLACED;
    /* Physical placement is not a claim that the player has seen the object. */
    chaos_event("curio", "result", "placed");
}

static int curio_private(int fd)
{
    struct stat st;
    return !fstat(fd, &st) && S_ISREG(st.st_mode)
        && st.st_uid == getuid() && st.st_nlink == 1
        && !(st.st_mode & (07777 & ~0600));
}

static int curio_evidence(int dir, const char *source, size_t len)
{
    int fd, ok = 0, attempts = 0;
    size_t pos = 0;
    ssize_t n;
    fd = openat(dir, "curio-used.lua",
                O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC,
                0600);
    if (fd < 0) return 0;
    if (!curio_private(fd)) goto out;
    while (pos < len && ++attempts <= 2 * CHAOS_CURIO_SOURCE) {
        n = write(fd, source + pos, len - pos);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) goto out;
        pos += (size_t)n;
    }
    if (pos != len || fsync(fd)) goto out;
    ok = 1;
out:
    if (close(fd)) ok = 0;
    /* Even a complete snapshot is not acceptance. Never unlink or repair it. */
    if (ok && fsync(dir)) ok = 0;
    return ok;
}

void chaos_curio_safe(int dir)
{
    struct chaos_curio_state next;
    struct chaos_curio_lua_context c;
    struct chaos_curio_lua_intent intent;
    char text[161];
    size_t used = 0;
    ssize_t n = 0;
    int fd, attempts = 0, closed;
    static int busy;
    if (busy || chaos_shadow_active()) return;
    /* Dungeon zero is the main dungeon; use local, not absolute depth. */
    if (u.uz.dnum == 0 && u.uz.dlevel >= 3
        && (u.curio.phase == CHAOS_CURIO_VIRGIN
            || u.curio.phase == CHAOS_CURIO_ADMITTED)) {
        u.curio.phase = CHAOS_CURIO_EXPIRED;
        u.curio.version = CHAOS_CURIO_VERSION;
        chaos_event("curio", "result", "expired");
    }
    if (dir < 0 || u.curio.phase != CHAOS_CURIO_VIRGIN
        || u.uz.dnum != 0 || u.uz.dlevel < 1 || u.uz.dlevel > 2
        || program_state.gameover || multi < 0 || u.usleep
        || (Upolyd ? u.mh : u.uhp) <= 0
        || chaos_budget(&u.chaos, u.usanity) < 1) return;
    busy = 1;
    fd = openat(dir, "curio.lua", O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0 && errno == ENOENT) { busy = 0; return; }
    /* Only absence is retryable after looking for a candidate. Keep failures
     * canonical and empty; source is held locally until the final commit. */
    memset(&u.curio, 0, sizeof u.curio);
    u.curio.version = CHAOS_CURIO_VERSION;
    u.curio.phase = CHAOS_CURIO_REJECTED;
    if (fd < 0) goto rejected;
    if (!curio_private(fd)) { close(fd); goto rejected; }
    memset(&next, 0, sizeof next);
    while (used < sizeof next.source && ++attempts <= 2 * CHAOS_CURIO_SOURCE) {
        n = read(fd, next.source + used, sizeof next.source - used);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) break;
        used += (size_t)n;
    }
    closed = close(fd);
    if (closed || n < 0 || attempts > 2 * CHAOS_CURIO_SOURCE
        || !used || used > CHAOS_CURIO_SOURCE) goto rejected;
    if (memchr(next.source, 0, used)) goto rejected;
    c.sanity = u.usanity; c.insight = u.uinsight; c.charges = 3; c.state = 0;
    if (chaos_lua_curio_load(next.source, used, next.name)
        || chaos_lua_curio_inspect(next.source, used, &c, text)
        || chaos_lua_curio_apply(next.source, used, &c, &intent)) goto rejected;
    next.version = CHAOS_CURIO_VERSION; next.phase = CHAOS_CURIO_ADMITTED;
    next.source_len = (unsigned)used; next.charges = 3;
    if (!curio_evidence(dir, next.source, used)
        || !chaos_event_checked("curio", "result", "pre_admitted")) goto rejected;
    pline("An uncanny curio may appear on a later floor.");
    u.curio = next;
    ++u.chaos.spent;
    /* A failed final receipt cannot reopen admission or refund the cost. */
    chaos_event("curio", "result", "admitted");
    busy = 0;
    return;
rejected:
    chaos_event("curio", "result", "rejected");
    busy = 0;
}
#endif
