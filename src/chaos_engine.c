/* NetHack General Public License. No event path draws engine RNG. */
#include "hack.h"
#include "chaos.h"
#include "chaos_next_use_schedule.h"
#include "chaos_io.h"
#include "chaos_haunt.h"
#include "chaos_curio.h"
#include "chaos_next_use.h"
#include "chaos_next_use_io.h"
#include <sys/stat.h>
#ifdef TTY_GRAPHICS
#include "wintty.h"
#endif

int chaos_next_use_on_safe(int, long, int, struct chaos_state *, int, int)
    __attribute__((weak));
void chaos_next_use_safe_bind_run(const char *) __attribute__((weak));
void chaos_next_use_safe_bind_telegraph(int (*)(void *, const char *), void *)
    __attribute__((weak));
void chaos_next_use_safe_bind_origin(const struct chaos_next_use_origin_ref *,
                                    int) __attribute__((weak));
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
static void observation_abort(void) {
    observation_clear();
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
static struct {
    int ready, pending;
    int root, notice, end, fact, operation, dnum, dlevel, move;
} next_use_origin[2];
static int next_use_slot_for_operation(int operation)
{
    if (operation == CHAOS_OBS_OP_FOUNTAIN_DRINK) return 1;
    if (operation == CHAOS_OBS_OP_WHISTLING) return 0;
    return -1;
}
static int next_use_warn(void *unused, const char *text)
{
    const char *line;
    (void)unused;
    line = chaos_next_use_player_warning(text);
    if (!line) return 0;
    pline("%s", line);
    return 1;
}
static const char *next_use_engine_fact(int operation, int fact)
{
    if (operation == CHAOS_OBS_OP_WHISTLING
        && fact >= CHAOS_OBS_FACT_SOUND_HIGH
        && fact <= CHAOS_OBS_FACT_SOUND_HUMMING)
        return "ordinary_whistle";
    if (operation == CHAOS_OBS_OP_FOUNTAIN_DRINK
        && fact == CHAOS_OBS_FACT_WATER_REFRESHED)
        return "water_refreshed";
    return 0;
}
static void next_use_bind_owned(void)
{
    struct chaos_next_use_origin_ref origin;
    struct stat st;
    char run[65];
    const char *fact;
    int slot;
    if (io.dir < 0 || fstat(io.dir, &st)) return;
    if (snprintf(run, sizeof run, "%016llx%016llx%016llx%016llx",
                 (unsigned long long)st.st_dev,
                 (unsigned long long)st.st_ino,
                 (unsigned long long)st.st_dev,
                 (unsigned long long)st.st_ino) != 64)
        return;
    if (chaos_next_use_safe_bind_run)
        chaos_next_use_safe_bind_run(run);
    if (chaos_next_use_safe_bind_telegraph)
        chaos_next_use_safe_bind_telegraph(next_use_warn, 0);
    if (!chaos_next_use_safe_bind_origin)
        return;
    for (slot = 0; slot < 2; ++slot) {
        if (!next_use_origin[slot].ready) continue;
        fact = next_use_engine_fact(next_use_origin[slot].operation,
                                    next_use_origin[slot].fact);
        if (!fact) continue;
        memset(&origin, 0, sizeof origin);
        origin.end_seq = next_use_origin[slot].end;
        strncpy(origin.fact, fact, sizeof origin.fact - 1);
        origin.family = slot == 1 ? CHAOS_NEXT_USE_FAMILY_F
                                  : CHAOS_NEXT_USE_FAMILY_W;
        origin.level_dlevel = next_use_origin[slot].dlevel;
        origin.level_dnum = next_use_origin[slot].dnum;
        origin.move = next_use_origin[slot].move;
        origin.notice_seq = next_use_origin[slot].notice;
        origin.root = next_use_origin[slot].root;
        memcpy(origin.run, run, 65);
        chaos_next_use_safe_bind_origin(&origin, 1);
    }
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
    if (started && !io.failed && !io.busy && u.chaos.safe > before) {
        const char *flag = getenv("NYARLATHACK_NEXT_USE_ADMIT");
        if (flag && !strcmp(flag, "1") && chaos_next_use_on_safe) {
            next_use_bind_owned();
            (void)chaos_next_use_on_safe(
                io.dir, u.chaos.safe, u.usanity, &u.chaos,
                (int)u.uz.dnum, (int)u.uz.dlevel);
        }
    }
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
    chaos_next_use_candidate_tick(io.failed ? -1 : io.dir);
}
int chaos_ward_count(int count) {
    return chaos_rule(&u.chaos, CHAOS_WARD, moves, count);
}
long chaos_observation_begin(int operation) {
    struct chaos_context c;
    if (operation == CHAOS_OBS_OP_WHISTLE_ATTENTION) return 0;
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

boolean chaos_observation_begin_exclusive(int operation, long *root_out) {
    struct chaos_context c;
    long root;
    if (!root_out) return FALSE;
    if (observation_root != 0) { *root_out = 0; return FALSE; }
    *root_out = 0;
    if (operation != CHAOS_OBS_OP_WHISTLE_ATTENTION) return FALSE;
    if (!observation_ready()) return FALSE;
    c = context();
    if (!chaos_io_observation(&io, &u.chaos, &c,
            CHAOS_OBS_OP_WHISTLE_ATTENTION, CHAOS_OBS_STAGE_STARTED,
            0, CHAOS_OBS_FACT_NONE)) return FALSE;
    root = u.chaos.seq;
    if (root <= 0) { observation_abort(); return FALSE; }
    observation_root = root;
    observation_turn = moves;
    observation_operation = CHAOS_OBS_OP_WHISTLE_ATTENTION;
    observation_pending = observation_used = observation_blocked = 0;
    *root_out = root;
    return TRUE;
}

boolean chaos_observation_finish(long root, int stage, long *end_seq_out) {
    struct chaos_context c;
    long end_seq;
    if (!end_seq_out) return FALSE;
    *end_seq_out = 0;
    if (root <= 0) return FALSE;
    if (root != observation_root) return FALSE;
    if (stage != CHAOS_OBS_STAGE_COMPLETED &&
        stage != CHAOS_OBS_STAGE_BLOCKED) return FALSE;
    if (observation_operation != CHAOS_OBS_OP_WHISTLE_ATTENTION ||
        observation_turn != moves) return FALSE;
    c = context();
    if (!chaos_io_observation(&io, &u.chaos, &c,
            CHAOS_OBS_OP_WHISTLE_ATTENTION, stage, root,
            CHAOS_OBS_FACT_NONE)) {
        observation_abort();
        return FALSE;
    }
    end_seq = u.chaos.seq;
    if (end_seq <= root) { observation_abort(); return FALSE; }
    *end_seq_out = end_seq;
    observation_clear();
    return TRUE;
}
void chaos_observation_end(long root) {
    struct chaos_context c;
    if (observation_operation == CHAOS_OBS_OP_WHISTLE_ATTENTION) return;
    if (root <= 0 || root != observation_root) return;
    if (observation_current()) {
        c = context();
        (void)chaos_io_observation(&io, &u.chaos, &c, observation_operation,
            observation_blocked ? CHAOS_OBS_STAGE_BLOCKED : CHAOS_OBS_STAGE_COMPLETED,
            root, CHAOS_OBS_FACT_NONE);
        if (!observation_blocked) {
            int slot = next_use_slot_for_operation(observation_operation);
            if (slot >= 0 && next_use_origin[slot].pending
                && next_use_origin[slot].root == (int)root
                && next_use_engine_fact(observation_operation,
                                        next_use_origin[slot].fact)) {
                next_use_origin[slot].end = u.chaos.seq;
                next_use_origin[slot].ready = 1;
                next_use_origin[slot].pending = 0;
                (void)chaos_next_use_note_origin(
                    io.dir, slot == 0 ? "W" : "F",
                    next_use_origin[slot].move,
                    next_use_origin[slot].dnum,
                    next_use_origin[slot].dlevel,
                    next_use_origin[slot].root,
                    next_use_origin[slot].notice,
                    next_use_origin[slot].end);
            }
        }
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
    if (next_use_engine_fact(observation_operation, fact->id)
        && monstermoves >= 0L && monstermoves <= 2147483547L) {
        int slot = next_use_slot_for_operation(observation_operation);
        if (slot >= 0) {
            next_use_origin[slot].pending = 1;
            next_use_origin[slot].ready = 0;
            next_use_origin[slot].root = (int)observation_root;
            next_use_origin[slot].notice = u.chaos.seq;
            next_use_origin[slot].end = 0;
            next_use_origin[slot].fact = fact->id;
            next_use_origin[slot].operation = observation_operation;
            next_use_origin[slot].dnum = (int)u.uz.dnum;
            next_use_origin[slot].dlevel = (int)u.uz.dlevel;
            next_use_origin[slot].move = (int)monstermoves;
        }
    }
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

boolean chaos_whistle_attention_message(struct chaos_whistle_witness *witness) {
    long before_seq;
    boolean tty_supported = FALSE;
    if (!witness || !witness->active || witness->root <= 0
        || witness->manifestation_delivered) return FALSE;
    witness->message_token.root = witness->root;
    witness->message_token.fact = CHAOS_OBS_FACT_ATTENTION;
    if (witness->message_token.root != witness->root
        || witness->message_token.fact != CHAOS_OBS_FACT_ATTENTION)
        return FALSE;
#if defined(CHAOS) && defined(TTY_GRAPHICS)
    tty_supported = iflags.window_inited
        && windowprocs.win_putstr == tty_putstr;
#endif
    if (!tty_supported) return FALSE;
    before_seq = u.chaos.seq;
    chaos_observation_arm(CHAOS_OBS_OP_WHISTLE_ATTENTION,
                          CHAOS_OBS_FACT_ATTENTION);
    pline("The whistle's echo sharpens your visible companion's attention.");
    chaos_observation_disarm();
    if (u.chaos.seq != before_seq + 1) return FALSE;
    witness->notice_seq = u.chaos.seq;
    chaos_next_use_manifestation_notice(witness->root, witness->notice_seq);
    witness->manifestation_delivered = TRUE;
    return TRUE;
}

void chaos_whistle_witness_finalize(struct monst *mtmp,
                                    struct chaos_whistle_witness *witness) {
    boolean published = FALSE;
    int stage;
    long end_seq = 0;
    if (witness && witness->active && !witness->finalized) {
        witness->finalized = TRUE;
        if (!mtmp || DEADMONSTER(mtmp) || mtmp->mtyp != PM_LITTLE_DOG
            || !mtmp->mtame || !get_mx(mtmp, MX_EDOG)
            || mtmp == u.usteed || mtmp == u.urider
            || mon_attacktype(mtmp, AT_EXPL) || !isok(mtmp->mx, mtmp->my)) {
            witness->invalid = TRUE;
        } else {
            witness->newx = mtmp->mx;
            witness->newy = mtmp->my;
            witness->post_glyph = glyph_at(mtmp->mx, mtmp->my);
            witness->displaced = witness->oldx != witness->newx
                || witness->oldy != witness->newy;
#if defined(CHAOS) && defined(TTY_GRAPHICS)
            if (witness->manifestation_delivered && witness->displaced
                && witness->pre_public && !Hallucination && !u.uswallow
                && canseemon(mtmp))
                published = chaos_tty_publication_certificate(
                    mtmp->mx, mtmp->my, glyph_at(mtmp->mx, mtmp->my));
#endif
        }
        stage = published ? CHAOS_OBS_STAGE_COMPLETED
                          : CHAOS_OBS_STAGE_BLOCKED;
        if (!chaos_observation_finish(witness->root, stage, &end_seq)) {
            chaos_next_use_manifestation_end(witness->root,
                witness->notice_seq, 0, FALSE);
            witness->invalid = TRUE;
            return;
        }
        chaos_next_use_manifestation_end(witness->root,
            witness->notice_seq, end_seq, published);
        if (published && witness->manifestation_delivered
            && witness->displaced && witness->pre_public
            && !witness->invalid
            && witness->root < witness->notice_seq
            && witness->notice_seq < end_seq)
            chaos_next_use_on_manifestation(witness, end_seq);
    }
}

void chaos_next_use_whistle_completed(struct obj *obj, long completed_root) {
    struct obj *otmp;
    struct monst *mtmp, *candidate, *resident, *id_owner;
    boolean tool_member, valid_whistle, current_member, captured;
    unsigned captured_id;
    int glyph, candidates, id_count;

    if (!obj || completed_root <= 0) return;
    tool_member = FALSE;
    for (otmp = invent; otmp; otmp = otmp->nobj)
        if (otmp == obj) { tool_member = TRUE; break; }
    valid_whistle = tool_member && invent
        && obj->where == OBJ_INVENT && obj->otyp == WHISTLE
        && obj->known && !obj->oartifact && obj->quan == 1L;
    if (valid_whistle
        && chaos_next_use_action_preflight(CHAOS_NEXT_USE_FAMILY_W,
                                            completed_root)) {
        candidate = (struct monst *) 0;
        candidates = 0;
#ifdef TTY_GRAPHICS
        if (!Hallucination && !u.uswallow)
            for (mtmp = fmon; mtmp; mtmp = mtmp->nmon) {
                if (DEADMONSTER(mtmp) || !canseemon(mtmp)
                    || !isok(mtmp->mx, mtmp->my)) continue;
                glyph = glyph_at(mtmp->mx, mtmp->my);
                if (!Hallucination && !u.uswallow
                    && !DEADMONSTER(mtmp) && canseemon(mtmp)
                    && isok(mtmp->mx, mtmp->my)
                    && glyph_is_monster(glyph)
                    && glyph_to_mon(glyph) == PM_LITTLE_DOG
                    && tty_snapshot_projectable(mtmp->mx, mtmp->my, glyph)) {
                    candidate = mtmp;
                    ++candidates;
                }
            }
#endif
        if (candidates == 1
            && chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W,
                                        completed_root, 0)) {
            current_member = FALSE;
            for (resident = fmon; resident; resident = resident->nmon)
                if (resident == candidate && !DEADMONSTER(resident)) {
                    current_member = TRUE;
                    break;
                }
            captured = FALSE;
            if (current_member
                && candidate->mtyp == PM_LITTLE_DOG
                && candidate->mtame && get_mx(candidate, MX_EDOG)
                && candidate != u.usteed && candidate != u.urider
                && !candidate->mleashed && !get_mx(candidate, MX_ESUM)
                && !mon_attacktype(candidate, AT_EXPL)
                && !Conflict && !candidate->mberserk) {
                captured_id = candidate->m_id;
                id_count = 0;
                id_owner = (struct monst *) 0;
                if (captured_id)
                    for (resident = fmon; resident; resident = resident->nmon)
                        if (!DEADMONSTER(resident)
                            && resident->m_id == captured_id) {
                            ++id_count;
                            id_owner = resident;
                        }
                if (captured_id && id_count == 1 && id_owner == candidate) {
                    chaos_next_use_capture_whistle(completed_root,
                                                   captured_id, monstermoves);
                    captured = TRUE;
                }
            }
            if (!captured)
                chaos_next_use_whistle_unavailable(completed_root);
        } else if (candidates != 1) {
            chaos_next_use_whistle_unavailable(completed_root);
        }
    }
}

boolean chaos_next_use_fountain_contact(long completed_root,
                                        struct chaos_fountain_token *token_out) {
    if (!token_out) return FALSE;
    if (completed_root <= 0) return FALSE;
    token_out->root = 0;
    token_out->active = 0;
    token_out->remap = 0;
    token_out->consumed = 0;
    token_out->active = chaos_next_use_on_action(
        CHAOS_NEXT_USE_FAMILY_F, completed_root, token_out) ? 1 : 0;
    return token_out->active;
}

void chaos_next_use_fountain_clear(struct chaos_fountain_token *token) {
    if (!token) return;
    memset(token, 0, sizeof *token);
}
