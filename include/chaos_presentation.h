/* NetHack General Public License. Process-local presentation, never save data. */
#ifndef CHAOS_PRESENTATION_H
#define CHAOS_PRESENTATION_H
struct monst;
struct chaos_presentation_request {
    unsigned long generation;
    long root, game, player_turn, monster_turn;
    unsigned target;
    int dnum, dlevel, x, y, glyph, consumed;
};
enum chaos_presentation_result {
    CHAOS_PRESENTATION_REJECTED = 0,
    CHAOS_PRESENTATION_UNSUPPORTED,
    CHAOS_PRESENTATION_UNDELIVERED,
    CHAOS_PRESENTATION_DELIVERED
};
#ifdef CHAOS
int chaos_presentation_snapshot(int, int, int, int *);
int chaos_presentation_message_supported(void);
int chaos_presentation_begin(struct chaos_presentation_request *, long,
                             struct monst *, int);
enum chaos_presentation_result chaos_presentation_publish(
    struct chaos_presentation_request *, long, struct monst *);
void chaos_presentation_cancel(struct chaos_presentation_request *);
#else
#define chaos_presentation_snapshot(x,y,type,out) (0)
#define chaos_presentation_message_supported() (0)
#define chaos_presentation_begin(request,root,target,glyph) (0)
#define chaos_presentation_publish(request,root,target) CHAOS_PRESENTATION_UNSUPPORTED
#define chaos_presentation_cancel(request) ((void)0)
#endif
#endif
