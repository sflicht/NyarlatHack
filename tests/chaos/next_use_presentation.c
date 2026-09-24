/* Synthetic request contract over real TTY; not admission or ordinary play. */
#define main dogmove_fixture_main
#include "next_use_dogmove.c"
#undef main

static int fake_calls;
static void fake_print(winid window, xchar x, xchar y, int glyph)
{
    (void)window; (void)x; (void)y; (void)glyph;
    ++fake_calls;
}
int main(int argc, char **argv)
{
    struct monst pet, other;
    struct chaos_presentation_request request = {0}, copy;
    const char *name;
    int started, first, second, original = -1, glyph;
    long root = 77;
    FILE *out;
    if (argc != 2) return 2;
    name = argv[1];
    fqn_prefix[TROUBLEPREFIX] = "./";
    setup_tty(&argc, argv);
    setup_level(&pet);
    glyph = glyph_at(pet.mx, pet.my);
    if (!strcmp(name, "pre_glyph")) glyph = monnum_to_glyph(PM_LITTLE_DOG);
    started = chaos_presentation_begin(&request, root, &pet, glyph);
    remove_monster(pet.mx, pet.my);
    place_monster(&pet, 11, 10);
    newsym(12, 10);
    newsym(11, 10);
    if (!strcmp(name, "root")) ++root;
    if (!strcmp(name, "generation")) ++request.generation;
    if (!strcmp(name, "game")) ++u.chaos_game_token;
    if (!strcmp(name, "level")) ++u.uz.dlevel;
    if (!strcmp(name, "turn")) ++moves;
    if (!strcmp(name, "monster_turn")) ++monstermoves;
    if (!strcmp(name, "identity")) ++pet.m_id;
    if (!strcmp(name, "hidden")) pet.minvis = TRUE;
    if (!strcmp(name, "glyph")) show_glyph(11, 10, cmap_to_glyph(S_litroom));
    if (!strcmp(name, "cancelled")) wins[WIN_MAP]->flags |= WIN_CANCELLED;
    if (!strcmp(name, "unsupported")) {
        /* This earlier, unrelated real draw must not certify our request. */
        tty_print_glyph(WIN_MAP, 18, 10, glyph_at(18, 10));
        windowprocs.win_print_glyph = fake_print;
    }
    if (!strcmp(name, "copy")) {
        copy = request;
        first = chaos_presentation_publish(&copy, root, &pet);
        original = chaos_presentation_publish(&request, root, &pet);
    } else if (!strcmp(name, "replacement")) {
        other = pet; /* same numeric id and visible cell, wrong native object */
        first = chaos_presentation_publish(&request, root, &other);
    } else first = chaos_presentation_publish(&request, root, &pet);
    wins[WIN_MAP]->flags &= ~WIN_CANCELLED;
    windowprocs.win_print_glyph = tty_print_glyph;
    second = chaos_presentation_publish(&request, root, &pet);
    out = fopen("presentation-result.json", "w");
    if (!out) return 2;
    fprintf(out, "{\"begin\":%d,\"result\":%d,\"repeat\":%d,\"original\":%d,\"fake_calls\":%d}\n",
            started, first, second, original, fake_calls);
    return fclose(out) ? 2 : 0;
}
