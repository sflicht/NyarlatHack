/* NGPL: native copy/split lifecycle, actual owned engine objects. */
#include "hack.h"
#include "chaos_curio.h"
#include "native_rng.h"
#include <stdio.h>
extern struct obj *nextgetobj;
static char output[8192];
static void text(winid w, int a, const char *s)
{
    (void)w; (void)a;
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
    strcpy(u.curio.name,"Copy counter");
    strcpy(u.curio.source,"return {name='Copy counter',inspect=function(c) return 'Original' end,apply=function(c) return {text='Used',state=18,sanity_delta=0} end}");
    u.curio.source_len=strlen(u.curio.source);
    assert(chaos_curio_valid(&u.curio));
    if(variant==1) u.curio.disabled=1;
    if(variant==2) u.curio.charges=0;
    if(variant==3) u.curio.owner++;
    if(variant==4) { o->otyp=LONG_SWORD; o->oclass=WEAPON_CLASS; o->owt=weight(o); }
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
static void copies(void)
{
    int tag, same, variant;
    for(tag=0;tag<=255;tag++) for(same=0;same<2;same++)
    for(variant=0;variant<5;variant++) {
        struct obj *o=object(WHISTLE,tag), *copy;
        struct chaos_curio_state saved;
        struct obj before;
        unsigned id;
        int next;
        addinv(o); record(o,variant); saved=u.curio; before=*o; id=flags.ident;
        next=test_rng_begin(); copy=duplicate_obj(o,same);
        test_rng_unchanged(next);
        assert(copy!=o && copy->o_id==id && flags.ident==id+1);
        assert(copy->quan==o->quan && copy->otyp==o->otyp);
        assert(!copy->owornmask && !copy->oextra_p && !copy->mp);
        assert(copy->curio_tag==(tag?CHAOS_CURIO_INERT_REMNANT:0));
        assert(o->curio_tag==tag);
        if(same) { assert(o->nobj==copy && copy->nobj==before.nobj); before.nobj=copy; }
        else assert(copy->where==OBJ_FREE && !copy->nobj);
        assert(!memcmp(&before,o,sizeof before));
        assert(!memcmp(&saved,&u.curio,sizeof saved));
        if(!same) addinv(copy);
        if(tag) {
            inert(copy);
            /* Even colliding IDs and a now-valid record cannot confer authority. */
            copy->o_id=o->o_id; record(copy,0); inert(copy); u.curio=saved;
        }
        if(tag==1 && variant==0) {
            char description[161];
            assert(chaos_curio_matches(o));
            assert(!strcmp(chaos_curio_name(o),"Copy counter"));
            chaos_curio_inspect(o,description); assert(!strcmp(description,"Original"));
            assert(command(o)==MOVE_STANDARD);
            saved.charges--; saved.state=18;
            assert(!memcmp(&saved,&u.curio,sizeof saved));
        }
        discard(copy); discard(o);
    }
    puts("copy: all tags, both chains, five states, source execution and ID collision passed");
}
static void splits(void)
{
    int tag, location;
    for(tag=0;tag<=255;tag++) for(location=0;location<3;location++) {
        struct obj *o=object(WHISTLE,tag), *copy, *box=0;
        struct chaos_curio_state saved;
        unsigned id;
        int next;
        o->quan=2; o->owt=weight(o); record(o,0); saved=u.curio;
        if(location==0) addinv(o);
        if(location==1) place_object(o,10,10);
        if(location==2) { box=object(BOX,0); add_to_container(box,o); }
        assert(!chaos_curio_matches(o)); id=flags.ident;
        next=test_rng_begin(); copy=splitobj(o,1L); test_rng_unchanged(next);
        /* The original was an INVALID stack; quantity reduction is not admission. */
        assert(o->curio_tag==(tag?CHAOS_CURIO_INERT_REMNANT:0));
        assert(copy->curio_tag==(tag?CHAOS_CURIO_INERT_REMNANT:0));
        assert(copy->o_id==id && flags.ident==id+1 && o->o_id==saved.owner);
        assert(o->quan==1 && copy->quan==1 && o->nobj==copy);
        assert(o->owt==(unsigned)weight(o) && copy->owt==(unsigned)weight(copy));
        assert(copy->where==o->where && !copy->owornmask);
        if(location==1) assert(level.objects[10][10]==o && o->nexthere==copy);
        if(location==2) assert(box->cobj==o && copy->ocontainer==box);
        assert(!memcmp(&saved,&u.curio,sizeof saved));
        if(tag) {
            if(location) { obj_extract_self(o); obj_extract_self(copy); addinv(o); addinv(copy); }
            inert(o); inert(copy);
            copy->o_id=saved.owner; inert(copy);
        }
        discard(copy); discard(o); if(box) discard(box);
    }
    puts("split: all tags, inventory/floor/container, original cannot promote, state unchanged");
}
static void nested(void)
{
    int tagged_box, same;
    for(tagged_box=0;tagged_box<2;tagged_box++) for(same=0;same<2;same++) {
        struct obj *box=object(BOX,tagged_box?255:0);
        struct obj *inner=object(BOX,0), *leaf=object(WHISTLE,tagged_box?0:1);
        struct obj *copy, *child;
        struct chaos_curio_state saved;
        int next;
        add_to_container(inner,leaf); add_to_container(box,inner);
        place_object(box,10,10); record(leaf,0); saved=u.curio;
        next=test_rng_begin(); copy=duplicate_obj(box,same); test_rng_unchanged(next);
        child=copy->cobj;
        assert(child && child!=inner && child->cobj && child->cobj!=leaf);
        assert(box->cobj==inner && inner->cobj==leaf && !inner->nobj && !leaf->nobj);
        assert(child->ocontainer==copy && child->cobj->ocontainer==child);
        assert(!child->nobj && !child->cobj->nobj);
        assert(copy->curio_tag==(tagged_box?2:0) && child->curio_tag==0);
        assert(child->cobj->curio_tag==(tagged_box?0:2));
        if(same) assert(box->nobj==copy && box->nexthere==copy && copy->where==OBJ_FLOOR);
        else assert(copy->where==OBJ_FREE && !copy->nobj && !copy->nexthere);
        assert(!memcmp(&saved,&u.curio,sizeof saved));
        if(tagged_box) inert(copy); else inert(child->cobj);
        discard(copy); /* Must not own or free the original descendants. */
        assert(inner->cobj==leaf && leaf->where==OBJ_CONTAINED);
        discard(box);
    }
    puts("nested copy: independent native chains, ordinary shells and ordinary descendants passed");
}
static void ordinary(void)
{
    struct obj *o=object(WHISTLE,1), *copy;
    struct monst sleeper;
    int next;
    addinv(o); record(o,0);
    next=test_rng_begin(); copy=duplicate_obj(o,TRUE); test_rng_unchanged(next);
    memset(&sleeper,0,sizeof sleeper); sleeper.data=&mons[PM_LITTLE_DOG];
    sleeper.mhp=sleeper.mhpmax=10; sleeper.mx=11; sleeper.my=10;
    sleeper.msleeping=sleeper.mcanmove=1; add_mx(&sleeper,MX_EDOG); fmon=&sleeper;
    discard(o); /* Destruction of the original never licenses its copy. */
    copy->o_id=u.curio.owner;
    inert(copy);
    assert(sleeper.msleeping && !EDOG(&sleeper)->whistletime);
    discard(copy);
    o=object(WHISTLE,0); addinv(o);
    next=test_rng_begin(); copy=duplicate_obj(o,TRUE); test_rng_unchanged(next);
    (void)command(copy); /* Native whistle action cost is not curio policy. */
    assert(!sleeper.msleeping && EDOG(&sleeper)->whistletime==moves);
    rem_all_mx(&sleeper); fmon=0; discard(copy); discard(o);
    o=object(ARROW,0); addinv(o); o->quan=2; o->owt=weight(o);
    copy=splitobj(o,1); o->nomerge=copy->nomerge=0;
    assert(merged(&o,&copy) && o->quan==2 && !o->curio_tag); discard(o);
    puts("ordinary: copied whistle wakes native dog; split arrows merge");
}
int main(int argc, char **argv)
{
    int i;
    test_rng_control(); if(argc>1) test_rng_negative_control(argv[1]);
    init_objects(); init_gods(); urace.malenum=PM_HUMAN; urole.malenum=PM_WIZARD;
    u.umonnum=u.umonster=PM_HUMAN; youmonst.data=&mons[PM_HUMAN];
    u.ulevel=1; u.uhp=u.uhprolled=20; u.uen=u.uenrolled=20;
    for(i=0;i<A_MAX;i++) ABASE(i)=AMAX(i)=12;
    u.ux=u.uy=10; u.usanity=73; u.uinsight=19; moves=101; init_artifacts();
    windowprocs.win_putstr=text; windowprocs.win_raw_print=raw;
    windowprocs.win_update_inventory=inventory_display;
    if(argc>1 && !strcmp(argv[1],"split")) splits();
    else if(argc>1 && !strcmp(argv[1],"nested")) nested();
    else if(argc>1 && !strcmp(argv[1],"ordinary")) ordinary();
    else copies();
    assert(!invent && !fobj);
    return 0;
}
