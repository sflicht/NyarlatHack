/* NGPL: real merge APIs and dobinding ritual; no selector/effect replacement. */
#include "hack.h"
#include "chaos_curio.h"
#include "native_rng.h"
#include <stdio.h>
#include <stdlib.h>

extern int dobinding(int, int);
static char output[16384];
static void text(winid w, int a, const char *s)
{
    (void)w; (void)a;
    assert(strlen(output)+strlen(s)+2 < sizeof output);
    strcat(output,s); strcat(output,"\n");
}
static void raw(const char *s) { text(0,0,s); }
static void inventory_display(void) {}
static void clear(winid w) { (void)w; }
static void show(winid w, BOOLEAN_P b) { (void)w; (void)b; }
static void cursor(winid w, int x, int y) { (void)w; (void)x; (void)y; }
static void glyph(winid w, XCHAR_P x, XCHAR_P y, int g) { (void)w; (void)x; (void)y; (void)g; }
static void clip(int x, int y) { (void)x; (void)y; }
static void record(struct obj *o, int variant)
{
    memset(&u.curio,0,sizeof u.curio);
    u.curio.version=CHAOS_CURIO_VERSION;
    u.curio.phase=CHAOS_CURIO_PLACED; u.curio.owner=o->o_id;
    u.curio.charges=3; u.curio.state=17;
    strcpy(u.curio.name,"Carrier counter");
    strcpy(u.curio.source,"return {name='Carrier counter',inspect=function(c) return 'Quiet' end,apply=function(c) return {text='Used',state=18,sanity_delta=0} end}");
    u.curio.source_len=strlen(u.curio.source);
    assert(chaos_curio_valid(&u.curio));
    if(variant==1) u.curio.charges=0;
    if(variant==2) u.curio.disabled=1;
    if(variant==3) u.curio.owner++;
    if(variant==4) u.curio.version=999;
}
static struct obj *object(int type, int tag)
{
    struct obj *o=mksobj(type,NO_MKOBJ_FLAGS);
    assert(o); o->quan=1; o->nomerge=0; o->curio_tag=tag;
    o->spe=0; o->blessed=o->cursed=0; o->owt=weight(o);
    return o;
}
static void pair(int type, int tag, int order, struct obj **a, struct obj **b)
{
    unsigned id;
    *a=object(type,0); *b=object(type,0);
    id=(*b)->o_id; **b=**a; (*b)->o_id=id;
    (order ? *b : *a)->curio_tag=tag;
}
static void merges(void)
{
    static const int types[]={ARROW,GOLD_PIECE,WHISTLE};
    unsigned t; int tag,order,v;
    for(t=0;t<SIZE(types);t++) for(tag=1;tag<=255;tag++)
    for(order=0;order<2;order++) for(v=0;v<5;v++) {
        struct obj *a,*b,*aa,*bb,sa,sb;
        struct chaos_curio_state saved;
        int next;
        pair(types[t],tag,order,&a,&b); aa=a; bb=b;
        record(order?b:a,v); saved=u.curio;
        /* sknown would be propagated by the old eligibility routine. */
        a->sknown=1; sa=*a; sb=*b;
        next=test_rng_begin();
        assert(!merged(&a,&b));
        assert(!merge_choice(a,b) && !merge_choice(b,a));
        assert(a==aa && b==bb);
        assert(!memcmp(a,&sa,sizeof sa) && !memcmp(b,&sb,sizeof sb));
        assert(!memcmp(&saved,&u.curio,sizeof saved));
        test_rng_unchanged(next);
        obfree(a,0); obfree(b,0);
    }
    /* Actual ordinary merges, not just eligibility or table assertions. */
    for(t=0;t<2;t++) for(order=0;order<2;order++) {
        struct obj *a,*b; pair(types[t],0,order,&a,&b);
        assert(merge_choice(a,b)==a); assert(merged(&a,&b));
        assert(a->quan==2 && !a->curio_tag); obfree(a,0);
    }
    puts("merge matrix: all nonzero tags, both orders, five record states; ordinary arrows/coins merge");
}
static void ritual(int tag, int variant, int order, int noise)
{
    struct obj *a=object(WHISTLE,tag), *b=object(APPLE,noise==1?tag:0);
    struct obj *c=0,*d=0,*o;
    struct obj sa,sb;
    struct chaos_curio_state saved;
    unsigned aid=a->o_id,bid=b->o_id;
    int founda=0,foundb=0,success=(!tag || noise==2);
    struct engr *ep;
    if(variant==5) { a->otyp=GOLD_PIECE; a->oclass=COIN_CLASS; }
    if(variant==6) a->quan=2;
    record(a,variant); saved=u.curio;
    make_engr_at(11,10,"",moves,DUST);
    ep=engr_at(11,10); assert(ep);
    ep->ward_id=ANDROMALIUS; ep->complete_wards=1; ep->halu_ward=0;
    if(noise==2) {
        c=object(DAGGER,0); d=object(BELL,0);
        place_object(d,11,10); place_object(c,11,10);
        b->curio_tag=tag;
    }
    place_object(order?a:b,11,10); place_object(order?b:a,11,10);
    sa=*a; sb=*b;
    test_rng_reset(); srandom(124);
    (void)dobinding(11,10); /* Actual selection, reward, binding and consumption. */
    assert(!memcmp(&saved,&u.curio,sizeof saved));
    assert(!!(u.sealsActive & SEAL_ANDROMALIUS)==success);
    assert(u.sealCounts==success);
    assert(u.sealTimeout[ANDROMALIUS-FIRST_SEAL]==(success?moves+5000:0));
    assert((invent != 0 || fmon != 0)==success); /* real item or tame-rat reward */
    for(o=level.objects[11][10];o;o=o->nexthere) {
        if(o->o_id==aid) founda=1;
        if(o->o_id==bid) foundb=1;
        if(noise==2) assert(o!=c && o!=d);
    }
    if(tag) {
        assert(founda && foundb);
        /* List links can change when ordinary offerings behind them vanish. */
        sa.nobj=a->nobj; sa.nexthere=a->nexthere;
        sb.nobj=b->nobj; sb.nexthere=b->nexthere;
        assert(!memcmp(a,&sa,sizeof sa) && !memcmp(b,&sb,sizeof sb));
    } else assert(!founda && !foundb);
    assert(!!strstr(output,"hands reach down")==success);
    fputs(output,stdout);
    printf("ritual tag=%d variant=%d order=%d noise=%d binding/reward=%d protected=%d\n",
        tag,variant,order,noise,success,tag!=0);
}
int main(int argc, char **argv)
{
    int i;

    test_rng_control(); if(argc>1) test_rng_negative_control(argv[1]);
    init_objects(); init_gods(); vision_init(); urace.malenum=PM_HUMAN; urole.malenum=PM_WIZARD;
    u.umonnum=u.umonster=PM_HUMAN; youmonst.data=&mons[PM_HUMAN];
    u.ulevel=1; u.uhp=u.uhprolled=20; u.uen=u.uenrolled=20;
    for(i=0;i<A_MAX;i++) ABASE(i)=AMAX(i)=12;
    u.ux=10; u.uy=10; moves=101; u.usanity=73;
    levl[10][10].typ=levl[11][10].typ=ROOM;
    init_artifacts(); windowprocs.win_putstr=text; windowprocs.win_raw_print=raw;
    windowprocs.win_update_inventory=inventory_display;
    windowprocs.win_clear_nhwindow=clear; windowprocs.win_display_nhwindow=show;
    windowprocs.win_curs=cursor; windowprocs.win_print_glyph=glyph;
    windowprocs.win_cliparound=clip;
    if(argc==6) ritual(atoi(argv[2]),atoi(argv[3]),atoi(argv[4]),atoi(argv[5]));
    else merges();
    return 0;
}
