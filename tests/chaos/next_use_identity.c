/* ENGINE-UNIT: production identity allocator, no gameplay RNG. */
#include "hack.h"
#include "chaos_next_use.h"
#include <stdio.h>
#include <string.h>

struct you u;

int main(void)
{
    long first, same, second;
    memset(&u, 0, sizeof u);
    u.ubirthday = 1750000001;
    first = chaos_next_use_game_identity();
    same = chaos_next_use_game_identity();
    memset(&u, 0, sizeof u);
    u.ubirthday = 1750000001;
    second = chaos_next_use_game_identity();
    printf("{\"positive\":%d,\"stable\":%d,\"distinct_same_second\":%d}\n",
           first > 0 && second > 0, first == same, first != second);
    return first > 0 && first == same && first != second ? 0 : 1;
}
