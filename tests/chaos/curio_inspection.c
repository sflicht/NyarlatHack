/* NGPL: linked native UI with a deterministic window-port fixture, no Lua mocks. */
#include "hack.h"
#include "chaos_curio.h"
#include <assert.h>
#include <stdio.h>
#include "native_rng.h"
/* Native quantity-aware sibling is local to objnam.c's declarations. */
char *xname2(struct obj *, BOOLEAN_P);
static char output[8192];
static char action_prompt[BUFSZ];
static int prompts, encyclopedias, applies;
static anything choice;
static void text(winid w,int a,const char *s) { (void)w;(void)a; strcat(output,s);strcat(output,"\n"); }
static winid create(int t) { (void)t; return 1; }
static void noop(winid w) { (void)w; }
static void show(winid w,int b) { (void)w;(void)b; }
static void end(winid w,const char *s) {
    (void)w;
    if (s && !strncmp(s,"Do what with ",13)) strcpy(action_prompt,s);
}
static void line(const char *p,char *b) { (void)p; ++prompts; strcpy(b,"Renamed"); }
static void menu(winid w,int g,const anything *a,int c,int d,int at,const char *s,int b) {
    (void)w;(void)g;(void)c;(void)d;(void)at;(void)b;
    if(a && (a->a_void==(genericptr_t)dotypeinv || (c=='a' && (strstr(s,"Counter") || strstr(s,"inert curio"))))) choice=*a;
    if(!strcmp(s,"Apply")) ++applies;
    assert(!strstr(s,"Blow this whistle"));
}
static int select_one(winid w,int how,menu_item **m) {
    (void)w;(void)how; *m=malloc(sizeof **m); (*m)->item=choice; (*m)->count=1; return 1;
}
/* Native inventory picker and commands use the controlled window port. */
void __wrap_checkfile(char *s,struct permonst *p,int a,int b,winid *w) {
    (void)s;(void)p;(void)a;(void)b;(void)w; ++encyclopedias;
}
static void fixture(struct obj *o) {
    memset(o,0,sizeof *o); o->otyp=WHISTLE; o->oclass=TOOL_CLASS;
    o->quan=1; o->o_id=42; o->curio_tag=1; o->invlet='a'; o->where=OBJ_INVENT; invent=o;
    memset(&u.curio,0,sizeof u.curio); u.curio.version=1;u.curio.phase=CHAOS_CURIO_PLACED;
    u.curio.owner=42;u.curio.charges=3;strcpy(u.curio.name,"Counter %s");
    strcpy(u.curio.source,"return {name='Counter %s',inspect=function(c) return 'Quiet %s %n.' end,apply=function(c) return {text='No.',state=0,sanity_delta=0} end}");
    u.curio.source_len=strlen(u.curio.source);
    output[0]=0;
}
static void inspect(struct obj *o,const char *expected,int ui) {
    struct you before=u; struct obj ob=*o; int next; long turn=moves; winid w=1;
    output[0]=0; action_prompt[0]=0; next=test_rng_begin();
    if(ui<0) describe_item(o,o->otyp,o->oartifact,&w);
    else { iflags.item_use_menu=ui;ddoinv(); }
    if (!strstr(output,expected)) fprintf(stderr,"ui=%d expected=%s output=%s\n",ui,expected,output);
    assert(strstr(output,expected)); assert(!strstr(output,"whistle"));
    assert(!memcmp(&before,&u,sizeof u)); assert(!memcmp(&ob,o,sizeof ob));
    assert(moves==turn);
    test_rng_unchanged(next);
    assert(!encyclopedias);
}
static void expect_name(const char *actual, const char *expected) {
    if (strcmp(actual,expected)) fprintf(stderr,"expected [%s], got [%s]\n",expected,actual);
    assert(!strcmp(actual,expected));
}
static void descname_check(struct obj *o, const char *expected) {
    struct obj before=*o;
    struct you player=u;
    struct objclass type=objects[o->otyp];
    char discoveries[sizeof output], *name;
    long turn=moves;
    int count, next=test_rng_begin();
    output[0]=0; count=disp_artifact_discoveries(1); strcpy(discoveries,output);
    name=obj_descname(o); expect_name(name,expected);
    name[0]='X'; /* Native callers own a writable buffer, not cached metadata. */
    assert(!memcmp(&before,o,sizeof before));
    assert(!memcmp(&player,&u,sizeof u));
    assert(!memcmp(&type,&objects[o->otyp],sizeof type));
    assert(moves==turn && invent==o);
    output[0]=0; assert(disp_artifact_discoveries(1)==count);
    expect_name(output,discoveries);
    test_rng_unchanged(next);
}
static void descname_regression(const char *which) {
    struct obj o;
    int tag, variant;
    fixture(&o);
    if (!strcmp(which,"descname-eyes")) {
        memset(u.curio.name,0,sizeof u.curio.name); strcpy(u.curio.name,"Eyes");
        memset(u.curio.source,0,sizeof u.curio.source);
        strcpy(u.curio.source,"return {name='Eyes',inspect=function(c) return 'Watching.' end,apply=function(c) return {text='No.',state=0,sanity_delta=0} end}");
        u.curio.source_len=strlen(u.curio.source);
    }
    assert(chaos_curio_valid(&u.curio));
    if (!strcmp(which,"descname-ordinary")) {
        o.curio_tag=0; o.dknown=1; o.known=1;
        objects[WHISTLE].oc_name_known=1;
        o.quan=2; descname_check(&o,"tiny mysterious whistle");
        return;
    }
    o.known=o.bknown=o.rknown=o.sknown=1; o.blessed=1; o.lamplit=1;
    objects[WHISTLE].oc_name_known=1;
    o.oartifact=ART_EXCALIBUR;
    discover_artifact(ART_EXCALIBUR); discover_artifact(ART_MAGICBANE);
    if (!strcmp(which,"descname-controls")) {
        /* Every nonzero tag; quantity must be checked before singular display. */
        for (tag=1; tag<=255; ++tag) for (variant=0; variant<5; ++variant) {
            o.curio_tag=tag; o.otyp=WHISTLE; o.o_id=42;
            o.quan=variant<3 ? variant : 1;
            if (variant==3) o.otyp=LONG_SWORD;
            if (variant==4) o.o_id++;
            descname_check(&o,tag==1 && variant==1 ? "Counter %s" : "inert curio");
        }
    } else descname_check(&o,u.curio.name);
}
static void encyc_check(struct obj *o, const char *expected) {
    struct obj before=*o;
    struct you player=u; /* Includes the exact cached name and complete source. */
    struct objclass type=objects[o->otyp];
    char discoveries[sizeof output], *name;
    long turn=moves;
    int count, next=test_rng_begin();
    assert(check_oprop(o,OPROP_GSSDW));
    output[0]=0; count=disp_artifact_discoveries(1); strcpy(discoveries,output);
    name=encyc_xname(o); expect_name(name,expected);
    /* The ordinary special phrase is intentionally still a native literal. */
    if (o->curio_tag) name[0]='X';
    assert(!memcmp(&before,o,sizeof before));
    assert(!memcmp(&player,&u,sizeof u));
    assert(!memcmp(&type,&objects[o->otyp],sizeof type));
    assert(moves==turn && invent==o);
    output[0]=0; assert(disp_artifact_discoveries(1)==count);
    expect_name(output,discoveries);
    test_rng_unchanged(next);
}
static void encyc_regression(const char *which) {
    struct obj o;
    char expected[BUFSZ];
    int tag, variant, known, artifact;
    fixture(&o);
    /* Install the property before inventory placement, as native creation does. */
    invent=0; o.where=OBJ_FREE;
    add_oprop(&o,OPROP_GSSDW);
    o.where=OBJ_INVENT; invent=&o;
    assert(check_oprop(&o,OPROP_GSSDW));
    if (!strcmp(which,"encyc-eyes")) {
        memset(u.curio.name,0,sizeof u.curio.name); strcpy(u.curio.name,"Eyes");
        memset(u.curio.source,0,sizeof u.curio.source);
        strcpy(u.curio.source,"return {name='Eyes',inspect=function(c) return 'Watching.' end,apply=function(c) return {text='No.',state=0,sanity_delta=0} end}");
        u.curio.source_len=strlen(u.curio.source);
    }
    assert(chaos_curio_valid(&u.curio));
    discover_artifact(ART_EXCALIBUR); discover_artifact(ART_MAGICBANE);
    if (!strcmp(which,"encyc-ordinary")) {
        o.curio_tag=0; o.otyp=LONG_SWORD; o.oclass=WEAPON_CLASS;
        o.dknown=1; objects[LONG_SWORD].oc_name_known=1;
        for (known=0; known<2; ++known) for (artifact=0; artifact<2; ++artifact) {
            o.known=known; o.oartifact=artifact ? ART_EXCALIBUR : 0;
            strcpy(expected,known && !artifact ? "gith silver sword" : xname_bland(&o));
            encyc_check(&o,expected);
        }
        return;
    }
    if (!strcmp(which,"encyc-controls")) {
        /* Original quantity and binding, every tag, with/without native ID/artifact. */
        for (tag=1; tag<=255; ++tag) for (variant=0; variant<6; ++variant)
        for (known=0; known<2; ++known) for (artifact=0; artifact<2; ++artifact) {
            o.curio_tag=tag; o.otyp=WHISTLE; o.oclass=TOOL_CLASS; o.o_id=42;
            o.quan=variant<3 ? variant : 1;
            o.known=known; o.oartifact=artifact ? ART_EXCALIBUR : 0;
            u.curio.phase=variant==5 ? CHAOS_CURIO_EXPIRED : CHAOS_CURIO_PLACED;
            if (variant==3) { o.otyp=LONG_SWORD; o.oclass=WEAPON_CLASS; }
            if (variant==4) o.o_id++;
            encyc_check(&o,tag==1 && variant==1 ? "Counter %s" : "inert curio");
        }
    } else {
        o.known=1;
        encyc_check(&o,u.curio.name);
    }
}
/* Public naming wrappers must retain identity, not just its native carrier. */
static void finalnames_check(struct obj *o, int helper, const char *expected) {
    struct obj before=*o;
    struct you player=u;
    struct objclass type=objects[o->otyp];
    struct flag saved_flags=flags;
    struct instance_flags saved_iflags=iflags;
    char discoveries[sizeof output];
    const char *name;
    long turn=moves;
    int count, next=test_rng_begin();
    output[0]=0; count=disp_artifact_discoveries(1); strcpy(discoveries,output);
    switch (helper) {
    case 0: name=ysimple_name(o); break;
    case 1: name=Ysimple_name2(o); break;
    case 2: name=cloak_simple_name(o); break;
    case 3: name=aobjnam(o,"fall"); break;
    case 4: name=Tobjnam(o,"fall"); break;
    case 5: name=killer_xname(o); break;
    case 6: name=yname(o); break;
    case 7: name=Yname2(o); break;
    case 8: name=mshot_xname(o); break;
    default: name=distant_name(o,xname); break;
    }
    expect_name(name,expected);
    if (helper!=2 || o->curio_tag) ((char *)name)[0]='X';
    assert(!memcmp(&before,o,sizeof before));
    assert(!memcmp(&player,&u,sizeof u));
    assert(!memcmp(&saved_flags,&flags,sizeof flags));
    assert(!memcmp(&saved_iflags,&iflags,sizeof iflags));
    assert(!memcmp(&type,&objects[o->otyp],sizeof type));
    assert(moves==turn && invent==o);
    output[0]=0; assert(disp_artifact_discoveries(1)==count);
    expect_name(output,discoveries); test_rng_unchanged(next);
}
static void finalnames_regression(const char *which) {
    struct obj o;
    char expected[BUFSZ];
    int tag, variant, i, known;
    int cloak=strstr(which,"cloak")!=0;
    const int types[]={ROBE,PRAYER_WARDED_WRAPPING,MUMMY_WRAPPING,ALCHEMY_SMOCK,CLOAK};
    fixture(&o);
    if (strstr(which,"eyes")) {
        memset(u.curio.name,0,sizeof u.curio.name); strcpy(u.curio.name,"Eyes");
        memset(u.curio.source,0,sizeof u.curio.source);
        strcpy(u.curio.source,"return {name='Eyes',inspect=function(c) return 'Watching.' end,apply=function(c) return {text='No.',state=0,sanity_delta=0} end}");
        u.curio.source_len=strlen(u.curio.source);
    }
    assert(chaos_curio_valid(&u.curio));
    if (strstr(which,"ordinary")) {
        o.curio_tag=0; o.dknown=o.known=1; objects[WHISTLE].oc_name_known=1;
        if (!cloak) {
            finalnames_check(&o,0,"your whistle");
            finalnames_check(&o,1,"Your whistle");
            o.where=OBJ_FREE;
            finalnames_check(&o,0,"the whistle");
            finalnames_check(&o,1,"The whistle");
        } else {
            expect_name(cloak_simple_name(0),"cloak");
            for(i=0;i<SIZE(types);++i) for(known=0;known<2;++known) {
                o.otyp=types[i]; o.dknown=known; objects[o.otyp].oc_name_known=known;
                finalnames_check(&o,2,i==0 ? "robe" : i<3 ? "wrapping" : i==3 ? (known ? "smock" : "apron") : "cloak");
            }
        }
        return;
    }
    if (strstr(which,"wrappers")) {
        finalnames_check(&o,3,"Counter %s falls");
        finalnames_check(&o,4,"The Counter %s falls");
        finalnames_check(&o,5,"a Counter %s");
        finalnames_check(&o,6,"your Counter %s");
        finalnames_check(&o,7,"Your Counter %s");
        m_shot.n=2; m_shot.i=2; m_shot.o=WHISTLE;
        finalnames_check(&o,8,"the 2nd Counter %s");
        finalnames_check(&o,9,"Counter %s");
        return;
    }
    if (strstr(which,"controls")) {
        invent=0; o.where=OBJ_FREE;
        add_oprop(&o,OPROP_GSSDW);
        o.where=OBJ_INVENT; invent=&o;
        o.known=o.dknown=o.bknown=o.rknown=o.sknown=1;
        o.blessed=o.lamplit=1; o.oartifact=ART_EXCALIBUR;
        discover_artifact(ART_EXCALIBUR);
        /* All tags, but only one dimension at a time for binding failures. */
        for(tag=1;tag<=255;++tag) {
            o.curio_tag=tag;
            finalnames_check(&o,cloak ? 2 : 0,tag==1 ? (cloak ? "Counter %s" : "your Counter %s") : (cloak ? "inert curio" : "your inert curio"));
        }
        o.curio_tag=1;
        for(variant=0;variant<9;++variant) {
            o.otyp=WHISTLE; o.quan=1; o.o_id=42; u.curio.phase=CHAOS_CURIO_PLACED;
            if(variant<2) o.quan=variant ? 2 : 0;
            else if(variant==2) o.o_id++;
            else if(variant==3) u.curio.phase=CHAOS_CURIO_EXPIRED;
            else o.otyp=types[variant-4];
            finalnames_check(&o,cloak ? 2 : 0,cloak ? "inert curio" : "your inert curio");
            if(!cloak) finalnames_check(&o,1,"Your inert curio");
        }
    } else if(cloak) finalnames_check(&o,2,u.curio.name);
    else {
        sprintf(expected,"your %s",u.curio.name); finalnames_check(&o,0,expected);
        expected[0]='Y'; finalnames_check(&o,1,expected);
        o.where=OBJ_FREE;
        sprintf(expected,"the %s",u.curio.name); finalnames_check(&o,0,expected);
        expected[0]='T'; finalnames_check(&o,1,expected);
    }
}
static void inspection_context_regression(const char *which) {
    struct obj o;
    fixture(&o);
    if (!strcmp(which,"inspect-inventory-where")) {
        o.where=OBJ_FLOOR;
        assert(invent==&o && chaos_curio_valid(&u.curio));
        inspect(&o,"This curio is inert.",-1);
        assert(invent==&o);
        return;
    }
    u.usanity=73; u.uinsight=19; u.curio.charges=2; u.curio.state=41;
    memset(u.curio.source,0,sizeof u.curio.source);
    strcpy(u.curio.source,"return {name='Counter %s',inspect=function(c) local text=c.sanity..':'..c.insight..':'..c.charges..':'..c.state; c.sanity=0; c.insight=0; c.charges=0; c.state=0; return text end,apply=function(c) return {text='No.',state=0,sanity_delta=0} end}");
    u.curio.source_len=strlen(u.curio.source);
    assert(chaos_curio_valid(&u.curio));
    for (int ui=-1; ui<2; ++ui) inspect(&o,"73:19:2:41",ui);
}
static void xprname_regression(const char *which, long quantity) {
    struct obj o, before;
    struct you player;
    char expected[BUFSZ];
    const char *txt = !strcmp(which,"xprname-text") ? "Literal %s" : 0;
    int next, dot, cost, fixed;
    long turn=moves;
    fixture(&o); o.quan=quantity; o.bknown=1; o.blessed=1; uwep=&o;
    before=o; player=u; next=test_rng_begin();
    for (fixed=0; fixed<2; ++fixed) for (dot=0; dot<2; ++dot) for (cost=0; cost<2; ++cost) {
        const char *body=txt ? txt : "a blessed inert curio (weapon in hand)";
        flags.invlet_constant=fixed;
        if (cost) sprintf(expected,"%c - %-45s %6ld zorkmids",dot && fixed ? 'a' : 'b',body,7L);
        else sprintf(expected,"%c - %s%s",fixed ? 'a' : 'b',body,dot ? "." : "");
        expect_name(xprname(&o,txt,'b',dot, cost ? 7L : 0L,1L),expected);
        assert(!memcmp(&before,&o,sizeof o));
    }
    flags.invlet_constant=0;
    expect_name(xprname(0,"Total",'*',FALSE,7L,1L),
                "* - Total                                              7 zorkmids");
    assert(!memcmp(&player,&u,sizeof u)); assert(moves==turn);
    test_rng_unchanged(next); uwep=0;
}
static void xprname_coin_regression(unsigned char tag) {
    struct obj o, before;
    struct you player;
    char expected[BUFSZ];
    int next, dot, cost, fixed, literal;
    long quantity, override, displayed, turn=moves;
    fixture(&o); o.otyp=GOLD_PIECE; o.oclass=COIN_CLASS; o.curio_tag=tag;
    o.dknown=1; /* Ordinary cost formatting may learn an unseen appearance. */
    player=u; next=test_rng_begin();
    for (quantity=1; quantity<=2; ++quantity) {
        o.quan=quantity; before=o;
        for (override=0; override<=2; ++override)
        for (fixed=0; fixed<2; ++fixed)
        for (dot=0; dot<2; ++dot)
        for (cost=0; cost<2; ++cost)
        for (literal=0; literal<2; ++literal) {
            const char *txt=literal ? "Literal %s" : 0;
            const char *body;
            displayed=override ? override : quantity;
            body=txt ? txt : tag ? (displayed==1 ? "an inert curio" : "2 inert curios")
                                : (displayed==1 ? "a gold piece" : "2 gold pieces");
            flags.invlet_constant=fixed;
            if (cost)
                sprintf(expected,"%c - %-45s %6ld zorkmids",dot && fixed ? 'a' : 'b',body,7L);
#ifndef GOLDOBJ
            else if (!tag)
                sprintf(expected,"%ld gold piece%s%s",displayed,displayed==1 ? "" : "s",dot ? "." : "");
#endif
            else
                sprintf(expected,"%c - %s%s",fixed ? 'a' : 'b',body,dot ? "." : "");
            expect_name(xprname(&o,txt,'b',dot,cost ? 7L : 0L,override),expected);
            assert(o.quan==quantity && o.curio_tag==tag);
            assert(!memcmp(&before,&o,sizeof o));
        }
    }
    flags.invlet_constant=0;
    assert(!memcmp(&player,&u,sizeof u)); assert(moves==turn);
    test_rng_unchanged(next);
}
static void xprname_controls(void) {
    struct obj o, before;
    int i, next;
    char ordinary[BUFSZ], expected[BUFSZ+8];
    fixture(&o); o.bknown=1; o.blessed=1; uwep=&o; before=o;
    next=test_rng_begin();
    expect_name(xprname(&o,0,'a',FALSE,0L,1L),"a - a blessed Counter %s (weapon in hand)");
    assert(!memcmp(&before,&o,sizeof o));
    for(i=0;i<6;i++) {
        fixture(&o);
        if(i==0)o.curio_tag=CHAOS_CURIO_INERT_REMNANT;
        if(i==1)o.curio_tag=255;
        if(i==2)o.otyp=LONG_SWORD;
        if(i==3)o.o_id++;
        if(i==4)u.curio.phase=CHAOS_CURIO_EXPIRED;
        if(i==5)o.quan=2;
        before=o;
        expect_name(xprname(&o,0,'a',FALSE,0L,1L),"a - an inert curio (weapon in hand)");
        assert(!memcmp(&before,&o,sizeof o));
    }
    fixture(&o); o.curio_tag=0; o.dknown=1; o.known=1;
    objects[WHISTLE].oc_name_known=1; uwep=0;
    strcpy(ordinary,doname(&o)); sprintf(expected,"a - %s.",ordinary);
    for(i=0;i<3;i++) {
        o.quan=i; before=o;
        expect_name(xprname(&o,0,'a',TRUE,0L,1L),expected);
        assert(!memcmp(&before,&o,sizeof o));
    }
    o.quan=2; before=o;
    sprintf(expected,"a - %s",doname(&o));
    expect_name(xprname(&o,0,'a',FALSE,0L,0L),expected);
    assert(!memcmp(&before,&o,sizeof o));
    test_rng_unchanged(next);
}
/* Private objcopy exposes these exact static native functions to this fixture. */
int dopayobj(struct monst *, struct bill_x *, struct obj **, int, BOOLEAN_P);
int lift_object(struct obj *, struct obj *, long *, BOOLEAN_P);
static char reply='n';
static char question[BUFSZ];
static void raw_text(const char *s) { text(0,0,s); }
static char answer(const char *q,const char *choices,int def) {
    (void)choices; (void)def; strcpy(question,q); return reply;
}
static void shop_fixture(struct monst *shk) {
    memset(shk,0,sizeof *shk); shk->data=&mons[PM_SHOPKEEPER];
    shk->isshk=1; shk->mhp=shk->mhpmax=10; shk->mcanmove=1; shk->mnotlaugh=0;
    shk->mx=5; shk->my=5; add_mx(shk,MX_ESHK);
    ESHK(shk)->shoproom=ROOMOFFSET; ESHK(shk)->shoplevel=u.uz;
    ESHK(shk)->shoptype=SHOPBASE; ESHK(shk)->bill_p=ESHK(shk)->bill;
    ESHK(shk)->surcharge=1; strcpy(ESHK(shk)->shknam,"Test Shopkeeper");
    fmon=shk; rooms[0].resident=shk; rooms[0].rtype=SHOPBASE;
    levl[5][5].roomno=ROOMOFFSET; levl[5][5].typ=ROOM;
    u.ushops[0]=ROOMOFFSET; u.ushops[1]=0;
    flags.soundok=1; windowprocs.win_raw_print=raw_text;
    windowprocs.win_yn_function=answer; question[0]=0;
}
static void shop_regression(const char *which) {
    struct obj o, before, *op=&o;
    struct monst shk;
    struct bill_x bill;
    struct chaos_curio_state curio;
    int next, result;
    fixture(&o); o.quan=2; o.dknown=1;
    shop_fixture(&shk); curio=u.curio;
    next=test_rng_begin();
    if (!strcmp(which,"shop-quote")) {
        before=o;
        addtobill(&o,TRUE,FALSE,FALSE);
        fprintf(stderr,"shop quote: %s",output);
        assert(strstr(output,"per inert curio.\"\n"));
        assert(!strstr(output,"Counter"));
        assert(o.quan==before.quan && o.curio_tag==before.curio_tag);
        assert(o.unpaid && ESHK(&shk)->billct==1);
        assert(ESHK(&shk)->bill[0].bquan==2);
    } else {
        memset(&bill,0,sizeof bill); bill.bo_id=o.o_id; bill.bquan=3; bill.price=7;
        o.unpaid=1; before=o;
        ESHK(&shk)->credit=100;
        reply=!strcmp(which,"shop-refuse-used") ? 'y' : 'n';
        if (!strcmp(which,"shop-poor")) ESHK(&shk)->credit=0;
        result=dopayobj(&shk,&bill,&op,!strcmp(which,"shop-refuse-used") ? 1 : 0,
                       strcmp(which,"shop-poor") != 0 && strcmp(which,"shop-paid") != 0);
        if (!strcmp(which,"shop-paid")) {
            expect_name(output,"The price is deducted from your credit.\n"
                        "You paid for an inert curio at a cost of 7 gold pieces.\n");
            assert(result==2 && ESHK(&shk)->credit==93);
            assert(bill.bquan==2 && !bill.useup);
            before.sknown=1; /* ordinary successful-purchase ID side effect */
        } else if (!strcmp(which,"shop-refuse-used")) {
            fprintf(stderr,"shop refusal: %s",output);
            expect_name(output,"\"Pay for the other inert curio before buying these.\"\n");
            assert(result==-1);
        } else if (!strcmp(which,"shop-poor")) {
            expect_name(output,"You don't have gold enough to pay for an inert curio.\n");
            assert(result==0);
        } else {
            expect_name(question,"An inert curio for 7 zorkmids.  Pay?");
            assert(result==-1);
        }
        assert(!memcmp(&before,&o,sizeof o)); assert(op==&o);
        assert(bill.bquan==(!strcmp(which,"shop-paid") ? 2 : 3) && bill.price==7);
    }
    assert(!memcmp(&curio,&u.curio,sizeof curio));
    test_rng_unchanged(next); rem_all_mx(&shk); fmon=0; rooms[0].resident=0;
}
static void lift_regression(void) {
    struct obj o, before, ballast;
    struct you player;
    long count=1;
    int next;
    fixture(&o); o.quan=2; o.where=OBJ_FLOOR;
    o.obj_material=objects[WHISTLE].oc_material; o.owt=weight(&o);
    memset(&ballast,0,sizeof ballast); ballast.otyp=ROCK; ballast.oclass=GEM_CLASS;
    ballast.quan=1; ballast.where=OBJ_INVENT;
    ballast.owt=weight_cap(); invent=&ballast;
    flags.pickup_burden=UNENCUMBERED;
    windowprocs.win_yn_function=answer; reply='n'; question[0]=0;
    windowprocs.win_clear_nhwindow=noop;
    before=o; player=u; next=test_rng_begin();
    assert(lift_object(&o,0,&count,FALSE)==0);
    expect_name(question,"You have a little trouble lifting an inert curio. Continue?");
    assert(count==1 && !memcmp(&before,&o,sizeof o));
    assert(!memcmp(&player,&u,sizeof u)); test_rng_unchanged(next);
}
static void naming_regression(const char *which, long quantity) {
    struct obj o, before;
    struct you player;
    const char *name = 0;
    int next;
    long turn=moves;
    fixture(&o);
    o.quan=quantity; o.bknown=1; o.blessed=1; uwep=&o;
    if (strstr(which,"corpse")) {
        o.otyp=CORPSE; o.oclass=FOOD_CLASS; o.corpsenm=PM_HUMAN;
    }
    before=o; player=u; next=test_rng_begin();
    if (!strcmp(which,"corpse-direct")) name=corpse_xname(&o,FALSE);
    else if (!strcmp(which,"corpse-direct-singular")) name=corpse_xname(&o,TRUE);
    else if (!strcmp(which,"corpse-cxname")) name=cxname(&o);
#ifdef SORTLOOT
    else if (!strcmp(which,"corpse-cxname2")) name=cxname2(&o);
#endif
    else if (!strcmp(which,"singular-xname") || !strcmp(which,"singular-corpse"))
        name=singular(&o,xname);
    else if (!strcmp(which,"singular-doname") || !strcmp(which,"singular-corpse-doname")) {
        name=singular(&o,doname);
        assert(!strcmp(name,"a blessed inert curio (weapon in hand)"));
    } else if (!strcmp(which,"corpse-menu")) {
        inspect(&o,"inert",1);
        assert(!strcmp(action_prompt,"Do what with the inert curio?"));
    } else if (!strcmp(which,"quantity-wrappers")) {
        assert(!strcmp(xname2(&o,TRUE),"inert curio"));
        assert(!strcmp(cxname2(&o),"inert curio"));
        assert(!strcmp(encyc_xname(&o),"inert curio"));
        assert(!strcmp(obj_descname(&o),"inert curio"));
    } else assert(0 && "unknown naming regression");
    if (name && !strstr(which,"doname")) {
        if (strcmp(name,"inert curio")) fprintf(stderr,"%s: got %s\n",which,name);
        assert(!strcmp(name,"inert curio"));
    }
    assert(!memcmp(&before,&o,sizeof o));
    assert(!memcmp(&player,&u,sizeof u));
    assert(moves==turn);
    assert(!encyclopedias);
    /* inspect owns its own identical oracle and consumes the sentinel draw. */
    if (strcmp(which,"corpse-menu")) test_rng_unchanged(next);
    uwep=0;
}
int main(int argc, char **argv) {
    struct obj o, before; int i; char *n;
    char ordinary_xname[BUFSZ], ordinary_doname[BUFSZ];
    test_rng_control();
    if (argc>1) test_rng_negative_control(argv[1]);
    init_objects();init_gods();urace.malenum=PM_HUMAN;urole.malenum=PM_WIZARD;
    u.umonnum=u.umonster=PM_HUMAN;youmonst.data=&mons[PM_HUMAN];u.usanity=100;u.uhp=10;
    init_artifacts();
    windowprocs.win_putstr=text;windowprocs.win_create_nhwindow=create;
    windowprocs.win_destroy_nhwindow=noop;windowprocs.win_display_nhwindow=show;
    windowprocs.win_start_menu=noop;windowprocs.win_end_menu=end;
    windowprocs.win_add_menu=menu;windowprocs.win_select_menu=select_one;windowprocs.win_getlin=line;
    if (argc>1) {
        if (!strncmp(argv[1],"finalnames-",11)) { finalnames_regression(argv[1]); return 0; }
        if (!strncmp(argv[1],"encyc-",6)) { encyc_regression(argv[1]); return 0; }
        if (!strncmp(argv[1],"descname-",9)) { descname_regression(argv[1]); return 0; }
        if (!strncmp(argv[1],"inspect-",8)) { inspection_context_regression(argv[1]); return 0; }
        if (!strncmp(argv[1],"shop-",5)) { shop_regression(argv[1]); return 0; }
        if (!strcmp(argv[1],"lift-prompt")) { lift_regression(); return 0; }
        if (!strcmp(argv[1],"xprname-coin-tag1")) { xprname_coin_regression(1); return 0; }
        if (!strcmp(argv[1],"xprname-coin-tag2")) { xprname_coin_regression(2); return 0; }
        if (!strcmp(argv[1],"xprname-coin-tag255")) { xprname_coin_regression(255); return 0; }
        if (!strcmp(argv[1],"xprname-coin-ordinary")) { xprname_coin_regression(0); return 0; }
        if (!strcmp(argv[1],"xprname-controls")) { xprname_controls(); return 0; }
        if (!strncmp(argv[1],"xprname",7)) {
            xprname_regression(argv[1],2L); xprname_regression(argv[1],0L); return 0;
        }
        naming_regression(argv[1],2L);
        if (strstr(argv[1],"corpse")) naming_regression(argv[1],1L);
        else naming_regression(argv[1],0L);
        return 0;
    }
    fixture(&o);before=o;assert(!strcmp(xname(&o),"Counter %s"));
    assert(!memcmp(&before,&o,sizeof o)); n=xname(&o);n[0]='X'; assert(!strcmp(u.curio.name,"Counter %s"));
    for(i=-1;i<2;i++) inspect(&o,"Quiet %s %n.",i);
    assert(applies==1);
    fixture(&o);o.curio_tag=2;inspect(&o,"inert",0);inspect(&o,"inert",1);
    fixture(&o);o.quan=2;assert(!strcmp(doname(&o),"2 inert curios"));
    fixture(&o);o.bknown=1;o.blessed=1;uwep=&o;
    before=o;
    assert(!strcmp(doname(&o),"a blessed Counter %s (weapon in hand)"));
    assert(!strcmp(singular(&o,doname),"a blessed Counter %s (weapon in hand)"));
    assert(!strcmp(singular(&o,xname),"Counter %s"));
    assert(!memcmp(&before,&o,sizeof o));uwep=0;
    fixture(&o);strcpy(u.curio.name,artilist[ART_EXCALIBUR].name);
    assert(!strcmp(xname(&o),artilist[ART_EXCALIBUR].name));
    fixture(&o);
    u.curio.charges=0;inspect(&o,"Quiet %s %n.",-1);
    u.curio.disabled=1;assert(!strcmp(xname(&o),"Counter %s"));inspect(&o,"inert",-1);
    u.curio.disabled=0;invent=0;assert(!strcmp(xname(&o),"Counter %s"));inspect(&o,"inert",-1);
    o.where=OBJ_FLOOR;assert(!strcmp(xname(&o),"Counter %s"));
    for(i=0;i<6;i++) {
        fixture(&o);
        if(i==0)o.o_id++;if(i==1)o.curio_tag=2;if(i==2)o.curio_tag=3;
        if(i==3)o.otyp=LONG_SWORD;if(i==4)o.quan=2;if(i==5)u.curio.phase=CHAOS_CURIO_EXPIRED;
        assert(!strcmp(xname(&o),"inert curio"));inspect(&o,"inert",-1);
        before=o;
        assert(!strcmp(singular(&o,xname),"inert curio"));
        assert(!strcmp(singular(&o,doname),"an inert curio"));
        assert(!memcmp(&before,&o,sizeof o));
    }
    for(i=0;i<4;i++) {
        fixture(&o);
        if(i==0)strcpy(u.curio.source,"error('bad')");
        if(i==1)strcpy(u.curio.source,"return {name='Counter %s',inspect=function(c) return '\\27' end,apply=function(c) return {} end}");
        if(i==2)strcpy(u.curio.source,"return {name='Counter %s',inspect=function(c) return '\\255' end,apply=function(c) return {} end}");
        if(i==3)strcpy(u.curio.source,"return {name='Other',inspect=function(c) return 'unsafe' end,apply=function(c) return {} end}");
        u.curio.source_len=strlen(u.curio.source);inspect(&o,"inert",-1);
    }
    fixture(&o);u.curio.name[0]='\033';assert(!strcmp(xname(&o),"inert curio"));
    fixture(&o);memset(u.curio.name,'A',sizeof u.curio.name);assert(!strcmp(xname(&o),"inert curio"));
    fixture(&o);before=o;
    assert(oname(&o,"Excalibur")==&o);assert(oname(&o,artilist[ART_SHARD_FROM_MORGOTH_S_CROWN].name)==&o);
    do_oname(&o);o.dknown=1;docall(&o);o.dknown=0;
    assert(!prompts && !memcmp(&before,&o,sizeof o) && !objects[WHISTLE].oc_uname);
    objects[WHISTLE].oc_name_known=0;objects[RUBY].oc_name_known=0;
    o.obj_material=GEMSTONE;o.sub_material=RUBY;o.oartifact=ART_EXCALIBUR;
    assert(undiscovered_artifact(ART_EXCALIBUR));
    assert(not_fully_identified(&o));fully_identify_obj(&o);
    assert(!objects[RUBY].oc_name_known && undiscovered_artifact(ART_EXCALIBUR));
    assert(!not_fully_identified(&o) && !objects[WHISTLE].oc_name_known);
    fixture(&o);o.curio_tag=0;fully_identify_obj(&o);assert(objects[WHISTLE].oc_name_known);
    assert(strstr(xname(&o),"whistle"));
    /* Untagged objects retain the original quantity and corpse conventions. */
    strcpy(ordinary_xname,xname(&o));strcpy(ordinary_doname,doname(&o));
    o.quan=2; before=o;
    assert(!strcmp(singular(&o,xname),ordinary_xname));
    assert(!strcmp(singular(&o,doname),ordinary_doname));
    assert(!memcmp(&before,&o,sizeof o));
    o.otyp=CORPSE;o.oclass=FOOD_CLASS;o.corpsenm=PM_HUMAN;before=o;
    assert(!strcmp(corpse_xname(&o,FALSE),"human corpses"));
    assert(!strcmp(corpse_xname(&o,TRUE),"human corpse"));
    assert(!strcmp(cxname(&o),"human corpses"));
    assert(!strcmp(cxname2(&o),"human corpse"));
    assert(!strcmp(singular(&o,xname),"human corpse"));
    assert(!memcmp(&before,&o,sizeof o));
    puts("curio inspection: native naming, identity, purity, rename, ID and both UI modes passed");return 0;
}
