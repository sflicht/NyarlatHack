/* NGPL: private test executable. Injected inventory, NOT natural admission.
 * All input, menus, description rendering and command dispatch use real tty.
 */
#include "hack.h"
#include "chaos_curio.h"
#include <assert.h>
#include <stdio.h>
#include "native_rng.h"

int original_game_main(int, char **);
void __real_chaos_start(void);
int __real_ddoinv(void);
void __real_checkfile(char *, struct permonst *, int, int, winid *);
static struct obj *curio;
static int active, encyclopedias;

static FILE *file(const char *name, const char *mode)
{
    FILE *f = fopen(name, mode);
    assert(f);
    return f;
}

void __wrap_chaos_start(void)
{
    FILE *f;
    int mode;
    size_t n;
    __real_chaos_start();
    assert(!curio);
    f = file("fixture-mode.txt", "r");
    assert(fscanf(f, "%d", &mode) == 1 && (mode == 0 || mode == 1));
    assert(!fclose(f));
    iflags.item_use_menu = mode;
    curio = mksobj(WHISTLE, NO_MKOBJ_FLAGS);
    assert(curio && !curio->curio_tag && curio->quan == 1);
    curio->curio_tag = CHAOS_CURIO_GENERATED;
    memset(&u.curio, 0, sizeof u.curio);
    u.curio.version = CHAOS_CURIO_VERSION;
    u.curio.phase = CHAOS_CURIO_PLACED;
    u.curio.owner = curio->o_id;
    u.curio.charges = 3;
    u.curio.state = 7;
    strcpy(u.curio.name, "Terminal counter %s");
    f = file("fixture-source.lua", "rb");
    n = fread(u.curio.source, 1, CHAOS_CURIO_SOURCE, f);
    assert(n > 0 && n < CHAOS_CURIO_SOURCE && !ferror(f));
    assert(!fclose(f));
    u.curio.source_len = n;
    assert(chaos_curio_valid(&u.curio));
    assert(addinv(curio) == curio);
    assert(curio->where == OBJ_INVENT && chaos_curio_matches(curio));
    f = file("fixture.json", "w");
    fprintf(f, "{\"injected\":true,\"mode\":%d,\"letter\":\"%c\",\"owner\":%u}\n",
            mode, curio->invlet, curio->o_id);
    assert(!fclose(f));
    test_rng_control(); /* Actual libc/native streams also agree under preload. */
}

void __wrap_checkfile(char *s, struct permonst *p, int a, int b, winid *w)
{
    if (active) ++encyclopedias;
    __real_checkfile(s, p, a, b, w);
}

static void snapshot(const char *name)
{
    FILE *f = file(name, "wb");
#define SAVE(v) assert(fwrite(&(v), sizeof(v), 1, f) == 1)
    /* Deliberately scoped to real ddoinv, not unrelated outer-loop bookkeeping.
     * Full record includes exact source, name, owner, phase, charges and state;
     * complete object and type capture all ID/knowledge flags (and more).
     */
    SAVE(u.curio); SAVE(u.usanity); SAVE(u.uinsight);
    SAVE(*curio); SAVE(objects[WHISTLE]); SAVE(moves);
    SAVE(reseed_count); SAVE(reseed_period);
#undef SAVE
    assert(!fclose(f));
}

int __wrap_ddoinv(void)
{
    struct chaos_curio_state record;
    struct obj object;
    struct objclass type;
    long turn;
    int sanity, insight, expected, actual, count, result;
    FILE *f;
    assert(curio && chaos_curio_matches(curio));
    record = u.curio; object = *curio; type = objects[WHISTLE];
    sanity = u.usanity; insight = u.uinsight; turn = moves;
    expected = test_rng_begin();
    snapshot("before.bin");
    active = 1;
    result = __real_ddoinv(); /* Never fake the command or any window callback. */
    active = 0;
    snapshot("after.bin");
    assert(!memcmp(&record, &u.curio, sizeof record));
    assert(!memcmp(&object, curio, sizeof object));
    assert(!memcmp(&type, &objects[WHISTLE], sizeof type));
    assert(sanity == u.usanity && insight == u.uinsight && turn == moves);
    assert(!encyclopedias);
    assert(result == (iflags.item_use_menu ? 0 : MOVE_INSTANT));
    count = reseed_count;
    test_rng_unchanged(expected);
    /* Repeat the already-verified first native draw for a readable receipt. */
    test_rng_reset(); actual = rn2(100000);
    f = file("receipt.json", "w");
    fprintf(f, "{\"return\":%d,\"move_instant\":%d,\"encyclopedias\":%d,"
            "\"rng_count\":%d,\"rng_expected\":%d,\"rng_actual\":%d,"
            "\"sanity\":%d,\"insight\":%d,\"moves\":%ld}\n",
            result, MOVE_INSTANT, encyclopedias, count, expected, actual,
            sanity, insight, turn);
    assert(!fclose(f));
    return result;
}

int main(int argc, char **argv)
{
    if (argc == 2 && strstr(argv[1], "negative-control")) {
        test_rng_negative_control(argv[1]);
        return 0;
    }
    return original_game_main(argc, argv);
}
