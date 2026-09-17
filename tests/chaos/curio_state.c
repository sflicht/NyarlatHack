/* NGPL: linked native state/version checks and test-only terminal save fixture. */
#include "hack.h"
#include "date.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "chaos_curio.h"

int original_game_main(int, char **);
int __real_dosave(void);
int __real_dorecover(int);
static struct chaos_curio_state fixture(void)
{
    struct chaos_curio_state s;
    memset(&s, 0, sizeof s);
    s.version = CHAOS_CURIO_VERSION;
    s.phase = CHAOS_CURIO_PLACED;
    strcpy(s.name, "Marked counter");
    strcpy(s.source, "-- exact saved bytes\nreturn {name='Marked counter',"
           "inspect=function(c) return 'Read.' end,"
           "apply=function(c) return {text='Used.',state=c.state,sanity_delta=0} end}\n");
    s.source_len = strlen(s.source);
    memset(s.source + s.source_len, ' ', CHAOS_CURIO_SOURCE - s.source_len);
    s.source_len = CHAOS_CURIO_SOURCE;
    s.owner = 424242U; /* Deliberately not a loaded/inventory object. */
    s.charges = 2; s.state = 255; s.disabled = 1;
    return s;
}
int __wrap_dosave(void)
{
    struct obj *o = mksobj(WHISTLE, NO_MKOBJ_FLAGS);
    assert(o && o->curio_tag == CHAOS_CURIO_ORDINARY);
    assert(sizeof o->curio_tag == 1);
    dealloc_obj(o);
    u.curio = fixture();
    /* Explicit test-only native save-entry faults; never touch live saves. */
    {
        char fault[16] = "";
        FILE *f = fopen("chaos-save-fault", "r");
        if (f) {
            assert(fgets(fault, sizeof fault, f));
            assert(!fclose(f));
            if (!strcmp(fault, "future")) {
                u.chaos.cosmetic_seen = 1;
                u.chaos.cosmetic_last_turn = moves + 1;
            } else if (!strcmp(fault, "mask")) u.chaos.cosmetic_seen = 8;
            else if (!strcmp(fault, "version")) u.chaos.version = 1;
            else if (!strcmp(fault, "haunt")) {
                u.haunt.count = CHAOS_TRAIL + 1;
                assert(!chaos_haunt_valid(&u.haunt));
            }
            else if (!strcmp(fault, "curio")) u.curio.version = 99;
            else assert(0);
        }
    }
    return __real_dosave();
}
int __wrap_dorecover(int fd)
{
    int ok = __real_dorecover(fd);
    if (ok) {
        struct chaos_curio_state s = fixture();
        FILE *f;
        assert(!memcmp(&s, &u.curio, sizeof s));
        assert(chaos_curio_valid(&u.curio));
        f = fopen("curio-restored.bin", "wb"); assert(f);
        assert(fwrite(&u.curio, sizeof u.curio, 1, f) == 1);
        assert(!fclose(f));
    }
    return ok;
}
int main(int argc, char **argv)
{
    struct version_info v = {VERSION_NUMBER, VERSION_FEATURES,
                            VERSION_SANITY1, VERSION_SANITY2};
    if (argc > 1) return original_game_main(argc, argv);
    assert(check_version(&v, "matching", FALSE));
    /* Same packed sizes/counts: only the explicit new discriminator differs. */
    assert(VERSION_FEATURES & (1UL << 29));
    v.feature_set &= ~(1UL << 29);
    assert(!check_version(&v, "old-chaos", FALSE));
    {
        struct chaos_curio_state s, good, copy;
        FILE *f;
        memset(&s, 0, sizeof s);
        assert(chaos_curio_valid(&s));
        assert(!chaos_curio_valid(NULL));
        s.phase = CHAOS_CURIO_REJECTED;
        assert(!chaos_curio_valid(&s));
        s.version = CHAOS_CURIO_VERSION;
        assert(chaos_curio_valid(&s));
        s.phase = CHAOS_CURIO_EXPIRED;
        assert(chaos_curio_valid(&s));
        s.name[1] = 'x'; assert(!chaos_curio_valid(&s)); s.name[1] = 0;
        s.source[4096] = 'x'; assert(!chaos_curio_valid(&s)); s.source[4096] = 0;
        s.charges = 1; assert(!chaos_curio_valid(&s));
        good = fixture(); assert(chaos_curio_valid(&good));
#define BAD(field, value) do { s = good; s.field = (value); assert(!chaos_curio_valid(&s)); } while (0)
        BAD(version, 99); BAD(phase, 99); BAD(phase, CHAOS_CURIO_VIRGIN);
        BAD(owner, 0); BAD(charges, 4); BAD(charges, -1);
        BAD(state, 256); BAD(state, -1); BAD(disabled, 2);
        BAD(source_len, 0); BAD(source_len, 4097);
        BAD(source[good.source_len], 'x'); BAD(source[10], '\0');
        BAD(name[0], 'X'); BAD(name[48], 'x');
        s = good; memset(s.name, 'x', sizeof s.name); assert(!chaos_curio_valid(&s));
        s = good; strcpy(s.source, "return {}"); s.source_len = strlen(s.source);
        assert(!chaos_curio_valid(&s));
        s = good; strcpy(s.source, "while true do end"); s.source_len = strlen(s.source);
        copy = s; assert(!chaos_curio_valid(&s)); assert(!memcmp(&s, &copy, sizeof s));
        assert(chaos_curio_valid(&good)); /* bad source cannot poison the next VM */
        s = good; s.phase = CHAOS_CURIO_REJECTED; assert(!chaos_curio_valid(&s));
        s = good; s.phase = CHAOS_CURIO_ADMITTED;
        s.owner = 0; s.charges = 3; s.state = 0; s.disabled = 0;
        assert(chaos_curio_valid(&s));
        s.disabled = 1; assert(!chaos_curio_valid(&s)); s.disabled = 0;
        s.state = 1; assert(!chaos_curio_valid(&s)); s.state = 0;
        s.charges = 2; assert(!chaos_curio_valid(&s)); s.charges = 3;
        s.phase = CHAOS_CURIO_EXPIRED; assert(chaos_curio_valid(&s));
        s.owner = 42; assert(!chaos_curio_valid(&s));
        s = good;
        memset(s.source + s.source_len, ' ', 4096 - s.source_len);
        s.source[4096] = 0; s.source_len = 4096;
        assert(chaos_curio_valid(&s));
        f = tmpfile(); assert(f);
        assert(fwrite(&s, sizeof s, 1, f) == 1); rewind(f);
        assert(fread(&copy, sizeof copy, 1, f) == 1); fclose(f);
        assert(!memcmp(&s, &copy, sizeof s)); assert(chaos_curio_valid(&copy));
        assert(zeroobj.curio_tag == CHAOS_CURIO_ORDINARY);
        assert(sizeof zeroobj.curio_tag == 1);
        puts("curio states/source roundtrip valid; zero template tag ordinary");
    }

    {
        struct chaos_haunt_state h;
        memset(&h, 0, sizeof h);
        assert(chaos_haunt_valid(&h));
        h.count = CHAOS_TRAIL + 1;
        assert(!chaos_haunt_valid(&h));
        puts("haunt save-entry count fault rejected by native validator");
    }
    puts("explicit feature mismatch rejected independently of sizes");
    return 0;
}
