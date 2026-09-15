/* NGPL: native bones preparation and buffered object-chain serialization.
 * Not a physical TTY savebones/getbones encounter or whole-level fixture. */
#include "hack.h"
#include "lev.h"
#include "chaos_curio.h"
#include "native_rng.h"
#include <stdio.h>
#include <unistd.h>
#include <signal.h>
#include <execinfo.h>
static void crash(int sig)
{
    void *frames[30]; int n=backtrace(frames,30);
    backtrace_symbols_fd(frames,n,2); signal(sig,SIG_DFL); raise(sig);
}
extern void resetobjs(struct obj *, boolean);
extern void saveobjchn(int, struct obj *, int);
extern struct obj *restobjchn(int, boolean, boolean);
extern void clear_id_mapping(void);
extern struct obj *nextgetobj;
static char output[4096];
static void text(winid w, int a, const char *s)
{
    (void)w; (void)a;
    assert(strlen(output)+strlen(s)+2<sizeof output);
    strcat(output,s); strcat(output,"\n");
    if (strstr(s,"impossible") || strstr(s,"free") || strstr(s,"Panic"))
        fprintf(stderr,"native: %s\n",s);
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
    strcpy(u.curio.name,"Bones counter");
    strcpy(u.curio.source,"return {name='Bones counter',inspect=function(c) return 'Original' end,apply=function(c) return {text='Used',state=18,sanity_delta=0} end}");
    u.curio.source_len=strlen(u.curio.source);
    if(variant==1) u.curio.disabled=1;
    if(variant==2) u.curio.charges=0;
    if(variant==3) u.curio.owner++;
    if(variant==4) { o->otyp=LONG_SWORD; o->oclass=WEAPON_CLASS; }
    if(variant==5) o->quan=2;
    if(variant==6) u.curio.source[0]='!';
}
static int command(struct obj *o)
{
    int result; output[0]=0; nextgetobj=o; result=doapply();
    assert(!nextgetobj); return result;
}
static void inert(struct obj *o)
{
    struct chaos_curio_state saved=u.curio;
    char description[161];
    int next=test_rng_begin(), sanity=u.usanity;
    long turn=moves;
    assert(o->curio_tag==CHAOS_CURIO_INERT_REMNANT);
    assert(!chaos_curio_matches(o));
    assert(!strcmp(chaos_curio_name(o),"inert curio"));
    assert(strstr(xname(o),"inert curio"));
    chaos_curio_inspect(o,description);
    assert(!strcmp(description,"This curio is inert."));
    assert(command(o)==MOVE_CANCELLED);
    assert(!strcmp(output,"This curio is inert.\n"));
    assert(!memcmp(&saved,&u.curio,sizeof saved));
    assert(sanity==u.usanity && turn==moves);
    test_rng_unchanged(next);
}
static FILE *stream(struct obj *o)
{
    char path[]="/tmp/curio6c-stream-XXXXXX";
    int fd=mkstemp(path); FILE *f;
    assert(fd>=0); bufon(fd);
    saveobjchn(fd,o,WRITE_SAVE); bflush(fd); bclose(fd);
    f=fopen(path,"rb"); assert(f); assert(!unlink(path));
    return f;
}
static struct obj *readstream(FILE *f, boolean ghostly)
{
    assert(lseek(fileno(f),0,SEEK_SET)==0); minit(); clear_id_mapping();
    return restobjchn(fileno(f),ghostly,FALSE);
}
static void discard(struct obj *o) { obj_extract_self(o); obfree(o,0); }
static void matrix(int outgoing)
{
    int tag, variant;
    for(tag=0;tag<256;tag++) for(variant=0;variant<7;variant++) {
        struct obj *owner=object(WHISTLE,1), *o=object(WHISTLE,tag), *r;
        struct chaos_curio_state saved;
        FILE *f;
        addinv(owner); record(owner,variant); saved=u.curio;
        o->otyp=owner->otyp; o->oclass=owner->oclass; o->quan=owner->quan;
        o->o_id=owner->o_id;
        if(outgoing) {
            resetobjs(o,FALSE);
            if(tag) assert(o->curio_tag==CHAOS_CURIO_INERT_REMNANT);
            else assert(!o->curio_tag);
        }
        f=stream(o);
        /* Same native stream with ghostly FALSE retains tag and identifier. */
        r=readstream(f,FALSE);
        assert(r->curio_tag==o->curio_tag && r->o_id==o->o_id);
        assert(r->otyp==o->otyp && r->quan==o->quan); discard(r);
        /* Native remapping itself collides with the live player record. */
        flags.ident=saved.owner;
        r=readstream(f,TRUE);
        assert(r->o_id==saved.owner && flags.ident==saved.owner+1);
        if(tag) {
            /* Hostile input is generated even without output preparation. */
            assert(r->curio_tag==CHAOS_CURIO_INERT_REMNANT);
            addinv(r); inert(r);
            r->o_id=saved.owner; r->otyp=WHISTLE; r->oclass=TOOL_CLASS; r->quan=1;
            inert(r); /* repairing ID/type/quantity can never reactivate it */
        } else assert(!r->curio_tag);
        assert(!memcmp(&saved,&u.curio,sizeof saved));
        fclose(f); discard(r); discard(o); discard(owner);
    }
    puts(outgoing ? "output: all byte tags x invalid-state matrix; native resetobjs/saveobjchn/restobjchn" : "input: hostile native streams; actual remapped-ID collision; forced repair; ordinary restore control");
}
static void checktree(struct obj *a, struct obj *b, int demoted)
{
    for(;a && b;a=a->nobj,b=b->nobj) {
        assert(b->curio_tag==(demoted && a->curio_tag ? CHAOS_CURIO_INERT_REMNANT:a->curio_tag));
        assert(a->otyp==b->otyp && a->quan==b->quan);
        if(a->cobj) {
            struct obj *c;
            assert(b->cobj); checktree(a->cobj,b->cobj,demoted);
            for(c=b->cobj;c;c=c->nobj) assert(c->ocontainer==b);
        } else assert(!b->cobj);
    }
    assert(!a && !b);
}
static void nested(void)
{
    struct obj *o=object(BOX,255), *box=object(BOX,0), *r, *owner=object(WHISTLE,1);
    struct chaos_curio_state saved;
    FILE *f;
    addinv(owner); record(owner,0); saved=u.curio;
    add_to_container(o,box); add_to_container(box,object(WHISTLE,1));
    add_to_container(box,object(LONG_SWORD,255)); add_to_container(box,object(WHISTLE,0));
    o->nobj=object(WHISTLE,1);
    /* Native resetobjs skips this root AND its contents, but saveobjchn does not. */
    add_ox(o,OX_ESUM);
    f=stream(o); r=readstream(f,FALSE); checktree(o,r,0);
    saveobjchn(-1,r,FREE_SAVE);
    r=readstream(f,TRUE); checktree(o,r,1); saveobjchn(-1,r,FREE_SAVE); fclose(f);
    resetobjs(o,FALSE);
    assert(o->curio_tag==CHAOS_CURIO_INERT_REMNANT);
    assert(o->nobj->curio_tag==CHAOS_CURIO_INERT_REMNANT);
    assert(box->curio_tag==0 && box->cobj->curio_tag==0);
    assert(box->cobj->nobj->curio_tag==CHAOS_CURIO_INERT_REMNANT);
    assert(box->cobj->nobj->nobj->curio_tag==CHAOS_CURIO_INERT_REMNANT);
    f=stream(o); r=readstream(f,FALSE); checktree(o,r,0);
    saveobjchn(-1,r,FREE_SAVE); fclose(f); saveobjchn(-1,o,FREE_SAVE);
    assert(!memcmp(&saved,&u.curio,sizeof saved)); discard(owner);
    puts("nested: serialized OX_ESUM root and descendants, mixed containers/siblings, native FREE_SAVE");
}
static void controls(void)
{
    struct obj *o=object(WHISTLE,1), *r, *ordinary=object(WHISTLE,0);
    struct chaos_curio_state saved;
    struct monst sleeper;
    char description[161]; FILE *f;
    addinv(o); record(o,0); saved=u.curio; assert(chaos_curio_valid(&u.curio));
    f=stream(o); discard(o); r=readstream(f,FALSE); fclose(f);
    assert(r->where==OBJ_INVENT && !invent); invent=r;
    assert(!memcmp(&saved,&u.curio,sizeof saved));
    assert(chaos_curio_matches(r)); chaos_curio_inspect(r,description);
    assert(!strcmp(description,"Original"));
    assert(command(r)==MOVE_STANDARD && u.curio.charges==1 && u.curio.state==18);
    saved=u.curio;
    memset(&sleeper,0,sizeof sleeper); sleeper.data=&mons[PM_LITTLE_DOG];
    sleeper.mhp=sleeper.mhpmax=10; sleeper.mx=11; sleeper.my=10;
    sleeper.msleeping=sleeper.mcanmove=1; add_mx(&sleeper,MX_EDOG); fmon=&sleeper;
    f=stream(r); flags.ident=saved.owner; o=readstream(f,TRUE); fclose(f);
    /* Standalone decoded foreign chain: simulate pickup, not getlev placement. */
    o->where=OBJ_FREE; addinv(o);
    inert(o); assert(sleeper.msleeping && !EDOG(&sleeper)->whistletime);
    addinv(ordinary); (void)command(ordinary);
    assert(!sleeper.msleeping && EDOG(&sleeper)->whistletime==moves);
    assert(!memcmp(&saved,&u.curio,sizeof saved));
    rem_all_mx(&sleeper); fmon=0; discard(o); discard(r); discard(ordinary);
    puts("controls: ordinary restore executes original Lua; foreign colliding remnant cannot wake pet; ordinary whistle can");
}
int main(int argc, char **argv)
{
    int i; signal(SIGABRT,crash); test_rng_control(); if(argc>1) test_rng_negative_control(argv[1]);
    init_objects(); init_gods(); vision_init();
    urace=races[str2race("human")]; urole=roles[str2role("Wizard")];
    u.uz.dnum=1; u.uz.dlevel=2; dungeons[1].depth_start=1; dungeons[1].num_dunlevs=20;
    u.umonnum=u.umonster=PM_HUMAN; youmonst.data=&mons[PM_HUMAN];
    u.ulevel=1; u.uhp=u.uhprolled=20; u.uen=u.uenrolled=20;
    for(i=0;i<A_MAX;i++) ABASE(i)=AMAX(i)=12;
    u.ux=u.uy=10; u.usanity=73; moves=101; init_artifacts();
    windowprocs.win_putstr=text; windowprocs.win_raw_print=raw;
    windowprocs.win_update_inventory=inventory_display;
    if(argc>1 && !strcmp(argv[1],"output")) matrix(1);
    else if(argc>1 && !strcmp(argv[1],"input")) matrix(0);
    else if(argc>1 && !strcmp(argv[1],"nested")) nested();
    else controls();
    clear_id_mapping(); assert(!invent); return 0;
}
