/* NetHack General Public License: link the real game, not mock rule functions.
 * Controlled initialized player/monster fixtures test onscary and gethungry.
 * This is a linked-engine test, not a full terminal gameplay session. */
#include "hack.h"
#include "chaos.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "native_rng.h"

static void cosmetic(int prefixed) {
    assert(u.chaos.cosmetic_seen==prefixed && u.chaos.cosmetic_last_turn==0);
}
static void begin_rule(int prefixed) {
    struct chaos_request ambient={1,1,CHAOS_AMBIENT,1,0,1,1};
    chaos_state_init(&u.chaos); u.chaos.safe=1;
    /* Actual core admission; this does not witness ambient UI delivery. */
    if(prefixed) assert(chaos_admit(&u.chaos,&ambient,0,60,1)==CHAOS_OK);
    assert(!u.chaos.spent && !u.chaos.reserved);
    cosmetic(prefixed);
}
int main(int argc, char **argv) {
    struct monst monster;
    struct engr *engr;
    int prefixed=argc==2;
    struct chaos_request hunger = {1,1,CHAOS_HUNGER,2,5,3,1};
    struct chaos_request ward = {1,1,CHAOS_WARD,50,5,2,1};
    assert(argc==1 || (argc==2 && !strcmp(argv[1],"--ambient-prefix")));
    hunger.id+=prefixed;ward.id+=prefixed;
    test_rng_control();test_rng_reset(); /* Same seed123 in both arms. */
    memset(&u,0,sizeof u);
    init_gods(); /* onscary also evaluates deity-specific protections */
    urace.malenum=PM_HUMAN; urole.malenum=PM_WIZARD;
    u.umonnum=u.umonster=PM_HUMAN; youmonst.data=&mons[PM_HUMAN];
    u.usanity=60; u.uhungermax=2000; u.uhunger=900; u.uhs=NOT_HUNGRY;
    u.uhp=u.uhpmax=20; u.ulevel=1; u.ux=5; u.uy=5;
    moves=10;
    begin_rule(prefixed);
    gethungry(); assert(u.uhunger==899);
    u.uhunger=900;
    assert(chaos_admit(&u.chaos,&hunger,moves,60,1)==CHAOS_OK);
    assert(u.chaos.spent==3 && u.chaos.reserved==3);cosmetic(prefixed);
    gethungry(); assert(u.uhunger==898);
    moves=15; u.uhunger=900;
    gethungry(); assert(u.uhunger==899);
    chaos_expire(&u.chaos,moves);
    assert(u.chaos.spent==3 && !u.chaos.reserved);cosmetic(prefixed);
    printf("real gethungry: normal=1, admitted hunger=2, expired=1\n");

    moves=20; begin_rule(prefixed);
    memset(&monster,0,sizeof monster);
    monster.data=&mons[PM_LITTLE_DOG]; monster.mtyp=PM_LITTLE_DOG;
    monster.mux=9; monster.muy=9; monster.mx=11; monster.my=10;
    make_engr_at(10,10,"",moves,DUST);
    engr=engr_at(10,10); assert(engr);
    engr->ward_id=HEPTAGRAM; engr->complete_wards=1;
    assert(num_wards_at(10,10)==1);
    assert(onscary(10,10,&monster));
    assert(chaos_admit(&u.chaos,&ward,moves,60,1)==CHAOS_OK);
    assert(u.chaos.spent==4 && u.chaos.reserved==4);cosmetic(prefixed);
    assert(!onscary(10,10,&monster));
    assert(num_wards_at(10,10)==1); /* actual engraving is not erased */
    moves=25;
    assert(onscary(10,10,&monster));
    assert(num_wards_at(10,10)==1);
    chaos_expire(&u.chaos,moves);
    assert(u.chaos.spent==4 && !u.chaos.reserved);cosmetic(prefixed);
    printf("real onscary: protected=1, admitted ward=0, expired=1; engraving retained\n");
    { int count=reseed_count, next=rn2(100000);
      printf("seed=123 moves=10,15,20,25 rng_count=%d next_draw=%d\n",count,next); }
    return 0;
}
