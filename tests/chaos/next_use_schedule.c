#include "chaos_next_use_schedule.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    int dir, status;
    if (argc != 2) return 2;
    dir = open(argv[1], O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (dir < 0) return 1;
    status = chaos_next_use_note_origin(dir, "W", 40, 0, 1, 10, 11, 12);
    printf("{\"status\":%d}\n", status);
    return status == 1 ? 0 : 1;
}
