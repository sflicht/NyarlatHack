/* NGPL: test-only access to a globalized COPY of src/rnd.o, never a RNG stub. */
#ifndef CHAOS_TEST_NATIVE_RNG_H
#define CHAOS_TEST_NATIVE_RNG_H
#include <assert.h>
#include <limits.h>
#include <string.h>

/* objcopy exposes these exact native statics in the fixture link only. */
extern int reseed_period, reseed_count;

static void test_rng_reset(void)
{
    reseed_period = INT_MAX;
    reseed_count = 0;
    srandom(123);
}

static int test_rng_begin(void)
{
    int expected;
    test_rng_reset();
    expected = rn2(100000);
    assert(reseed_count == 1 && reseed_period == INT_MAX);
    test_rng_reset();
    return expected;
}

static void test_rng_unchanged(int expected)
{
    /* Count catches even coincident output; draw comparison catches raw random(). */
    assert(reseed_period == INT_MAX);
    assert(reseed_count == 0);
    assert(rn2(100000) == expected);
}

static void test_rng_control(void)
{
    int expected[32], i;
    /* Prove native rn2 still consumes libc's real random stream, and its
     * internal check_reseed sees the counters we control (not --wrap). */
    test_rng_reset();
    for (i = 0; i < 32; ++i) expected[i] = (int)(random() % 100000L);
    assert(expected[0] != expected[1]);
    test_rng_reset();
    for (i = 0; i < 32; ++i) {
        assert(rn2(100000) == expected[i]);
        assert(reseed_count == i + 1);
        assert(reseed_period == INT_MAX);
    }
    test_rng_unchanged(test_rng_begin());
}

static void test_rng_negative_control(const char *mode)
{
    int expected = test_rng_begin();
    if (!strcmp(mode, "--rng-negative-control")) (void)rn2(100000);
    else if (!strcmp(mode, "--raw-rng-negative-control")) (void)random();
    else return;
    test_rng_unchanged(expected); /* Must abort at the purity oracle. */
}
#endif
