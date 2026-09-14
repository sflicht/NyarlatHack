/* NetHack General Public License. Linux/x86-64 fork sandbox: deny by default. */
#define _GNU_SOURCE
#include "chaos_shadow.h"
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stddef.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>
#if defined(__linux__) && defined(__x86_64__)
#include <linux/audit.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#define ALLOW(n) BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,(n),0,1),BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW)
#endif
static struct chaos_shadow_report *running;
int chaos_shadow_active(void) {return running!=NULL;}
static void finish_child(void) {
    if(running) (void)write(3,running,sizeof *running);
    _exit(0);
}
void chaos_shadow_end(int died) {
    if(running) {running->ok=0;running->died=!!died;finish_child();}
}
static int sandbox(void) {
#if defined(__linux__) && defined(__x86_64__)
    struct sock_filter filter[]={
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,arch)),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,AUDIT_ARCH_X86_64,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_KILL_PROCESS),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,nr)),
        /* writes only to private /dev/null stdout/stderr or the report pipe */
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,__NR_write,0,4),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,args[0])),
        BPF_JUMP(BPF_JMP|BPF_JGT|BPF_K,3,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ERRNO|EPERM),
        /* read-only opens permit the engine's periodic entropy reads */
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,__NR_openat,0,4),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,args[2])),
        BPF_JUMP(BPF_JMP|BPF_JSET|BPF_K,O_WRONLY|O_RDWR|O_CREAT|O_TRUNC,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ERRNO|EPERM),
        BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K,__NR_open,0,4),
        BPF_STMT(BPF_LD|BPF_W|BPF_ABS,offsetof(struct seccomp_data,args[1])),
        BPF_JUMP(BPF_JMP|BPF_JSET|BPF_K,O_WRONLY|O_RDWR|O_CREAT|O_TRUNC,1,0),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ALLOW),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ERRNO|EPERM),
        ALLOW(__NR_read),ALLOW(__NR_close),ALLOW(__NR_fstat),ALLOW(__NR_newfstatat),ALLOW(__NR_lseek),
        ALLOW(__NR_brk),ALLOW(__NR_mmap),ALLOW(__NR_munmap),ALLOW(__NR_mprotect),ALLOW(__NR_mremap),
        ALLOW(__NR_rt_sigaction),ALLOW(__NR_rt_sigprocmask),ALLOW(__NR_rt_sigreturn),
        ALLOW(__NR_clock_gettime),ALLOW(__NR_getpid),ALLOW(__NR_gettid),ALLOW(__NR_getuid),ALLOW(__NR_geteuid),
        ALLOW(__NR_futex),ALLOW(__NR_getrandom),ALLOW(__NR_exit),ALLOW(__NR_exit_group),
        BPF_STMT(BPF_RET|BPF_K,SECCOMP_RET_ERRNO|EPERM)
    };
    struct sock_fprog program={(unsigned short)(sizeof filter/sizeof filter[0]),filter};
    return !prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0) && !prctl(PR_SET_SECCOMP,SECCOMP_MODE_FILTER,&program);
#else
    return 0;
#endif
}
int chaos_shadow_run(void (*fn)(void *,struct chaos_shadow_report *),void *arg,struct chaos_shadow_report *out) {
    int fds[2],status=0;pid_t pid;ssize_t got=-1;
    memset(out,0,sizeof *out);
    if(running || pipe(fds))return 0;
    pid=fork();
    if(pid==0) {
        struct chaos_shadow_report report={0};struct rlimit cpu={1,1},memory={512UL*1024*1024,512UL*1024*1024};
        int nullfd=open("/dev/null",O_RDWR);
        if(nullfd<0)_exit(2);
        if(dup2(nullfd,0)<0 || dup2(nullfd,1)<0 || dup2(nullfd,2)<0 || dup2(fds[1],3)<0)_exit(2);
        /* No inherited live writable descriptor survives. */
#if defined(__linux__) && defined(__NR_close_range)
        if(syscall(__NR_close_range,4,~0U,0))_exit(2);
#else
        _exit(2);
#endif
        signal(SIGALRM,SIG_DFL);alarm(2);
        if(setrlimit(RLIMIT_CPU,&cpu) || setrlimit(RLIMIT_AS,&memory))_exit(2);
        running=&report;
        if(!sandbox())finish_child();
        report.sandboxed=1;
        fn(arg,&report);finish_child();
    }
    close(fds[1]);
    if(pid<0){close(fds[0]);return 0;}
    struct pollfd p={fds[0],POLLIN,0};
    if(poll(&p,1,2500)>0)got=read(fds[0],out,sizeof *out);
    close(fds[0]);
    if(got!=(ssize_t)sizeof *out)kill(pid,SIGKILL);
    while(waitpid(pid,&status,0)<0 && errno==EINTR){}
    return got==(ssize_t)sizeof *out && WIFEXITED(status) && WEXITSTATUS(status)==0 && out->sandboxed;
}
