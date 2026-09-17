/* NGPL: actual linked-engine lifecycle with absent or failed transport. */
#define _GNU_SOURCE
#include "hack.h"
#include "chaos.h"
#include "chaos_haunt.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "chaos_shadow.h"
#include "native_rng.h"
#include <fcntl.h>
#include <errno.h>
#include <stdarg.h>

/* Caller-accounting isolation: trial outcomes/faults are controlled, not
 * evidence of real shadow acceptance. Successful parent creation is native. */
extern int n_dgns;
static const char *mode;
static int spends, spawns, warnings, trials, initial_spent, used_fd=-1, report_fd=-1;
static int ismode(const char *s) { return mode && !strcmp(mode,s); }
int __real_chaos_spend_non_effect(struct chaos_state *,int,int) __attribute__((weak));
int __wrap_chaos_spend_non_effect(struct chaos_state *s,int sanity,int who) {
 assert(s!=&u.chaos && who==CHAOS_SPEND_HAUNT); ++spends;
 assert(__real_chaos_spend_non_effect);
 return __real_chaos_spend_non_effect(s,sanity,who);
}
static void unchanged(struct chaos_state before) {
 before.seq=u.chaos.seq;
 assert(!memcmp(&before,&u.chaos,sizeof before));
}
/* pline is intentionally quiet, but must never conceal engine diagnostics.
 * Keep the real paniclog evidence, then fail even if logging itself failed. */
void __real_paniclog(const char *,const char *);
void __wrap_paniclog(const char *type,const char *reason) {
 __real_paniclog(type,reason);
 fprintf(stderr,"unexpected engine diagnostic: %s: %s\n",type,reason);
 fflush(stdout);fflush(stderr);exit(86);
}
void __wrap_pline(const char *fmt,...) {
 struct chaos_state before=u.chaos;
 if(mode && strstr(fmt,"learned the rhythm")) {
  ++warnings; assert(u.chaos.spent==initial_spent);
  if(ismode("hooks")) chaos_event("read","attempt","");
 }
 unchanged(before);
}
struct monst *__real_makemon(struct permonst *,int,int,int);
struct monst *__wrap_makemon(struct permonst *p,int x,int y,int fl) {
 struct chaos_state before=u.chaos; struct monst *m;
 ++spawns; assert(u.chaos.spent==initial_spent);
 if(ismode("spawnfail")) return NULL;
 m=__real_makemon(p,x,y,fl);
 unchanged(before);
 if(ismode("hooks")) chaos_event("read","attempt","");
 return m;
}
int __wrap_chaos_shadow_run(void (*fn)(void *,struct chaos_shadow_report *),void *arg,struct chaos_shadow_report *r) {
 (void)fn;(void)arg;++trials;memset(r,0,sizeof *r);
 r->ok=!ismode("rejected");r->steps=64;r->moved=1;r->escaped=1;
 return !ismode("trialfail");
}
int __real_openat(int,const char *,int,...);
int __wrap_openat(int dir,const char *name,int fl,...) {
 int fd;
 if((ismode("usedfail") && !strcmp(name,"haunting-used.lua")) ||
    (ismode("reportfail") && !strcmp(name,"dreamlands.json"))) {errno=EIO;return -1;}
 fd=(fl&O_CREAT)?__real_openat(dir,name,fl,0600):__real_openat(dir,name,fl);
 if(!strcmp(name,"haunting-used.lua"))used_fd=fd;
 if(!strcmp(name,"dreamlands.json"))report_fd=fd;
 return fd;
}
int __real_close(int);
int __wrap_close(int fd) {
 if(fd==used_fd)used_fd=-1;if(fd==report_fd)report_fd=-1;
 return __real_close(fd);
}
ssize_t __real_write(int,const void *,size_t);
ssize_t __wrap_write(int fd,const void *buf,size_t n) {
 if((ismode("usedwrite") && fd==used_fd) || (ismode("reportwrite") && fd==report_fd) ||
    (ismode("prefail") && memmem(buf,n,"pre_admitted",12)) ||
    (ismode("finalfail") && memmem(buf,n,"\"detail\":\"accepted\"",19))) {errno=EIO;return -1;}
 return __real_write(fd,buf,n);
}
static void quietglyph(winid w,XCHAR_P x,XCHAR_P y,int g) {(void)w;(void)x;(void)y;(void)g;}
static int admission(const char *which) {
 int x,y,dir,reach,success,count,next;long seq;struct chaos_state before;
 static char visible[ROWNO][COLNO],*rows[ROWNO];
 mode=which;test_rng_control();id_permonst();init_objects();init_gods();
 memset(&u,0,sizeof u);urace=races[str2race("human")];urole=roles[str2role("Wizard")];
 u.umonnum=u.umonster=PM_HUMAN;youmonst.data=&mons[PM_HUMAN];
 u.usanity=100;u.ux=10;u.uy=10;u.ulevel=1;u.uhp=u.uhpmax=20;
 /* Keep native creation out of the otherwise zero-initialized quest. */
 n_dgns=2;dungeons[1].depth_start=1;dungeons[1].num_dunlevs=20;
 u.uz.dnum=1;u.uz.dlevel=1;moves=10;flags.ident=1;
 windowprocs.win_print_glyph=quietglyph;
 for(y=0;y<ROWNO;++y){rows[y]=visible[y];for(x=1;x<COLNO;++x){levl[x][y].typ=ROOM;visible[y][x]=IN_SIGHT|COULD_SEE;}}
 viz_array=rows;chaos_state_init(&u.chaos);chaos_start();
 initial_spent=ismode("budget")?1:0;u.chaos.spent=initial_spent;
 if(ismode("invalid"))u.chaos.reserved=1;
 u.haunt.count=4;u.haunt.backtracks=1;u.haunt.last_turn=moves;
 u.haunt.dnum=1;u.haunt.dlevel=1;
 for(x=0;x<4;++x){u.haunt.history[x].x=10;u.haunt.history[x].y=10;}
 dir=open(getenv("NYARLATHACK_RUN_DIR"),O_RDONLY|O_DIRECTORY);assert(dir>=0);
 before=u.chaos;test_rng_reset();chaos_haunt_tick(dir);
 count=reseed_count;next=rn2(100000);
 reach=ismode("valid")||ismode("hooks")||ismode("spawnfail")||ismode("finalfail");
 success=reach&&!ismode("spawnfail");
 assert(spawns==reach && warnings==reach);
 assert(trials==!(ismode("budget")||ismode("invalid")||ismode("source")||ismode("absent")||ismode("usedfail")||ismode("usedwrite")));
#ifndef HAUNT_BASELINE
 assert(spends==reach);
#endif
 assert(u.chaos.spent==initial_spent+2*success);
 assert(u.haunt.active==success);
 if(success)assert(u.haunt.target && u.haunt.until==moves+60);
 before.spent=u.chaos.spent;unchanged(before);
 seq=u.chaos.seq;chaos_haunt_tick(dir);
 assert(u.chaos.spent==initial_spent+2*success && spawns==reach);
 assert(u.chaos.seq==seq);
 printf("mode=%s spent=%d spawns=%d trials=%d rng_count=%d next_draw=%d seq=%ld\n",mode,u.chaos.spent,spawns,trials,count,next,seq);
 close(dir);return 0;
}
int main(int argc,char **argv) {
 struct monst m;struct stat target,opened;int fd,closed=0;
 /* Every process runs in its own diagnostic directory; never use a game prefix. */
 fqn_prefix[TROUBLEPREFIX]="./";
 if(argc==2 && !strcmp(argv[1],"--diagnostic-impossible")) {
  impossible("haunt lifecycle diagnostic negative control: impossible");
  puts("diagnostic escaped");return 0;
 }
 if(argc==2 && !strcmp(argv[1],"--diagnostic-paniclog")) {
  paniclog("paniclog","haunt lifecycle diagnostic negative control: paniclog");
  puts("diagnostic escaped");return 0;
 }
 if(argc==3 && !strcmp(argv[1],"--admission"))return admission(argv[2]);
 memset(&u,0,sizeof u);init_gods();
 urace.malenum=PM_HUMAN;urole.malenum=PM_WIZARD;
 u.umonnum=u.umonster=PM_HUMAN;youmonst.data=&mons[PM_HUMAN];
 u.usanity=80;u.ux=5;u.uy=5;u.ulevel=1;u.uhp=u.uhpmax=20;
 u.uz.dnum=0;u.uz.dlevel=1;moves=10;
 chaos_state_init(&u.chaos); /* state exists, as on restore */
 u.haunt.active=u.haunt.checked=1;u.haunt.target=42;
 u.haunt.until=80;u.haunt.last_turn=10;u.haunt.dnum=0;u.haunt.dlevel=1;
 u.haunt.count=1;u.haunt.history[0].x=5;u.haunt.history[0].y=5;u.haunt.state=7;
 strcpy(u.haunt.source,"return function(c) return {dx=0,dy=0,state=c.state+1} end");
 u.haunt.source_len=strlen(u.haunt.source);assert(chaos_haunt_valid(&u.haunt));
 chaos_start();
 if(argc==2) {
  assert(!stat(argv[1],&target));
  for(fd=3;fd<128;++fd)if(!fstat(fd,&opened) && target.st_dev==opened.st_dev && target.st_ino==opened.st_ino) {
   close(fd);++closed;
  }
  assert(closed==1); /* fault only this fixture's real event descriptor */
  assert(!chaos_event_checked("read","attempt",""));
 }
 memset(&m,0,sizeof m);m.m_id=42;m.mtyp=PM_JACKAL;m.data=&mons[PM_JACKAL];m.mx=4;m.my=5;
 u.ux=6;moves=11;chaos_observe();
 printf("last_turn=%ld history_x=%d player_x=%d\n",u.haunt.last_turn,u.haunt.history[u.haunt.count-1].x,u.ux);fflush(stdout);
 assert(u.haunt.last_turn==11 && u.haunt.history[u.haunt.count-1].x==6);
 assert(u.haunt.active && chaos_haunt_pick(&m,NULL,0)==-1 && u.haunt.state==8);
 u.uz.dlevel=2;moves=12;chaos_observe();assert(!u.haunt.active);
 u.uz.dlevel=1;moves=13;chaos_observe();
 assert(!u.haunt.active && chaos_haunt_pick(&m,NULL,0)==-2 && u.haunt.state==8);
 u.haunt.active=1;u.haunt.until=14;moves=14;chaos_observe();assert(!u.haunt.active);
 puts("history maintained; level expiry permanent; deadline maintained");
 return 0;
}
