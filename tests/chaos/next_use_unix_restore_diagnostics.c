/* NGPL. TEST ONLY readonly diagnostics for the uncompressed Unix fixture.
 * Never import a snapshot or alter the trusted player/snapshot identities.
 * savegamestate writes sizeof(struct you) immediately before NUS1.
 */
#include "hack.h"
#include "chaos_next_use_runtime.h"
#include <assert.h>
#include <stddef.h>
#include <stdio.h>
#include <unistd.h>

int __real_chaos_next_use_restore_bound(int, long, long);

int test_native_save_layout(void)
{
#if defined(ZEROCOMP) || defined(COMPRESS)
    fputs("native restore identity fixture requires uncompressed saves\n", stderr);
    return 1;
#else
    printf("{\"compressed\":0,\"you_size\":%lu,\"dlevel_offset\":%lu,"
           "\"dlevel_size\":%lu}\n",
           (unsigned long)sizeof(struct you),
           (unsigned long)(offsetof(struct you, uz) + offsetof(d_level, dlevel)),
           (unsigned long)sizeof(u.uz.dlevel));
    return 0;
#endif
}

int __wrap_chaos_next_use_restore_bound(int fd, long run, long level_token)
{
    if (access("diagnose-restore-bound", F_OK) == 0) {
#if defined(ZEROCOMP) || defined(COMPRESS)
        assert(!"native restore diagnostic requires uncompressed saves");
#else
        /* Native raw reader has no buffered state. Read and validate a copy,
         * then return fd to the exact NUS1 boundary before the REAL restore.
         * This proves the real codec accepted the untouched binding/digest,
         * and that restgamestate reached its trusted identity boundary. */
        struct chaos_next_use_snapshot snap, live;
        off_t start = lseek(fd, 0, SEEK_CUR);
        char magic[4];
        int present, valid, result, published;
        FILE *f;
        assert(start >= 0);
        memset(&snap, 0, sizeof snap);
        memset(&live, 0, sizeof live);
        assert(chaos_next_use_mread(fd, magic, sizeof magic));
        assert(!memcmp(magic, "NUS1", 4));
        assert(chaos_next_use_mread(fd, &present, sizeof present) && present == 1);
        valid = chaos_next_use_snapshot_read(fd, &snap);
        assert(lseek(fd, start, SEEK_SET) == start);
        result = __real_chaos_next_use_restore_bound(fd, run, level_token);
        published = chaos_next_use_snapshot_export(&live);
        f = fopen("restore-bound.json", "w");
        assert(f);
        fprintf(f, "{\"snapshot_valid\":%d,\"result\":%d,\"published\":%d,"
            "\"run_token\":%ld,\"level_token\":%ld,\"armed_m_id\":%u,"
            "\"phase\":%d,\"trusted_run\":%ld,\"trusted_level\":%ld,"
            "\"trusted_dlevel\":%d}\n",
            valid, result, published, snap.run_token, snap.level_token,
            snap.armed_m_id, snap.phase, run, level_token, u.uz.dlevel);
        assert(!fclose(f));
        return result;
#endif
    }
    return __real_chaos_next_use_restore_bound(fd, run, level_token);
}
