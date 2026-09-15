/* NGPL. Test-only new-game seed, native command receipts and inert floor probe.
 * No owner pointer survives an unload. Real Game tty commands do all transfers.
 */
#include "hack.h"
#include "chaos_curio.h"
#include <assert.h>
#include <stdio.h>

void __real_chaos_start(void);
int __real_doapply(void), __real_dodrop(void), __real_dosave(void);
int __real_dorecover(int), __real_ddoinv(void);
int __real_dopickup(void), __real_dotogglepickup(void);
void __real_deferred_goto(void);
static int restored;
static const char source[] =
    "return {name='Transfer counter',inspect=function(c) "
    "if c.charges==2 and c.state==8 then return 'Two uses remain; state eight.' end "
    "return 'Transfer counter ready.' end,apply=function(c) "
    "return {text='One mark advances.',state=c.state+1,sanity_delta=0} end}";

static FILE *file(const char *name, const char *mode)
{
    FILE *f = fopen(name, mode);
    assert(f);
    return f;
}

static struct obj *search(struct obj *chain)
{
    struct obj *o, *found;
    for (o = chain; o; o = o->nobj) {
        if (o->o_id == u.curio.owner) return o;
        found = search(o->cobj);
        if (found) return found;
    }
    return NULL;
}

static struct obj *monsearch(struct monst *chain)
{
    struct monst *m;
    struct obj *o;
    for (m = chain; m; m = m->nmon) {
        o = search(m->minvent);
        if (o) return o;
    }
    return NULL;
}

static struct obj *owner(void)
{
    struct obj *o;
    int i;
#define SEARCH(chain) do { o = search(chain); if (o) return o; } while (0)
    SEARCH(invent); SEARCH(fobj); SEARCH(level.buriedobjlist);
    SEARCH(migrating_objs); SEARCH(billobjs);
    for (i = 0; i < 10; ++i) { SEARCH(magic_chest_objs[i]); }
#undef SEARCH
    o = monsearch(fmon); if (o) return o;
    o = monsearch(mydogs); if (o) return o;
    return monsearch(migrating_mons);
}

static void snapshot(const char *name)
{
    char path[80];
    struct obj *o = owner();
    struct obj *p;
    int floor_chain = 0, player_floor_chain = 0;
    FILE *f;
    assert(chaos_curio_valid(&u.curio));
    assert(u.curio.phase == CHAOS_CURIO_PLACED);
    assert(!strcmp(u.curio.source, source));
    if (o) assert(chaos_curio_matches(o));
    /* Read actual top-level floor and square chains, not just o->where. */
    for (p = fobj; p; p = p->nobj)
        if (p->o_id == u.curio.owner) floor_chain = 1;
    for (p = level.objects[u.ux][u.uy]; p; p = p->nexthere)
        if (p->o_id == u.curio.owner) player_floor_chain = 1;
    snprintf(path, sizeof path, "%s.bin", name);
    f = file(path, "wb");
    assert(fwrite(&u.curio, sizeof u.curio, 1, f) == 1);
    assert(!fclose(f));
    snprintf(path, sizeof path, "%s.json", name);
    f = file(path, "w");
    fprintf(f, "{\"owner\":%u,\"loaded\":%d,\"tag\":%d,\"where\":\"%s\","
            "\"letter\":\"%c\",\"charges\":%d,\"state\":%d,\"phase\":%u,"
            "\"level\":%d,\"ux\":%d,\"uy\":%d,\"ox\":%d,\"oy\":%d,"
            "\"object_id\":%u,\"in_inventory\":%d,\"floor_chain\":%d,"
            "\"player_floor_chain\":%d,\"autopickup\":%d}\n",
            u.curio.owner, !!o, o ? o->curio_tag : -1,
            !o ? "unloaded" : o->where == OBJ_INVENT ? "inventory" :
            o->where == OBJ_FLOOR ? "floor" : "other",
            o && o->invlet ? o->invlet : '-', u.curio.charges, u.curio.state,
            u.curio.phase, u.uz.dlevel, u.ux, u.uy, o ? o->ox : -1,
            o ? o->oy : -1, o ? o->o_id : 0, !!search(invent),
            floor_chain, player_floor_chain, !!flags.pickup);
    assert(!fclose(f));
}

void __wrap_chaos_start(void)
{
    FILE *f;
    struct obj *o;
    __real_chaos_start();
    if (restored) {
        assert(!owner());
        snapshot("restored-start");
        return;
    }
    /* Existing marker is a hard failure, never a signal to silently reseed. */
    f = fopen("seed-count.txt", "r");
    assert(!f);
    f = file("seed-count.txt", "w");
    assert(fputs("seed\n", f) >= 0); assert(!fclose(f));
    iflags.item_use_menu = FALSE;
    o = mksobj(WHISTLE, NO_MKOBJ_FLAGS);
    assert(o && o->quan == 1 && !o->curio_tag);
    o->curio_tag = CHAOS_CURIO_GENERATED;
    memset(&u.curio, 0, sizeof u.curio);
    u.curio.version = CHAOS_CURIO_VERSION;
    u.curio.phase = CHAOS_CURIO_PLACED;
    u.curio.owner = o->o_id;
    u.curio.charges = 3; u.curio.state = 7;
    strcpy(u.curio.name, "Transfer counter");
    strcpy(u.curio.source, source);
    u.curio.source_len = strlen(source);
    assert(addinv(o) == o);
    f = file("fixture-source.lua", "wb");
    assert(fwrite(source, 1, strlen(source), f) == strlen(source));
    assert(!fclose(f));
    snapshot("seeded");
}

int __wrap_doapply(void)
{
    struct chaos_curio_state expected = u.curio;
    int result = __real_doapply();
    --expected.charges; ++expected.state;
    assert(!memcmp(&expected, &u.curio, sizeof expected));
    assert(owner() && owner()->where == OBJ_INVENT);
    snapshot(u.curio.charges == 2 ? "applied-first" : "applied-final");
    assert(result == MOVE_STANDARD);
    return result;
}

int __wrap_dodrop(void)
{
    struct chaos_curio_state before = u.curio;
    struct obj *o;
    char text[161];
    int result = __real_dodrop(), move;
    o = owner();
    assert(o && o->where == OBJ_FLOOR);
    assert(chaos_curio_matches(o));
    assert(!strcmp(chaos_curio_name(o), "Transfer counter"));
    chaos_curio_inspect(o, text);
    assert(!strcmp(text, "This curio is inert."));
    assert(chaos_curio_apply(o, &move) && move == MOVE_CANCELLED);
    assert(!memcmp(&before, &u.curio, sizeof before));
    snapshot("dropped");
    return result;
}

void __wrap_deferred_goto(void)
{
    struct chaos_curio_state before = u.curio;
    /* Native levelport schedules this entry; goto_level is in the same object
     * and cannot itself be intercepted by GNU ld --wrap on that call edge. */
    __real_deferred_goto();
    assert(!memcmp(&before, &u.curio, sizeof before));
    if (u.uz.dlevel == 2) {
        assert(!owner());
        snapshot("away");
    } else {
        assert(u.uz.dlevel == 1 && owner());
        snapshot("returned");
    }
}

int __wrap_dosave(void)
{
    assert(!owner());
    snapshot("save-entry");
    return __real_dosave();
}

int __wrap_dorecover(int fd)
{
    int ok = __real_dorecover(fd);
    assert(ok);
    restored = 1;
    assert(!owner());
    snapshot("restored");
    return ok;
}

int __wrap_ddoinv(void)
{
    snapshot("inventory");
    return __real_ddoinv();
}

int __wrap_dopickup(void)
{
    static unsigned int calls;
    struct chaos_curio_state before = u.curio;
    char name[80];
    FILE *f;
    int result;
    /* cmd.o's external command-table entry is wrappable; do not replace
     * pickup() or intercept teleds' automatic pickup instead of comma. */
    ++calls;
    snprintf(name, sizeof name, "manual-%u-before", calls);
    snapshot(name);
    result = __real_dopickup();
    assert(!memcmp(&before, &u.curio, sizeof before));
    snprintf(name, sizeof name, "manual-%u-after", calls);
    snapshot(name);
    snprintf(name, sizeof name, "manual-%u-result.json", calls);
    f = file(name, "w");
    fprintf(f, "{\"result\":%d,\"move_standard\":%d,\"move_cancelled\":%d}\n",
            result, MOVE_STANDARD, MOVE_CANCELLED);
    assert(!fclose(f));
    return result;
}

int __wrap_dotogglepickup(void)
{
    struct chaos_curio_state before = u.curio;
    boolean pickup_before = flags.pickup;
    int result;
    snapshot("autopickup-before");
    result = __real_dotogglepickup();
    assert(flags.pickup == !pickup_before);
    assert(!memcmp(&before, &u.curio, sizeof before));
    snapshot("autopickup-after");
    assert(result == MOVE_CANCELLED);
    return result;
}
