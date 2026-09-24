/* NetHack General Public License. One bounded synchronous presentation request.
 * This adapter certifies delivery, never legality, admission or human notice. */
#include "hack.h"
#include "chaos_presentation.h"
#include <limits.h>
#ifdef TTY_GRAPHICS
#include "wintty.h"
#endif

static unsigned long generation;
static struct chaos_presentation_request pending;
static struct chaos_presentation_request *owner;
static struct monst *pending_target;

static int map_supported(void)
{
#ifdef TTY_GRAPHICS
    return iflags.window_inited && windowprocs.win_print_glyph == tty_print_glyph;
#else
    return 0;
#endif
}

int chaos_presentation_message_supported(void)
{
#ifdef TTY_GRAPHICS
    return iflags.window_inited && windowprocs.win_putstr == tty_putstr;
#else
    return 0;
#endif
}

int chaos_presentation_snapshot(int x, int y, int type, int *out)
{
    int glyph;
    if (!isok(x, y)) return 0;
    glyph = glyph_at(x, y);
    if (out) *out = glyph;
#ifdef TTY_GRAPHICS
    return glyph_is_monster(glyph) && glyph_to_mon(glyph) == type
        && tty_snapshot_projectable((xchar)x, (xchar)y, glyph);
#else
    (void)type;
    return 0;
#endif
}

int chaos_presentation_begin(struct chaos_presentation_request *request,
                             long root, struct monst *target, int glyph)
{
    if (!request || owner) return 0;
    memset(request, 0, sizeof *request);
    if (generation == ULONG_MAX || root <= 0 || !target || !target->m_id
        || u.chaos_game_token <= 0 || !isok(target->mx, target->my)
        || glyph != glyph_at(target->mx, target->my) || !glyph_is_monster(glyph)
        || !chaos_presentation_snapshot(target->mx, target->my,
                                        glyph_to_mon(glyph), 0)) return 0;
    request->generation = ++generation; /* no wrap and no gameplay RNG */
    request->root = root;
    request->game = u.chaos_game_token;
    request->player_turn = moves;
    request->monster_turn = monstermoves;
    request->target = target->m_id;
    request->dnum = u.uz.dnum;
    request->dlevel = u.uz.dlevel;
    request->x = target->mx;
    request->y = target->my;
    request->glyph = glyph;
    pending = *request;
    pending_target = target;
    owner = request;
    return 1;
}

static int current(const struct chaos_presentation_request *request, long root)
{
    return request && request == owner && !request->consumed
        && request->generation == pending.generation
        && request->root == pending.root && root == pending.root
        && request->game == pending.game && pending.game == u.chaos_game_token
        && request->player_turn == pending.player_turn && pending.player_turn == moves
        && request->monster_turn == pending.monster_turn && pending.monster_turn == monstermoves
        && request->dnum == pending.dnum && pending.dnum == u.uz.dnum
        && request->dlevel == pending.dlevel && pending.dlevel == u.uz.dlevel
        && request->target == pending.target
        && request->x == pending.x && request->y == pending.y
        && request->glyph == pending.glyph;
}

void chaos_presentation_cancel(struct chaos_presentation_request *request)
{
    if (request && request == owner) {
        owner = 0;
        pending_target = 0;
        memset(&pending, 0, sizeof pending);
    }
    if (request) request->consumed = 1;
}

enum chaos_presentation_result chaos_presentation_publish(
    struct chaos_presentation_request *request, long root, struct monst *target)
{
    enum chaos_presentation_result result = CHAOS_PRESENTATION_REJECTED;
    int glyph;
    if (!current(request, root)) {
        chaos_presentation_cancel(request);
        return result;
    }
    if (!map_supported()) result = CHAOS_PRESENTATION_UNSUPPORTED;
    else if (target && target == pending_target && target->m_id == pending.target && !DEADMONSTER(target)
             && canseemon(target) && !Hallucination && !u.uswallow
             && (target->mx != pending.x || target->my != pending.y)
             && chaos_presentation_snapshot(target->mx, target->my,
                                             glyph_to_mon(pending.glyph), &glyph)) {
        result = CHAOS_PRESENTATION_UNDELIVERED;
#ifdef TTY_GRAPHICS
        /* Keep the real bounded reprint: a drained glyph buffer is not a
         * certificate. The existing TTY observer verifies this exact print. */
        if (chaos_tty_publication_certificate(target->mx, target->my, glyph))
            result = CHAOS_PRESENTATION_DELIVERED;
#endif
    }
    chaos_presentation_cancel(request); /* including failed/cancelled delivery */
    return result;
}
