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
    assert(s.spent == 3 && s.reserved == 3); /* ward costs 3 (was 4) */
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
    assert(restored.spent == 3 && restored.reserved == 0);
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
    assert(restored.spent == 6 && restored.reserved == 3);
    assert(chaos_budget(&restored, 100) == 0);
    assert(chaos_budget(&restored, 0) == 6);
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
    assert(s.spent==9 && s.reserved==6); /* ward 3 + hunger 3 + curio 1 + haunt 2 */
    chaos_expire(&s,15);assert(s.spent==9 && s.reserved==0);
    assert(chaos_state_valid(&s));before=s;
    assert(chaos_spend_non_effect(&s,100,1)==CHAOS_BUDGET);
    assert(!memcmp(&s,&before,sizeof s));
    puts("non-effect ok");
}
/* #164 pacing. Independent literals: base 2, descent from DL2 capped +4,
 * level cap 3, witnessed +1 per source capped +2, ceiling 12. */
static void pacing_tests(void)
{
    struct chaos_state s, before, v2;
    int d, i;
    assert(CHAOS_STATE_VERSION == 5 && CHAOS_PACING_VERSION == 1);
    assert(CHAOS_PACING_DESCENT_FROM == 2 && CHAOS_PACING_DESCENT_CAP == 4);
    assert(CHAOS_PACING_LEVEL_CAP == 3 && CHAOS_PACING_WITNESSED_CREDIT == 1);
    assert(CHAOS_PACING_WITNESSED_CAP == 2 && CHAOS_BUDGET_CEILING == 12);
    /* Policy 2 (pacing 0) is unchanged: hooks are no-ops, formula identical. */
    chaos_state_init(&v2); before = v2;
    chaos_pacing_level(&v2, 9); chaos_pacing_credit(&v2, CHAOS_PACING_SRC_ALL);
    assert(!memcmp(&v2, &before, sizeof v2));
    for(i = 0; i <= 100; i += 10) assert(chaos_budget(&v2, i) == 2 + (100 - i) / 10);
    assert(chaos_spend_non_effect(&v2, 100, CHAOS_SPEND_HAUNT) == CHAOS_OK);
    assert(v2.spent == 2 && v2.level_spent == 0 && chaos_state_valid(&v2));
    /* A policy-2 state carrying pacing fields is invalid (fails closed). */
    before = v2; before.deepest = 3; assert(!chaos_state_valid(&before));
    before = v2; before.pacing = 2; assert(!chaos_state_valid(&before));
    /* Descent credit: +1 per deepest level beyond DL2, capped at +4. */
    chaos_state_init(&s); s.pacing = 1;
    for(d = 1; d <= 12; ++d) {
        chaos_pacing_level(&s, d);
        assert(s.deepest == d);
        assert(chaos_pacing_extra(&s) == (d <= 2 ? 0 : d - 2 > 4 ? 4 : d - 2));
    }
    /* Deepest only: bouncing back up and down never grows it or re-opens
     * the per-level allowance. */
    chaos_state_init(&s); s.pacing = 1;
    chaos_pacing_level(&s, 3);
    assert(chaos_spend_non_effect(&s, 100, CHAOS_SPEND_HAUNT) == CHAOS_OK);
    assert(s.level_spent == 2 && chaos_budget(&s, 100) == 1); /* capacity 3 */
    assert(chaos_spend_non_effect(&s, 100, CHAOS_SPEND_CURIO) == CHAOS_OK);
    assert(s.level_spent == 3 && chaos_budget(&s, 100) == 0);
    for(i = 0; i < 20; ++i) {
        chaos_pacing_level(&s, i & 1 ? 2 : 3);
        chaos_pacing_level(&s, 1);
    }
    assert(s.deepest == 3 && s.level_spent == 3 && chaos_pacing_extra(&s) == 1);
    before = s;
    assert(chaos_spend_non_effect(&s, 100, CHAOS_SPEND_CURIO) == CHAOS_BUDGET);
    assert(!memcmp(&s, &before, sizeof s));
    /* A new deepest level opens a fresh per-level allowance of 3. */
    chaos_pacing_level(&s, 4);
    assert(s.level_spent == 0 && chaos_pacing_extra(&s) == 2);
    assert(chaos_budget(&s, 100) == 1);  /* capacity 2 + 2 = 4, 3 spent */
    /* Per-level cap holds even with lifetime capacity to spare. */
    chaos_state_init(&s); s.pacing = 1; chaos_pacing_level(&s, 1);
    assert(chaos_budget(&s, 0) == 3);    /* capacity 12, level cap 3 */
    assert(chaos_spend_non_effect(&s, 0, CHAOS_SPEND_CURIO) == CHAOS_OK);
    assert(chaos_spend_non_effect(&s, 0, CHAOS_SPEND_CURIO) == CHAOS_OK);
    assert(chaos_spend_non_effect(&s, 0, CHAOS_SPEND_CURIO) == CHAOS_OK);
    before = s;
    assert(chaos_spend_non_effect(&s, 0, CHAOS_SPEND_CURIO) == CHAOS_BUDGET);
    assert(chaos_spend_non_effect(&s, 0, CHAOS_SPEND_HAUNT) == CHAOS_BUDGET);
    assert(!memcmp(&s, &before, sizeof s));
    /* Witnessed credit: one per delivering source, idempotent, capped +2. */
    chaos_state_init(&s); s.pacing = 1;
    chaos_pacing_credit(&s, CHAOS_PACING_SRC_HAUNT);
    chaos_pacing_credit(&s, CHAOS_PACING_SRC_HAUNT);
    assert(chaos_pacing_extra(&s) == 1);
    chaos_pacing_credit(&s, CHAOS_PACING_SRC_CURIO);
    chaos_pacing_credit(&s, CHAOS_PACING_SRC_NEXT_USE);
    assert(s.credited == CHAOS_PACING_SRC_ALL && chaos_pacing_extra(&s) == 2);
    before = s; chaos_pacing_credit(&s, 8); chaos_pacing_credit(&s, -1);
    assert(!memcmp(&s, &before, sizeof s));
    /* Lifetime ceiling unchanged: capacity never exceeds 12 however many
     * credits; over-budget still fails closed and leaves state intact. */
    chaos_state_init(&s); s.pacing = 1; s.credited = CHAOS_PACING_SRC_ALL;
    for(d = 3; d <= 40; ++d) {
        chaos_pacing_level(&s, d);
        while(chaos_budget(&s, 0) >= 1)
            assert(chaos_spend_non_effect(&s, 0, CHAOS_SPEND_CURIO) == CHAOS_OK);
    }
    assert(s.spent == 12 && chaos_state_valid(&s));
    chaos_pacing_level(&s, 41); before = s;
    assert(chaos_budget(&s, 0) == 0);
    assert(chaos_spend_non_effect(&s, 0, CHAOS_SPEND_CURIO) == CHAOS_BUDGET);
    assert(!memcmp(&s, &before, sizeof s));
    /* Effects: ward (3, lowered from 4 so it fits K = 3) is admitted when the
     * level has room, and then nothing else mechanical fits on that level;
     * hunger (3) fits exactly on its own. */
    {
        struct chaos_request r = {1, 1, CHAOS_WARD, 50, 5, 2, 1};
        chaos_state_init(&s); s.pacing = 1; s.safe = 1; chaos_pacing_level(&s, 6);
        assert(chaos_admit(&s, &r, 10, 0, 1) == CHAOS_OK);
        assert(s.spent == 3 && s.level_spent == 3 && chaos_budget(&s, 10) == 0);
        r.id = 2; r.kind = CHAOS_HUNGER; r.value = 2; r.telegraph = 3;
        assert(chaos_admit(&s, &r, 10, 0, 1) == CHAOS_BUDGET);
        assert(s.spent == 3 && s.level_spent == 3 && s.reserved == 3);
        before = s;
        assert(chaos_spend_non_effect(&s, 0, CHAOS_SPEND_CURIO) == CHAOS_BUDGET);
        assert(!memcmp(&s, &before, sizeof s));
        chaos_state_init(&s); s.pacing = 1; s.safe = 1; chaos_pacing_level(&s, 6);
        assert(chaos_admit(&s, &r, 10, 0, 1) == CHAOS_OK);
        assert(s.spent == 3 && s.level_spent == 3 && chaos_budget(&s, 10) == 0);
    }
    /* Invalid pacing fields are rejected by validation (save/restore). */
    chaos_state_init(&s); s.pacing = 1;
    before = s; before.deepest = -1; assert(!chaos_state_valid(&before));
    before = s; before.deepest = CHAOS_PACING_MAX_DEPTH + 1; assert(!chaos_state_valid(&before));
    before = s; before.credited = 8; assert(!chaos_state_valid(&before));
    before = s; before.level_spent = 1; assert(!chaos_state_valid(&before)); /* > spent */
    puts("pacing ok");
}
/* #1 door_reluctance: cost 1, halve, 1..300 turns, no Sanity gate. */
static void door_tests(void)
{
    struct chaos_state s, restored, before;
    struct chaos_request r = {1, 1, CHAOS_DOOR, 50, 300, 4, 1};
    FILE *f;
    /* 4 = door extension (#1); 5, 6 = Arc 1 recurrence lines, 7, 8 =
     * broad next-use lines (C) and 9-11 = ring lines, which no mutation
     * references, so no director request can select them. */
    assert(CHAOS_SIGNAL_COUNT == 11 && CHAOS_DURATION_CAP == 300);
    assert(CHAOS_TURN_HEADROOM == 50 && CHAOS_DURATION_HEADROOM == 300);
    chaos_state_init(&s); s.safe = 1;
    /* Full Sanity qualifies: no gate. Budget base 2 at Sanity 100. */
    assert(chaos_admit(&s, &r, 10, 100, 2) == CHAOS_OK);
    assert(s.spent == 1 && s.reserved == 1 && s.effects[CHAOS_DOOR].expires == 310);
    assert(chaos_rule(&s, CHAOS_DOOR, 10, 11) == 5);
    assert(chaos_rule(&s, CHAOS_DOOR, 309, 11) == 5);
    assert(chaos_rule(&s, CHAOS_DOOR, 310, 11) == 11);
    /* Other kinds are untouched while the door effect is active. */
    assert(chaos_rule(&s, CHAOS_HUNGER, 10, 3) == 3 && chaos_rule(&s, CHAOS_WARD, 10, 3) == 3);
    /* Active duplicate: no stacking, no refresh. */
    r.id = 2; s.safe = 2; r.at = 2; before = s;
    assert(chaos_admit(&s, &r, 11, 100, 2) == CHAOS_ACTIVE);
    assert(s.spent == before.spent && s.effects[CHAOS_DOOR].expires == 310);
    /* Save/restore round trip keeps the active effect. */
    f = tmpfile(); assert(f);
    assert(fwrite(&s, sizeof s, 1, f) == 1); rewind(f);
    assert(fread(&restored, sizeof restored, 1, f) == 1); fclose(f);
    assert(chaos_state_valid(&restored));
    assert(chaos_rule(&restored, CHAOS_DOOR, 200, 11) == 5);
    chaos_expire(&restored, 310);
    assert(!restored.reserved && restored.spent == 1 && chaos_rule(&restored, CHAOS_DOOR, 310, 11) == 11);
    /* Unconscious or dead: ineligible. */
    chaos_state_init(&s); s.safe = 1; r.id = 1; r.at = 1;
    assert(chaos_admit(&s, &r, 10, 100, 0) == CHAOS_INELIGIBLE && !s.spent);
    /* Over budget: pacing capacity exhausted. */
    chaos_state_init(&s); s.safe = 1; s.spent = 2;
    assert(chaos_admit(&s, &r, 10, 100, 2) == CHAOS_BUDGET && s.spent == 2);
    /* Bad duration, value or telegraph: rejected at the parser/validator. */
    assert(chaos_parse("{\"v\":1,\"id\":1,\"mutation\":\"door_reluctance\",\"value\":50,\"duration\":301,\"telegraph\":4,\"at\":1}", strlen("{\"v\":1,\"id\":1,\"mutation\":\"door_reluctance\",\"value\":50,\"duration\":301,\"telegraph\":4,\"at\":1}"), &r) == CHAOS_SCHEMA);
    assert(chaos_parse("{\"v\":1,\"id\":1,\"mutation\":\"door_reluctance\",\"value\":50,\"duration\":0,\"telegraph\":4,\"at\":1}", strlen("{\"v\":1,\"id\":1,\"mutation\":\"door_reluctance\",\"value\":50,\"duration\":0,\"telegraph\":4,\"at\":1}"), &r) == CHAOS_SCHEMA);
    assert(chaos_parse("{\"v\":1,\"id\":1,\"mutation\":\"door_reluctance\",\"value\":50,\"duration\":300,\"telegraph\":1,\"at\":1}", strlen("{\"v\":1,\"id\":1,\"mutation\":\"door_reluctance\",\"value\":50,\"duration\":300,\"telegraph\":1,\"at\":1}"), &r) == CHAOS_SCHEMA);
    assert(chaos_parse("{\"v\":1,\"id\":1,\"mutation\":\"door_reluctance\",\"value\":49,\"duration\":300,\"telegraph\":4,\"at\":1}", strlen("{\"v\":1,\"id\":1,\"mutation\":\"door_reluctance\",\"value\":49,\"duration\":300,\"telegraph\":4,\"at\":1}"), &r) == CHAOS_SCHEMA);
    assert(chaos_parse("{\"v\":1,\"id\":1,\"mutation\":\"door_reluctance\",\"value\":50,\"duration\":300,\"telegraph\":4,\"at\":1}", strlen("{\"v\":1,\"id\":1,\"mutation\":\"door_reluctance\",\"value\":50,\"duration\":300,\"telegraph\":4,\"at\":1}"), &r) == CHAOS_OK);
    /* Hunger and ward keep their own 50-turn bound. */
    assert(chaos_parse("{\"v\":1,\"id\":1,\"mutation\":\"hunger_rate\",\"value\":2,\"duration\":51,\"telegraph\":3,\"at\":1}", strlen("{\"v\":1,\"id\":1,\"mutation\":\"hunger_rate\",\"value\":2,\"duration\":51,\"telegraph\":3,\"at\":1}"), &r) == CHAOS_SCHEMA);
    assert(chaos_parse("{\"v\":1,\"id\":1,\"mutation\":\"ward_efficacy\",\"value\":50,\"duration\":51,\"telegraph\":2,\"at\":1}", strlen("{\"v\":1,\"id\":1,\"mutation\":\"ward_efficacy\",\"value\":50,\"duration\":51,\"telegraph\":2,\"at\":1}"), &r) == CHAOS_SCHEMA);
    /* Overflow guard reads the larger cap. */
    chaos_state_init(&s); s.safe = 1; r = (struct chaos_request){1, 1, CHAOS_DOOR, 50, 300, 4, 1};
    assert(chaos_admit(&s, &r, LONG_MAX - 299, 100, 2) == CHAOS_INELIGIBLE);
    r.id = 2; s.safe = 2; r.at = 2;
    assert(chaos_admit(&s, &r, LONG_MAX - 300, 100, 2) == CHAOS_OK);
    puts("door ok");
}
int main(int argc, char **argv)
{
    char buf[2048], out[16384];
    size_t n;
    struct chaos_request r;
    if(argc > 1 && !strcmp(argv[1], "state")) { state_tests(); return 0; }
    if(argc > 1 && !strcmp(argv[1], "non-effect")) { non_effect_tests(); return 0; }
    if(argc > 1 && !strcmp(argv[1], "pacing")) { pacing_tests(); return 0; }
    if(argc > 1 && !strcmp(argv[1], "door")) { door_tests(); return 0; }
    n = fread(buf, 1, sizeof buf, stdin);
    if(argc > 1 && !strcmp(argv[1], "escape")) {
        assert(chaos_quote(out, sizeof out, buf, n)); puts(out); return 0;
    }
    puts(chaos_reason(chaos_parse(buf, n, &r)));
    return 0;
}
