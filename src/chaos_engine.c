/* NetHack General Public License. No event path draws engine RNG. */
#include "hack.h"
#include "chaos.h"
#include "chaos_io.h"
#include "chaos_haunt.h"
#include "chaos_curio.h"

static struct chaos_io io = { -1, -1, -1, 0, 0 };
static int started, oldsanity, oldinsight;
static int food_metabolism(void) {
    return !inediate(youracedata) && !uclockwork && !Race_if(PM_INCANTIFIER);
}
static struct chaos_context context(void) {
    struct chaos_context c;
    c.turn = moves; c.sanity = u.usanity; c.insight = u.uinsight;
    /* Same health selection/clamp as bot2str; no names or RNG calls. */
    c.hp = Upolyd ? u.mh : u.uhp;
    if (c.hp < 0) c.hp = 0;
    c.hp_max = Upolyd ? u.mhmax : u.uhpmax;
    c.power = u.uen; c.power_max = u.uenmax;
    c.eligible = program_state.gameover || multi < 0 ? 0 : food_metabolism() ? 1 : 2;
    return c;
}
static int show(void *unused, int telegraph, int ambient) {
    static const char *const signals[] = { "",
        "A distant whisper brushes against your thoughts.",
        "The lines of your wards seem thin and uncertain.",
        "An unnatural hunger coils in your stomach." };
    static const char *const messages[] = { "", "The shadows lean closer.",
        "Something beyond the walls listens.", "For a moment, silence has teeth." };
    (void)unused;
    if (telegraph < 1 || telegraph > 3 || ambient < 0 || ambient > 3) return 0;
    pline("%s", signals[telegraph]);
    if (ambient) pline("%s", messages[ambient]);
    return 1;
}
int chaos_event_checked(const char *name, const char *phase, const char *detail) {
    struct chaos_context c;
    if (!started || chaos_shadow_active()) return 0;
    c = context();
    return chaos_io_event(&io, &u.chaos, &c, name, phase, detail);
}
void chaos_event(const char *name, const char *phase, const char *detail) {
    (void)chaos_event_checked(name,phase,detail);
}
void chaos_safe(const char *why) {
    struct chaos_context c;
    long before;
    static int busy;
    if (busy || chaos_shadow_active()) return;
    busy = 1;
    before = u.chaos.safe;
    if (started) {
        c = context();
        chaos_io_safe(&io, &u.chaos, &c, why, show, 0);
    }
    /* Preserve the legacy index/ID/ACK schedule. Expiry needs no transport. */
    chaos_curio_safe(started && !io.failed && !io.busy
                     && u.chaos.safe > before ? io.dir : -1);
    busy = 0;
}
void chaos_start(void) {
    int fresh = u.chaos.version == 0;
    if (started) return;
    if (fresh) chaos_state_init(&u.chaos);
    oldsanity = u.usanity; oldinsight = u.uinsight;
    started = 1;
    (void)chaos_io_open(&io, getenv("NYARLATHACK_RUN_DIR"));
    chaos_event("session", "result", fresh ? "new" : "restore");
    if (fresh) {
        chaos_event("level_enter", "result", "");
        chaos_safe("level_enter");
    }
}
void chaos_observe(void) {
    struct chaos_context c;
    int threshold;
    if (!started || chaos_shadow_active()) return;
    c = context();
    chaos_io_expire(&io, &u.chaos, &c);
    threshold = oldsanity / 20 != u.usanity / 20;
    if (oldsanity != u.usanity) chaos_event("sanity", "result", "");
    if (oldinsight != u.uinsight) chaos_event("insight", "result", "");
    oldsanity = u.usanity; oldinsight = u.uinsight;
    if (threshold) chaos_safe("sanity_threshold");
    chaos_haunt_tick(io.failed ? -1 : io.dir);
}
int chaos_ward_count(int count) {
    return chaos_rule(&u.chaos, CHAOS_WARD, moves, count);
}
int chaos_food(int amount) {
    return food_metabolism() ? chaos_rule(&u.chaos, CHAOS_HUNGER, moves, amount) : amount;
}
