#include "chaos_next_use_schedule.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    int dir, status;
    if (argc < 2 || argc > 3) return 2;
    if (argc == 3 && !strcmp(argv[2], "fifo")) {
        char path[512];
        int n = snprintf(path, sizeof path, "%s/next_use-schedule.jsonl", argv[1]);
        if (n < 1 || (size_t)n >= sizeof path) return 1;
        if (mkfifo(path, 0600)) return 1;
        dir = open(argv[1], O_RDONLY | O_DIRECTORY | O_CLOEXEC);
        if (dir < 0) return 1;
        status = chaos_next_use_note_origin(dir, "W", 40, 0, 1, 10, 11, 12);
        printf("{\"status\":%d}\n", status);
        close(dir);
        return status == 0 ? 0 : 1;
    }
    dir = open(argv[1], O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (dir < 0) return 1;
    status = chaos_next_use_note_origin(dir, "W", 40, 0, 1, 10, 11, 12);
    printf("{\"status\":%d}\n", status);
    close(dir);
    return status == 1 ? 0 : 1;
}
