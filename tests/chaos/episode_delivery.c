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
extern char prevmsg[BUFSZ];

static int forwarded_calls;
static void forwarding_putstr(winid window, int attr, const char *text)
{
    ++forwarded_calls;
    assert(window == WIN_MESSAGE && attr == 0);
    assert(!strcmp(text, "You produce a high whistling sound."));
    tty_putstr(window, attr, text);
}

int main(int argc, char **argv)
{
    long root;
    int expected, enabled, stopped, replacement, append, pre_more;
    int post_newline, post_wrap, escape;
    int noshow, msg_norep, norep, empty, raw, early, renamed, wrapped, tty_named;
    struct window_procs saved_procs;
    const char *message = "produce a high whistling sound.";
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
    pre_more = !strcmp(argv[1], "--pre-more-space")
        || !strcmp(argv[1], "--pre-more-escape");
    post_newline = !strcmp(argv[1], "--post-newline-escape");
    post_wrap = !strcmp(argv[1], "--post-wrap-escape");
    append = !strcmp(argv[1], "--append");
    noshow = !strcmp(argv[1], "--filter-noshow");
    msg_norep = !strcmp(argv[1], "--filter-msgtype-norep");
    norep = !strcmp(argv[1], "--filter-norep");
    empty = !strcmp(argv[1], "--early-empty");
    raw = !strcmp(argv[1], "--early-raw");
    early = noshow || msg_norep || norep || empty || raw;
    renamed = !strcmp(argv[1], "--port-native-renamed");
    tty_named = !strcmp(argv[1], "--port-wrapper-tty");
    wrapped = !strcmp(argv[1], "--port-wrapper") || tty_named;
    escape = !strcmp(argv[1], "--pre-more-escape") || post_newline || post_wrap;
    replacement = !strcmp(argv[1], "--stop-replacement") || pre_more;
    assert(stopped || pre_more || post_newline || post_wrap || append
           || early || renamed || wrapped
           || !strcmp(argv[1], "--render"));
    if (post_newline)
        message = "produce a high whistling sound.\nThe echo fades.";
    if (post_wrap)
        message = "produce a high whistling sound. The echo travels along the empty "
                  "corridor and slowly fades into silence.";
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
    /* Multiline More restores native map rows and inspects the status window.
     * Use real windows rather than stubbing docorner/row_refresh. */
    if (post_newline || post_wrap) {
        WIN_STATUS = create_nhwindow(NHW_STATUS);
        WIN_MAP = create_nhwindow(NHW_MAP);
        assert(wins[WIN_STATUS] && wins[WIN_MAP]);
    }
    /* Native first display marks the message window initialized. */
    display_nhwindow(WIN_MESSAGE, FALSE);
    assert(iflags.window_inited && wins[WIN_MESSAGE]);
    assert(windowprocs.win_putstr == tty_putstr);
    assert(ttyDisplay->cols == 80 && ttyDisplay->rows == 24);

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
    if (stopped || pre_more || append) {
        /* Real unarmed output establishes append-fit or pre-render More.
         * Priming itself fits one empty line and cannot require input. */
        You(replacement
            ? "wait beside the quiet fountain and listen to the water."
            : "wait.");
        assert(ttyDisplay->toplin == 1 && wins[WIN_MESSAGE]->cury == 0);
        assert((strlen("You produce a high whistling sound.")
                + strlen(toplines) + 3 < (unsigned)(CO - 8)) == !replacement);
        /* Only the original initial-WIN_STOP cases set the flag directly. */
        if (stopped) wins[WIN_MESSAGE]->flags |= WIN_STOP;
    } else {
        assert(ttyDisplay->toplin == 0 && wins[WIN_MESSAGE]->cury == 0);
    }
    if (!stopped) assert(!(wins[WIN_MESSAGE]->flags & WIN_STOP));
    if (msg_norep || norep) {
        /* Prime the real prevmsg/toplines paths before arming, not fake state. */
        You("%s", message);
        assert(!strcmp(prevmsg, "You produce a high whistling sound."));
        assert(!strcmp(toplines, prevmsg));
        assert(ttyDisplay->toplin == 1 && wins[WIN_MESSAGE]->cury == 0);
    }
    if (noshow || msg_norep) {
        iflags.msgtype_regex = FALSE;
        msgpline_add(noshow ? MSGTYP_NOSHOW : MSGTYP_NOREP,
                     "You produce a high whistling sound.");
        assert(msgpline_type("You produce a high whistling sound.")
               == (noshow ? MSGTYP_NOSHOW : MSGTYP_NOREP));
    }
    saved_procs = windowprocs;
    if (renamed || wrapped) {
        /* Controlled test port identity, not actual curses coverage. All other
         * native callbacks remain intact; the wrapper renders once via TTY. */
        windowprocs.name = tty_named ? "tty" : "fixture-forwarding";
        if (wrapped) windowprocs.win_putstr = forwarding_putstr;
        assert((windowprocs.win_putstr == tty_putstr) == !wrapped);
    }
    expected = test_rng_begin();
    root = chaos_observation_begin(CHAOS_OBS_OP_WHISTLING);
    assert(enabled ? root > 0 : root == 0);
    chaos_observation_arm(CHAOS_OBS_OP_WHISTLING, CHAOS_OBS_FACT_SOUND_HIGH);
    if (raw) {
        assert(iflags.window_inited);
        iflags.window_inited = FALSE;
    }
    if (empty) {
        /* Pass an actually empty line at vpline entry, not You("") or "%s".
         * Runtime argv terminator avoids -Wformat-zero-length on pline(""). */
        const char *empty_line = argv[1] + strlen(argv[1]);
        assert(!*empty_line);
        /* The unused argument satisfies -Wformat-security; vpline returns
         * before reading any format arguments because the line is empty. */
        pline(empty_line, 0);
    } else if (norep) Norep("You produce a high whistling sound.");
    else You("%s", message);
    if (raw) {
        assert(!iflags.window_inited);
        iflags.window_inited = TRUE;
    }
    assert(forwarded_calls == (wrapped ? 1 : 0));
    windowprocs = saved_procs;
    if (early) {
        /* No disarm/end/rearm/take probe before this ordinary native output:
         * it must not steal the suppressed/empty/raw call's pending token. */
        assert(msgpline_type("You listen.") == MSGTYP_NORMAL);
        You("listen.");
    }
    chaos_observation_disarm();
    chaos_observation_end(root);
    test_rng_unchanged(expected);
    assert(!!(wins[WIN_MESSAGE]->flags & WIN_STOP) == !!(stopped || escape));
    if (pre_more || post_newline || post_wrap) {
        /* Read by the real native xwaitforspace, not a fixture input shim. */
        assert(morc == (escape ? '\033' : ' '));
        assert(ttyDisplay->toplin == (escape ? 0 : 1));
    }
    if (post_newline || post_wrap) assert(strchr(toplines, '\n'));
    if (append) {
        assert(!strcmp(toplines, "You wait.  You produce a high whistling sound."));
        assert(ttyDisplay->toplin == 1 && wins[WIN_MESSAGE]->cury == 0);
    }
    fflush(stdout);
    /* State evidence on a separate pipe, never the terminal-text oracle. */
    fprintf(stderr, "{\"root\":%ld,\"flags\":%d,\"toplin\":%d,"
        "\"message_x\":%d,\"message_y\":%d,\"display_x\":%d,\"display_y\":%d,"
        "\"forwarded_calls\":%d}\n",
        root, (int)wins[WIN_MESSAGE]->flags, (int)ttyDisplay->toplin,
        (int)wins[WIN_MESSAGE]->curx, (int)wins[WIN_MESSAGE]->cury,
        (int)ttyDisplay->curx, (int)ttyDisplay->cury, forwarded_calls);
    /* Full stored text/history comparison, not a rendering acknowledgement. */
    history = fopen("native-history.txt", "w");
    assert(history);
    fprintf(history, "toplines:%s\nmaxrow:%ld maxcol:%ld\n", toplines,
            wins[WIN_MESSAGE]->maxrow, wins[WIN_MESSAGE]->maxcol);
    for (i = 0; i < wins[WIN_MESSAGE]->rows; ++i)
        fprintf(history, "%ld:%s\n", i, wins[WIN_MESSAGE]->data[i]
                ? wins[WIN_MESSAGE]->data[i] : "<null>");
    assert(fclose(history) == 0);
    if (noshow || msg_norep) msgpline_free();
    tty_exit_nhwindows((char *)0);
    return 0;
}
