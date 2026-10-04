/* NGPL: controlled map fixtures with actual native objects, not bones files. */
#include "hack.h"
#include "mkroom.h"
#include "chaos.h"
#include "chaos_curio.h"
#include <assert.h>
#include <stdio.h>
#include "native_rng.h"

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
    rooms[0].lx=3; rooms[0].hx=7; rooms[0].ly=3; rooms[0].hy=7;
    rooms[1].lx=12; rooms[1].hx=16; rooms[1].ly=3; rooms[1].hy=7;
    for(x=3;x<=16;x++) for(y=3;y<=7;y++)
        if(x<=7 || x>=12) levl[x][y].typ=ROOM;
    upstairs_room=&rooms[1]; xupstair=14; yupstair=5;
    levl[14][5].typ=STAIRS;
}

static int draws_and_raw(void (*body)(void), int *raw_changed) {
    int expected, count, next;
    expected = test_rng_begin();          /* reset; expected = first rn2 */
    body();
    count = reseed_count;                 /* rn2-family draws via check_reseed */
    next = rn2(100000);
    /* With zero counted draws, a changed next value means raw random(). */
    *raw_changed = (count == 0 && next != expected);
    return count;
}
static void one_whistle(void) { (void)__real_mksobj(WHISTLE, MKOBJ_NOINIT); }
static void placement(void) { generation(0,1,0); }
int main(void) {
    int raw, n, i;
    test_rng_control();
    init_objects();
    init_gods(); urace.malenum=PM_HUMAN; urole.malenum=PM_WIZARD;
    u.umonnum=u.umonster=PM_HUMAN; youmonst.data=&mons[PM_HUMAN];
    u.ulevel=1; u.usanity=100; u.uhp=10; flags.ident=1;
    for (i = 0; i < 5; i++) {
        fixture();
        n = draws_and_raw(one_whistle, &raw);
        printf("mksobj(WHISTLE,MKOBJ_NOINIT) draws=%d raw_random=%d\n", n, raw);
    }
    for (i = 0; i < 3; i++) {
        fixture();
        n = draws_and_raw(placement, &raw);
        printf("full placement draws=%d raw_random=%d creates=%d placed=%d\n",
               n, raw, creates, u.curio.phase==CHAOS_CURIO_PLACED);
    }
    return 0;
}
