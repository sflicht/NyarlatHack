/* NGPL. Test-only setup wrappers; real main, moveloop, dodrink and done.
 * No replacement RNG, action or death implementation. Not stock gameplay:
 * the first quaff receives an explicit fountain/HP/strength test baseline. */
#include "hack.h"
#include <assert.h>
#include <limits.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
extern int reseed_period, reseed_count;
extern int __real_main(int, char **);
extern int __real_dodrink(void);
static int entered, returned;
static unsigned selected_seed;

static void reset_seed(unsigned seed)
{
    void *libc = dlopen("libc.so.6", RTLD_NOW | RTLD_LOCAL);
    void (*seedfn)(unsigned);
    assert(libc);
    seedfn = (void (*)(unsigned)) dlsym(libc, "srandom");
    assert(seedfn);
    reseed_period = INT_MAX; reseed_count = 0;
    seedfn(seed);
    dlclose(libc);
}

static void exit_witness(void)
{
    FILE *f = fopen("native-exit.json", "w");
    assert(f);
    fprintf(f, "{\"gameover\":%d,\"hp\":%d,\"entered\":%d,\"returned\":%d,\"rng_count\":%d}\n",
            program_state.gameover, u.uhp, entered, returned, reseed_count);
    assert(!fclose(f));
}

int __wrap_main(int argc, char **argv)
{
    unsigned seed;
    if (argc == 2 && !strcmp(argv[1], "--calibrate")) {
        for (seed = 1; seed <= 4096; ++seed) {
            reset_seed(seed);
            if (rnd(30) == 21) {
                printf("{\"seed\":%u,\"fate\":21,\"candidates\":%u,\"limit\":4096}\n", seed, seed);
                return 0;
            }
        }
        return 2;
    }
    assert(getenv("FATAL_FOUNTAIN_SEED"));
    selected_seed = (unsigned) atoi(getenv("FATAL_FOUNTAIN_SEED"));
    assert(selected_seed >= 1 && selected_seed <= 4096);
    assert(!atexit(exit_witness));
    return __real_main(argc, argv);
}

int __wrap_dodrink(void)
{
    int result, fatal;
    FILE *f;
    assert(!entered++);
    assert(getenv("FATAL_FOUNTAIN_CASE"));
    fatal = !strcmp(getenv("FATAL_FOUNTAIN_CASE"), "fatal");
    assert(fatal || !strcmp(getenv("FATAL_FOUNTAIN_CASE"), "healthy"));
    assert(!wizard && !discover && !Upolyd && !Poison_resistance && !Lifesaved);
    assert(!Invulnerable && !Levitation && !Underwater && !u.uswallow);
    assert(Race_if(PM_HUMAN) && Role_if(PM_WIZARD));
    assert(iflags.window_inited && iflags.vision_inited && dungeons[u.uz.dnum].num_dunlevs > 0);
    if (!IS_FOUNTAIN(levl[u.ux][u.uy].typ)) ++level.flags.nfountains;
    levl[u.ux][u.uy].typ = FOUNTAIN;
    levl[u.ux][u.uy].blessedftn = 0;
    levl[u.ux][u.uy].flags = 0;
    ABASE(A_STR) = AMAX(A_STR) = 18;
    u.uhprolled = 40; calc_total_maxhp();
    u.uhp = fatal ? 1 : u.uhpmax;
    newsym(u.ux, u.uy);
    f = fopen("native-before.json", "w"); assert(f);
    fprintf(f, "{\"hp\":%d,\"hp_max\":%d,\"strength\":%d,\"seed\":%u,\"turn\":%ld,\"poison_resistance\":0,\"lifesaving\":0,\"invulnerable\":0}\n",
            u.uhp, u.uhpmax, ABASE(A_STR), selected_seed, moves);
    assert(!fclose(f));
    reset_seed(selected_seed);
    result = __real_dodrink();
    returned = 1;
    assert(!fatal && result == MOVE_QUAFFED && u.uhp > 0);
    return result;
}
