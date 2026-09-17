/* NGPL: linked native admission; wrappers inject faults, never Lua results. */
#define _GNU_SOURCE
#include "hack.h"
#include "chaos.h"
#include "chaos_curio.h"
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <sys/stat.h>
#include <unistd.h>
#include "native_rng.h"

static const char *mode;
static int warned, evidence_fd=-1, evidence_synced, dir_synced, spend_calls, source_opens;
static int initial_spent, prefixed;
int __real_chaos_spend_non_effect(struct chaos_state *, int, int);
int __wrap_chaos_spend_non_effect(struct chaos_state *s, int sanity, int spender) {
    assert(s != &u.chaos && spender == CHAOS_SPEND_CURIO);
    ++spend_calls;
    return __real_chaos_spend_non_effect(s, sanity, spender);
}
ssize_t __real_write(int, const void *, size_t);
int __real_fsync(int);
int __real_close(int);
int __wrap_close(int fd) {
    if (fd == evidence_fd) evidence_fd = -1;
    return __real_close(fd);
}
int __real_openat(int, const char *, int, ...);
int __wrap_openat(int dir, const char *name, int flags, ...) {
    int fd;
    if (!strcmp(name,"curio.lua")) ++source_opens;
    if (flags & O_CREAT) fd=__real_openat(dir,name,flags,0600);
    else fd=__real_openat(dir,name,flags);
    if (!strcmp(name,"curio-used.lua")) evidence_fd=fd;
    return fd;
}
ssize_t __wrap_write(int fd, const void *buf, size_t n) {
    if (fd==evidence_fd && !strcmp(mode,"writefail")) { errno=ENOSPC; return -1; }
    if (fd==evidence_fd && !strcmp(mode,"shortwrite") && n>3) n=3;
    if (!strcmp(mode,"prefail") && memmem(buf,n,"pre_admitted",12)) { errno=EIO; return -1; }
    if (!strcmp(mode,"transportfail") && memmem(buf,n,"safe_point",10)) { errno=EIO; return -1; }
    if (!strcmp(mode,"finalfail") && memmem(buf,n,"\"detail\":\"admitted\"",strlen("\"detail\":\"admitted\""))) { errno=EIO; return -1; }
    return __real_write(fd,buf,n);
}
int __wrap_fsync(int fd) {
    struct stat st; assert(!fstat(fd,&st));
    if (fd==evidence_fd) {
        if (!strcmp(mode,"fsyncfail")) { errno=EIO; return -1; }
        evidence_synced=1;
    }
    if (S_ISDIR(st.st_mode)) {
        if (!strcmp(mode,"dirsyncfail")) { errno=EIO; return -1; }
        dir_synced=1;
    }
    return __real_fsync(fd);
}
void __wrap_pline(const char *fmt, ...) {
    struct chaos_state before;
    if (prefixed && !strcmp(fmt,"%s")) return;
    assert(strstr(fmt,"may appear"));
    assert(u.curio.phase==CHAOS_CURIO_REJECTED
           && u.chaos.spent==initial_spent);
    assert(u.chaos.cosmetic_seen==prefixed && u.chaos.cosmetic_last_turn==(prefixed?10:0));
    assert(evidence_synced && dir_synced);
    ++warned;
    before=u.chaos;
    chaos_safe("recursive");
    assert(!memcmp(&before,&u.chaos,sizeof before));
}
int main(int argc, char **argv) {
    int expected, spent, rng; struct chaos_curio_state saved;
    if(argc==2) { test_rng_negative_control(argv[1]); return 0; }
    assert(argc==3); mode=argv[1]; expected=atoi(argv[2]);
    prefixed=!strcmp(mode,"legacy")||!strcmp(mode,"tight")||!strcmp(mode,"exhausted");
    initial_spent=(!strcmp(mode,"budget")||!strcmp(mode,"exhausted"))?2:
                  (!strcmp(mode,"tight")||!strcmp(mode,"tight-control"))?1:0;
    test_rng_control();
    memset(&u,0,sizeof u); init_gods();
    urace.malenum=PM_HUMAN; urole.malenum=PM_WIZARD;
    u.umonnum=u.umonster=PM_HUMAN; youmonst.data=&mons[PM_HUMAN];
    u.usanity=100; u.ux=u.uy=5; u.ulevel=1; u.ualign.god=1;
    u.uz.dnum=0; u.uz.dlevel=1; moves=10;
    u.uhp=7; u.uhpmax=20; u.uen=2; u.uenmax=10;
    if (!strcmp(mode,"branch")) u.uz.dnum=1;
    if (!strcmp(mode,"level2")) u.uz.dlevel=2;
    if (!strcmp(mode,"level3")) u.uz.dlevel=3;
    if (!strcmp(mode,"asleep")) u.usleep=1;
    if (!strcmp(mode,"busy")) multi=-1;
    if (!strcmp(mode,"dead")) u.uhp=0;
    if (!strcmp(mode,"gameover")) program_state.gameover=1;
    if (!strcmp(mode,"budget")) { chaos_state_init(&u.chaos); u.chaos.spent=2; }
    if (!strcmp(mode,"noadvance")) { chaos_state_init(&u.chaos); u.chaos.safe=CHAOS_MAX_COUNTER; }
    if (initial_spent) { chaos_state_init(&u.chaos); u.chaos.spent=initial_spent; }
    rng=test_rng_begin();
    chaos_start();
    if (!strcmp(mode,"tight")||!strcmp(mode,"tight-control")||!strcmp(mode,"exhausted")) chaos_safe("sleep");
    if (!strcmp(mode,"invalidstate")) {
        struct chaos_state invalid;int dir;
        /* Exercise the caller directly, without startup repairing state. */
        memset(&u.curio,0,sizeof u.curio);u.chaos.reserved=1;invalid=u.chaos;
        dir=open(getenv("NYARLATHACK_RUN_DIR"),O_RDONLY|O_DIRECTORY);assert(dir>=0);
        source_opens=0;chaos_curio_safe(dir);close(dir);assert(!source_opens);
        assert(!memcmp(&invalid,&u.chaos,sizeof invalid) && !spend_calls);
        assert(u.curio.phase==CHAOS_CURIO_VIRGIN);test_rng_unchanged(rng);return 0;
    }
    if (!strcmp(mode,"noadvance") || !strcmp(mode,"budget")) chaos_safe("sleep");
    assert(u.curio.phase==(unsigned)expected);
    assert(chaos_curio_valid(&u.curio));
    assert(u.chaos.last_id==prefixed && u.chaos.reserved==0);
    assert(u.chaos.cosmetic_seen==prefixed && u.chaos.cosmetic_last_turn==(prefixed?10:0));
    assert(u.chaos.safe==(!strcmp(mode,"noadvance")?CHAOS_MAX_COUNTER:1));
    if (expected==CHAOS_CURIO_ADMITTED) {
        assert(warned==1 && u.chaos.spent==initial_spent+1);
        assert(!strcmp(u.curio.name,"Exact counter"));
        assert(u.curio.charges==3 && !u.curio.state && !u.curio.owner);
        assert(u.usanity==100 && u.uhp==7 && u.uen==2);
    } else { assert(!warned); assert(u.chaos.spent==initial_spent); }
    if (!strcmp(mode,"exhausted")) assert(!source_opens);
    saved=u.curio; spent=u.chaos.spent;
    if (expected==CHAOS_CURIO_ADMITTED || expected==CHAOS_CURIO_REJECTED) {
        char path[1024]; int fd;
        snprintf(path,sizeof path,"%s/curio.lua",getenv("NYARLATHACK_RUN_DIR"));
        unlink(path); fd=open(path,O_CREAT|O_WRONLY,0600); assert(fd>=0);
        assert(write(fd,"return {}",9)==9); close(fd);
        chaos_safe("sleep"); assert(!memcmp(&saved,&u.curio,sizeof saved));
        assert(u.chaos.spent==spent);
    }
    /* Transport-independent, no safe advance required to close the window. */
    u.uz.dnum=0; u.uz.dlevel=3;
    if (!strcmp(mode,"transportfail") || !strcmp(mode,"noadvance")) chaos_safe("level_enter");
    else chaos_curio_safe(-1);
    if (expected==CHAOS_CURIO_VIRGIN || expected==CHAOS_CURIO_ADMITTED)
        assert(u.curio.phase==CHAOS_CURIO_EXPIRED);
    assert(chaos_curio_valid(&u.curio) && u.chaos.spent==spent);
    assert(u.chaos.cosmetic_seen==prefixed && u.chaos.cosmetic_last_turn==(prefixed?10:0));
    assert(spend_calls == (expected==CHAOS_CURIO_ADMITTED));
    test_rng_unchanged(rng);
    puts("native admission, exact lifecycle, budget and safe schedule verified; RNG draws=0");
    return 0;
}
