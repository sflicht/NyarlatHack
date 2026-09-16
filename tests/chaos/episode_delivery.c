/* NGPL. Full-linked delivery regression: real native output, synthetic scope/context.
 * Not doapply, action purity, or an ordinary-game witness. No renderer stubs. */
#include "hack.h"
#include "chaos.h"
#include "wintty.h"
#include "native_rng.h"
#include <stdio.h>
#include <stdlib.h>

/* Native exported implementation has no public declaration in extern.h. */
extern int msgpline_type(const char *);

int main(int argc, char **argv)
{
    long root;
    int expected, enabled, stopped, replacement;
    long i;
    FILE *history;
    const char *observe;

    test_rng_control();
    if (argc > 1) test_rng_negative_control(argv[1]);
    /* native_rng.verify_native_fixture runs the unchanged RNG oracle separately;
     * it does NOT run this TTY scenario or prove message/action purity. */
    if (argc == 1) {
        test_rng_unchanged(test_rng_begin());
        return 0;
    }
    assert(argc == 2);
    stopped = !strcmp(argv[1], "--stop-append")
        || !strcmp(argv[1], "--stop-replacement");
    replacement = !strcmp(argv[1], "--stop-replacement");
    assert(stopped || !strcmp(argv[1], "--render"));
    assert(getenv("HOME") && getenv("MAIL") && getenv("NETHACKOPTIONS"));
    assert(getenv("NYARLATHACK_RUN_DIR"));
    observe = getenv("NYARLATHACK_OBSERVATIONS");
    enabled = observe && !strcmp(observe, "1");

    /* Same port/options ordering as unixmain; options read one private file.
     * No newgame(), level generation, lock/save/bones, or filesystem chdirx(). */
    choose_windows("tty");
    initoptions();
    init_nhwindows(&argc, argv);
    WIN_MESSAGE = create_nhwindow(NHW_MESSAGE);
    /* Native first display marks the message window initialized. */
    display_nhwindow(WIN_MESSAGE, FALSE);
    assert(iflags.window_inited && wins[WIN_MESSAGE]);
    assert(windowprocs.win_putstr == tty_putstr);
    assert(ttyDisplay->cols >= 80 && ttyDisplay->rows >= 24);

    init_gods();
    urace.malenum = PM_HUMAN; urole.malenum = PM_WIZARD;
    u.umonnum = u.umonster = PM_HUMAN;
    youmonst.data = &mons[PM_HUMAN];
    u.ulevel = 1; u.ualign.god = 1;
    u.uz.dnum = 0; u.uz.dlevel = 1;
    u.usanity = 60; u.uinsight = 4;
    u.uhp = 7; u.uhpmax = 20; u.uen = 2; u.uenmax = 10;
    moves = 10;
    /* No level exists: don't request vision/flush. These real engine routines
     * remain linked, not replaced. This is explicitly synthetic context. */
    u.ux = u.uy = 0; vision_full_recalc = FALSE;
    chaos_start();
    assert(u.chaos.safe == 1);
    assert(msgpline_type("You produce a high whistling sound.") == MSGTYP_NORMAL);
    assert(!(wins[WIN_MESSAGE]->flags & WIN_STOP));
    if (stopped) {
        /* Prime through real, unarmed native output; no More is needed.
         * Only this initial-condition setup writes WIN_STOP. */
        You(replacement
            ? "wait beside the quiet fountain and listen to the water."
            : "wait.");
        assert(ttyDisplay->toplin == 1 && wins[WIN_MESSAGE]->cury == 0);
        assert((strlen("You produce a high whistling sound.")
                + strlen(toplines) + 3 < (unsigned)(CO - 8)) == !replacement);
        wins[WIN_MESSAGE]->flags |= WIN_STOP;
    }
    expected = test_rng_begin();
    root = chaos_observation_begin(CHAOS_OBS_OP_WHISTLING);
    assert(enabled ? root > 0 : root == 0);
    chaos_observation_arm(CHAOS_OBS_OP_WHISTLING, CHAOS_OBS_FACT_SOUND_HIGH);
    You("produce a high whistling sound.");
    chaos_observation_disarm();
    chaos_observation_end(root);
    test_rng_unchanged(expected);
    fflush(stdout);
    /* State evidence on a separate pipe, never the terminal-text oracle. */
    fprintf(stderr, "{\"root\":%ld,\"flags\":%d,\"toplin\":%d,"
        "\"message_x\":%d,\"message_y\":%d,\"display_x\":%d,\"display_y\":%d}\n",
        root, (int)wins[WIN_MESSAGE]->flags, (int)ttyDisplay->toplin,
        (int)wins[WIN_MESSAGE]->curx, (int)wins[WIN_MESSAGE]->cury,
        (int)ttyDisplay->curx, (int)ttyDisplay->cury);
    /* Full stored text/history comparison, not a rendering acknowledgement. */
    history = fopen("native-history.txt", "w");
    assert(history);
    fprintf(history, "toplines:%s\nmaxrow:%ld maxcol:%ld\n", toplines,
            wins[WIN_MESSAGE]->maxrow, wins[WIN_MESSAGE]->maxcol);
    for (i = 0; i < wins[WIN_MESSAGE]->rows; ++i)
        fprintf(history, "%ld:%s\n", i, wins[WIN_MESSAGE]->data[i]
                ? wins[WIN_MESSAGE]->data[i] : "<null>");
    assert(fclose(history) == 0);
    tty_exit_nhwindows((char *)0);
    return 0;
}
