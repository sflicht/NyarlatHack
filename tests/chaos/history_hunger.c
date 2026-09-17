/* NGPL. Test-only passive, forward-once full-game witness. Not an engine event.
 * Caller precreates a private 0600 regular fd, inherited over exec, and exports
 * NYARLATHACK_HUNGER_FD. No main replacement, RNG calls or game-state writes.
 * Compile ONLY against the frozen production header root used by the objects.
 */
#include "hack.h"
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <sys/stat.h>
#include <unistd.h>

extern void __real_gethungry(void);
extern int __real_chaos_food(int);
extern int __real_near_capacity(void);
static unsigned long capacity_calls, capacity_count;
static int food_busy, capacity_busy;
static unsigned long hungry_calls, food_calls, scope, count;
static long input_sum, output_sum;
static int telemetry_fd = -1;
static unsigned long written_bytes;
#define TRACE_LIMIT 1048576UL

static void fail(void) { _exit(125); }
static void emit(const char *data, int length) {
    struct stat st;
    const char *setting;
    char *end;
    long number;
    int flags;
    ssize_t n;
    if (telemetry_fd < 0) {
        setting = getenv("NYARLATHACK_HUNGER_FD");
        if (!setting || !*setting) fail();
        errno = 0;
        number = strtol(setting, &end, 10);
        if (errno || *end || number < 3 || number > INT_MAX) fail();
        telemetry_fd = (int)number;
        flags = fcntl(telemetry_fd, F_GETFL);
        if (flags < 0 || (flags & O_ACCMODE) != O_WRONLY || !(flags & O_APPEND)
            || fstat(telemetry_fd, &st) || !S_ISREG(st.st_mode)
            || (st.st_mode & 0777) != 0600 || st.st_uid != geteuid()
            || st.st_nlink != 1 || st.st_size != 0) fail();
    }
    if (length <= 0 || length >= 4096
        || (unsigned long)length > TRACE_LIMIT - written_bytes) fail();
    if (fstat(telemetry_fd, &st) || st.st_size != (off_t)written_bytes) fail();
    while (length) {
        n = write(telemetry_fd, data, (size_t)length);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) fail();
        written_bytes += (unsigned long)n;
        data += n;
        length -= (int)n;
    }
}

/* Snapshot raw admission state, without querying or expiring any rule. */
#define STATE_FORMAT "\"event_seq\":%ld,\"safe\":%ld,\"last_id\":%d,\"spent\":%d," \
    "\"reserved\":%d,\"effect_value\":%d,\"effect_expires\":%ld"
#define STATE_ARGS(s) (s).seq, (s).safe, (s).last_id, (s).spent, (s).reserved, \
    (s).effects[CHAOS_HUNGER].value, (s).effects[CHAOS_HUNGER].expires

/* real_calls intentionally duplicates wrapper counters. Forward-once is a
 * source invariant, not an independently instrumented real-call measurement. */
int __wrap_chaos_food(int amount) {
    char line[4096];
    int saved = errno, result, after_errno, length;
    long before = u.uhunger, turn = moves;
    struct chaos_state state = u.chaos;
    if (food_busy || food_calls == ULONG_MAX) fail();
    food_busy = 1;
    ++food_calls;
    errno = saved;
    result = __real_chaos_food(amount);
    after_errno = errno;
    if (scope) {
        if (count == ULONG_MAX || amount < 0 || result < 0
            || input_sum > LONG_MAX - amount || output_sum > LONG_MAX - result)
            fail();
        ++count;
        input_sum += amount;
        output_sum += result;
    }
    length = snprintf(line, sizeof line,
        "{\"kind\":\"food\",\"call\":%lu,\"scope\":%lu,\"turn\":%ld,"
        "\"before\":%ld,\"after\":%ld,\"input\":%d,\"output\":%d,\"real_calls\":%lu,"
        STATE_FORMAT "}\n",
        food_calls, scope, turn, before, (long)u.uhunger, amount, result, food_calls,
        STATE_ARGS(state));
    emit(line, length);
    food_busy = 0;
    errno = after_errno;
    return result;
}

int __wrap_near_capacity(void) {
    char line[4096];
    int saved = errno, result, after_errno, length;
    long turn = moves;
    if (capacity_busy) fail();
    capacity_busy = 1;
    errno = saved;
    result = __real_near_capacity();
    after_errno = errno;
    if (scope) {
        if (capacity_calls == ULONG_MAX || capacity_count == ULONG_MAX) fail();
        ++capacity_calls;
        ++capacity_count;
        length = snprintf(line, sizeof line,
            "{\"kind\":\"capacity\",\"call\":%lu,\"scope\":%lu,\"turn\":%ld,"
            "\"result\":%d,\"real_calls\":%lu}\n",
            capacity_calls, scope, turn, result, capacity_calls);
        emit(line, length);
    }
    capacity_busy = 0;
    errno = after_errno;
    return result;
}

void __wrap_gethungry(void) {
    char line[4096];
    int saved = errno, after_errno, length, ordinary;
    int artifact, gluttony, clear_thoughts, insanity, nightmare_sanity;
    int regen_hurt, hunger, ahazu, conflict, fast_ring;
    int left_ring, right_ring, amulet, yendor;
    long before = u.uhunger, turn = moves, regen_mask;
    struct chaos_state state = u.chaos;
    if (scope || hungry_calls == ULONG_MAX) fail();
    scope = ++hungry_calls;
    count = capacity_count = 0;
    input_sum = output_sum = 0;
    ordinary = !Invulnerable && !Upolyd && !inediate(youracedata)
        && !uclockwork && !Race_if(PM_INCANTIFIER) && !Slow_digestion;
    /* Read-only macros/fields only. No second capacity/size/helper calls.
     * Scope supports ordinary nonpolymorphed food metabolism; oracle rejects
     * everything else. The native ordinary-call input supplies the size cost.
     * eat.c's first odd capacity call precedes newuhs (which may call bot). */
    artifact = !!(uwep && (uwep->oartifact == ART_GARNET_ROD
        || (uwep->oartifact == ART_TENSA_ZANGETSU && !is_undead(youracedata))));
    gluttony = !!(u.umadness & MAD_GLUTTONY);
    clear_thoughts = !!BlockableClearThoughts;
    insanity = NightmareAware_Insanity;
    nightmare_sanity = NightmareAware_Sanity;
    regen_hurt = !!(HRegeneration && u.uhp < u.uhpmax);
    regen_mask = ERegeneration & (~W_ART);
    if (uwep && uwep->oartifact) regen_mask &= ~W_WEP;
    if (uarms && uarms->oartifact) regen_mask &= ~W_ARMS;
    hunger = !!Hunger;
    ahazu = !!(u.sealsActive & SEAL_AHAZU);
    conflict = !!(HConflict || (EConflict & (~W_ARTI)));
    fast_ring = !!(EFast & (W_RINGL | W_RINGR));
    left_ring = !!(uleft && (uleft->spe || !objects[uleft->otyp].oc_charged));
    right_ring = !!(uright && (uright->spe || !objects[uright->otyp].oc_charged));
    amulet = !!uamul;
    yendor = !!u.uhave.amulet;
    errno = saved;
    __real_gethungry();
    after_errno = errno;
    length = snprintf(line, sizeof line,
        "{\"kind\":\"hungry\",\"call\":%lu,\"turn\":%ld,\"end_turn\":%ld,"
        "\"before\":%ld,\"after\":%ld,\"count\":%lu,\"input_sum\":%ld,"
        "\"output_sum\":%ld,\"real_calls\":%lu,\"ordinary\":%d,"
        "\"capacity_count\":%lu,\"artifact\":%d,\"gluttony\":%d,"
        "\"clear_thoughts\":%d,\"insanity\":%d,\"nightmare_sanity\":%d,"
        "\"regen_hurt\":%d,\"regen_mask\":%ld,\"hunger\":%d,\"ahazu\":%d,"
        "\"conflict\":%d,\"fast_ring\":%d,\"left_ring\":%d,\"right_ring\":%d,"
        "\"amulet\":%d,\"yendor\":%d," STATE_FORMAT "}\n",
        scope, turn, (long)moves, before, (long)u.uhunger, count,
        input_sum, output_sum, hungry_calls, ordinary, capacity_count,
        artifact, gluttony, clear_thoughts, insanity, nightmare_sanity,
        regen_hurt, regen_mask, hunger, ahazu, conflict, fast_ring,
        left_ring, right_ring, amulet, yendor, STATE_ARGS(state));
    emit(line, length);
    scope = 0;
    errno = after_errno;
}
