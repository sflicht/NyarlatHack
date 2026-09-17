/* NGPL. Real selected doapply/dodrink under event-inode transport faults.
 * Narrow initialized world; not moveloop. No native action/RNG/render stubs. */
#include "hack.h"
#include "chaos.h"
#include "wintty.h"
#include "native_rng.h"
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <unistd.h>
extern short disco[NUM_OBJECTS];
extern struct obj *nextgetobj;
extern char prevmsg[BUFSZ];
static struct stat identity;
static const char *stage, *transport;
static int pending, triggered, writes_after, syncs_after;
static long committed;
static char request[3072];
static size_t request_size;
ssize_t __real_write(int, const void *, size_t);
int __real_fsync(int);
static int event_fd(int fd)
{
    struct stat st;
    return !fstat(fd,&st) && st.st_dev == identity.st_dev && st.st_ino == identity.st_ino;
}
ssize_t __wrap_write(int fd, const void *buf, size_t n)
{
    char line[3072], needle[80];
    if (!event_fd(fd)) return __real_write(fd,buf,n);
    if (triggered) ++writes_after;
    assert(n < sizeof line); memcpy(line,buf,n); line[n] = 0;
    assert(snprintf(needle,sizeof needle,"\"stage\":\"%s\"",stage) < (int)sizeof needle);
    if (!triggered && strcmp(transport,"healthy") && strstr(line,needle)) {
        memcpy(request,buf,n); request_size=n; committed=u.chaos.seq;
        if (!strcmp(transport,"write")) { ++triggered; errno=EIO; return -1; }
        assert(!strcmp(transport,"fsync")); pending=1;
    }
    return __real_write(fd,buf,n);
}
int __wrap_fsync(int fd)
{
    if (!event_fd(fd)) return __real_fsync(fd);
    if (triggered) ++syncs_after;
    if (pending) { pending=0; ++triggered; errno=EIO; return -1; }
    return __real_fsync(fd);
}
static void seeded_reset(unsigned seed)
{
    void *libc=dlopen("libc.so.6",RTLD_NOW|RTLD_LOCAL);
    void (*reset)(unsigned);
    assert(libc); reset=(void (*)(unsigned))dlsym(libc,"srandom"); assert(reset);
    reseed_period=INT_MAX; reseed_count=0; reset(seed); assert(!dlclose(libc));
}
static void bytes(FILE *f,const void *p,size_t n) { assert(fwrite(p,1,n,f)==n); }
/* Full structs in this deliberately pointer-free world. Native monster identity
 * is fixed/checked before removing its address; EDOG is separately serialized.
 * Only observation seq/safe transport counters differ; spent/effects/time
 * are NEVER masked. Safe's marker-failure behavior is asserted explicitly. */
static void snapshot(const char *name,struct obj *o,struct monst *dog)
{
    FILE *f=fopen(name,"wb");
    struct you hero=u;
    struct monst mon=*dog, you=youmonst;
    int x,y;
    assert(f && !nextgetobj && invent==o && fmon==dog && !fobj && !ftrap);
    assert(!migrating_mons && !migrating_objs && !o->nobj && !o->cobj && !o->oextra_p && !o->mp);
    assert(!mon.nmon && !mon.minvent && mon.data==&mons[PM_LITTLE_DOG]);
    assert(you.data==&mons[PM_HUMAN] && !you.mextra_p);
    hero.chaos.seq=0;
    /* Failed enabled marker prevents the startup safe counter advancing.
     * This transport counter is explicitly checked above, not gameplay time. */
    assert(u.chaos.safe==(!strcmp(stage,"enabled") && triggered ? 0 : 1));
    hero.chaos.safe=0;
    mon.data=0; mon.mextra_p=0; you.data=0;
    bytes(f,&hero,sizeof hero); bytes(f,o,sizeof *o);
    bytes(f,&mon,sizeof mon); bytes(f,EDOG(dog),sizeof *EDOG(dog));
    bytes(f,&you,sizeof you); bytes(f,levl,sizeof levl);
    bytes(f,&level.flags,sizeof level.flags); bytes(f,disco,sizeof(short)*NUM_OBJECTS);
    for(x=0;x<NUM_OBJECTS;++x) assert(!objects[x].oc_uname);
    bytes(f,objects,sizeof(struct objclass)*NUM_OBJECTS);
    bytes(f,&moves,sizeof moves); bytes(f,&monstermoves,sizeof monstermoves);
    bytes(f,&multi,sizeof multi); bytes(f,multi_txt,sizeof multi_txt);
    assert(!occupation && !afternmv && !nomovemsg);
    for(x=0;x<COLNO;++x) for(y=0;y<ROWNO;++y) {
        assert(!level.objects[x][y] && !t_at(x,y));
        assert(level.monsters[x][y]==((x==11 && y==10)?dog:0));
    }
    assert(!fclose(f));
}
int main(int argc,char **argv)
{
    struct obj o;
    struct monst dog;
    int fountain,result,continuation,count,next,expected,fate=0,hunger=0,dry=0,i,x,y;
    long seq_action;
    FILE *f;
    char path[1024];
    const char *negative=getenv("ACTION_NEGATIVE");
    assert(argc==4); fountain=!strcmp(argv[1],"fountain");
    assert(fountain || !strcmp(argv[1],"whistle")); stage=argv[2]; transport=argv[3];
    test_rng_control(); test_rng_negative_control("unused");
    seeded_reset(2);
    if(fountain) { fate=rnd(30); hunger=rnd(10); dry=rn2(3); assert(fate<10 && dry>0); }
    count=reseed_count; expected=rn2(100000);
    f=fopen("preflight.json","w"); assert(f);
    fprintf(f,"{\"seed\":2,\"fate\":%d,\"hunger\":%d,\"dry\":%d,\"count\":%d,\"next\":%d}\n",fate,hunger,dry,count,expected); assert(!fclose(f));
    choose_windows("tty"); initoptions(); init_nhwindows(&argc,argv);
    WIN_MESSAGE=create_nhwindow(NHW_MESSAGE); WIN_STATUS=create_nhwindow(NHW_STATUS); WIN_MAP=create_nhwindow(NHW_MAP);
    display_nhwindow(WIN_MESSAGE,FALSE);
    assert(iflags.window_inited && windowprocs.win_putstr==tty_putstr);
    init_objects(); init_gods(); id_permonst();
    urace.malenum=PM_HUMAN; urole.malenum=PM_WIZARD;
    u.umonnum=u.umonster=PM_HUMAN; youmonst.data=&mons[PM_HUMAN]; youmonst.mtyp=PM_HUMAN;
    u.ulevel=1; u.uhp=u.uhprolled=20; u.uen=u.uenrolled=20;
    u.usanity=73; u.uinsight=19;
    for(i=0;i<A_MAX;++i) ABASE(i)=AMAX(i)=12;
    u.ux=u.uy=10; moves=101; u.uz.dlevel=1; u.ualign.god=1;
    init_artifacts(); calc_total_maxhp(); calc_total_maxen();
    u.uhungermax=2000; u.uhunger=500; u.uhs=NOT_HUNGRY;
    sokoban_dnum=1; neutral_dnum=2;
    assert(!in_town(10,10) && !wizard && !Levitation && !Hallucination && !Blind);
    for(x=7;x<=17;++x) for(y=7;y<=13;++y) { levl[x][y].typ=ROOM; levl[x][y].lit=1; }
    if(fountain) { levl[10][10].typ=FOUNTAIN; level.flags.nfountains=1; }
    memset(&o,0,sizeof o); o.otyp=WHISTLE; o.oclass=TOOL_CLASS; o.quan=1;
    o.o_id=42; o.invlet='a'; o.where=OBJ_INVENT; o.known=o.dknown=1;
    objects[WHISTLE].oc_name_known=1; o.owt=weight(&o); invent=&o;
    memset(&dog,0,sizeof dog); dog.data=&mons[PM_LITTLE_DOG]; dog.mtyp=PM_LITTLE_DOG;
    dog.mhp=dog.mhpmax=10; dog.msleeping=1; dog.mcanmove=1;
    add_mx(&dog,MX_EDOG); fmon=&dog; place_monster(&dog,11,10);
    vision_init(); vision_reset(); vision_recalc(0);
    for(x=1;x<COLNO;++x) for(y=0;y<ROWNO;++y) newsym(x,y);
    assert(snprintf(path,sizeof path,"%s/events.jsonl",getenv("NYARLATHACK_RUN_DIR"))<(int)sizeof path);
    /* Precreate and pin before chaos_start so enabled-marker faults are scoped
     * to the actual inode, never merely a descriptor number or filename. */
    f=fopen(path,"wb"); assert(f && !fclose(f)); assert(!stat(path,&identity));
    chaos_start(); assert(u.chaos.safe==(triggered ? 0 : 1));
    snapshot("before.bin",&o,&dog);
    seeded_reset(2);
    result=fountain?dodrink():doapply();
    assert(result==(fountain?MOVE_QUAFFED:MOVE_PARTIAL));
    assert(u.uhunger==500+hunger && moves==101 && multi==0);
    assert(dog.msleeping==fountain && EDOG(&dog)->whistletime==(fountain?0:101));
    seq_action=u.chaos.seq;
    snapshot("after.bin",&o,&dog);
    /* A second real selected command, no seed reset or scripted scope. */
    clear_nhwindow(WIN_MESSAGE);
    continuation=doapply(); assert(continuation==MOVE_PARTIAL);
    assert(!dog.msleeping && EDOG(&dog)->whistletime==101);
    if(negative) {
        if(!strcmp(negative,"native")) (void)rn2(100000);
        else if(!strcmp(negative,"raw")) (void)random();
        else { assert(!strcmp(negative,"budget")); ++u.chaos.spent; }
    }
    count=reseed_count; next=rn2(100000);
    snapshot("continuation.bin",&o,&dog);
    f=fopen("native.json","w"); assert(f);
    fprintf(f,"{\"action_completed\":true,\"continuation_completed\":true,\"return\":%d,\"continuation\":%d,\"count\":%d,\"next\":%d,\"expected\":%d,\"spent\":%d,\"hunger\":%d,\"sleeping\":%d,\"whistletime\":%ld,\"moves\":%ld,\"monstermoves\":%ld}\n",result,continuation,count,next,expected,u.chaos.spent,u.uhunger,dog.msleeping,EDOG(&dog)->whistletime,moves,monstermoves); assert(!fclose(f));
    f=fopen("transport.json","w"); assert(f);
    fprintf(f,"{\"triggered\":%d,\"committed\":%ld,\"seq_action\":%ld,\"seq_final\":%ld,\"writes_after\":%d,\"syncs_after\":%d}\n",triggered,committed,seq_action,u.chaos.seq,writes_after,syncs_after); assert(!fclose(f));
    f=fopen("request.bin","wb"); assert(f); bytes(f,request,request_size); assert(!fclose(f));
    fflush(stdout); exit_nhwindows((char *)0); return 0;
}
