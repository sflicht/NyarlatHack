/* NGPL: exercise actual shop accounting, not a financial mock. */
#include "hack.h"
#include "chaos_curio.h"
#include "native_rng.h"
#include "lev.h"
#include <assert.h>
#include <stdio.h>
#include <execinfo.h>
#include <signal.h>
#include <unistd.h>
static void crash(int sig) {
    void *frames[30]; int n=backtrace(frames,30);
    backtrace_symbols_fd(frames,n,2); _exit(128+sig);
}
long get_cost(struct obj *, struct monst *);
long set_cost(struct obj *, struct monst *);
int dopayobj(struct monst *, struct bill_x *, struct obj **, int, BOOLEAN_P);
long addupbill(struct monst *);
void add_to_billobjs(struct obj *);
long shop_debt(struct eshk *);
long cheapest_item(struct monst *);
boolean rob_shop(struct monst *, struct obj *);
boolean inherits(struct monst *, int, int);
void saveobjchn(int, struct obj *, int);
void savemonchn(int, struct monst *, int);
void sub_one_frombill(struct obj *, struct monst *);
long *__real_alloc(unsigned int);
static unsigned allocations;
long *__wrap_alloc(unsigned int size) { ++allocations; return __real_alloc(size); }
static int prompts;
static char response = 'y';
static char output[16384];
static void text(winid w, int a, const char *s) {
    (void)w; (void)a;
    if (strlen(output)+strlen(s)+2 < sizeof output) { strcat(output,s); strcat(output,"\n"); }
}
static winid window(int type) { (void)type; return 1; }
static void display(winid w, BOOLEAN_P block) { (void)w; (void)block; }
static void destroy(winid w) { (void)w; }
static void inventory_update(void) {}
static void raw(const char *s) { text(0,0,s); }
static char answer(const char *q, const char *c, int d) {
    (void)q; (void)c; (void)d; ++prompts; return response;
}
static void object(struct obj *o, int type, int id, int tag) {
    memset(o,0,sizeof *o); o->otyp=type; o->oclass=objects[type].oc_class;
    o->obj_material=objects[type].oc_material; o->o_id=id; o->curio_tag=tag;
    o->quan=1; o->ox=o->oy=5; o->where=OBJ_FLOOR; o->dknown=1;
    objects[type].oc_name_known=1;
}
static void shop(struct monst *s) {
    memset(s,0,sizeof *s); s->data=&mons[PM_SHOPKEEPER]; s->isshk=1;
    s->mhp=s->mhpmax=10; s->mcanmove=s->mpeaceful=s->mnotlaugh=1; s->mx=s->my=5;
    viz_array[5][5]=IN_SIGHT|COULD_SEE;
    add_mx(s,MX_ESHK); ESHK(s)->shoproom=ROOMOFFSET;
    ESHK(s)->shoplevel=u.uz; ESHK(s)->shoptype=SHOPBASE;
    ESHK(s)->bill_p=ESHK(s)->bill; strcpy(ESHK(s)->shknam,"Fixture");
    fmon=s; rooms[0].resident=s; rooms[0].rtype=SHOPBASE;
    level.flags.has_shop=1; levl[5][5].roomno=ROOMOFFSET; levl[5][5].typ=ROOM;
    u.ushops[0]=ROOMOFFSET; u.ushops[1]=0; u.ux=u.uy=5;
    u.acurr.a[A_CHA]=u.amax.a[A_CHA]=12; flags.soundok=1;
}
static void reset(struct monst *s) {
    memset(ESHK(s)->bill,0,sizeof ESHK(s)->bill); ESHK(s)->billct=0;
    ESHK(s)->credit=ESHK(s)->debit=ESHK(s)->robbed=ESHK(s)->loan=0;
    prompts=0;
}
static void direct(struct monst *s, const char *mode) {
    struct obj o, before; struct chaos_curio_state state; int tag, variant;
    for(tag=1;tag<=255;++tag) for(variant=0;variant<5;++variant) {
        reset(s); object(&o,variant==4 ? GOLD_PIECE : WHISTLE,42,tag);
#ifndef GOLDOBJ
        u.ugold=1234;
#endif
        o.no_charge=variant==1; o.unpaid=variant==2; o.nomerge=variant==3;
        u.curio.disabled=variant==1; u.curio.charges=variant==2 ? 0 : 3;
        u.curio.owner=variant==3 ? 43 : 42; state=u.curio; before=o;
        if(!strcmp(mode,"buy")) addtobill(&o,TRUE,FALSE,FALSE);
        else if(!strcmp(mode,"sell")) { sellobj_state(SELL_NORMAL); sellobj(&o,5,5); }
        else if(!strcmp(mode,"theft")) assert(stolen_value(&o,5,5,TRUE,TRUE)==0);
        else if(!strcmp(mode,"use")) { check_unpaid_usage(&o,FALSE); check_unpaid_usage(&o,TRUE); }
        else if(!strcmp(mode,"stale")) {
            struct obj *op=&o; struct bill_x b, saved;
            memset(&b,0,sizeof b); b.bo_id=o.o_id; b.bquan=3; b.price=77; b.useup=1;
            saved=b; assert(dopayobj(s,&b,&op,0,TRUE)==-1);
            assert(op==&o && !memcmp(&saved,&b,sizeof b));
        } else {
            assert(!saleable(s,&o)); assert(getprice(&o,TRUE,FALSE)==0);
            assert(get_cost(&o,s)==0); assert(set_cost(&o,s)==0);
        }
        assert(!ESHK(s)->billct && !ESHK(s)->debit && !ESHK(s)->credit);
        assert(!ESHK(s)->robbed && !ESHK(s)->loan && !prompts);
#ifndef GOLDOBJ
        assert(u.ugold==1234);
#endif
        assert(!memcmp(&before,&o,sizeof o)); assert(!memcmp(&state,&u.curio,sizeof state));
    }
}
static void mixed(struct monst *s, int tagged_box, int selling) {
    struct obj box, curio, normal, coin, before; long expected, amount;
    reset(s); object(&box,SACK,10,tagged_box); object(&curio,WHISTLE,42,255);
    object(&normal,WHISTLE,11,0); object(&coin,GOLD_PIECE,12,2); coin.quan=200;
    box.cobj=&curio; curio.nobj=&normal; normal.nobj=&coin;
    curio.where=normal.where=coin.where=OBJ_CONTAINED;
    curio.ocontainer=normal.ocontainer=coin.ocontainer=&box; before=curio;
    assert(contained_gold(&box)==0);
    if(selling==2) {
        expected=get_cost(&normal,s)+(tagged_box ? 0 : get_cost(&box,s));
        assert(stolen_value(&box,5,5,TRUE,TRUE)==expected);
        assert(ESHK(s)->debit==expected && expected>0);
        ESHK(s)->debit=0;
    } else if(selling) {
        expected=set_cost(&normal,s)+(tagged_box ? 0 : set_cost(&box,s));
        amount=contained_cost(&box,s,0,TRUE,FALSE); assert(amount==set_cost(&normal,s));
        sellobj_state(SELL_NORMAL); sellobj(&box,5,5);
        assert(ESHK(s)->credit==expected*9/10+(expected<=1));
    } else {
        expected=get_cost(&normal,s);
        assert(contained_cost(&box,s,0,FALSE,FALSE)==expected);
        addtobill(&box,TRUE,FALSE,TRUE);
        assert(ESHK(s)->billct==(tagged_box ? 1 : 2));
        assert(normal.unpaid && !curio.unpaid && !coin.unpaid);
        assert(box.unpaid==!tagged_box);
    }
    assert(!memcmp(&before,&curio,sizeof curio));
    assert(!ESHK(s)->debit && !ESHK(s)->loan && !ESHK(s)->robbed);
    assert(box.cobj==&curio && curio.nobj==&normal && normal.nobj==&coin);
}
static void ordinary(struct monst *s) {
    struct obj o, *op=&o; long price;
    reset(s); object(&o,WHISTLE,11,0); o.where=OBJ_INVENT; invent=&o;
    assert(saleable(s,&o)); price=get_cost(&o,s); assert(price>0);
    addtobill(&o,TRUE,FALSE,FALSE); assert(o.unpaid && ESHK(s)->billct==1);
    assert(ESHK(s)->bill[0].price==price && ESHK(s)->bill[0].bo_id==11);
    ESHK(s)->credit=1000;
    assert(dopayobj(s,&ESHK(s)->bill[0],&op,1,FALSE)==1);
    assert(!o.unpaid && ESHK(s)->credit==1000-price);
    reset(s); o.where=OBJ_FLOOR; invent=0; sellobj_state(SELL_NORMAL); sellobj(&o,5,5);
    assert(ESHK(s)->credit>0);
    reset(s); object(&o,WHISTLE,11,0);
    assert(stolen_value(&o,5,5,TRUE,TRUE)>0 && ESHK(s)->debit>0);
    reset(s); o.unpaid=1; check_unpaid(&o); assert(ESHK(s)->debit>0);
    reset(s); object(&o,GOLD_PIECE,11,0); o.quan=50;
    addtobill(&o,TRUE,FALSE,TRUE); assert(ESHK(s)->debit==50 && ESHK(s)->loan==50);
}
/* Inject only attributable stale rows; unresolved rows are independent controls. */
static void row(struct monst *s, struct obj *o, long price, long quantity, int used) {
    struct bill_x *b=&ESHK(s)->bill[ESHK(s)->billct++];
    b->bo_id=o->o_id; b->price=price; b->bquan=quantity; b->useup=used;
    o->unpaid=!used;
}
static void dummy_test(struct monst *s) {
    struct obj o, before; unsigned id, count; int tag;
    for(tag=0;tag<=255;++tag) {
        reset(s); object(&o,WHISTLE,42,tag); o.where=OBJ_INVENT; invent=&o;
        row(s,&o,77,3,0); before=o; id=flags.ident; count=allocations;
        bill_dummy_object(&o);
        if(tag) {
            assert(allocations==count && flags.ident==id);
            assert(!billobjs && invent==&o && !memcmp(&before,&o,sizeof o));
            assert(ESHK(s)->billct==1 && ESHK(s)->bill[0].bquan==3);
        } else {
            assert(allocations>count && flags.ident>id && billobjs);
            assert(o.no_charge && !o.unpaid && doinvbill(0)>0);
            setpaid(s);
        }
    }
    invent=0;
}
static void split_test(struct monst *s) {
    struct obj o, part, before, part_before; struct bill_x saved; int variant;
    for(variant=0;variant<4;++variant) {
        reset(s); object(&o,WHISTLE,42,variant&1); object(&part,WHISTLE,43,variant&2);
        row(s,&o,77,3,0); o.quan=2; part.unpaid=1;
        before=o; part_before=part; saved=ESHK(s)->bill[0];
        splitbill(&o,&part);
        if(variant) {
            assert(ESHK(s)->billct==1 && !memcmp(&saved,ESHK(s)->bill,sizeof saved));
            assert(!memcmp(&before,&o,sizeof o) && !memcmp(&part_before,&part,sizeof part));
        } else assert(ESHK(s)->billct==2 && ESHK(s)->bill[0].bquan==2
                      && ESHK(s)->bill[1].bo_id==43 && ESHK(s)->bill[1].price==77);
    }
}
static void aggregate_test(struct monst *s, const char *mode) {
    struct obj o, normal, missing; struct obj *used;
    reset(s); object(&o,WHISTLE,42,255); o.where=OBJ_INVENT; invent=&o;
    row(s,&o,77,3,0);
    if(!strcmp(mode,"robbery")) {
        ESHK(s)->credit=100; assert(!rob_shop(s,0));
        assert(ESHK(s)->robbed==0 && s->mpeaceful && ESHK(s)->credit==100);
        assert(ESHK(s)->billct==1 && o.unpaid && o.curio_tag==255);
        /* Native credit settlement is retained for real ordinary debt. */
        reset(s); o.curio_tag=0; row(s,&o,77,3,0); ESHK(s)->credit=300;
        assert(!rob_shop(s,0)); assert(!ESHK(s)->robbed);
        invent=0; return;
    }
    used=newobj(0); object(used,WHISTLE,43,1); used->where=OBJ_FREE;
    add_to_billobjs(used); row(s,used,51,2,1);
    if(!strcmp(mode,"used-view")) {
        assert(doinvbill(0)==0); output[0]=0; doinvbill(1);
        assert(!strstr(output,"whistle"));
        assert(strstr(output,"Total:") && strstr(output,"0"));
        used->curio_tag=0; assert(doinvbill(0)==1);
        output[0]=0; doinvbill(1); assert(strstr(output,"whistle") && strstr(output,"102"));
    } else {
        assert(addupbill(s)==0 && shop_debt(ESHK(s))==0 && cheapest_item(s)==0);
        object(&normal,WHISTLE,44,0); normal.where=OBJ_INVENT; o.nobj=&normal;
        row(s,&normal,29,2,0); object(&missing,WHISTLE,45,0); row(s,&missing,17,2,0);
        ESHK(s)->debit=13; ESHK(s)->loan=7;
        assert(addupbill(s)==92 && shop_debt(ESHK(s))==105 && cheapest_item(s)==34);
        assert(ESHK(s)->billct==4 && ESHK(s)->debit==13 && ESHK(s)->loan==7);
    }
    setpaid(s); invent=0;
}
static void destruction_test(struct monst *s, const char *mode) {
    struct obj *o; struct chaos_curio_state state; int tag;
    for(tag=0;tag<2;++tag) {
        reset(s); o=newobj(0); object(o,WHISTLE,42,tag); o->where=OBJ_FREE;
        state=u.curio; row(s,o,77,3,0);
        if(!strcmp(mode,"useup")) {
            o->where=OBJ_INVENT; invent=o; o->quan=2;
            useup(o); assert(o->quan==1 && invent==o);
            if(tag) assert(addupbill(s)==0 && doinvbill(0)==0);
            useup(o); assert(!invent);
        } else if(!strcmp(mode,"dealloc")) {
            /* Raw frees also implement unload, not financial destruction. */
            dealloc_obj(o);
        } else {
            place_object(o,5,5); delobj(o); assert(!fobj && !level.objects[5][5]);
        }
        if(tag && strcmp(mode,"dealloc")) assert(!ESHK(s)->billct && !billobjs && addupbill(s)==0);
        else {
            assert(ESHK(s)->billct==1 && addupbill(s)==231);
            if(strcmp(mode,"dealloc")) assert(billobjs && doinvbill(0)==1);
        }
        assert(!memcmp(&state,&u.curio,sizeof state));
        assert(!ESHK(s)->debit && !ESHK(s)->credit && !ESHK(s)->robbed);
        setpaid(s);
    }
}
static void stale_commands(struct monst *s, const char *mode) {
    struct obj o, normal, before; struct obj *used; struct bill_x saved;
    reset(s); object(&o,WHISTLE,42,1); o.where=OBJ_INVENT; invent=&o;
    row(s,&o,77,3,0);
    if(!strcmp(mode,"surcharge")) {
        object(&normal,WHISTLE,43,0); normal.where=OBJ_INVENT; o.nobj=&normal;
        row(s,&normal,30,1,0); hot_pursuit(s);
        assert(ESHK(s)->bill[0].price==77 && ESHK(s)->bill[1].price==40);
        pacify_shk(s);
        assert(ESHK(s)->bill[0].price==77 && ESHK(s)->bill[1].price==30);
    } else if(!strcmp(mode,"inheritance")) {
#ifndef GOLDOBJ
        /* Native out-of-shop inheritance must not seize cash on a tag alone. */
        u.ushops[0]=0; u.ugold=123; s->mgold=1000;
        ESHK(s)->bill_p=(struct bill_x *)-1000;
        assert(!inherits(s,1,1)); assert(u.ugold==123 && s->mgold==1000);
        /* Ordinary billed merchandise still triggers native repossession. */
        reset(s); o.curio_tag=0; row(s,&o,77,3,0);
        assert(inherits(s,1,1)); assert(u.ugold==0 && s->mgold==1123);
        /* No debt does not prevent ordinary in-shop inheritance. */
        reset(s); o.curio_tag=1; row(s,&o,77,3,0);
        ESHK(s)->bill_p=ESHK(s)->bill;
        u.ushops[0]=ROOMOFFSET; u.ugold=123; output[0]=0;
        (void)inherits(s,1,1);
        assert(strstr(output,"gratefully inherits all your possessions"));
        assert(u.ugold==123 && s->mgold==1123);
#endif
    } else {
        invent=0; reset(s);
        used=newobj(0); object(used,WHISTLE,44,255); used->where=OBJ_FREE;
        add_to_billobjs(used); row(s,used,77,3,1); before=*used; saved=ESHK(s)->bill[0];
#ifndef GOLDOBJ
        u.ugold=500; s->mgold=1000;
#endif
        ESHK(s)->credit=1000; (void)dopay();
        assert(billobjs==used && !memcmp(&before,used,sizeof before));
        assert(ESHK(s)->billct==1 && !memcmp(&saved,ESHK(s)->bill,sizeof saved));
        assert(ESHK(s)->credit==1000);
#ifndef GOLDOBJ
        assert(u.ugold==500 && s->mgold==1000);
#endif
        used->curio_tag=0; (void)dopay();
        assert(!billobjs && !ESHK(s)->billct && ESHK(s)->credit==769);
    }
    setpaid(s); invent=0;
}
static void release_test(struct monst *s, const char *mode) {
    struct obj *box=newobj(0), *child=newobj(0);
    struct chaos_curio_state state;
    struct bill_x normal;
    reset(s); object(box,SACK,42,1); object(child,WHISTLE,43,0);
    box->where=OBJ_FREE; child->where=OBJ_CONTAINED;
    box->cobj=child; child->ocontainer=box;
    row(s,box,77,1,0); row(s,child,30,1,0); normal=ESHK(s)->bill[1];
    u.curio.version=CHAOS_CURIO_VERSION; u.curio.phase=CHAOS_CURIO_PLACED;
    u.curio.owner=42; u.curio.charges=3; u.curio.state=17;
    strcpy(u.curio.name,"test curio"); strcpy(u.curio.source,"return {}");
    u.curio.source_len=strlen(u.curio.source); state=u.curio;
    if(!strcmp(mode,"local-retirement")) {
        ESHK(s)->bill_p=(struct bill_x *)-1000;
        sub_one_frombill(box,s);
        assert(ESHK(s)->billct==1 && !memcmp(&normal,ESHK(s)->bill,sizeof normal));
        assert(child->unpaid && box->cobj==child && !billobjs);
        row(s,box,77,1,0); ESHK(s)->bill_p=0;
        sub_one_frombill(box,s);
        assert(ESHK(s)->billct==1 && !memcmp(&normal,ESHK(s)->bill,sizeof normal));
        assert(child->unpaid && box->cobj==child && !billobjs);
        ESHK(s)->bill_p=ESHK(s)->bill;
    } else if(!strcmp(mode,"destroy-container")) {
        obfree(box,0);
        assert(ESHK(s)->billct==1 && ESHK(s)->bill[0].bo_id==43);
        assert(ESHK(s)->bill[0].price==30 && ESHK(s)->bill[0].useup);
        assert(billobjs==child && !child->curio_tag && addupbill(s)==30);
        assert(!memcmp(&state,&u.curio,sizeof state));
        setpaid(s); return;
    } else if(!strcmp(mode,"save-monsters")) {
        struct monst *first=(struct monst *)alloc(sizeof *first);
        struct monst *second=(struct monst *)alloc(sizeof *second);
        memset(first,0,sizeof *first); memset(second,0,sizeof *second);
        first->data=second->data=&mons[PM_SHOPKEEPER];
        first->isshk=second->isshk=1;
        add_mx(first,MX_ESHK); add_mx(second,MX_ESHK);
        first->nmon=second; first->minvent=box;
        box->where=OBJ_MINVENT; box->ocarry=first;
        second->minvent=newobj(0);
        object(second->minvent,WHISTLE,44,255);
        second->minvent->where=OBJ_MINVENT; second->minvent->ocarry=second;
        fmon=first;
        /* Frees each shopkeeper's extra data before its inventory, and
         * leaves fmon pointing at the freed first monster during the second. */
        savemonchn(0,first,FREE_SAVE);
        fmon=s;
        assert(ESHK(s)->billct==2 && !memcmp(&normal,&ESHK(s)->bill[1],sizeof normal));
        assert(!memcmp(&state,&u.curio,sizeof state));
        return;
    } else {
        /* A raw release must never walk the global monster chain. */
        fmon=(struct monst *)1;
        saveobjchn(0,box,FREE_SAVE);
        fmon=s;
        assert(ESHK(s)->billct==2 && !memcmp(&normal,&ESHK(s)->bill[1],sizeof normal));
        assert(!memcmp(&state,&u.curio,sizeof state));
        return;
    }
    box->cobj=0; child->where=OBJ_FREE;
    dealloc_obj(child); dealloc_obj(box);
    assert(!memcmp(&state,&u.curio,sizeof state));
}
static void cash_test(struct monst *s) {
#ifndef GOLDOBJ
    struct obj o, before; long price; int tag;
    for(tag=0;tag<=255;++tag) {
        reset(s); object(&o,WHISTLE,42,tag); s->mgold=1000; u.ugold=123;
        price=set_cost(&o,s); before=o;
        sellobj_state(SELL_NORMAL); sellobj(&o,5,5);
        assert(u.ugold==123+price && s->mgold==1000-price && !ESHK(s)->credit);
        if(tag) assert(!memcmp(&before,&o,sizeof o) && !prompts);
        else assert(price>0 && o.shopOwned && !o.unpaid);
    }
#endif
}
static void pickup_test(struct monst *s, int partial) {
#ifndef GOLDOBJ
    struct obj *o; struct chaos_curio_state state; long amount, capacity; int tag;
    for(tag=0;tag<2;++tag) {
        reset(s); u.ugold=0; u.acurr.a[A_STR]=u.amax.a[A_STR]=12;
        u.acurr.a[A_CON]=u.amax.a[A_CON]=12;
        capacity=(long)max_capacity()*-100L-51L; assert(capacity>0);
        amount=partial ? capacity+200 : 50;
        o=newobj(0); object(o,GOLD_PIECE,42,tag); o->quan=amount;
        o->where=OBJ_FREE; place_object(o,5,5); state=u.curio;
        assert(pickup_object(o,amount,FALSE)==1);
        assert(u.ugold==(partial ? capacity : amount));
        assert(ESHK(s)->debit==(tag ? 0 : u.ugold) && ESHK(s)->loan==ESHK(s)->debit);
        assert(!ESHK(s)->billct && !ESHK(s)->robbed && !ESHK(s)->credit);
        if(partial) {
            assert(fobj==o && o->quan==200 && o->curio_tag==tag);
            delobj(o);
        }
        assert(!fobj && !level.objects[5][5]);
        assert(!memcmp(&state,&u.curio,sizeof state));
    }
#endif
}
/* Preserve topology for theft: a native no-charge shell has the same zero
 * shell price as a protected shell.  Do not 'fix' legacy recursive arithmetic. */
static void nested_test(struct monst *s, const char *mode) {
    struct obj outer, middle, inner, leaf, protected, saved[3];
    long expected, actual, control=0; int tagged_outer, pass;
    for(tagged_outer=0;tagged_outer<2;++tagged_outer) for(pass=0;pass<3;++pass) {
        reset(s); object(&outer,SACK,10,pass ? tagged_outer : 0);
        object(&middle,pass==2 ? GOLD_PIECE : SACK,11,pass ? 255 : 0); object(&inner,SACK,12,0);
        object(&leaf,WHISTLE,13,0); object(&protected,WHISTLE,42,1);
        outer.cobj=&middle; middle.cobj=&inner; inner.cobj=&leaf;
        leaf.nobj=pass ? &protected : 0;
        middle.where=inner.where=leaf.where=protected.where=OBJ_CONTAINED;
        middle.ocontainer=&outer; inner.ocontainer=&middle;
        leaf.ocontainer=protected.ocontainer=&inner;
        if(!pass) { middle.no_charge=1; outer.no_charge=tagged_outer; }
        saved[0]=outer; saved[1]=middle; saved[2]=protected;
        if(!strcmp(mode,"nested-theft")) {
            actual=stolen_value(&outer,5,5,TRUE,TRUE);
            if(!pass) control=actual;
            else assert(actual==control && actual>0 && ESHK(s)->debit==actual);
        } else if(!pass) continue;
        else if(!strcmp(mode,"nested-buy")) {
            addtobill(&outer,TRUE,FALSE,TRUE);
            assert(ESHK(s)->billct==(tagged_outer ? 2 : 3));
            assert(inner.unpaid && leaf.unpaid && !middle.unpaid && !protected.unpaid);
            expected=get_cost(&inner,s)+get_cost(&leaf,s)+(tagged_outer ? 0 : get_cost(&outer,s));
            outer.where=OBJ_INVENT; invent=&outer;
            assert(addupbill(s)==expected && expected>0); invent=0; outer.where=OBJ_FLOOR;
        } else {
#ifndef GOLDOBJ
            s->mgold=1000; u.ugold=0;
            expected=set_cost(&inner,s)+set_cost(&leaf,s)+(tagged_outer ? 0 : set_cost(&outer,s));
            sellobj_state(SELL_NORMAL); sellobj(&outer,5,5);
            assert(u.ugold==expected && expected>0 && s->mgold==1000-expected);
            assert(!ESHK(s)->credit);
#endif
        }
        if(pass) {
            if(tagged_outer) assert(!memcmp(&saved[0],&outer,sizeof outer));
            assert(!memcmp(&saved[1],&middle,sizeof middle));
            assert(!memcmp(&saved[2],&protected,sizeof protected));
            assert(outer.cobj==&middle && middle.cobj==&inner && inner.cobj==&leaf);
        }
    }
}
/* Compare native topology rather than duplicating recursive pricing rules. */
static void container_theft(struct monst *s, const char *mode) {
    struct obj box, shell, normal, gold, before;
    long control=0, actual; int pass;
    int coin=!strcmp(mode,"coin-shell-theft");
    int nested=!strcmp(mode,"unpaid-nested-theft");
    for(pass=0;pass<2;++pass) {
        reset(s); object(&box,coin && pass ? GOLD_PIECE : SACK,10,coin && pass);
        object(&shell,SACK,42,pass); object(&normal,WHISTLE,11,0);
        object(&gold,GOLD_PIECE,12,0); gold.quan=37;
        box.no_charge=1; shell.no_charge=1;
        box.cobj=coin ? &normal : &shell;
        if(nested) { shell.cobj=&normal; row(s,&normal,17,1,0); }
        else shell.nobj=&normal;
        normal.nobj=&gold;
        shell.where=normal.where=gold.where=OBJ_CONTAINED;
        shell.ocontainer=&box; normal.ocontainer=gold.ocontainer=nested ? &shell : &box;
        if(!coin && pass) shell.unpaid=1;
        if(coin) box.quan=900;
        before=coin ? box : shell;
        actual=stolen_value(&box,5,5,TRUE,TRUE);
        printf("%s pass=%d value=%ld control=%ld\n",mode,pass,actual,control); fflush(stdout);
        if(!pass) { control=actual; assert(control>0); }
        else {
            assert(actual==control && ESHK(s)->debit==control);
            assert(!memcmp(&before,coin ? &box : &shell,sizeof before));
        }
    }
    if(coin) {
        reset(s); object(&gold,GOLD_PIECE,12,0); gold.quan=900;
        assert(stolen_value(&gold,5,5,TRUE,TRUE)==900 && ESHK(s)->debit==900);
    }
}
static void aggregate_sale(struct monst *s, const char *mode) {
#ifndef GOLDOBJ
    struct obj box, a, b, returned, before, ca, cb;
    struct chaos_curio_state state;
    long cash=0, credit=0; int pass, type, control_prompts=0;
    int funds=(!strcmp(mode,"aggregate-zero") || !strcmp(mode,"aggregate-credit-decline")) ? 0 : !strcmp(mode,"aggregate-short") ? 5 : 1000;
    int decline=(!strcmp(mode,"aggregate-decline") || !strcmp(mode,"aggregate-credit-decline")), dont=!strcmp(mode,"aggregate-dontsell");
    int types[]={SACK,GOLD_PIECE,TALLOW_CANDLE,FOOD_RATION,BALL};
    ESHK(s)->shoptype=WEAPONSHOP;
    u.curio.version=CHAOS_CURIO_VERSION; u.curio.phase=CHAOS_CURIO_PLACED;
    u.curio.owner=42; u.curio.charges=3; u.curio.state=17;
    strcpy(u.curio.name,"test curio"); strcpy(u.curio.source,"return {}");
    u.curio.source_len=strlen(u.curio.source); state=u.curio;
    for(type=0;type<(int)(sizeof types/sizeof types[0]);++type) for(pass=0;pass<2;++pass) {
        reset(s); object(&box,pass ? types[type] : SACK,42,pass ? 255 : 0);
        object(&a,ARROW,11,0); object(&b,ARROW,13,0); a.quan=b.quan=5;
        box.cobj=&a; a.nobj=&b; a.where=b.where=OBJ_CONTAINED;
        a.ocontainer=b.ocontainer=&box; box.dknown=0;
        object(&returned,ARROW,15,0); returned.where=OBJ_CONTAINED;
        returned.ocontainer=&box; b.nobj=&returned; row(s,&returned,17,1,0);
        if(pass) { box.unpaid=1; box.ostolen=1; box.oeaten=1; }
        assert(!saleable(s,&box));
        assert(set_cost(&a,s)==5 && set_cost(&b,s)==5);
        a.sknown=b.sknown=0; before=box;
        s->mgold=funds; u.ugold=123; response=decline ? 'n' : 'y';
        sellobj_state(dont ? SELL_DONTSELL : SELL_DELIBERATE); sellobj(&box,5,5);
        printf("%s type=%d pass=%d cash=%ld credit=%ld prompts=%d\n",mode,types[type],pass,u.ugold-123,ESHK(s)->credit,prompts); fflush(stdout);
        if(!pass) {
            cash=u.ugold; credit=ESHK(s)->credit; ca=a; cb=b; control_prompts=prompts;
            assert(credit==(!funds && !decline && !dont ? 9 : 0));
            assert(cash==123+(decline || dont ? 0 : funds==5 ? 5 : funds ? 10 : 0));
        } else {
            assert(cash==u.ugold && credit==ESHK(s)->credit && prompts==control_prompts);
            assert(a.no_charge==ca.no_charge && b.no_charge==cb.no_charge);
            assert(a.unpaid==ca.unpaid && b.unpaid==cb.unpaid);
            assert(a.shopOwned==ca.shopOwned && b.shopOwned==cb.shopOwned);
            assert(!memcmp(&before,&box,sizeof box));
            assert(!memcmp(&state,&u.curio,sizeof state));
        }
        assert(s->mgold==funds-(u.ugold-123));
        assert(!returned.unpaid && !ESHK(s)->billct);
    }
#endif
}
int main(int argc, char **argv) {
    struct monst s;
    signal(SIGSEGV,crash);
    test_rng_control(); if(argc>1) test_rng_negative_control(argv[1]);
    init_objects(); init_gods(); vision_init(); urace.malenum=PM_HUMAN; urole.malenum=PM_WIZARD;
    u.umonnum=u.umonster=PM_HUMAN; youmonst.data=&mons[PM_HUMAN]; u.uhp=10;
    windowprocs.win_putstr=text; windowprocs.win_raw_print=raw; windowprocs.win_yn_function=answer;
    windowprocs.win_create_nhwindow=window; windowprocs.win_display_nhwindow=display;
    windowprocs.win_destroy_nhwindow=destroy; windowprocs.win_update_inventory=inventory_update;
    flags.ident=100;
    shop(&s);
    if(argc==1 || !strcmp(argv[1],"ordinary")) ordinary(&s);
    else if(!strcmp(argv[1],"mixed-buy")) mixed(&s,0,0);
    else if(!strcmp(argv[1],"mixed-sell")) mixed(&s,0,1);
    else if(!strcmp(argv[1],"tagged-box-buy")) mixed(&s,1,0);
    else if(!strcmp(argv[1],"tagged-box-sell")) mixed(&s,1,1);
    else if(!strcmp(argv[1],"mixed-theft")) mixed(&s,0,2);
    else if(!strcmp(argv[1],"tagged-box-theft")) mixed(&s,1,2);
    else if(!strcmp(argv[1],"dummy")) dummy_test(&s);
    else if(!strcmp(argv[1],"split")) split_test(&s);
    else if(!strcmp(argv[1],"totals") || !strcmp(argv[1],"robbery") || !strcmp(argv[1],"used-view")) aggregate_test(&s,argv[1]);
    else if(!strcmp(argv[1],"destroy") || !strcmp(argv[1],"useup") || !strcmp(argv[1],"dealloc")) destruction_test(&s,argv[1]);
    else if(!strcmp(argv[1],"cash")) cash_test(&s);
    else if(!strcmp(argv[1],"local-retirement") || !strcmp(argv[1],"save-release") || !strcmp(argv[1],"save-monsters") || !strcmp(argv[1],"destroy-container")) release_test(&s,argv[1]);
    else if(!strcmp(argv[1],"surcharge") || !strcmp(argv[1],"pay-command") || !strcmp(argv[1],"inheritance")) stale_commands(&s,argv[1]);
    else if(!strcmp(argv[1],"pickup-full")) pickup_test(&s,0);
    else if(!strcmp(argv[1],"pickup-partial")) pickup_test(&s,1);
    else if(!strncmp(argv[1],"nested-",7)) nested_test(&s,argv[1]);
    else if(!strncmp(argv[1],"aggregate-",10)) aggregate_sale(&s,argv[1]);
    else if(!strcmp(argv[1],"unpaid-floor-theft") || !strcmp(argv[1],"unpaid-nested-theft") || !strcmp(argv[1],"coin-shell-theft")) container_theft(&s,argv[1]);
    else direct(&s,argv[1]);
    rem_all_mx(&s); puts("native shop accounting OK"); return 0;
}
