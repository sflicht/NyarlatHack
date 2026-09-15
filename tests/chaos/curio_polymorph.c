/* NGPL: genuine poly_obj/core/randpoly_obj; no replacement engine functions. */
#include "hack.h"
#include "chaos_curio.h"
#include "native_rng.h"
#include <stdio.h>
#include <execinfo.h>
#include <signal.h>
#include <unistd.h>
static void crash(int sig)
{
    void *frames[30]; int n=backtrace(frames,30);
    backtrace_symbols_fd(frames,n,2); _exit(128+sig);
}
extern struct obj *nextgetobj;
/* Test-only globalized copy of zap.o exposes the real internal core. */
extern struct obj *poly_obj_core(struct obj *, int);
static char output[8192];
static void text(winid w, int a, const char *s)
{
    (void)w; (void)a;
    if (strstr(s,"mkclass called with bad class")) crash(SIGSEGV);
    assert(strlen(output)+strlen(s)+2 < sizeof output);
    strcat(output,s); strcat(output,"\n");
}
static void raw(const char *s) { text(0,0,s); }
static void inventory_display(void) {}
static struct obj *object(int type, int tag)
{
    struct obj *o=mksobj(type,MKOBJ_NOINIT);
    assert(o && !o->cobj && !o->oextra_p && !o->timed && !o->light);
    o->quan=1; o->curio_tag=tag; o->nomerge=1; o->owt=weight(o);
    return o;
}
static void record(struct obj *o, int variant)
{
    memset(&u.curio,0,sizeof u.curio);
    u.curio.version=CHAOS_CURIO_VERSION; u.curio.phase=CHAOS_CURIO_PLACED;
    u.curio.owner=o->o_id; u.curio.charges=2; u.curio.state=17;
    strcpy(u.curio.name,"Poly counter");
    strcpy(u.curio.source,"return {name='Poly counter',inspect=function(c) return 'Original' end,apply=function(c) return {text='Used',state=18,sanity_delta=0} end}");
    u.curio.source_len=strlen(u.curio.source);
    if(variant==1) u.curio.disabled=1;
    if(variant==2) u.curio.charges=0;
    if(variant==3) u.curio.owner++;
    if(variant==4) { o->otyp=LONG_SWORD; o->oclass=WEAPON_CLASS; }
    if(variant==5) o->quan=2;
    o->owt=weight(o);
}
static void discard(struct obj *o) { obj_extract_self(o); obfree(o,0); }
static int command(struct obj *o)
{
    int result; output[0]=0; nextgetobj=o; result=doapply();
    assert(!nextgetobj); return result;
}
static void inert(struct obj *o)
{
    struct chaos_curio_state saved=u.curio;
    char description[161];
    int result=123, next=test_rng_begin(), sanity=u.usanity;
    long turn=moves;
    assert(chaos_curio_tagged(o) && !chaos_curio_matches(o));
    assert(!strcmp(chaos_curio_name(o),"inert curio"));
    assert(strstr(xname(o),"inert curio"));
    chaos_curio_inspect(o,description);
    assert(!strcmp(description,"This curio is inert."));
    assert(chaos_curio_apply(o,&result) && result==MOVE_CANCELLED);
    if(o->where==OBJ_INVENT) {
        assert(command(o)==MOVE_CANCELLED);
        assert(!strcmp(output,"This curio is inert.\n"));
    }
    assert(!memcmp(&saved,&u.curio,sizeof saved));
    assert(sanity==u.usanity && turn==moves);
    test_rng_unchanged(next);
}
static void no_program(struct obj *o)
{
    struct chaos_curio_state saved=u.curio;
    int move=123, next=test_rng_begin();
    assert(!o->curio_tag && !chaos_curio_matches(o));
    assert(!chaos_curio_apply(o,&move) && move==123);
    assert(!memcmp(&saved,&u.curio,sizeof saved));
    test_rng_unchanged(next);
}
static void locate(struct obj *o, int location, struct obj **box)
{
    *box=0;
    if(location==0) addinv(o);
    if(location==1) place_object(o,10,10);
    if(location==2) {
        *box=object(BOX,0); addinv(*box); add_to_container(*box,o);
    }
}
static void chain(struct obj *o, int location, struct obj *box)
{
    if(location==0) assert(invent==o && o->where==OBJ_INVENT);
    if(location==1) assert(fobj==o && level.objects[10][10]==o && o->where==OBJ_FLOOR);
    if(location==2) assert(box->cobj==o && o->ocontainer==box && o->where==OBJ_CONTAINED);
}
static void matrix(int retain)
{
    int tag, location, same, variant;
    for(tag=0;tag<=255;tag++) for(location=0;location<3;location++)
    for(same=0;same<2;same++) for(variant=0;variant<6;variant++) {
        struct obj *o, *n, *box;
        struct chaos_curio_state saved;
        unsigned old_id;
        /* All tags; extra invalid-state combinations on representative tags. */
        if(variant && tag!=0 && tag!=1 && tag!=2 && tag!=255) continue;
        o=object(WHISTLE,tag); record(o,variant); saved=u.curio; old_id=o->o_id;
        locate(o,location,&box);
        n=retain ? poly_obj_core(o,same?WHISTLE:ARROW) : poly_obj(o,same?WHISTLE:ARROW);
        assert(n!=o && n->o_id!=old_id && n->otyp==(same?WHISTLE:ARROW));
        assert(n->quan==(same?1:(variant==5?2:1)));
        chain(n,location,box); no_program(n);
        assert(!memcmp(&saved,&u.curio,sizeof saved));
        if(retain) {
            /* Core intentionally leaves old allocation alive, but not its identity. */
            assert(o->where==OBJ_FREE);
            addinv(o);
            if(tag) {
                /* This is the RED: baseline can execute this retained original. */
                inert(o);
                assert(o->curio_tag==CHAOS_CURIO_INERT_REMNANT);
                o->otyp=WHISTLE; o->oclass=TOOL_CLASS; o->quan=1;
                o->o_id=saved.owner; inert(o);
            } else assert(!o->curio_tag);
            discard(o);
        }
        /* A same-ID native replacement remains ordinary, even on reverse poly. */
        n->o_id=saved.owner; no_program(n);
        n=poly_obj(n,same?ARROW:WHISTLE); chain(n,location,box);
        n->o_id=saved.owner; no_program(n);
        n=poly_obj(n,WHISTLE); n->o_id=saved.owner; no_program(n);
        assert(!memcmp(&saved,&u.curio,sizeof saved));
        discard(n); if(box) discard(box);
    }
    puts(retain ? "core: all tags; retained originals inert; inventory/floor/container; invalid states; collisions/reverse/repeated poly" : "explicit: all tags; native replacements, chains, quantity, record/latch/source/charges preserved");
}
struct outcome {
    int type, material, spe, recharged, blessed, cursed, bknown, erosion;
    unsigned weight;
    long quantity, worn;
    int draws, next;
};
static struct outcome random_result(int seed, int tag, int location)
{
    struct obj *o=object(WHISTLE,tag), *n, *box;
    struct chaos_curio_state saved;
    struct outcome result;
    output[0]=0;
    record(o,0); saved=u.curio; locate(o,location,&box);
    o->blessed=o->bknown=1; o->recharged=2; o->spe=2;
    if(!location) setuwep(o);
    test_rng_reset(); srandom((unsigned)seed);
    n=randpoly_obj(o);
    memset(&result,0,sizeof result);
    result.draws=reseed_count; result.next=rn2(100000);
    assert(result.draws>0); /* Native polymorph is intentionally not RNG-pure. */
    chain(n,location,box); no_program(n);
    if(!location) assert(!uwep && !n->owornmask);
    result.type=n->otyp; result.material=n->obj_material; result.spe=n->spe;
    result.recharged=n->recharged; result.blessed=n->blessed;
    result.cursed=n->cursed; result.bknown=n->bknown; result.erosion=n->oeroded;
    result.weight=n->owt; result.quantity=n->quan; result.worn=n->owornmask;
    assert(!memcmp(&saved,&u.curio,sizeof saved));
    discard(n); if(box) discard(box);
    return result;
}
static void randoms(void)
{
    int seed, location, i, tags[]={1,2,255};
    for(seed=0;seed<32;seed++) for(location=0;location<3;location++) {
        struct outcome ordinary=random_result(seed,0,location);
        for(i=0;i<3;i++) {
            struct outcome tagged=random_result(seed,tags[i],location);
            assert(!memcmp(&ordinary,&tagged,sizeof ordinary));
        }
    }
    puts("random: seeds 0..31, all three locations, ordinary/generated/inert/unknown; equal selected native fields, draw counts, and next draw; inventory unwear");
}
static void whistle(void)
{
    struct obj *o=object(WHISTLE,1), *n, *copy;
    struct chaos_curio_state saved;
    struct monst sleeper;
    char description[161];
    addinv(o); record(o,0); assert(chaos_curio_valid(&u.curio));
    chaos_curio_inspect(o,description); assert(!strcmp(description,"Original"));
    assert(command(o)==MOVE_STANDARD && u.curio.charges==1 && u.curio.state==18);
    saved=u.curio;
    copy=duplicate_obj(o,TRUE);
    /* Transforming a nonowner sharing the ID must not disable the owner. */
    copy->o_id=o->o_id; n=poly_obj(copy,WHISTLE); no_program(n); discard(n);
    assert(!memcmp(&saved,&u.curio,sizeof saved));
    chaos_curio_inspect(o,description); assert(!strcmp(description,"Original"));
    memset(&sleeper,0,sizeof sleeper); sleeper.data=&mons[PM_LITTLE_DOG];
    sleeper.mhp=sleeper.mhpmax=10; sleeper.mx=11; sleeper.my=10;
    sleeper.msleeping=sleeper.mcanmove=1; add_mx(&sleeper,MX_EDOG); fmon=&sleeper;
    n=poly_obj_core(o,WHISTLE); n->o_id=saved.owner;
    addinv(o); inert(o);
    assert(sleeper.msleeping && !EDOG(&sleeper)->whistletime);
    no_program(n); (void)command(n);
    assert(!sleeper.msleeping && EDOG(&sleeper)->whistletime==moves);
    assert(!memcmp(&saved,&u.curio,sizeof saved));
    rem_all_mx(&sleeper); fmon=0; discard(o); discard(n);
    puts("whistle: real prior Lua use; colliding copy cannot disable owner; old core object inert; same-type replacement is genuinely native, not a curio");
}
int main(int argc, char **argv)
{
    int i;
    signal(SIGSEGV,crash);
    test_rng_control(); if(argc>1) test_rng_negative_control(argv[1]);
    init_objects(); init_gods(); vision_init();
    urace=races[str2race("human")]; urole=roles[str2role("Wizard")];
    /* Isolated ordinary dungeon: zero-initialized special branches are in
     * slot zero.  Do not accidentally run quest monster generation when a
     * random tool needs a native figurine monster type. */
    u.uz.dnum=1; u.uz.dlevel=2;
    dungeons[1].depth_start=1; dungeons[1].num_dunlevs=20;
    u.umonnum=u.umonster=PM_HUMAN; youmonst.data=&mons[PM_HUMAN];
    u.ulevel=1; u.uhp=u.uhprolled=20; u.uen=u.uenrolled=20;
    for(i=0;i<A_MAX;i++) ABASE(i)=AMAX(i)=12;
    u.ux=u.uy=10; u.usanity=73; u.uinsight=19; moves=101; init_artifacts();
    windowprocs.win_putstr=text; windowprocs.win_raw_print=raw;
    windowprocs.win_update_inventory=inventory_display;
    if(argc>1 && !strcmp(argv[1],"explicit")) matrix(0);
    else if(argc>1 && !strcmp(argv[1],"random")) randoms();
    else if(argc>1 && !strcmp(argv[1],"whistle")) whistle();
    else matrix(1);
    assert(!invent && !fobj);
    return 0;
}
