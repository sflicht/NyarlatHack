/* NetHack General Public License. No event path draws engine RNG. */
#include "hack.h"
#include "chaos.h"
#include "chaos_io.h"
#include "chaos_haunt.h"
#include "chaos_curio.h"

static struct chaos_io io = { -1, -1, -1, 0, 0 };
static int started, oldsanity, oldinsight;
static int observations;
static long observation_root, observation_turn;
static int observation_operation;
/* Positive pending facts are armed; negative ones were taken by their channel.
 * Root binding closes identical-fact reentry ambiguity: an old caller cannot
 * deliver a replacement action's notice. This is not proof of UI delivery. */
static int observation_pending, observation_used, observation_blocked;
static void observation_clear(void) {
    observation_root = observation_turn = 0;
    observation_operation = CHAOS_OBS_OP_NONE;
    observation_pending = observation_used = observation_blocked = 0;
}
static int observation_ready(void) {
    return observations && started && io.events >= 0 && !io.failed
        && !chaos_shadow_active() && !program_state.gameover;
}
static int observation_current(void) {
    if (observation_turn != moves) observation_clear();
    return observation_ready() && observation_root > 0;
}
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
#define MESSAGE(id, text) text,
    static const char *const signals[] = { "", CHAOS_SIGNAL_ROWS(MESSAGE) };
    static const char *const messages[] = { "", CHAOS_AMBIENT_MESSAGE_ROWS(MESSAGE) };
#undef MESSAGE
    (void)unused;
    if (telegraph < 1 || telegraph > CHAOS_SIGNAL_COUNT || ambient < 0 || ambient > CHAOS_AMBIENT_MESSAGE_COUNT) return 0;
    pline("%s", signals[telegraph]);
    if (ambient) pline("%s", messages[ambient]);
    return 1;
}
int chaos_event_checked(const char *name, const char *phase, const char *detail) {
    struct chaos_context c;
    /* Boundaries invalidate attribution even when their event is suppressed. */
    if (!strcmp(name, "session") || !strcmp(name, "level_enter")
        || !strcmp(name, "level_leave") || !strcmp(name, "death"))
        observation_clear();
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
    const char *flag;
    struct chaos_context c;
    if (started) return;
    observation_clear();
    if (fresh) chaos_state_init(&u.chaos);
    oldsanity = u.usanity; oldinsight = u.uinsight;
    started = 1;
    (void)chaos_io_open(&io, getenv("NYARLATHACK_RUN_DIR"));
    flag = getenv("NYARLATHACK_OBSERVATIONS");
    observations = flag && !strcmp(flag, "1") && io.events >= 0
        && !io.failed && !chaos_shadow_active() && !program_state.gameover;
    if (observations) {
        c = context();
        observations = chaos_io_observation(&io, &u.chaos, &c,
            CHAOS_OBS_OP_NONE, CHAOS_OBS_STAGE_ENABLED, 0, CHAOS_OBS_FACT_NONE);
    }
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
long chaos_observation_begin(int operation) {
    struct chaos_context c;
    if (!chaos_obs_family(operation)) return 0;
    observation_clear();
    if (!observation_ready()) return 0;
    c = context();
    if (!chaos_io_observation(&io, &u.chaos, &c, operation,
            CHAOS_OBS_STAGE_STARTED, 0, CHAOS_OBS_FACT_NONE)) return 0;
    observation_root = u.chaos.seq;
    observation_turn = moves;
    observation_operation = operation;
    return observation_root;
}
void chaos_observation_end(long root) {
    struct chaos_context c;
    if (root <= 0 || root != observation_root) return;
    if (observation_current()) {
        c = context();
        (void)chaos_io_observation(&io, &u.chaos, &c, observation_operation,
            observation_blocked ? CHAOS_OBS_STAGE_BLOCKED : CHAOS_OBS_STAGE_COMPLETED,
            root, CHAOS_OBS_FACT_NONE);
    }
    observation_clear();
}
int chaos_food(int amount) {
    return food_metabolism() ? chaos_rule(&u.chaos, CHAOS_HUNGER, moves, amount) : amount;
}
void chaos_observation_arm(int operation, int fact) {
    observation_pending = 0;
    if (!observation_current() || observation_used
        || operation != observation_operation) return;
    if (!chaos_obs_fact(operation, fact)) return;
    observation_pending = fact;
}
void chaos_observation_disarm(void) {
    observation_pending = 0;
}
static struct chaos_observation_token observation_take(int channel) {
    struct chaos_observation_token token = {0L, CHAOS_OBS_FACT_NONE};
    const struct chaos_obs_fact_info *fact;
    if (!observation_current() || observation_used || observation_pending <= 0) return token;
    fact = chaos_obs_fact(observation_operation, observation_pending);
    if (!fact || fact->channel != channel) return token;
    token.root = observation_root;
    token.fact = observation_pending;
    observation_pending = -token.fact;
    return token;
}
struct chaos_observation_token chaos_observation_take_message(void) {
    return observation_take(CHAOS_OBS_CHANNEL_MESSAGE);
}
struct chaos_observation_token chaos_observation_take_map(void) {
    return observation_take(CHAOS_OBS_CHANNEL_MAP);
}
static void observation_notice(const struct chaos_obs_fact_info *fact) {
    struct chaos_context c = context();
    observation_pending = 0;
    observation_used = 1;
    if (fact->implies_blocked) observation_blocked = 1;
    (void)chaos_io_observation(&io, &u.chaos, &c, observation_operation,
        CHAOS_OBS_STAGE_NOTICE, observation_root, fact->id);
}
static void observation_deliver(struct chaos_observation_token token, int channel) {
    const struct chaos_obs_fact_info *fact;
    /* Wrong-root tokens must not trigger current()'s expiry side effect. */
    if (token.root <= 0 || token.root != observation_root
        || !observation_current() || observation_used) return;
    fact = chaos_obs_fact(observation_operation, token.fact);
    if (!fact || fact->channel != channel || observation_pending != -token.fact) return;
    observation_notice(fact);
}
void chaos_observation_delivered(struct chaos_observation_token token) {
    observation_deliver(token, CHAOS_OBS_CHANNEL_MESSAGE);
}
void chaos_observation_map_delivered(struct chaos_observation_token token) {
    observation_deliver(token, CHAOS_OBS_CHANNEL_MAP);
}
void chaos_observation_blocked(void) {
    const struct chaos_obs_family_info *family;
    if (!observation_current()) return;
    family = chaos_obs_family(observation_operation);
    if (family && family->allow_blocked) observation_blocked = 1;
}
