/* NetHack General Public License. Unix transport: no RNG and bounded work. */
#define _POSIX_C_SOURCE 200809L
#include "chaos_io.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int regular(int dir, const char *name, int flags) {
    struct stat st;
    int fd = openat(dir,name,flags|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC,0600);
    if(fd < 0) return -1;
    if(fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_uid != getuid() || st.st_nlink != 1) {
        close(fd); return -1;
    }
    return fd;
}
int chaos_io_open(struct chaos_io *io, const char *path) {
    struct stat st;
    memset(io,0,sizeof *io); io->dir=io->events=io->journal=-1;
    if(!path || path[0] != '/') return 0;
    io->dir=open(path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
    if(io->dir < 0) return 0;
    if(fstat(io->dir,&st) || st.st_uid != getuid() || (st.st_mode & 077)) {
        chaos_io_close(io); return 0;
    }
    io->events=regular(io->dir,"events.jsonl",O_WRONLY|O_APPEND|O_CREAT);
    io->journal=regular(io->dir,"whispers.jsonl",O_WRONLY|O_APPEND|O_CREAT);
    if(io->events < 0 || io->journal < 0) io->failed=1;
    return !io->failed;
}
void chaos_io_close(struct chaos_io *io) {
    if(io->events >= 0) close(io->events);
    if(io->journal >= 0) close(io->journal);
    if(io->dir >= 0) close(io->dir);
    io->events=io->journal=io->dir=-1;
}
static int append(struct chaos_io *io, int fd, const char *buf) {
    size_t n = strlen(buf), pos = 0;
    if(fd < 0 || io->failed) return 0;
    while(pos < n) {
        ssize_t k = write(fd,buf+pos,n-pos);
        if(k < 0 && errno == EINTR) continue;
        if(k <= 0) { io->failed=1; return 0; }
        pos += (size_t)k;
    }
    if(fsync(fd)) { io->failed=1; return 0; }
    return 1;
}
static int event(struct chaos_io *io, struct chaos_state *s, const struct chaos_context *c, int version,
                 const char *name, const char *phase, const char *detail, const char *extra) {
    char a[160], b[160], d[1538], line[3072];
    int n;
    if(io->events < 0 || io->failed || s->seq >= CHAOS_MAX_COUNTER) return 0;
    if(!chaos_quote(a,sizeof a,name,strlen(name)) || !chaos_quote(b,sizeof b,phase,strlen(phase)) ||
       !chaos_quote(d,sizeof d,detail,strlen(detail))) return 0;
    n=snprintf(line,sizeof line,
        CHAOS_EVENT_FORMAT,
        version,s->seq+1,c->turn,s->safe,a,b,d,c->sanity,c->insight,chaos_budget(s,c->sanity),s->spent,s->reserved,s->last_id,
        c->hp,c->hp_max,c->power,c->power_max,extra);
    if(n < 0 || (size_t)n >= sizeof line || !append(io,io->events,line)) return 0;
    ++s->seq; return 1;
}
int chaos_io_event(struct chaos_io *io, struct chaos_state *s, const struct chaos_context *c,
                   const char *name, const char *phase, const char *detail) {
    return event(io,s,c,1,name,phase,detail,"");
}
int chaos_io_observation(struct chaos_io *io, struct chaos_state *s,
                         const struct chaos_context *c, int operation, int stage,
                         long root_seq, int fact) {
    char extra[512];
    int n;
    /* Check before +1; row validity does not authenticate an active root. */
    if(s->seq < 0 || s->seq >= CHAOS_MAX_COUNTER ||
       !chaos_obs_row_valid(operation, stage, s->seq + 1, root_seq, fact)) return 0;
    n=snprintf(extra,sizeof extra,",\"observation\":{\"operation\":\"%s\",\"stage\":\"%s\","
        "\"root_seq\":%ld,\"fact\":\"%s\"}",chaos_obs_operation_name(operation),chaos_obs_stage(stage)->name,root_seq,chaos_obs_fact_name(fact));
    if(n < 0 || (size_t)n >= sizeof extra) return 0;
    return event(io,s,c,2,"observation",chaos_obs_stage(stage)->phase,"",extra);
}
static void fields(char *buf, size_t cap, const struct chaos_request *r, const char *status, long expires) {
    snprintf(buf,cap,CHAOS_ACK_FORMAT,
        r->id,status,chaos_name(r->kind),r->value,r->duration,r->telegraph,r->at,chaos_cost(r->kind),expires);
}
static void ack(struct chaos_io *io, struct chaos_state *s, const struct chaos_context *c,
                const struct chaos_request *r, int result) {
    char extra[512];
    fields(extra,sizeof extra,r,result == CHAOS_OK ? CHAOS_STATUS_ACCEPTED : CHAOS_STATUS_REJECTED,
        result == CHAOS_OK && r->duration ? c->turn+r->duration : 0);
    (void)event(io,s,c,1,"ack","result",chaos_reason(result),extra);
}
void chaos_io_expire(struct chaos_io *io, struct chaos_state *s, const struct chaos_context *c) {
    int i, mask=0;
    for(i=1;i<CHAOS_KINDS;++i)
        if(s->effects[i].value && c->turn >= s->effects[i].expires) mask |= 1<<i;
    chaos_expire(s,c->turn);
    for(i=1;i<CHAOS_KINDS;++i)
        if(mask & (1<<i)) (void)chaos_io_event(io,s,c,"expiry","result",chaos_name(i));
}
void chaos_io_safe(struct chaos_io *io, struct chaos_state *s, const struct chaos_context *c,
                   const char *why, chaos_telegraph_fn show, void *arg) {
    int fd, result;
    ssize_t n;
    size_t used=0;
    char data[CHAOS_MAX_REQUEST+1], extra[512], log[1024];
    struct chaos_request r;
    struct chaos_state next;
    if(io->busy || io->dir < 0 || io->failed || s->safe >= CHAOS_MAX_COUNTER) return;
    io->busy=1;
    chaos_io_expire(io,s,c);
    ++s->safe;
    if(!chaos_io_event(io,s,c,"safe_point","result",why)) goto out;
    fd=regular(io->dir,"whisper.json",O_RDONLY);
    if(fd < 0) goto out;
    do {
        n=read(fd,data+used,sizeof data-used);
        if(n < 0 && errno == EINTR) continue;
        if(n <= 0) break;
        used+=(size_t)n;
    } while(used < sizeof data);
    close(fd);
    if(n < 0) goto out;
    result=chaos_parse(data,used,&r);
    if(result != CHAOS_OK) {
        memset(&r,0,sizeof r); r.kind=-1;
        ack(io,s,c,&r,result); goto out;
    }
    next=*s;
    result=chaos_admit(&next,&r,c->turn,c->sanity,c->eligible);
    if(result == CHAOS_FUTURE) goto out;
    if(result != CHAOS_OK) { s->last_id=next.last_id; ack(io,s,c,&r,result); goto out; }
    /* Targeted valid requests consume their ID even if logging/UI fails. */
    s->last_id=next.last_id;
    fields(extra,sizeof extra,&r,CHAOS_STATUS_ADMITTED,r.duration ? c->turn+r.duration : 0);
    snprintf(log,sizeof log,CHAOS_JOURNAL_FORMAT,c->turn,s->safe,extra);
    if(!append(io,io->journal,log) ||
       !chaos_io_event(io,s,c,"telegraph","result",chaos_name(r.kind))) goto out;
    if(!show || !show(arg,r.telegraph,r.kind == CHAOS_AMBIENT ? r.value : 0)) {
        ack(io,s,c,&r,CHAOS_LOG_FAILURE); goto out;
    }
    next.seq=s->seq; /* preserve telegraph's sequence, emitted before commit */
    *s=next;
    ack(io,s,c,&r,CHAOS_OK);
out:
    io->busy=0;
}
