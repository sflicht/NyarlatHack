/* NGPL. Linked native physical handlers with controlled input/window callbacks.
 * Not a tty session, monster AI encounter, or whole-turn/RNG purity claim.
 */
#include "hack.h"
#include "chaos_curio.h"
#include "native_rng.h"
#include <stdio.h>
#include <execinfo.h>
#include <signal.h>
#include <unistd.h>

/* Exposed only in private objcopy copies; engine objects are never edited. */
extern struct obj *nextgetobj, *current_container;
extern int n_dgns;
int in_container(struct obj *);
int out_container(struct obj *);
struct obj *__real_mksobj(int, int);
static unsigned creates, directions;
static int throwing;
static char output[32768];
static void crash(int sig)
{
    void *frames[40];
    int n = backtrace(frames, 40);
    (void)write(2, output, strlen(output));
    backtrace_symbols_fd(frames, n, 2);
    signal(sig, SIG_DFL); raise(sig);
}
static struct chaos_curio_state baseline;
static unsigned original_id;
static int original_tag;
static unsigned launches, landings;
void __real_freeinv(struct obj *);
void __real_place_object(struct obj *, int, int);
void __wrap_freeinv(struct obj *o)
{
    if (throwing) {
        assert(o->o_id == original_id && o->where == OBJ_INVENT && invent == o);
        assert(!memcmp(&baseline, &u.curio, sizeof baseline));
        ++launches;
    }
    __real_freeinv(o);
    if (throwing) assert(o->where == OBJ_FREE && !invent);
}
void __wrap_place_object(struct obj *o, int x, int y)
{
    if (throwing) {
        assert(launches == 1 && !landings && o->o_id == original_id);
        assert(o->where == OBJ_FREE && o->curio_tag == original_tag);
        assert(!memcmp(&baseline, &u.curio, sizeof baseline));
        ++landings;
    }
    __real_place_object(o, x, y);
}
static const char source[] =
    "return {name='Transfer counter',inspect=function(c) return 'Counter ready.' end,"
    "apply=function(c) return {text='One mark advances.',state=c.state+1,"
    "sanity_delta=0} end}";

struct obj *__wrap_mksobj(int type, int flags_arg)
{
    ++creates;
    return __real_mksobj(type, flags_arg); /* observe, never force success/failure */
}
int __wrap_getdir(const char *prompt)
{
    (void)prompt;
    assert(throwing && directions == 0);
    ++directions;
    u.dx = 1; u.dy = u.dz = 0;
    return 1; /* controlled direction input, not projectile replacement */
}
static void text(winid w, int a, const char *s)
{
    (void)w; (void)a;
    assert(strlen(output) + strlen(s) + 2 < sizeof output);
    strcat(output, s); strcat(output, "\n");
}
static void raw(const char *s) { text(0, 0, s); }
static void noop(void) {}
static void delay(int milliseconds) { (void)milliseconds; }
static void clear(winid w) { (void)w; }
static void display(winid w, BOOLEAN_P b) { (void)w; (void)b; }
static void cursor(winid w, int x, int y) { (void)w; (void)x; (void)y; }
static void glyph(winid w, XCHAR_P x, XCHAR_P y, int g)
{ (void)w; (void)x; (void)y; (void)g; }
static void clip(int x, int y) { (void)x; (void)y; }
static winid window(int type) { (void)type; return 1; }
static char answer(const char *q, const char *c, int d)
{ (void)q; (void)c; (void)d; assert(0 && "unexpected prompt"); return 'n'; }

static void setup(void)
{
    int i, x, y;
    id_permonst(); init_objects(); init_gods(); vision_init();
    urace = races[str2race("human")]; urole = roles[str2role("Wizard")];
    /* Native monster creation must not run in the zero-initialized quest. */
    n_dgns = 2; u.uz.dnum = 1; u.uz.dlevel = 2;
    dungeons[1].depth_start = 1; dungeons[1].num_dunlevs = 20;
    dungeons[0].depth_start = 1; dungeons[0].num_dunlevs = 20;
    u.umonnum = u.umonster = PM_HUMAN; init_uasmon();
    u.ulevel = 1; u.uhp = u.uhprolled = 20; u.uen = u.uenrolled = 20;
    for (i = 0; i < A_MAX; ++i) ABASE(i) = AMAX(i) = 12;
    u.ux = u.uy = 10; u.usanity = 73; moves = 101; monstermoves = 100;
    strcpy(plname, "Task6f"); init_artifacts(); flags.ident = 100;
    flags.pickup = FALSE; flags.soundok = TRUE;
    windowprocs.win_putstr = text; windowprocs.win_raw_print = raw;
    windowprocs.win_update_inventory = noop; windowprocs.win_wait_synch = noop;
    windowprocs.win_delay_output = delay; windowprocs.win_clear_nhwindow = clear;
    windowprocs.win_display_nhwindow = display; windowprocs.win_curs = cursor;
    windowprocs.win_print_glyph = glyph; windowprocs.win_cliparound = clip;
    windowprocs.win_create_nhwindow = window; windowprocs.win_destroy_nhwindow = clear;
    windowprocs.win_yn_function = answer;
    for (x = 1; x < COLNO-1; ++x) for (y = 1; y < ROWNO-1; ++y) {
        levl[x][y].typ = ROOM; levl[x][y].lit = 1;
        viz_array[y][x] = IN_SIGHT | COULD_SEE;
    }
    nroom = 1; rooms[0].lx = 3; rooms[0].hx = 25;
    rooms[0].ly = 3; rooms[0].hy = 15; rooms[0].rtype = OROOM;
    upstairs_room = &rooms[0]; xupstair = 10; yupstair = 9;
    levl[10][9].typ = STAIRS;
    calc_total_maxhp(); calc_total_maxen();
}
static struct obj *object(int type)
{
    struct obj *o = mksobj(type, MKOBJ_NOINIT);
    assert(o && o->where == OBJ_FREE && !o->curio_tag && o->quan == 1);
    return o;
}
static void record(void)
{
    assert(u.curio.phase == CHAOS_CURIO_VIRGIN);
    memset(&u.curio, 0, sizeof u.curio);
    u.curio.version = CHAOS_CURIO_VERSION; u.curio.phase = CHAOS_CURIO_ADMITTED;
    u.curio.charges = 3;
    strcpy(u.curio.name, "Transfer counter"); strcpy(u.curio.source, source);
    u.curio.source_len = strlen(source);
    assert(chaos_curio_valid(&u.curio));
}
static void same_record(void)
{
    assert(!memcmp(&baseline, &u.curio, sizeof baseline));
    assert(chaos_curio_valid(&u.curio));
}
/* Validate recursive chains AND backpointers; return original ID occurrences. */
static int chain(struct obj *o, int where, struct obj *parent, struct monst *carrier)
{
    int count = 0;
    for (; o; o = o->nobj) {
        struct obj *at;
        assert(o->where == where);
        if (parent) assert(o->ocontainer == parent);
        if (carrier) assert(o->ocarry == carrier);
        if (where == OBJ_FLOOR) {
            for (at = level.objects[o->ox][o->oy]; at && at != o; at = at->nexthere) {}
            assert(at == o);
        }
        if (o->o_id == original_id) {
            ++count;
            assert(o->curio_tag == original_tag && o->otyp == WHISTLE && o->quan == 1);
        }
        count += chain(o->cobj, OBJ_CONTAINED, o, NULL);
    }
    return count;
}
static int roots(void)
{
    struct monst *m;
    int i;
    int count = chain(invent, OBJ_INVENT, NULL, NULL)
        + chain(fobj, OBJ_FLOOR, NULL, NULL);
    for (m = fmon; m; m = m->nmon) {
        assert(level.monsters[m->mx][m->my] == m);
        count += chain(m->minvent, OBJ_MINVENT, NULL, m);
    }
    assert(!level.buriedobjlist && !migrating_objs && !billobjs);
    assert(!mydogs && !migrating_mons);
    for (i = 0; i < 10; ++i) assert(!magic_chest_objs[i]);
    return count;
}
static void checkpoint(struct obj *o, int where)
{
    int count = roots();
    assert(count == 1);
    assert(o->o_id == original_id && o->where == where && o->curio_tag == original_tag);
    same_record();
    if (original_tag) assert(chaos_curio_matches(o));
    printf("checkpoint id=%u where=%d tag=%d charges=%d state=%d ux=%d uy=%d\n",
           original_id, where, original_tag, u.curio.charges, u.curio.state, u.ux, u.uy);
}
static void inert(struct obj *o)
{
    int move = 123, rng = test_rng_begin();
    struct obj saved = *o;
    output[0] = 0;
    assert(chaos_curio_apply(o, &move) && move == MOVE_CANCELLED);
    assert(!strcmp(output, "This curio is inert.\n"));
    same_record(); assert(!memcmp(&saved, o, sizeof saved));
    test_rng_unchanged(rng); /* only this helper, never physical interactions */
    if (o->where != OBJ_INVENT) {
        char desc[161];
        chaos_curio_inspect(o, desc); assert(!strcmp(desc, "This curio is inert."));
        same_record();
    }
}
static void apply_once(struct obj *o)
{
    struct chaos_curio_state expected = u.curio;
    assert(o->where == OBJ_INVENT && u.curio.charges > 0 && !u.curio.disabled);
    nextgetobj = o; output[0] = 0;
    assert(doapply() == MOVE_STANDARD && !nextgetobj);
    --expected.charges; ++expected.state;
    assert(!memcmp(&expected, &u.curio, sizeof expected));
    assert(strstr(output, "One mark advances."));
    baseline = u.curio;
}
static void generation(void)
{
    chaos_curio_prepare(0); chaos_curio_begin(); chaos_curio_ordinary(); chaos_curio_finish(1);
}
static struct obj *seed(const char *variant, int placement)
{
    struct obj *o;
    int ordinary = !strcmp(variant, "ordinary");
    if (!ordinary) record();
    if (placement && !ordinary) {
        unsigned calls = creates;
        struct chaos_curio_state expected = u.curio;
        u.uz.dnum = 0;
        generation(); /* ADMITTED positive control on this exact legal map */
        assert(creates == calls + 1 && u.curio.phase == CHAOS_CURIO_PLACED);
        o = fobj; assert(o && !o->nobj && o->o_id == u.curio.owner);
        assert(o->curio_tag == CHAOS_CURIO_GENERATED && o->where == OBJ_FLOOR);
        expected.phase = CHAOS_CURIO_PLACED; expected.owner = o->o_id;
        assert(!memcmp(&expected, &u.curio, sizeof expected));
        printf("positive placement id=%u creates=%u floor=%d,%d\n", o->o_id, creates, o->ox, o->oy);
        obj_extract_self(o); /* setup acquisition, not a claimed UI pickup */
    } else {
        o = object(WHISTLE);
        if (!ordinary) {
            o->curio_tag = CHAOS_CURIO_GENERATED; o->nomerge = 1;
            u.curio.phase = CHAOS_CURIO_PLACED; u.curio.owner = o->o_id;
        }
    }
    original_id = o->o_id; original_tag = o->curio_tag;
    assert(addinv(o) == o); baseline = u.curio;
    if (!ordinary) {
        u.curio.state = 7; /* handwritten initial owned-state fixture */
        apply_once(o);
        assert(u.curio.charges == 2 && u.curio.state == 8);
        if (!strcmp(variant, "disabled")) u.curio.disabled = 1;
        else if (!strcmp(variant, "depleted")) { apply_once(o); apply_once(o); }
    }
    baseline = u.curio; checkpoint(o, OBJ_INVENT);
    return o;
}
static void returned(struct obj *o)
{
    checkpoint(o, OBJ_INVENT);
    if (original_tag) {
        if (u.curio.disabled || !u.curio.charges) inert(o);
        else apply_once(o);
        checkpoint(o, OBJ_INVENT);
    } else {
        int move = 123;
        assert(!chaos_curio_apply(o, &move) && move == 123);
        same_record();
    }
}
static void outside(struct obj *o, int where)
{
    checkpoint(o, where);
    if (original_tag) inert(o);
}
static void containers(struct obj *o)
{
    struct obj *inner = object(SACK), *outer = object(SACK);
    assert(addinv(inner) == inner && addinv(outer) == outer);
    assert(!inner->curio_tag && !outer->curio_tag && !inner->cobj && !outer->cobj);
    current_container = inner;
    assert(o->where == OBJ_INVENT && inner->where == OBJ_INVENT);
    assert(in_container(o) == 1);
    assert(inner->cobj == o && o->ocontainer == inner); outside(o, OBJ_CONTAINED);
    current_container = outer;
    assert(inner->where == OBJ_INVENT && outer->where == OBJ_INVENT);
    assert(in_container(inner) == 1);
    assert(outer->cobj == inner && inner->ocontainer == outer && inner->cobj == o);
    assert(outer->where == OBJ_INVENT && inner->where == OBJ_CONTAINED);
    outside(o, OBJ_CONTAINED);
    /* Inner cannot be opened while contained: remove it through the real handler. */
    assert(out_container(inner) == 1);
    assert(!outer->cobj && inner->where == OBJ_INVENT && inner->cobj == o);
    outside(o, OBJ_CONTAINED);
    current_container = inner;
    assert(out_container(o) == 1);
    assert(!inner->cobj); current_container = NULL;
    returned(o);
}
static void step_east(struct obj *o, int carried)
{
    int x = u.ux, y = u.uy;
    assert(levl[x+1][y].typ == ROOM && !m_at(x+1,y) && !t_at(x+1,y));
    assert(!Stunned && !Confusion && !u.ustuck && near_capacity() == UNENCUMBERED);
    if (carried) checkpoint(o, OBJ_INVENT);
    u.dx = 1; u.dy = u.dz = 0; flags.move = 0;
    domove();
    assert(u.ux == x+1 && u.uy == y && (flags.move & MOVE_MOVED));
    same_record();
    if (carried) {
        xchar ox, oy;
        checkpoint(o, OBJ_INVENT);
        assert(get_obj_location(o, &ox, &oy, 0) && ox == u.ux && oy == u.uy);
    }
}
static void pickup_here(struct obj *o)
{
    assert(o->where == OBJ_FLOOR && o->ox == u.ux && o->oy == u.uy);
    assert(obj_here(o, u.ux, u.uy));
    assert(pickup_object(o, 1L, FALSE) == 1);
    assert(!fobj && !level.objects[u.ux][u.uy]); returned(o);
}
static void monster_transfer(struct obj *o, int theft)
{
    struct monst *m = makemon(&mons[PM_DRYAD], 11, 10, NO_MINVENT);
    char name[BUFSZ];
    assert(m && fmon == m && !m->nmon && !m->minvent);
    assert(m->mtyp == PM_DRYAD && mon_attacktype(m, AT_CLAW));
    assert(monnear(m, u.ux, u.uy) && m->mhp > 0);
    assert(invent == o && !o->nobj && !o->owornmask && o->where == OBJ_INVENT);
    if (theft) {
        output[0] = 0;
        assert(steal(m, name, 0, 0) == 1);
        assert(name[0] && strstr(output, "stole") && m->mavenge);
    } else {
        freeinv(o); assert(o->where == OBJ_FREE && !invent);
        assert(mpickobj(m, o) == 0);
    }
    assert(!invent && m->minvent == o && !o->nobj && o->ocarry == m);
    outside(o, OBJ_MINVENT);
    /* mdrop_obj's native callers extract first; it requires OBJ_FREE. */
    obj_extract_self(o);
    assert(o->where == OBJ_FREE && !m->minvent); same_record();
    if (original_tag) inert(o);
    mdrop_obj(m, o, FALSE);
    assert(!m->minvent && o->where == OBJ_FLOOR && o->ox == m->mx && o->oy == m->my);
    outside(o, OBJ_FLOOR);
    /* Native relocation only clears the pickup route; no simulated AI scheduling. */
    rloc_to(m, 20, 10);
    assert(m->mx == 20 && m->my == 10 && !m_at(11,10));
    step_east(o, 0); pickup_here(o);
}
static void physical_throw(struct obj *o)
{
    int result, origin = u.ux;
    assert(!fmon && !fobj && !ftrap && invent == o && !o->nobj && !o->owornmask);
    assert(!nolimbs(youracedata) && near_capacity() == UNENCUMBERED);
    nextgetobj = o; throwing = 1;
    result = dothrow(); throwing = 0;
    assert(!nextgetobj && directions == 1 && result == MOVE_STANDARD);
    assert(launches == 1 && landings == 1);
    printf("dothrow result=%d launches=%u landings=%u\n", result, launches, landings);
    assert(!invent && o->where == OBJ_FLOOR && o->ox > origin && o->oy == u.uy);
    outside(o, OBJ_FLOOR);
    {
        xchar x, y;
        assert(get_obj_location(o, &x, &y, 0) && x == o->ox && y == o->oy);
    }
    /* Genuine domove to the landing square, autopickup deliberately disabled. */
    while (u.ux < o->ox) { assert(u.ux < COLNO-2); step_east(o, 0); }
    pickup_here(o);
}
static void destroy_original(struct obj *o, const char *flow)
{
    unsigned calls, ident;
    if (!strcmp(flow, "useup")) {
        checkpoint(o, OBJ_INVENT); useup(o);
    } else {
        freeinv(o); assert(o->where == OBJ_FREE && !invent); same_record();
        if (!strcmp(flow, "delobj")) {
            place_object(o, u.ux, u.uy); outside(o, OBJ_FLOOR); delobj(o);
        } else obfree(o, NULL);
    }
    /* No access to the destroyed pointer, including no dealloc_obj observer. */
    o = NULL;
    assert(roots() == 0 && !invent && !fobj && !level.objects[u.ux][u.uy]);
    same_record(); calls = creates; ident = flags.ident;
    if (original_tag) {
        int depth, attempt;
        assert(u.curio.phase == CHAOS_CURIO_PLACED && u.curio.owner == original_id);
        for (depth = 2; depth <= 4; ++depth) for (attempt = 0; attempt < 3; ++attempt) {
            u.uz.dlevel = depth;
            chaos_curio_safe(-1); generation(); chaos_curio_safe(-1);
            assert(creates == calls && flags.ident == ident && roots() == 0);
            assert(!invent && !fobj); same_record();
        }
    }
}
int main(int argc, char **argv)
{
    char flow[32]; const char *variant, *colon;
    struct obj *o;
    assert(argc == 2);
    signal(SIGABRT, crash); signal(SIGSEGV, crash);
    test_rng_control(); test_rng_negative_control(argv[1]); setup();
    if (!strcmp(argv[1], "--record-negative-control")) {
        o = seed("active", 0); ++baseline.charges; checkpoint(o, OBJ_INVENT);
        return 1;
    }
    if (!strcmp(argv[1], "--chain-negative-control")) {
        o = seed("active", 0); freeinv(o); checkpoint(o, OBJ_FREE); return 1;
    }
    colon = strchr(argv[1], ':'); assert(colon && colon-argv[1] < (int)sizeof flow);
    memcpy(flow, argv[1], colon-argv[1]); flow[colon-argv[1]] = 0; variant = colon+1;
    o = seed(variant, !strcmp(flow,"delobj") || !strcmp(flow,"useup") || !strcmp(flow,"obfree"));
    if (!strcmp(flow, "containers")) containers(o);
    else if (!strcmp(flow, "receive")) monster_transfer(o, 0);
    else if (!strcmp(flow, "steal")) monster_transfer(o, 1);
    else if (!strcmp(flow, "throw")) physical_throw(o);
    else if (!strcmp(flow, "carry")) { step_east(o, 1); returned(o); }
    else if (!strcmp(flow,"delobj") || !strcmp(flow,"useup") || !strcmp(flow,"obfree"))
        destroy_original(o, flow);
    else assert(0 && "unknown flow");
    printf("PASS %s id=%u tag=%d charges=%d state=%d creates=%u directions=%u\n",
           argv[1], original_id, original_tag, u.curio.charges, u.curio.state, creates, directions);
    return 0;
}
