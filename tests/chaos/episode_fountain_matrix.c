/* NGPL. Separate native all-fate fixture; no gameplay or RNG replacements. */
#include "hack.h"
#include "chaos.h"
#include "wintty.h"
#include "dlb.h"
#include "native_rng.h"
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
extern short disco[NUM_OBJECTS];
static void seed_reset(unsigned seed) {
    void *libc = dlopen("libc.so.6", RTLD_NOW | RTLD_LOCAL);
    void (*reset)(unsigned) = (void (*)(unsigned))dlsym(libc,"srandom");
    assert(reset); reseed_period=INT_MAX; reseed_count=0; reset(seed); dlclose(libc);
}
static void hex(FILE *f,const void *p,size_t n) {
    const unsigned char *s=p; size_t i; fputc('"',f);
    for(i=0;i<n;i++) fprintf(f,"%02x",s[i]);
    fputc('"',f);
}
static void objs(FILE *f,struct obj *o) {
    int comma=0; fputc('[',f);
    for(;o;o=o->nobj) {
        struct obj c=*o;
        if(comma++) fputc(',',f);
        /* Reject unsupported pointer-bearing auxiliaries, never silently omit. */
        assert(!o->mp && !o->light && !o->timed && !o->oextra_p);
        c.nobj=0; c.nexthere=0; c.cobj=0;
        fputs("{\"bytes\":",f);hex(f,&c,sizeof c);
        fputs(",\"contents\":",f);objs(f,o->cobj);fputc('}',f);
    } fputc(']',f);
}
static void mons_record(FILE *f,struct monst *m) {
    int comma=0; fputc('[',f);
    for(;m;m=m->nmon) {
        struct monst c=*m;
        if(comma++) fputc(',',f);
        assert(!m->light && !m->timed);
        c.nmon=0;c.data=0;c.minvent=0;c.mw=0;c.msw=0;c.mextra_p=0;
        fputs("{\"bytes\":",f);hex(f,&c,sizeof c);
        fprintf(f,",\"data\":%d,\"weapon\":%u,\"offhand\":%u,\"inventory\":",m->data->mtyp,m->mw?m->mw->o_id:0,m->msw?m->msw->o_id:0);
        objs(f,m->minvent);fputs(",\"extras\":",f);
        if(m->mextra_p) {
            /* Native bundle contains all components; reject pointer components. */
            long n;void *b;
            assert(!m->mextra_p->eshk_p && !m->mextra_p->esum_p);
            b=bundle_mextra(m,&n);hex(f,b,n);free(b);
        } else fputs("null",f);
        fputc('}',f);
    } fputc(']',f);
}
static void context_record(FILE *f) {
    fprintf(f,"{\"turn\":%ld,\"safe\":%ld,\"sanity\":%d,\"insight\":%d,"
            "\"budget\":%d,\"spent\":%d,\"reserved\":%d,\"last_id\":%d,"
            "\"vitals\":{\"hp\":%d,\"hp_max\":%d,\"power\":%d,\"power_max\":%d}}",
            moves,u.chaos.safe,u.usanity,u.uinsight,
            chaos_budget(&u.chaos,u.usanity),u.chaos.spent,
            u.chaos.reserved,u.chaos.last_id,u.uhp,u.uhpmax,u.uen,u.uenmax);
}
static void snapshot(FILE *f) {
    struct you c=u; struct objclass defs[NUM_OBJECTS];struct trap *t;
    int i,x,y,comma=0;
    /* Only journal seq is excluded; budget/spent/safe remain compared. */
    c.chaos.seq=0;assert(!c.ustuck && !c.usteed && !c.urider);
    fputs("{\"player\":",f);hex(f,&c,sizeof c);
    fputs(",\"youmonst\":",f);{struct monst m=youmonst;m.nmon=0;mons_record(f,&m);}
    fputs(",\"terrain\":",f);hex(f,levl,sizeof levl);
    fputs(",\"level_flags\":",f);hex(f,&level.flags,sizeof level.flags);
    fputs(",\"inventory\":",f);objs(f,invent);
    fputs(",\"floor\":",f);objs(f,fobj);
    fputs(",\"monsters\":",f);mons_record(f,fmon);
    fputs(",\"migrating_monsters\":",f);mons_record(f,migrating_mons);
    fputs(",\"migrating_objects\":",f);objs(f,migrating_objs);
    fputs(",\"traps\":[",f);for(t=ftrap;t;t=t->ntrap) {struct trap q=*t;q.ntrap=0;if(comma++) fputc(',',f);hex(f,&q,sizeof q);}fputc(']',f);
    fputs(",\"discovery\":",f);hex(f,disco,sizeof disco);
    memcpy(defs,objects,sizeof defs);for(i=0;i<NUM_OBJECTS;i++) assert(!defs[i].oc_uname);
    fputs(",\"definitions\":",f);hex(f,defs,sizeof defs);
    fputs(",\"vitals\":",f);hex(f,mvitals,sizeof mvitals);
    fputs(",\"flags\":",f);hex(f,&flags,sizeof flags);
    fprintf(f,",\"globals\":[%ld,%ld,%d,%d,%d,%d],\"motion\":",moves,monstermoves,multi,!!occupation,!!afternmv,!!nomovemsg);hex(f,multi_txt,sizeof multi_txt);
    fputs(",\"grid\":[",f);comma=0;
    for(x=0;x<COLNO;x++)for(y=0;y<ROWNO;y++) {assert(!level.objects[x][y] || !level.objects[x][y]->nexthere);if(comma++)fputc(',',f);fprintf(f,"[%u,%u]",level.monsters[x][y]?level.monsters[x][y]->m_id:0,level.objects[x][y]?level.objects[x][y]->o_id:0);}
    fputs("]}",f);
}
int main(int argc,char **argv) {
    unsigned seed;int fate,i,x,y,result,count,next,hp,hunger,attr,moncount=0,puddles=0,cursed=0;
    struct monst *m;struct obj *o;FILE *f;
    assert(argc==2);test_rng_control();test_rng_negative_control(argv[1]);
    if(!strcmp(argv[1],"--calibrate")) {
        puts("[");for(seed=1;seed<=4096;seed++){seed_reset(seed);fate=rnd(30);printf("%s{\"seed\":%u,\"fate\":%d}",seed==1?"":",",seed,fate);}puts("]");return 0;
    }
    fate=atoi(argv[1]);assert(fate>=1&&fate<=30);
    seed=atoi(getenv("FOUNTAIN_SEED"));assert(seed>=1&&seed<=4096);
    seed_reset(seed);assert(rnd(30)==fate);
    choose_windows("tty");initoptions();init_nhwindows(&argc,argv);
    WIN_MESSAGE=create_nhwindow(NHW_MESSAGE);WIN_STATUS=create_nhwindow(NHW_STATUS);WIN_MAP=create_nhwindow(NHW_MAP);display_nhwindow(WIN_MESSAGE,FALSE);
    init_objects();init_gods();id_permonst();
    urace.malenum=PM_HUMAN;urole.malenum=PM_WIZARD;u.umonnum=u.umonster=PM_HUMAN;
    youmonst.data=&mons[PM_HUMAN];youmonst.mtyp=PM_HUMAN;
    u.ulevel=1;u.uhp=u.uhprolled=100;u.uen=u.uenrolled=20;u.usanity=73;u.uinsight=19;
    for(i=0;i<A_MAX;i++)ABASE(i)=AMAX(i)=12;
    u.ux=10;u.uy=10;moves=101;u.uz.dlevel=1;u.ualign.god=1;u.ulycn=u.ugrave_arise=NON_PM;
    init_artifacts();calc_total_maxhp();calc_total_maxen();
    u.uhungermax=2000;u.uhunger=500;u.uhs=NOT_HUNGRY;
    /* Real dungeon data initializes depths/branches required by makemon. */
    dlb_init();init_dungeons();
    u.uz.dnum=0;u.uz.dlevel=(fate==23 ? 20 : 1);
    /* A legal deeper baseline makes the native marid wish threshold 100;
     * no RNG suppression, summon failure or action retry is involved. */
    assert(dungeons[0].num_dunlevs>=u.uz.dlevel);
    if(fate==23) assert(level_difficulty()>=20);
    for(x=3;x<=20;x++)for(y=3;y<=17;y++){levl[x][y].typ=ROOM;levl[x][y].lit=1;}
    levl[10][10].typ=FOUNTAIN;level.flags.nfountains=1;
    vision_init();vision_reset();vision_recalc(0);
    if(fate==26||fate==29){m=makemon(&mons[PM_LITTLE_DOG],12,10,NO_MINVENT);assert(m);}
    if(fate==24){o=mksobj(DAGGER,MKOBJ_NOINIT);assert(o);o->quan=1;o->blessed=o->cursed=0;o->owt=weight(o);addinv(o);}
    for(x=1;x<COLNO;x++)for(y=0;y<ROWNO;y++)newsym(x,y);
    docrt();clear_nhwindow(WIN_MESSAGE);flush_screen(1);fflush(stdout);
    chaos_start();assert(u.chaos.safe==1);
    f=fopen(getenv("FOUNTAIN_STATE"),"w");assert(f);fputs("{\"before\":",f);snapshot(f);fflush(f);
    hp=u.uhp;hunger=u.uhunger;attr=ABASE(A_STR);
    fputs(",\"context_before\":",f);context_record(f);
    seed_reset(seed);result=dodrink();
    /* Test-only measured-action controls: after real action, before capture. */
    if(getenv("FOUNTAIN_INJECTION")) {
        const char *mode=getenv("FOUNTAIN_INJECTION");
        assert(fate==1);
        if(!strcmp(mode,"native")) (void)rn2(100000);
        else if(!strcmp(mode,"raw")) {
            void *libc=dlopen("libc.so.6",RTLD_NOW|RTLD_LOCAL);
            long (*draw)(void)=(long (*)(void))dlsym(libc,"random");
            assert(draw);(void)draw();dlclose(libc);
        } else {assert(!strcmp(mode,"budget"));u.chaos.spent++;}
    }
    count=reseed_count;next=rn2(100000);
    assert(result==MOVE_QUAFFED&&reseed_period==INT_MAX);
    for(m=fmon;m;m=m->nmon)moncount++;
    for(x=0;x<COLNO;x++)for(y=0;y<ROWNO;y++)puddles+=levl[x][y].typ==PUDDLE;
    for(o=invent;o;o=o->nobj)cursed+=o->cursed;
    if(fate<10)assert(u.uhunger>hunger);
    if(fate==20)assert(u.uhunger<hunger&&multi==-2);
    if(fate==21)assert(u.uhp<hp&&u.uhp>0&&ABASE(A_STR)<attr);
    if(fate==22)assert(moncount>=2&&fmon->mtyp==PM_WATER_MOCCASIN);
    if(fate==23)assert(moncount==1&&fmon->mtyp==PM_MARID);
    if(fate==24)assert(cursed>0);
    if(fate==25)assert(HSee_invisible);
    if(fate==27)assert(fobj&&fobj->oclass==GEM_CLASS);
    if(fate==28)assert(moncount==1&&fmon->mtyp==PM_NAIAD&&!fmon->msleeping);
    if(fate==29)assert(fmon&&fmon->mflee);
    if(fate==30)assert(puddles>0);
    fputs(",\"after\":",f);snapshot(f);
    fputs(",\"context_after\":",f);context_record(f);
    fprintf(f,",\"spent_layout\":[%lu,%lu]",(unsigned long)((char *)&u.chaos.spent-(char *)&u),(unsigned long)sizeof u.chaos.spent);
    fprintf(f,",\"fate\":%d,\"seed\":%u,\"count\":%d,\"next\":%d,\"return\":%d,\"witness\":{\"population\":%d,\"puddles\":%d,\"cursed\":%d,\"hp_loss\":%d,\"hunger_delta\":%d}}\n",fate,seed,count,next,result,moncount,puddles,cursed,hp-u.uhp,u.uhunger-hunger);assert(!fclose(f));
    fflush(stdout);exit_nhwindows((char *)0);return 0;
}
