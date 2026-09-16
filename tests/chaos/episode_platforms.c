/* Synthetic whistling scope through actual initialized curses, not doapply. */
#include <curses.h>
#include "hack.h"
#include "chaos.h"
#include "wintty.h"
#include "wincurs.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
    long root;
    int enabled = getenv("NYARLATHACK_OBSERVATIONS") &&
        !strcmp(getenv("NYARLATHACK_OBSERVATIONS"), "1");
    struct chaos_observation_token pending;
    choose_windows("curses");
    initoptions();
    init_nhwindows(&argc, argv);
    WIN_MESSAGE = create_nhwindow(NHW_MESSAGE);
    WIN_STATUS = create_nhwindow(NHW_STATUS);
    WIN_MAP = create_nhwindow(NHW_MAP);
    assert(iflags.window_inited);
    assert(windowprocs.win_putstr == curses_putstr);
    assert(windowprocs.win_putstr != tty_putstr);
    init_gods();
    urace.malenum = PM_HUMAN; urole.malenum = PM_WIZARD;
    u.umonnum = u.umonster = PM_HUMAN;
    youmonst.data = &mons[PM_HUMAN];
    u.ulevel = 1; u.ualign.god = 1;
    u.uz.dnum = 0; u.uz.dlevel = 1;
    u.usanity = 60; u.uinsight = 4;
    u.uhp = 7; u.uhpmax = 20; u.uen = 2; u.uenmax = 10;
    moves = 10;
    u.ux = u.uy = 0; vision_full_recalc = FALSE;
    chaos_start();
    assert(u.chaos.safe == 1);
    root = chaos_observation_begin(CHAOS_OBS_OP_WHISTLING);
    assert(enabled ? root > 0 : root == 0);
    chaos_observation_arm(CHAOS_OBS_OP_WHISTLING, CHAOS_OBS_FACT_SOUND_HIGH);
    You("produce a high whistling sound.");
    /* No disarm/end/probe before the unrelated message. */
    You("listen.");
    pending = chaos_observation_take_message();
    assert(pending.root == 0 && pending.fact == CHAOS_OBS_FACT_NONE);
    chaos_observation_disarm();
    chaos_observation_end(root);
    assert(!strcmp(toplines, "You listen."));
    fprintf(stderr, "{\"root\":%ld,\"port\":\"curses\",\"toplines\":\"%s\","
            "\"pending\":%ld}\n", root, toplines, pending.root);
    fflush(stdout);
    exit_nhwindows((char *)0);
    assert(!iflags.window_inited);
    return 0;
}
