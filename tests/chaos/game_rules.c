/* NetHack General Public License: link the real game, not mock rule functions.
 * Controlled initialized player/monster fixtures test onscary and gethungry.
 * This is a linked-engine test, not a full terminal gameplay session. */
#include "hack.h"
#include "chaos.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void) {
    struct monst monster;
    struct engr *engr;
    struct chaos_request hunger = {1,1,CHAOS_HUNGER,2,5,3,1};
    struct chaos_request ward = {1,1,CHAOS_WARD,50,5,2,1};
    memset(&u,0,sizeof u);
    init_gods(); /* onscary also evaluates deity-specific protections */
    urace.malenum=PM_HUMAN; urole.malenum=PM_WIZARD;
    u.umonnum=u.umonster=PM_HUMAN; youmonst.data=&mons[PM_HUMAN];
    u.usanity=60; u.uhungermax=2000; u.uhunger=900; u.uhs=NOT_HUNGRY;
    u.uhp=u.uhpmax=20; u.ulevel=1; u.ux=5; u.uy=5;
    moves=10;
    chaos_state_init(&u.chaos); u.chaos.safe=1;
    gethungry(); assert(u.uhunger==899);
    u.uhunger=900;
    assert(chaos_admit(&u.chaos,&hunger,moves,60,1)==CHAOS_OK);
    gethungry(); assert(u.uhunger==898);
    moves=15; u.uhunger=900;
    gethungry(); assert(u.uhunger==899);
    printf("real gethungry: normal=1, admitted hunger=2, expired=1\n");

    moves=20; chaos_state_init(&u.chaos); u.chaos.safe=1;
    memset(&monster,0,sizeof monster);
    monster.data=&mons[PM_LITTLE_DOG]; monster.mtyp=PM_LITTLE_DOG;
    monster.mux=9; monster.muy=9; monster.mx=11; monster.my=10;
    make_engr_at(10,10,"",moves,DUST);
    engr=engr_at(10,10); assert(engr);
    engr->ward_id=HEPTAGRAM; engr->complete_wards=1;
    assert(num_wards_at(10,10)==1);
    assert(onscary(10,10,&monster));
    assert(chaos_admit(&u.chaos,&ward,moves,60,1)==CHAOS_OK);
    assert(!onscary(10,10,&monster));
    assert(num_wards_at(10,10)==1); /* actual engraving is not erased */
    moves=25;
    assert(onscary(10,10,&monster));
    printf("real onscary: protected=1, admitted ward=0, expired=1; engraving retained\n");
    return 0;
}
