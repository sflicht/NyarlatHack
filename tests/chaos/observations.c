/* NGPL: real engine observation and safe-point fixtures; no model or game RNG. */
#include "hack.h"
#include "chaos.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static int questions;
static char decline(const char *question, const char *choices, CHAR_P def) {
    (void)question; (void)choices; (void)def; ++questions; return 'n';
}
int main(void) {
    memset(&u,0,sizeof u); init_gods();
    urace.malenum=PM_HUMAN; urole.malenum=PM_WIZARD;
    u.umonnum=u.umonster=PM_HUMAN; youmonst.data=&mons[PM_HUMAN];
    u.usanity=100; u.ux=u.uy=5; u.ulevel=1; u.ualign.god=1;
    u.uz.dnum=0; u.uz.dlevel=1; moves=10;
    u.uhp=7; u.uhpmax=20; u.uen=2; u.uenmax=10;
    chaos_start(); assert(u.chaos.safe==1);
    chaos_event("read","attempt","");
    flags.prayconfirm=1; windowprocs.win_yn_function=decline;
    assert(dopray()==MOVE_CANCELLED); assert(questions==1);
    assert(u.chaos.safe==1); /* declining creates no admission opportunity */
    u.umonnum=PM_JACKAL; youmonst.data=&mons[PM_JACKAL];
    u.mh=3; u.mhmax=9; u.uhp=999; u.uhpmax=1000;
    chaos_event("apply","attempt","");
    u.mh=-4; u.uen=-1; chaos_event("zap","attempt","");
    u.usanity=40; chaos_observe(); assert(u.chaos.safe==2);
    chaos_observe(); assert(u.chaos.safe==2);
    u.usanity=100; chaos_observe(); assert(u.chaos.safe==3);
    puts("native cancellation and coalesced threshold counts verified");
    return 0;
}
