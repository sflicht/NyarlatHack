/* NGPL. Read a published next-use envelope; no admission. */
#define _GNU_SOURCE
#include "chaos_next_use_io.h"
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    struct chaos_next_use_envelope envelope;
    struct stat st;
    char run[65];
    int dir, rc;

    if (argc != 2 && argc != 3) return 2;
    dir = open(argv[1], O_RDONLY | O_DIRECTORY);
    if (dir < 0) return 2;
    if (argc == 3 && !strcmp(argv[2], "runhex")) {
        if (fstat(dir, &st)) return 2;
        if (snprintf(run, sizeof run, "%016llx%016llx%016llx%016llx",
                     (unsigned long long)st.st_dev,
                     (unsigned long long)st.st_ino,
                     (unsigned long long)st.st_dev,
                     (unsigned long long)st.st_ino) != 64)
            return 2;
        close(dir);
        printf("%s\n", run);
        return 0;
    }
    memset(&envelope, 0, sizeof envelope);
    rc = chaos_next_use_envelope_load(dir, &envelope);
    close(dir);
    printf("load=%d id=%d cost=%d at=%d ttl=%d ops=%d family=%d sha=%s telegraph=%s source_len=%zu\n",
           rc, envelope.id, envelope.cost, envelope.at, envelope.ttl,
           envelope.operation_count, envelope.operations[0],
           envelope.source_sha256, envelope.telegraph, envelope.source_length);
    return rc == CHAOS_NEXT_USE_OK ? 0 : 1;
}
