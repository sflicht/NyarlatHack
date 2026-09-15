/* NGPL: actual doapply, Lua and native Sanity; controlled selection/window port. */
#define _GNU_SOURCE
#include "hack.h"
#include "chaos.h"
#include "chaos_curio.h"
#include "chaos_lua.h"
#include "native_rng.h"
#include <stdio.h>
#include <errno.h>
#include <unistd.h>
/* Weak only so the pre-implementation RED fixture links the original engine. */
extern int chaos_curio_apply(struct obj *, int *) __attribute__((weak));
extern struct obj *nextgetobj;
static char output[8192], receipt[160];
static struct chaos_curio_state before_warning;
static int watching, warned, sanity_calls, expected_delta, event_calls, warning_sanity;
static int lua_calls, write_failure, failed_writes;
ssize_t __real_write(int, const void *, size_t);
ssize_t __wrap_write(int fd, const void *buf, size_t n)
{
    if (write_failure && memmem(buf,n,"applied requested=",sizeof "applied requested="-1)) {
        ++failed_writes; errno=EIO; return -1;
    }
    return __real_write(fd,buf,n);
}
int __real_chaos_lua_curio_apply(const char *, size_t,
    const struct chaos_curio_lua_context *, struct chaos_curio_lua_intent *);
int __wrap_chaos_lua_curio_apply(const char *s, size_t n,
    const struct chaos_curio_lua_context *c, struct chaos_curio_lua_intent *r)
{
    ++lua_calls; return __real_chaos_lua_curio_apply(s,n,c,r);
}
int __real_touch_artifact(struct obj *, struct monst *, BOOLEAN_P);
int __wrap_touch_artifact(struct obj *o, struct monst *m, BOOLEAN_P hypothetical)
{
    assert(!o->curio_tag);
    return __real_touch_artifact(o,m,hypothetical);
}
void __real_change_usanity(int, BOOLEAN_P);
void __real_chaos_event(const char *, const char *, const char *);
static void text(winid w, int a, const char *s)
{
    (void)w; (void)a;
    assert(strlen(output)+strlen(s)+2 < sizeof output);
    strcat(output,s); strcat(output,"\n");
    if (watching && strstr(s,"requests a Sanity change")) {
        assert(!memcmp(&before_warning,&u.curio,sizeof u.curio));
        assert(u.usanity==warning_sanity);
        assert(!sanity_calls); ++warned;
    }
}
static void raw(const char *s) { text(0,0,s); }
void __wrap_change_usanity(int delta, BOOLEAN_P check)
{
    assert(warned==1 && check==FALSE && delta==expected_delta);
    assert(u.curio.charges==before_warning.charges-1);
    ++sanity_calls;
    __real_change_usanity(delta,check);
}
void __wrap_chaos_event(const char *event, const char *key, const char *detail)
{
    if (!strcmp(event,"curio")) {
        assert(!strcmp(key,"result"));
        assert(strlen(detail)<sizeof receipt); strcpy(receipt,detail); ++event_calls;
    }
    /* Actual transport is intentionally uninitialized: effects must still commit. */
    __real_chaos_event(event,key,detail);
}
static void source(const char *body)
{
    memset(u.curio.source,0,sizeof u.curio.source);
    snprintf(u.curio.source,sizeof u.curio.source,
        "return {name='Counter %%s',inspect=function(c) return 'Quiet.' end,apply=function(c) %s end}",body);
    u.curio.source_len=strlen(u.curio.source);
}
static void fixture(struct obj *o)
{
    memset(o,0,sizeof *o); o->otyp=WHISTLE; o->oclass=TOOL_CLASS;
    o->quan=1; o->o_id=42; o->curio_tag=1; o->invlet='a';
    o->where=OBJ_INVENT; invent=o;
    memset(&u.curio,0,sizeof u.curio); u.curio.version=1;
    u.curio.phase=CHAOS_CURIO_PLACED; u.curio.owner=42; u.curio.charges=3;
    strcpy(u.curio.name,"Counter %s");
    source("return {text='Literal %s %n.',state=c.state+1,sanity_delta=-2}");
    u.usanity=73; u.uinsight=19; u.umadness=0;
    output[0]=receipt[0]=0; watching=warned=sanity_calls=event_calls=0;
}
static int command(struct obj *o)
{
    int result;
    nextgetobj=o; result=doapply(); assert(!nextgetobj); return result;
}
static void inert(struct obj *o, int native)
{
    struct chaos_curio_state saved=u.curio;
    struct obj saved_obj=*o;
    int sanity=u.usanity, next=test_rng_begin(), result=123, calls=lua_calls;
    long turn=moves;
    output[0]=0;
    if (native) result=command(o);
    else assert(chaos_curio_apply(o,&result));
    assert(result==MOVE_CANCELLED);
    assert(!strcmp(output,"This curio is inert.\n"));
    assert(!memcmp(&saved,&u.curio,sizeof saved));
    if (memcmp(&saved_obj,o,sizeof saved_obj)) {
        size_t k;
        fprintf(stderr,"object changed native=%d tag=%d type=%d\n",native,o->curio_tag,o->otyp);
        for(k=0;k<sizeof saved_obj;k++) if(((unsigned char *)&saved_obj)[k]!=((unsigned char *)o)[k])
            fprintf(stderr,"byte %zu: %u -> %u\n",k,((unsigned char *)&saved_obj)[k],((unsigned char *)o)[k]);
    }
    assert(!memcmp(&saved_obj,o,sizeof saved_obj));
    assert(sanity==u.usanity && turn==moves);
    assert(lua_calls==calls);
    test_rng_unchanged(next);
}
static void success(struct obj *o, int delta, int actual, int state, int native)
{
    int result=123, sanity=u.usanity, hp, en;
    struct obj saved=*o;
    char expected[160];
    /* Deliberately stale maxima prove the native routine recalculates both. */
    calc_total_maxhp(); calc_total_maxen(); hp=u.uhpmax; en=u.uenmax;
    u.uhpmax=999; u.uenmax=999;
    before_warning=u.curio; output[0]=receipt[0]=0;
    warning_sanity=u.usanity;
    watching=1; warned=sanity_calls=event_calls=0; expected_delta=delta;
    if (native) result=command(o);
    else assert(chaos_curio_apply(o,&result));
    watching=0;
    assert(result==MOVE_STANDARD && warned==1 && sanity_calls==1);
    assert(u.curio.charges==before_warning.charges-1 && u.curio.state==state);
    assert(u.usanity==sanity+actual && u.uhpmax==hp && u.uenmax==en);
    assert(!memcmp(&saved,o,sizeof saved));
    before_warning.charges--; before_warning.state=state;
    assert(!memcmp(&before_warning,&u.curio,sizeof u.curio));
    snprintf(expected,sizeof expected,"applied requested=%d actual=%d",delta,actual);
    assert(event_calls==1 && !strcmp(receipt,expected));
    assert(strstr(output,"Literal %s %n."));
}
static void failures(struct obj *o)
{
    static const char *bad[]={
        "return {text='PARTIAL',state=4,sanity_delta=3}",
        "return {text='PARTIAL',state=256,sanity_delta=0}",
        "return {text='PARTIAL',state=1,sanity_delta=0,extra=1}",
        "return {text='PARTIAL',state=1}",
        "return {text='PARTIAL',state=true,sanity_delta=0}",
        "return {text='PARTIAL',state=1.0,sanity_delta=0}",
        "return {text='bad\\27',state=1,sanity_delta=0}",
        "return {text=' ',state=1,sanity_delta=0}",
        "while true do end",
        "local t={} while true do t[#t+1]={} end",
        "return unavailable()"
    };
    unsigned i;
    for(i=0;i<sizeof bad/sizeof *bad;i++) {
        char body[1024]; struct chaos_curio_state saved;
        struct chaos_curio_lua_context c={73,19,3,0};
        struct chaos_curio_lua_intent intent;
        fixture(o);
        snprintf(body,sizeof body,"if c.state==0 then return {text='Fine',state=1,sanity_delta=0} end %s",bad[i]);
        source(body); assert(chaos_curio_valid(&u.curio));
        assert(!chaos_lua_curio_apply(u.curio.source,u.curio.source_len,&c,&intent));
        u.curio.state=1; saved=u.curio;
        assert(command(o)==MOVE_CANCELLED);
        assert(!strcmp(output,"This curio is inert.\n"));
        assert(!sanity_calls && u.usanity==73);
        saved.disabled=1; assert(!memcmp(&saved,&u.curio,sizeof saved));
        inert(o,1); inert(o,0);
    }
}
int main(int argc, char **argv)
{
    struct obj o, fake;
    struct monst sleeper;
    int i, tag, result=123;
    test_rng_control(); if(argc>1) test_rng_negative_control(argv[1]);
    init_objects(); init_gods(); urace.malenum=PM_HUMAN; urole.malenum=PM_WIZARD;
    u.umonnum=u.umonster=PM_HUMAN; youmonst.data=&mons[PM_HUMAN];
    u.ulevel=1; u.uhp=u.uhprolled=20; u.uen=u.uenrolled=20;
    for(i=0;i<A_MAX;i++) ABASE(i)=AMAX(i)=12;
    u.ux=10;u.uy=10; moves=101;
    init_artifacts(); windowprocs.win_putstr=text; windowprocs.win_raw_print=raw;
    /* RED checks the real native command before the not-yet-present helper. */
    fixture(&o); o.curio_tag=2; inert(&o,1);
    assert(chaos_curio_apply);
    fixture(&o); o.curio_tag=0;
    assert(!chaos_curio_apply(&o,&result) && result==123);
    assert(!chaos_curio_apply(0,&result) && result==123);
    for(tag=1;tag<=255;tag++) {
        fixture(&o); o.curio_tag=tag;
        if(tag==1) u.curio.disabled=1;
        inert(&o,0); inert(&o,1);
        o.oartifact=ART_EXCALIBUR; o.ostolen=1;
        o.owt=weight(&o); /* Native capacity check refreshes artifact weight. */
        u.sealsActive=SEAL_ANDROMALIUS;
        inert(&o,1); assert(u.sealsActive==SEAL_ANDROMALIUS);
        o.otyp=GOLD_PIECE; o.oclass=COIN_CLASS; o.owt=weight(&o); inert(&o,1);
        u.sealsActive=0;
    }
    for(i=0;i<19;i++) {
        fixture(&o);
        switch(i) {
        case 0:o.otyp=LONG_SWORD;break;
        case 1:o.quan=2;break;
        case 2:o.quan=0;break;
        case 3:o.o_id++;break;
        case 4:u.curio.owner=0;break;
        case 5:u.curio.phase=CHAOS_CURIO_EXPIRED;break;
        case 6:o.where=OBJ_FLOOR;break;
        case 7:invent=0;break;
        case 8:fake=o; invent=&fake;break;
        case 9:u.curio.disabled=1;break;
        case 10:u.curio.charges=0;break;
        case 11:u.curio.version++;break;
        case 12:u.curio.source_len=4097;break;
        case 13:u.curio.source[5]=0;break;
        case 14:u.curio.source_len=0;break;
        case 15:u.curio.state=256;break;
        case 16:u.curio.charges=4;break;
        case 17:u.curio.name[0]='X';break;
        case 18:source("return {}"); u.curio.source[0]='!';break;
        }
        inert(&o,0); inert(&o,1);
    }
    fixture(&o);
    success(&o,-2,-2,1,0); success(&o,-2,-2,2,1);
    success(&o,-2,-2,3,1); inert(&o,1);
    fixture(&o);
    source("if c.sanity~=73 or c.insight~=19 or c.charges~=3 or c.state~=0 then return {} end c.charges=0; c.sanity=0; c.insight=0; return {text='Literal %s %n.',state=255,sanity_delta=2}");
    success(&o,2,2,255,1); assert(u.uinsight==19);
    fixture(&o); source("return {text='Literal %s %n.',state=7,sanity_delta=0}");
    success(&o,0,0,7,0);
    fixture(&o); u.usanity=100;
    source("return {text='Literal %s %n.',state=9,sanity_delta=2}");
    success(&o,2,0,9,1);
    fixture(&o); u.usanity=50; success(&o,-2,0,1,1);
    fixture(&o); u.usanity=51; success(&o,-2,-1,1,1);
    failures(&o);
    /* Real native whistle wakes this nearby monster and updates its dog record. */
    memset(&sleeper,0,sizeof sleeper); sleeper.data=&mons[PM_LITTLE_DOG];
    sleeper.mhp=sleeper.mhpmax=10; sleeper.mx=11;sleeper.my=10;
    sleeper.msleeping=1;sleeper.mcanmove=1; add_mx(&sleeper,MX_EDOG);
    fmon=&sleeper;
    fixture(&o); success(&o,-2,-2,1,1);
    assert(sleeper.msleeping && EDOG(&sleeper)->whistletime==0);
    for(tag=1;tag<=255;tag++) {
        o.curio_tag=tag; u.curio.disabled=1; inert(&o,1);
        assert(sleeper.msleeping && EDOG(&sleeper)->whistletime==0);
    }
    o.curio_tag=0; watching=0; (void)command(&o);
    assert(!sleeper.msleeping && EDOG(&sleeper)->whistletime==moves);
    rem_all_mx(&sleeper); fmon=0;
    if (argc>1 && (!strcmp(argv[1],"--receipt-failure") || !strcmp(argv[1],"--receipts"))) {
        fixture(&o); u.uz.dlevel=1; u.ualign.god=1;
        chaos_start(); write_failure=!strcmp(argv[1],"--receipt-failure");
        success(&o,-2,-2,1,1);
        if (write_failure) assert(failed_writes>0);
        success(&o,-2,-2,2,1); success(&o,-2,-2,3,1);
        inert(&o,1);
    }
    puts("curio apply: native dispatch, atomic intents, three uses, native Sanity and inert guards passed");
    return 0;
}
