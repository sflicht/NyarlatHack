/* NGPL: synthetic context, real standalone transport; not gameplay purity. */
#define _POSIX_C_SOURCE 200809L
#include "chaos_io.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Missing implementation is a behavioral failure, not a linker failure. */
extern int chaos_io_observation(struct chaos_io *, struct chaos_state *,
    const struct chaos_context *, int, int, long, int) __attribute__((weak));
static int event_fd = -1, fault, writes, syncs;
ssize_t __real_write(int, const void *, size_t);
int __real_fsync(int);
ssize_t __wrap_write(int fd, const void *buf, size_t n) {
    if(fd == event_fd) {
        ++writes;
        if(fault == 1 && writes == 1) { errno=EINTR; return -1; }
        if((fault == 1 && writes == 2) || (fault == 2 && writes == 1))
            return __real_write(fd,buf,n > 7 ? 7 : n);
        if(fault == 2) { errno=EIO; return -1; }
    }
    return __real_write(fd,buf,n);
}
int __wrap_fsync(int fd) {
    if(fd == event_fd) {
        ++syncs;
        if(fault == 3) { errno=EIO; return -1; }
    }
    return __real_fsync(fd);
}
static int show(void *arg, int telegraph, int ambient) {
    (void)arg; assert(telegraph == 2); assert(ambient == 0); return 1;
}
int main(int argc, char **argv) {
    struct chaos_io io, before_io;
    struct chaos_state s, before_s;
    struct chaos_context c, before_c;
    int op, stage, fact, ok;
    long root, seq;
    assert(argc == 4);
    assert(CHAOS_OBS_OP_NONE == 0 && CHAOS_OBS_OP_WHISTLING == 1 &&
           CHAOS_OBS_OP_FOUNTAIN_DRINK == 2);
    assert(CHAOS_OBS_STAGE_ENABLED == 0 && CHAOS_OBS_STAGE_STARTED == 1 &&
           CHAOS_OBS_STAGE_NOTICE == 2 && CHAOS_OBS_STAGE_COMPLETED == 3 &&
           CHAOS_OBS_STAGE_BLOCKED == 4);
    assert(CHAOS_OBS_FACT_NONE == 0 && CHAOS_OBS_FACT_SOUND_HIGH == 1 &&
           CHAOS_OBS_FACT_SOUND_SHRILL == 2 && CHAOS_OBS_FACT_SOUND_NORMAL == 3 &&
           CHAOS_OBS_FACT_SOUND_STRANGE == 4 && CHAOS_OBS_FACT_SOUND_HUMMING == 5 &&
           CHAOS_OBS_FACT_WATER_REFRESHED == 6 && CHAOS_OBS_FACT_WATER_FOUL == 7 &&
           CHAOS_OBS_FACT_CANNOT_REACH == 8 && CHAOS_OBS_FACT_DETECTION_PRESENTED == 9);
    memset(&c,0,sizeof c); chaos_state_init(&s);
    c.turn=10; c.sanity=0; c.eligible=1;
    c.hp=7; c.hp_max=20; c.power=-2; c.power_max=10;
    assert(chaos_io_open(&io,argv[1])); event_fd=io.events;
    fault=atoi(argv[3]);
    if(!strcmp(argv[2],"legacy")) {
        assert(chaos_io_event(&io,&s,&c,"apply","attempt","quote\"\\\n"));
        chaos_io_safe(&io,&s,&c,"level_enter",show,NULL);
        c.turn=11; chaos_io_expire(&io,&s,&c);
    } else {
        while(scanf("%ld %d %d %ld %d",&seq,&op,&stage,&root,&fact) == 5) {
            if(seq >= 0 || !strcmp(argv[2],"literal-sequence")) s.seq=seq;
            memcpy(&before_s,&s,sizeof s); memcpy(&before_c,&c,sizeof c);
            memcpy(&before_io,&io,sizeof io);
            if(op == -99) ok=chaos_io_event(&io,&s,&c,"apply","attempt","");
            else ok=chaos_io_observation ?
                chaos_io_observation(&io,&s,&c,op,stage,root,fact) : 0;
            before_s.seq+=ok;
            assert(!memcmp(&s,&before_s,sizeof s));
            assert(!memcmp(&c,&before_c,sizeof c));
            before_io.failed=io.failed;
            assert(!memcmp(&io,&before_io,sizeof io));
            printf("%d %ld %d %d %d\n",ok,s.seq,io.failed,writes,syncs);
        }
    }
    chaos_io_close(&io); return 0;
}
