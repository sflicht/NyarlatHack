/* Sweep-only clock/seed control (NGPL; see dat/license). Never linked into
 * the game; LD_PRELOADed by scripts/seed_sweep.py only.
 *
 * Derived from replay_clock.c (same fixed clock 1700000000, same xorshift32
 * /dev/urandom stream shape), with one declared difference: the per-game seed
 * S = NYARLATHACK_SWEEP_SEED selects the stream instead of fixed constants.
 *   - first srandom() call: libc srandom(S)          (replay_clock: 7654321)
 *   - srand():              libc srand(S)            (replay_clock: 1234567)
 *   - /dev/urandom state:   987654321 ^ (S * 2654435761) mod 2^32
 *   - later srandom() calls (native check_reseed): passed through unchanged.
 * Their argument is fixed clock + controlled entropy, so the game remains a
 * pure function of S. replay_clock.c instead pins every reseed to one value,
 * which restarts the identical random prefix every 10..709 draws; a population
 * sweep must not do that. No new generator: the game still draws libc
 * random() through the unmodified rnd.c. A missing or malformed seed aborts
 * the process (fail closed, never a silent default). */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static unsigned int sweep_seed(void)
{
    const char *text = getenv("NYARLATHACK_SWEEP_SEED");
    char *end = 0;
    unsigned long value;
    if (!text || !*text || strlen(text) > 10 || text[0] < '0' || text[0] > '9')
        abort();
    value = strtoul(text, &end, 10);
    if (!end || *end || value > UINT_MAX)
        abort();
    return (unsigned int)value;
}

FILE *fopen(const char *path, const char *mode)
{
    static uint32_t state;
    static uint32_t entropy[2];
    if (!strcmp(path, "/dev/urandom")) {
        if (!state) {
            state = 987654321U ^ (uint32_t)(sweep_seed() * 2654435761U);
            if (!state) state = 987654321U; /* xorshift32 must not be zero */
        }
        for (int i = 0; i < 2; i++) {
            state ^= state << 13; state ^= state >> 17; state ^= state << 5;
            entropy[i] = state;
        }
        return fmemopen(entropy, sizeof entropy, "r");
    }
    FILE *(*real)(const char *, const char *) = dlsym(RTLD_NEXT, "fopen");
    return real(path, mode);
}

time_t time(time_t *out) { time_t t = 1700000000; if (out) *out = t; return t; }

void srand(unsigned int ignored)
{
    void (*real)(unsigned int) = dlsym(RTLD_NEXT, "srand");
    (void)ignored;
    real(sweep_seed());
}

void srandom(unsigned int seed)
{
    static int initial = 1;
    void (*real)(unsigned int) = dlsym(RTLD_NEXT, "srandom");
    if (initial) {
        initial = 0;
        seed = sweep_seed();
    }
    real(seed);
}
