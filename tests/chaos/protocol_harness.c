/* NetHack General Public License; test the production protocol core. */
#include "chaos_protocol.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

static void state_tests(void)
{
    struct chaos_state s, restored;
    struct chaos_request r = {1, 1, CHAOS_WARD, 50, 5, 2, 1};
    FILE *f;
    chaos_state_init(&s);
    s.safe = 1;
    assert(chaos_admit(&s, &r, 10, 100, 1) == CHAOS_INELIGIBLE);
    assert(s.last_id == 1 && s.spent == 0);
    assert(chaos_admit(&s, &r, 10, 80, 1) == CHAOS_DUPLICATE);
    r.id = 2;
    assert(chaos_admit(&s, &r, 10, 80, 1) == CHAOS_OK);
    assert(s.spent == 4 && s.reserved == 4);
    assert(chaos_rule(&s, CHAOS_WARD, 10, 3) == 1);
    assert(chaos_rule(&s, CHAOS_HUNGER, 10, 3) == 3);
    r.id = 3;
    assert(chaos_admit(&s, &r, 11, 0, 1) == CHAOS_ACTIVE);
    f = tmpfile(); assert(f);
    assert(fwrite(&s, sizeof s, 1, f) == 1); rewind(f);
    assert(fread(&restored, sizeof restored, 1, f) == 1); fclose(f);
    assert(chaos_state_valid(&restored));
    assert(chaos_rule(&restored, CHAOS_WARD, 14, 3) == 1);
    assert(chaos_admit(&restored, &r, 14, 0, 1) == CHAOS_DUPLICATE);
    assert(chaos_rule(&restored, CHAOS_WARD, 15, 3) == 3);
    chaos_expire(&restored, 15);
    assert(restored.spent == 4 && restored.reserved == 0);
    r.id = 4;
    assert(chaos_admit(&restored, &r, 15, 80, 1) == CHAOS_BUDGET);
    r.id = 5; r.at = 2;
    assert(chaos_admit(&restored, &r, 15, 0, 1) == CHAOS_FUTURE);
    assert(restored.last_id == 4);
    restored.safe = 3;
    assert(chaos_admit(&restored, &r, 15, 0, 1) == CHAOS_SCHEDULE);
    r.id = 6; r.at = 3; r.kind = CHAOS_HUNGER; r.value = 2; r.telegraph = 3;
    assert(chaos_admit(&restored, &r, 15, 0, 0) == CHAOS_INELIGIBLE);
    r.id = 7;
    assert(chaos_admit(&restored, &r, 15, 0, 1) == CHAOS_OK);
    assert(chaos_rule(&restored, CHAOS_HUNGER, 16, 3) == 6);
    assert(restored.spent == 7 && restored.reserved == 3);
    assert(chaos_budget(&restored, 100) == 0);
    assert(chaos_budget(&restored, 0) == 5);
    assert(chaos_state_valid(&restored));
    restored.spent = 100; assert(!chaos_state_valid(&restored));
    puts("state ok");
}
static void non_effect_tests(void)
{
    const int sanities[] = {-1,0,60,90,100,101};
    const int invalid[] = {-1,13,INT_MIN,INT_MAX};
    const int selectors[] = {0,-1,3,INT_MAX};
    struct chaos_state s, before, expected;
    struct chaos_request r = {1,1,CHAOS_WARD,50,5,2,1};
    size_t i; int spent, spender, cost, capacity, result, field;
    assert(CHAOS_SPEND_CURIO == 1 && CHAOS_SPEND_HAUNT == 2);
    assert(CHAOS_COST_CURIO == 1 && CHAOS_COST_HAUNT == 2);
    assert(chaos_spend_non_effect(NULL,100,CHAOS_SPEND_CURIO)==CHAOS_SCHEMA);
    for(spender=1;spender<=2;++spender) {
        cost=spender; /* Independent literal prices 1 and 2. */
        for(i=0;i<sizeof sanities/sizeof *sanities;++i) {
            int sanity=sanities[i];
            capacity=2+(100-(sanity<0?0:sanity>100?100:sanity))/10;
            for(spent=0;spent<=12;++spent) {
                chaos_state_init(&s);s.spent=spent;s.seq=9;s.safe=7;s.last_id=3;
                before=s;expected=s;
                result=spent+cost<=capacity?CHAOS_OK:CHAOS_BUDGET;
                if(result==CHAOS_OK)expected.spent+=cost;
                assert(chaos_spend_non_effect(&s,sanity,spender)==result);
                assert(!memcmp(&s,&expected,sizeof s));
            }
        }
        for(i=0;i<sizeof invalid/sizeof *invalid;++i) {
            chaos_state_init(&s);s.spent=invalid[i];before=s;
            assert(chaos_spend_non_effect(&s,0,spender)==CHAOS_SCHEMA);
            assert(!memcmp(&s,&before,sizeof s));
        }
        for(field=0;field<9;++field) {
            chaos_state_init(&s);
            switch(field) {
            case 0:s.version=0;break;case 1:s.reserved=1;break;
            case 2:s.last_id=-1;break;case 3:s.seq=-1;break;case 4:s.safe=-1;break;
            case 5:s.effects[CHAOS_AMBIENT].value=1;break;
            case 6:s.effects[CHAOS_WARD].cost=4;break;
            case 7:s.effects[CHAOS_WARD].expires=1;break;
            case 8:s.effects[CHAOS_WARD].value=49;break;
            }
            before=s;assert(chaos_spend_non_effect(&s,0,spender)==CHAOS_SCHEMA);
            assert(!memcmp(&s,&before,sizeof s));
        }
        chaos_state_init(&s);
        while(s.spent+cost<=12)assert(chaos_spend_non_effect(&s,0,spender)==CHAOS_OK);
        before=s;assert(s.spent==12);
        assert(chaos_spend_non_effect(&s,0,spender)==CHAOS_BUDGET);
        assert(!memcmp(&s,&before,sizeof s));
    }
    chaos_state_init(&s);
    for(i=0;i<sizeof selectors/sizeof *selectors;++i) {
        before=s;assert(chaos_spend_non_effect(&s,0,selectors[i])==CHAOS_SCHEMA);
        assert(!memcmp(&s,&before,sizeof s));
    }
    s.safe=1;assert(chaos_admit(&s,&r,10,0,1)==CHAOS_OK);
    r.id=2;r.kind=CHAOS_HUNGER;r.value=2;r.telegraph=3;
    assert(chaos_admit(&s,&r,10,0,1)==CHAOS_OK);
    for(spender=1;spender<=2;++spender) {
        expected=s;expected.spent+=spender;
        assert(chaos_spend_non_effect(&s,0,spender)==CHAOS_OK);
        assert(!memcmp(&s,&expected,sizeof s));
    }
    assert(s.spent==10 && s.reserved==7);
    chaos_expire(&s,15);assert(s.spent==10 && s.reserved==0);
    assert(chaos_state_valid(&s));before=s;
    assert(chaos_spend_non_effect(&s,100,1)==CHAOS_BUDGET);
    assert(!memcmp(&s,&before,sizeof s));
    puts("non-effect ok");
}
int main(int argc, char **argv)
{
    char buf[2048], out[16384];
    size_t n;
    struct chaos_request r;
    if(argc > 1 && !strcmp(argv[1], "state")) { state_tests(); return 0; }
    if(argc > 1 && !strcmp(argv[1], "non-effect")) { non_effect_tests(); return 0; }
    n = fread(buf, 1, sizeof buf, stdin);
    if(argc > 1 && !strcmp(argv[1], "escape")) {
        assert(chaos_quote(out, sizeof out, buf, n)); puts(out); return 0;
    }
    puts(chaos_reason(chaos_parse(buf, n, &r)));
    return 0;
}
