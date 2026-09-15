/* NGPL. Test-only native whole-level bones integration, controlled wizard
 * geometry (not dungeon generation/TTY discovery). No serialization mocks. */
#include "hack.h"
#include "lev.h"
#include "chaos_curio.h"
#include <stdio.h>
#include <assert.h>
#include <unistd.h>
#include <sys/resource.h>
#if defined(COMPRESS) || defined(COMPRESS_EXTENSION) || defined(INTERNAL_COMP) || defined(ZEROCOMP) || defined(RLECOMP)
#error "Whole-bones fixture currently validates only the native uncompressed build"
#endif
static const char *fault;
extern int n_dgns;
extern struct obj *nextgetobj;
extern struct fruit *loadfruitchn(int);
extern void freefruitchn(struct fruit *);
static int serial, counts[7], tagged, ordinary, collisions, summoned, deepest;
static struct obj *foreign, *whistle;
static char output[4096];
static void text(winid w, int a, const char *s)
{
    (void)w; (void)a;
    assert(strlen(output)+strlen(s)+2<sizeof output);
    strcat(output,s); strcat(output,"\n");
    fprintf(stderr,"native: %s\n",s);
}
static void raw(const char *s) { text(0,0,s); }
static void inventory_display(void) {}
static void window_sync(void) { fputs("native: window synchronization\n",stderr); }
static char answer(const char *q, const char *choices, int def)
{
    (void)choices; (void)def;
    fprintf(stderr,"wizard prompt: %s\n",q);
    if (!strcmp(q,"Get bones?")) return 'y';
    if (!strcmp(q,"Unlink bones?")) return 'n';
    assert(!"unexpected native prompt"); return 'n';
}
static void record(int live)
{
    memset(&u.curio,0,sizeof u.curio);
    u.curio.version=CHAOS_CURIO_VERSION;
    u.curio.phase=CHAOS_CURIO_PLACED;
    u.curio.owner=live ? 100004 : 4242;
    u.curio.charges=2; u.curio.state=live ? 71 : 19;
    strcpy(u.curio.name,live ? "Live record" : "Dead record");
    snprintf(u.curio.source,sizeof u.curio.source,
      "return {name='%s',inspect=function(c) return '%s' end,apply=function(c) return {text='EXECUTED',state=99,sanity_delta=1} end}",
      u.curio.name,live ? "TASK6D_LIVE_SOURCE_ONLY" : "TASK6D_DEAD_SOURCE_ONLY");
    u.curio.source_len=strlen(u.curio.source);
    assert(chaos_curio_valid(&u.curio));
}
static struct obj *object(int root, int type, int tag)
{
    struct obj *o=mksobj(type,MKOBJ_NOINIT);
    assert(o && !o->cobj && !o->timed && !o->oextra_p);
    o->quan=1; o->nomerge=1; o->curio_tag=tag; o->age=50;
    o->ovar1=root*1000000L+tag*1000L+(++serial);
    o->owt=weight(o); return o;
}
static struct obj *tree(int root)
{
    int tags[]={0,2,255,1}, i;
    struct obj *a=object(root,BOX,1), *b=object(root,BOX,0), *c=object(root,BOX,255);
    add_ox(a,OX_ESUM); /* actual native skip, but serialized with contents */
    add_to_container(a,b); add_to_container(b,c);
    for(i=0;i<4;i++) add_to_container(c,object(root,WHISTLE,tags[i]));
    return a;
}
static void attach(int root, struct obj *o, struct monst *m, struct trap *t)
{
    switch(root) {
    case 1: place_object(o,12,10); break;
    case 2: o->ox=13; o->oy=10; add_to_buried(o); break;
    case 3: assert(!add_to_minv(m,o)); break;
    case 4: /* native ammo supports a chain; construct controlled fixture chain */
        o->where=OBJ_INTRAP; o->otrap=t; o->nobj=t->ammo; t->ammo=o; break;
    case 5: o->where=OBJ_ONBILL; o->nobj=billobjs; billobjs=o; break;
    case 6: addinv(o); break;
    default: assert(0);
    }
}
static void setup(void)
{
    int i,x,y;
    srandom(607); id_permonst(); init_objects(); init_gods(); vision_init();
    urace=races[str2race("vampire")]; urole=roles[str2role("Wizard")];
    u.uz.dnum=1; u.uz.dlevel=2; n_dgns=2;
    dungeons[1].depth_start=1; dungeons[1].num_dunlevs=20;
    dungeons[1].boneid='D';
    u.umonnum=u.umonster=PM_HUMAN; init_uasmon();
    u.ulevel=1; u.uhp=u.uhprolled=20; u.uen=u.uenrolled=20;
    for(i=0;i<A_MAX;i++) ABASE(i)=AMAX(i)=12;
    u.ux=u.uy=10; u.usanity=73; moves=101; monstermoves=100;
    u.ugrave_arise=NON_PM; strcpy(plname,"Task6d"); strcpy(lock,"task6d");
    wizard=TRUE; iflags.bones=TRUE; init_artifacts();
    windowprocs.win_putstr=text; windowprocs.win_raw_print=raw;
    windowprocs.win_update_inventory=inventory_display;
    windowprocs.win_wait_synch=window_sync;
    windowprocs.win_yn_function=answer;
    for(x=1;x<COLNO-1;x++) for(y=1;y<ROWNO-1;y++) levl[x][y].typ=ROOM;
    assert(can_make_bones());
}
static void publish(void)
{
    int root,i,tags[]={0,1,2,255};
    struct chaos_curio_state saved;
    struct monst *m=makemon(&mons[PM_LITTLE_DOG],11,10,NO_MINVENT);
    struct trap *t=newtrap();
    assert(m); memset(t,0,sizeof *t); t->tx=14; t->ty=10; t->ttyp=ARROW_TRAP; ftrap=t;
    for(root=1;root<=5;root++) {
        for(i=0;i<4;i++) attach(root,object(root,WHISTLE,tags[i]),m,t);
        attach(root,tree(root),m,t);
    }
    for(i=0;i<4;i++) attach(6,object(6,WHISTLE,tags[i]),m,t);
    record(0); saved=u.curio;
    savebones((struct obj *)0); /* real header/fruit/savelev/free/native publication */
    assert(!memcmp(&saved,&u.curio,sizeof saved));
    puts("publish: native savebones returned; five roots and vampire death-drop requested");
    /* Level has been freed. Never inspect its old pointers. */
}
static void checkchain(struct obj *o,int root,int depth,struct obj *parent, int ghostly)
{
    for(;o;o=o->nobj) {
        int original=(o->ovar1%1000000L)/1000L;
        int family=o->ovar1/1000000L;
        assert(family==root || (root==1 && family==6));
        counts[family]++;
        assert(o->quan==1 && (o->otyp==BOX || o->otyp==WHISTLE));
        assert(o->curio_tag==(original ? CHAOS_CURIO_INERT_REMNANT : 0));
        assert(o->age==(ghostly ? 150 : 50));
        if(ghostly) assert(o->o_id>=100000);
        else assert(o->o_id<100000);
        if(parent) assert(o->where==OBJ_CONTAINED && o->ocontainer==parent);
        if(depth>deepest) deepest=depth;
        if(get_ox(o,OX_ESUM)) { summoned++; assert(o->cobj); }
        if(original) {
            char desc[161]; tagged++;
            assert(!chaos_curio_matches(o));
            assert(!strcmp(chaos_curio_name(o),"inert curio"));
            assert(strstr(xname(o),"inert curio"));
            chaos_curio_inspect(o,desc); assert(!strcmp(desc,"This curio is inert."));
            if(o->o_id==u.curio.owner) {
                assert(o->otyp==WHISTLE && original==1);
                foreign=o; collisions++;
            }
        } else { ordinary++; if(o->otyp==WHISTLE && !parent && root==1) whistle=o; }
        if(o->cobj) checkchain(o->cobj,root,depth+1,o,ghostly);
    }
}
static void readback(int ghostly)
{
    int root,fd,total=0; char *id,c,oldid[16]; struct obj *o;
    struct monst *m; struct trap *t;
    struct chaos_curio_state saved;
    record(1); saved=u.curio; flags.ident=100000;
    if(ghostly) { monstermoves=200; assert(getbones()==1); assert(has_loaded_bones); }
    else {
        struct version_info version;
        fd=open_bonesfile(&u.uz,&id); assert(fd>=0);
        assert(read(fd,&version,sizeof version)==(ssize_t)sizeof version);
        assert(lseek(fd,0,SEEK_SET)==0);
        assert(uptodate(fd,"bones"));
        printf("native-version: %llu %llu %llu %llu\n",version.incarnation,
               version.feature_set,version.entity_count,version.struct_sizes);
        mread(fd,&c,sizeof c); assert(c>0 && (unsigned)c<=sizeof oldid);
        mread(fd,oldid,(unsigned)c); assert(!strcmp(id,oldid));
        freefruitchn(loadfruitchn(fd));
        getlev(fd,0,0,FALSE); /* unconditional native decode: no input demotion */
        assert(close(fd)==0); compress_bonesfile();
    }
    /* Assertion-sensitivity control, not a claimed engine-induced mutation. */
    if(fault && !strcmp(fault,"record")) u.curio.source[0]^=1;
    assert(!memcmp(&saved,&u.curio,sizeof saved));
    checkchain(fobj,1,0,0,ghostly);
    for(o=fobj;o;o=o->nobj) {
        struct obj *at;
        assert(o->where==OBJ_FLOOR);
        for(at=level.objects[o->ox][o->oy];at && at!=o;at=at->nexthere) {}
        assert(at==o);
    }
    checkchain(level.buriedobjlist,2,0,0,ghostly);
    for(o=level.buriedobjlist;o;o=o->nobj) assert(o->where==OBJ_BURIED);
    assert(fmon && !fmon->nmon);
    for(m=fmon;m;m=m->nmon) {
        assert(level.monsters[m->mx][m->my]==m);
        for(o=m->minvent;o;o=o->nobj) assert(o->where==OBJ_MINVENT && o->ocarry==m);
        checkchain(m->minvent,3,0,0,ghostly);
    }
    assert(ftrap && !ftrap->ntrap);
    for(t=ftrap;t;t=t->ntrap) {
        for(o=t->ammo;o;o=o->nobj) assert(o->where==OBJ_INTRAP && o->otrap==t);
        checkchain(t->ammo,4,0,0,ghostly);
    }
    checkchain(billobjs,5,0,0,ghostly);
    for(o=billobjs;o;o=o->nobj) assert(o->where==OBJ_ONBILL);
    for(root=1;root<=5;root++) assert(counts[root]==11);
    assert(counts[6]==4 && tagged==43 && ordinary==16 && summoned==5 && deepest==3);
    if(ghostly) {
        assert(collisions==1 && foreign && whistle);
        obj_extract_self(foreign); addinv(foreign);
        m=fmon; add_mx(m,MX_EDOG); m->msleeping=1;
        output[0]=0; nextgetobj=foreign;
        assert(doapply()==MOVE_CANCELLED && !nextgetobj);
        if(fault && !strcmp(fault,"output")) strcpy(output,"EXECUTED\n");
        assert(!strcmp(output,"This curio is inert.\n"));
        assert(m->msleeping && !EDOG(m)->whistletime);
        assert(!memcmp(&saved,&u.curio,sizeof saved));
        obj_extract_self(whistle); addinv(whistle); nextgetobj=whistle;
        (void)doapply(); assert(!m->msleeping && EDOG(m)->whistletime==moves);
    }
    assert(!memcmp(&saved,&u.curio,sizeof saved));
    for(root=1;root<=6;root++) total+=counts[root];
    printf("%s: %d objects; %d inert/%d ordinary; all five native roots; %d OX_ESUM; depth %d; death-drop %d; exact current record unchanged; collisions=%d\n",ghostly ? "consume" : "observe",total,tagged,ordinary,summoned,deepest,counts[6],collisions);
}
/* Negative-only native writer: re-read a COPY of the successful publication,
 * then write one legacy generated tag via the native whole-level writer.
 * This is not savebones output evidence and does not replace its hooks. */
static void legacy_file(void)
{
    int fd; char *id, c, why[BUFSZ]; struct obj *o;
    readback(0);
    for(o=fobj;o && !o->curio_tag;o=o->nobj) {}
    assert(o && o->curio_tag==CHAOS_CURIO_INERT_REMNANT);
    o->curio_tag=1;
    fd=create_bonesfile(&u.uz,&id,why); assert(fd>=0);
    c=(char)(strlen(id)+1);
    store_version(fd); bwrite(fd,(genericptr_t)&c,sizeof c);
    bwrite(fd,(genericptr_t)id,(unsigned)c);
    savefruitchn(fd,WRITE_SAVE | FREE_SAVE);
    savelev(fd,ledger_no(&u.uz),WRITE_SAVE | FREE_SAVE);
    bclose(fd); commit_bonesfile(&u.uz); compress_bonesfile();
    puts("negative-only: native whole-file legacy tag written");
}
int main(int argc,char **argv)
{
    struct rlimit core_limit={0,0};
    assert(setrlimit(RLIMIT_CORE,&core_limit)==0);
    assert(argc==2); setup();
    puts("compiled-format: native-uncompressed; COMPRESS/COMPRESS_EXTENSION/INTERNAL_COMP/ZEROCOMP/RLECOMP absent");
    if(!strcmp(argv[1],"publish")) publish();
    else if(!strcmp(argv[1],"observe")) readback(0);
    else if(!strcmp(argv[1],"consume")) readback(1);
    else if(!strcmp(argv[1],"legacy-file")) legacy_file();
    else if(!strcmp(argv[1],"bad-record")) { fault="record"; readback(0); }
    else if(!strcmp(argv[1],"bad-output")) { fault="output"; readback(1); }
    else assert(!"unknown mode");
    return 0;
}
