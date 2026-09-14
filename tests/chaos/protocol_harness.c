/* NetHack General Public License; test the production protocol core. */
#include "chaos_protocol.h"
#include <assert.h>
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
int main(int argc, char **argv)
{
    char buf[2048], out[16384];
    size_t n;
    struct chaos_request r;
    if(argc > 1 && !strcmp(argv[1], "state")) { state_tests(); return 0; }
    n = fread(buf, 1, sizeof buf, stdin);
    if(argc > 1 && !strcmp(argv[1], "escape")) {
        assert(chaos_quote(out, sizeof out, buf, n)); puts(out); return 0;
    }
    puts(chaos_reason(chaos_parse(buf, n, &r)));
    return 0;
}
