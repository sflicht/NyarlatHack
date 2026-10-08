/* NGPL: controlled map fixtures with actual native objects, not bones files. */
#include "hack.h"
#include "mkroom.h"
#include "chaos.h"
#include "chaos_curio.h"
#include <assert.h>
#include <stdio.h>
#include "native_rng.h"
extern int n_dgns; /* src/dungeon.c, not in any header */

static int creates, fail_create, shadow;
/* Controlled getbones early-return, explicitly not a real bones file. */
int __wrap_getbones(void) { return 1; }
struct obj *__real_mksobj(int, int);
struct obj *__wrap_mksobj(int typ, int fl) {
    ++creates; assert(typ == WHISTLE && fl == MKOBJ_NOINIT);
    return fail_create ? (struct obj *)0 : __real_mksobj(typ, fl);
}
boolean __wrap_chaos_shadow_active(void) { return shadow; }
/* Weak placeholders let RED exercise the missing behavior, not link failure. */
void chaos_curio_prepare(unsigned) __attribute__((weak));
void chaos_curio_begin(void) __attribute__((weak));
void chaos_curio_ordinary(void) __attribute__((weak));
void chaos_curio_finish(int) __attribute__((weak));
static void generation(unsigned fl, int ordinary, int bones) {
    if (chaos_curio_prepare) chaos_curio_prepare(fl);
    if (chaos_curio_begin) chaos_curio_begin();
    if (ordinary && chaos_curio_ordinary) chaos_curio_ordinary();
    if (chaos_curio_finish) chaos_curio_finish(!bones);
    assert(u.chaos.spent==1);
}
static void fixture(void) {
    int x,y;
    chaos_state_init(&u.chaos);u.chaos.spent=1;
    memset(&u.curio,0,sizeof u.curio);
    u.curio.version=1; u.curio.phase=CHAOS_CURIO_ADMITTED;
    strcpy(u.curio.source,"return {name='Counter',inspect=function(c) return 'Quiet.' end,apply=function(c) return {text='Quiet.',state=0,sanity_delta=0} end}");
    u.curio.source_len=strlen(u.curio.source); strcpy(u.curio.name,"Counter");
    u.curio.charges=3;
    memset(levl,0,sizeof levl); memset(rooms,0,sizeof rooms);
    memset(&level.flags,0,sizeof level.flags);
    memset(level.objects,0,sizeof level.objects);
    memset(level.monsters,0,sizeof level.monsters);
    fobj=0; ftrap=0; nroom=2; creates=0; shadow=fail_create=0;
    u.uz.dnum=0; u.uz.dlevel=2;
    /* Absolute depth: main dungeon from 1, Mines (dnum 1) from 3, Sokoban
     * (dnum 2) from 2. The dungeon numbers are this fixture's, not dNAO's. */
    n_dgns=3; dungeon_topology.d_mines_dnum=1; dungeon_topology.d_sokoban_dnum=2;
    dungeons[0].depth_start=1; dungeons[0].num_dunlevs=25;
    dungeons[1].depth_start=3; dungeons[1].num_dunlevs=10;
    dungeons[2].depth_start=2; dungeons[2].num_dunlevs=4;
    rooms[0].lx=3; rooms[0].hx=7; rooms[0].ly=3; rooms[0].hy=7;
    rooms[1].lx=12; rooms[1].hx=16; rooms[1].ly=3; rooms[1].hy=7;
    for(x=3;x<=16;x++) for(y=3;y<=7;y++)
        if(x<=7 || x>=12) levl[x][y].typ=ROOM;
    upstairs_room=&rooms[1]; xupstair=14; yupstair=5;
    levl[14][5].typ=STAIRS;
}
int main(int argc, char **argv) {
    struct chaos_curio_state before; struct obj *o; int i, expected;
    unsigned excluded[]={LFILE_EXISTS,VISITED,FORGOTTEN,LFILE_EXISTS|VISITED};

    test_rng_control();
    if (argc>1) test_rng_negative_control(argv[1]);
    init_objects();
    init_gods(); urace.malenum=PM_HUMAN; urole.malenum=PM_WIZARD;
    u.umonnum=u.umonster=PM_HUMAN; youmonst.data=&mons[PM_HUMAN];
    u.ulevel=1; u.usanity=100; u.uhp=10; flags.ident=1;
    /* Slice 2b: a placing generation, mksobj(WHISTLE, MKOBJ_NOINIT) included,
     * draws nothing from the RNG (counted rn2 draws and raw random()), so a
     * replayed curio cannot shift the game's random stream. */
    fixture(); before=u.curio;
    expected=test_rng_begin();
    generation(0,1,0);
    test_rng_unchanged(expected);
    assert(creates==1 && u.curio.phase==CHAOS_CURIO_PLACED);
    o=fobj; assert(o && !o->nobj && o->o_id==u.curio.owner);
    assert(o->otyp==WHISTLE && o->quan==1 && o->nomerge);
    assert(o->curio_tag==CHAOS_CURIO_GENERATED && o->where==OBJ_FLOOR);
    assert(o->ox>=12 && o->ox<=16 && distmin(o->ox,o->oy,14,5)==1);
    before.phase=CHAOS_CURIO_PLACED; before.owner=o->o_id;
    assert(!memcmp(&before,&u.curio,sizeof before) && chaos_curio_valid(&u.curio));
    u.uz.dlevel=3; chaos_curio_safe(-1); generation(0,1,0);
    assert(creates==1 && u.curio.phase==CHAOS_CURIO_PLACED);
    obj_extract_self(o); obfree(o,0);
    generation(0,1,0); assert(creates==1);
    for(i=0;i<4;i++) { fixture(); generation(excluded[i],1,0); assert(!creates); }
    fixture(); generation(0,1,1); assert(!creates);
    fixture(); chaos_curio_prepare(0); mklev(); assert(!creates);
    chaos_curio_begin(); chaos_curio_ordinary(); chaos_curio_finish(1); assert(!creates);
    fixture(); generation(0,0,0); assert(!creates);
    fixture(); u.uz.dnum=1; generation(0,1,0); assert(creates==1); /* Mines */
    /* The window by absolute depth (#item 2): main 2..5 places, 1 and 6 not. */
    for(i=1;i<=7;i++) {
        fixture(); u.uz.dlevel=i; generation(0,1,0);
        assert(creates==(i>=CHAOS_CURIO_PLACE_MIN_DEPTH && i<=CHAOS_CURIO_PLACE_MAX_DEPTH));
        assert(u.curio.phase==(creates?CHAOS_CURIO_PLACED:CHAOS_CURIO_ADMITTED));
    }
    assert(CHAOS_CURIO_PLACE_MIN_DEPTH==2 && CHAOS_CURIO_PLACE_MAX_DEPTH==5);
    /* Mines filler: makemaz("minefill") never marks ordinary generation.
     * Depth 3..5 places (dlevel 1..3), depth 6 does not. */
    for(i=1;i<=4;i++) {
        fixture(); u.uz.dnum=1; u.uz.dlevel=i; generation(0,0,0);
        assert(creates==(depth(&u.uz)<=5) && depth(&u.uz)==i+2);
    }
    /* Minetown / Mines' End are special levels: refused. */
    {
        s_level special;
        memset(&special,0,sizeof special); fixture(); u.uz.dnum=1; u.uz.dlevel=2;
        special.dlevel=u.uz; sp_levchn=&special;
        generation(0,0,0); assert(!creates); sp_levchn=0;
    }
    fixture(); u.uz.dnum=1; level.flags.is_maze_lev=1; generation(0,0,0); assert(!creates);
    fixture(); u.uz.dnum=1; generation(LFILE_EXISTS|VISITED,0,0); assert(!creates);
    /* Sokoban at depth 2..5, ordinary or not: never. */
    for(i=1;i<=4;i++) {
        fixture(); u.uz.dnum=2; u.uz.dlevel=i; generation(0,1,0); assert(!creates);
        generation(0,0,0); assert(!creates && u.curio.phase==CHAOS_CURIO_ADMITTED);
    }
    /* Any other branch (here dnum 3, depth 3): never. */
    fixture(); n_dgns=4; dungeons[3].depth_start=3; dungeons[3].num_dunlevs=5;
    u.uz.dnum=3; u.uz.dlevel=1; generation(0,1,0); assert(!creates);
    /* Expiry: a safe point at depth 6 or deeper, any branch; not at 5,
     * not in Sokoban at depth 5 (dlevel 4). */
    fixture(); u.uz.dlevel=5; chaos_curio_safe(-1); assert(u.curio.phase==CHAOS_CURIO_ADMITTED);
    u.uz.dnum=2; u.uz.dlevel=4; chaos_curio_safe(-1); assert(u.curio.phase==CHAOS_CURIO_ADMITTED);
    u.uz.dnum=1; u.uz.dlevel=3; chaos_curio_safe(-1); assert(u.curio.phase==CHAOS_CURIO_ADMITTED);
    u.uz.dnum=1; u.uz.dlevel=4; chaos_curio_safe(-1); assert(u.curio.phase==CHAOS_CURIO_EXPIRED);
    fixture(); u.uz.dlevel=6; chaos_curio_safe(-1); assert(u.curio.phase==CHAOS_CURIO_EXPIRED);
    generation(0,1,0); assert(!creates);
    fixture(); u.uz.dnum=3; u.uz.dlevel=4; n_dgns=4;
    dungeons[3].depth_start=3; chaos_curio_safe(-1); assert(u.curio.phase==CHAOS_CURIO_EXPIRED);
    assert(CHAOS_CURIO_EXPIRE_DEPTH==6);
    {
        s_level special;
        memset(&special,0,sizeof special); fixture();
        special.dlevel=u.uz; sp_levchn=&special;
        generation(0,1,0); assert(!creates); sp_levchn=0;
    }
    {
        static branch entrance;
        memset(&entrance,0,sizeof entrance); fixture();
        entrance.end1=u.uz; entrance.end2.dnum=1; entrance.end2.dlevel=1;
        insert_branch(&entrance,FALSE);
        assert(Is_branchlev(&u.uz)==&entrance);
        generation(0,1,0); assert(creates==1);
    }
    fixture(); level.flags.is_maze_lev=1; generation(0,1,0); assert(!creates);
    fixture(); dungeons[0].proto[0]='x'; generation(0,1,0); assert(!creates);
    dungeons[0].proto[0]=0;
    fixture(); rogue_level=u.uz; generation(0,1,0); assert(!creates);
    rogue_level.dlevel=0;
    fixture(); shadow=1; generation(0,1,0); shadow=0;
    chaos_curio_begin(); chaos_curio_ordinary(); chaos_curio_finish(1); assert(!creates);
    fixture(); chaos_curio_prepare(0); u.uz.dlevel=3;
    chaos_curio_begin(); chaos_curio_ordinary(); chaos_curio_finish(1); assert(!creates);
    fixture(); chaos_curio_prepare(0); chaos_curio_begin(); chaos_curio_begin();
    chaos_curio_ordinary(); chaos_curio_finish(1); assert(!creates);
    for(i=0;i<3;i++) {
        fixture(); memset(&u.curio,0,sizeof u.curio);
        if(i) { u.curio.version=1; u.curio.phase=i==1?CHAOS_CURIO_REJECTED:CHAOS_CURIO_EXPIRED; }
        expected=test_rng_begin();
        generation(0,1,0);
        test_rng_unchanged(expected);
        assert(!creates);
        assert(!fobj);
    }
    fixture(); rooms[0].rtype=rooms[1].rtype=SHOPBASE;
    generation(0,1,0); assert(!creates && u.curio.phase==CHAOS_CURIO_ADMITTED);
    rooms[0].rtype=OROOM; u.uz.dlevel=3; generation(0,1,0); assert(creates==1);
    fixture(); rooms[0].rtype=rooms[1].rtype=SHOPBASE;
    generation(0,1,0); u.uz.dlevel=3; generation(0,1,0); u.uz.dlevel=6; chaos_curio_safe(-1);
    assert(!creates && u.curio.phase==CHAOS_CURIO_EXPIRED && u.chaos.spent==1);
    fixture(); fail_create=1; generation(0,1,0); assert(creates==1);
    assert(u.curio.phase==CHAOS_CURIO_EXPIRED && chaos_curio_valid(&u.curio));
    fail_create=0; u.uz.dlevel=3; generation(0,1,0); assert(creates==1);
    /* Irregular room membership and subroom exclusion, not bounding boxes. */
    fixture(); rooms[1].irregular=1; rooms[0].rtype=SHOPBASE;
    generation(0,1,0); assert(!creates);
    levl[12][3].roomno=ROOMOFFSET+1; generation(0,1,0); assert(creates==1 && fobj->ox==12 && fobj->oy==3);
    fixture(); rooms[0].rtype=SHOPBASE; rooms[1].nsubrooms=1;
    rooms[1].sbrooms[0]=&rooms[2]; rooms[2]=rooms[1]; rooms[2].nsubrooms=0;
    generation(0,1,0); assert(!creates);
    /* Only one free dry room square; all others are reserved/occupied. */
    fixture(); rooms[0].rtype=SHOPBASE;
    for(i=12;i<=16;i++) { int y; for(y=3;y<=7;y++) levl[i][y].typ=POOL; }
    levl[12][3].typ=ROOM; generation(0,1,0); assert(creates==1 && fobj->ox==12 && fobj->oy==3);
    /* Occupancy rejection independently for each native map index. */
    for(i=0;i<3;i++) {
        struct trap trap; struct monst monster; struct obj object;
        int x,y;
        fixture(); rooms[0].rtype=SHOPBASE;
        for(x=12;x<=16;x++) for(y=3;y<=7;y++) levl[x][y].typ=ALTAR;
        levl[12][3].typ=ROOM;
        memset(&trap,0,sizeof trap); trap.tx=12; trap.ty=3;
        if(i==0) ftrap=&trap;
        if(i==1) level.monsters[12][3]=&monster;
        if(i==2) level.objects[12][3]=&object;
        generation(0,1,0); assert(!creates);
        ftrap=0;
    }
    puts("controlled map placement, freshness, one-shot, source and RNG checks passed");
    return 0;
}
