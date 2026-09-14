/* NetHack General Public License. One bounded, opt-in delayed-footstep encounter. */
#define _POSIX_C_SOURCE 200809L
#include "hack.h"
#include "chaos.h"
#include "chaos_haunt.h"
#include "chaos_shadow.h"
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

static int pending_state, script_error, blocked_move;
static int simple_floor(int x,int y) {
 return isok(x,y) && (levl[x][y].typ==ROOM || levl[x][y].typ==CORR) && !t_at(x,y);
}
static void remember_position(void) {
 struct chaos_haunt_state *h=&u.haunt;int i;
 if(h->count==CHAOS_TRAIL) {
  memmove(h->history,h->history+1,(CHAOS_TRAIL-1)*sizeof h->history[0]);--h->count;
 }
 h->history[h->count].x=u.ux;h->history[h->count].y=u.uy;++h->count;
}
int chaos_haunt_valid(const struct chaos_haunt_state *h) {
 int i;
 if(h->checked<0 || h->checked>1 || h->active<0 || h->active>1 || h->state<0 || h->state>1000000 ||
    h->count<0 || h->count>CHAOS_TRAIL || h->source_len<0 || h->source_len>CHAOS_LUA_SOURCE ||
    h->echo_pending<0 || h->echo_pending>3 || h->echo_delivered<0 || h->echo_delivered>1 ||
    h->last_turn<0 || h->until<0 || h->source[h->source_len] ||
    (h->source_len && memchr(h->source,0,h->source_len)) || (h->active && (!h->target || !h->source_len)))return 0;
 for(i=0;i<h->count;++i)if(!isok(h->history[i].x,h->history[i].y))return 0;
 return 1;
}
int chaos_haunt_pick(struct monst *m,const struct nhcoord *poss,int count) {
 struct chaos_haunt_state *h=&u.haunt;
 struct chaos_lua_context c;struct chaos_lua_intent intent;int i,x,y;
 if(!h->active || m->m_id!=h->target || moves>=h->until ||
    u.uz.dnum!=h->dnum || u.uz.dlevel!=h->dlevel)return -2;
 if(m->mtyp!=PM_JACKAL || m->mtame || m->mpeaceful)return -2;
 memset(&c,0,sizeof c);c.mx=m->mx;c.my=m->my;c.state=h->state;c.count=h->count;
 memcpy(c.history,h->history,sizeof c.history);
 pending_state=h->state;
 if(chaos_lua_step(h->source,h->source_len,&c,&intent)) {++script_error;return -1;}
 if(!intent.dx && !intent.dy) {h->state=intent.state;return -1;}
 x=m->mx+intent.dx;y=m->my+intent.dy;
 /* Match the game's own legal candidates; never alter terrain, attack or teleport. */
 for(i=0;i<count;++i)if(poss[i].x==x && poss[i].y==y && simple_floor(x,y) &&
    !m_at(x,y) && (x!=u.ux || y!=u.uy)) {
  pending_state=intent.state;return i;
 }
 ++blocked_move;return -1;
}
void chaos_haunt_commit(struct monst *m) {
 if(u.haunt.active && m->m_id==u.haunt.target) {
  u.haunt.state=pending_state;
  if(!chaos_shadow_active() && canseemon(m))chaos_event("haunt_step","result","");
 }
}
/* Headless callbacks are installed only in the fork child. */
static void quietstr(winid w,int attr,const char *s){(void)w;(void)attr;(void)s;}
static void quietraw(const char *s){(void)s;}
static void quietwin(winid w){(void)w;}
static void quietdisplay(winid w,BOOLEAN_P b){(void)w;(void)b;}
static void quietcurs(winid w,int x,int y){(void)w;(void)x;(void)y;}
static void quietglyph(winid w,XCHAR_P x,XCHAR_P y,int g){(void)w;(void)x;(void)y;(void)g;}
static void quiet(void){}
static int cancelkey(void){return '\033';}
static char cancelyn(const char *q,const char *r,CHAR_P d){(void)q;(void)r;(void)d;return 'n';}
static void cancelline(const char *q,char *b){(void)q;b[0]='\033';b[1]=0;}
static int cancelmenu(winid w,int how,menu_item **p){(void)w;(void)how;*p=NULL;return 0;}
static void headless(void) {
 windowprocs.win_putstr=quietstr;windowprocs.win_raw_print=quietraw;windowprocs.win_raw_print_bold=quietraw;
 windowprocs.win_clear_nhwindow=quietwin;windowprocs.win_display_nhwindow=quietdisplay;
 windowprocs.win_curs=quietcurs;windowprocs.win_print_glyph=quietglyph;
 windowprocs.win_mark_synch=quiet;windowprocs.win_wait_synch=quiet;windowprocs.win_update_inventory=quiet;
 windowprocs.win_nhgetch=cancelkey;windowprocs.win_yn_function=cancelyn;windowprocs.win_getlin=cancelline;
 windowprocs.win_select_menu=cancelmenu;
 flags.pickup=FALSE;iflags.debug_fuzzer=TRUE;
}
struct trial_input {int x,y;};
static struct monst *spawn_hound(int x,int y) {
 struct monst *m=makemon(&mons[PM_JACKAL],x,y,MM_NOGROUP|MM_NOWAIT|NO_MINVENT);
 if(m) {setmangry(m);m=christen_monst(m,"echo hound");}
 return m;
}
static void trial(void *arg,struct chaos_shadow_report *r) {
 struct trial_input *a=arg;struct monst *m;int i,j,before,ox,oy,dx,dy,bx,by,best,score;
 headless();m=spawn_hound(a->x,a->y);
 if(!m || m->mtyp!=PM_JACKAL || m->mtame || m->mpeaceful)return;
 u.haunt.active=1;u.haunt.target=m->m_id;u.haunt.until=moves+65;
 script_error=blocked_move=0;
 for(i=0;i<64;++i) {
  /* Bounded evasive bot: one legal player step, one designated-monster action.
   * This is NOT a full turn-loop or a whole-dungeon safety proof. */
  bx=u.ux;by=u.uy;best=-1;
  for(j=0;j<8;++j) {
   static const int xs[8]={1,1,0,-1,-1,-1,0,1},ys[8]={0,1,1,1,0,-1,-1,-1};
   dx=xs[(j+i)%8];dy=ys[(j+i)%8];
   if(simple_floor(u.ux+dx,u.uy+dy) && !m_at(u.ux+dx,u.uy+dy) &&
      goodpos(u.ux+dx,u.uy+dy,&youmonst,0)) {
    score=dist2(u.ux+dx,u.uy+dy,m->mx,m->my);
    if(score>best){best=score;bx=u.ux+dx;by=u.uy+dy;}
   }
  }
  if(bx!=u.ux || by!=u.uy){u.dx=bx-u.ux;u.dy=by-u.uy;(void)domove();}
  ++moves;++monstermoves;remember_position();
  before=u.uhp;ox=m->mx;oy=m->my;
  (void)m_move(m,0);
  if(m->mx!=ox || m->my!=oy)++r->moved;
  if(distmin(u.ux,u.uy,m->mx,m->my)<=1){++r->contacts;(void)mattacku(m);}
  if(before-u.uhp>r->max_damage)r->max_damage=before-u.uhp;
  ++r->steps;r->blocked=blocked_move;r->script_errors=script_error;
  if(script_error)break;
  if(i>8 && distmin(u.ux,u.uy,m->mx,m->my)>=3)r->escaped=1;
 }
 r->ok=(r->steps==64 && r->moved>0 && r->escaped && !r->script_errors && r->max_damage<=4 && !r->died);
}
static int private_file(int dir,const char *name,int flags) {
 struct stat st;int fd=openat(dir,name,flags|O_NOFOLLOW|O_NONBLOCK,0600);
 if(fd<0)return -1;
 if(fstat(fd,&st) || !S_ISREG(st.st_mode) || st.st_uid!=getuid() || st.st_nlink!=1 || (st.st_mode&077)) {
  close(fd);return -1;
 }
 return fd;
}
static void recollect(void) {
 struct chaos_haunt_state *h=&u.haunt;int woke=h->was_asleep && !u.usleep;
 const char *disabled=getenv("NYARLATHACK_ECHOES");
 h->was_asleep=!!u.usleep;
 if(h->echo_pending && !h->echo_delivered && multi>=0 && (woke || u.usanity<=60 || u.uinsight>0) &&
    windowprocs.name && !strcmp(windowprocs.name,"tty")) {
  static const char *const echoes[]={"",
   "You recall footsteps on a path you never took.",
   "Something in your dream refuses to take shape.",
   "For a moment, you remember dying here."};
  if(!disabled || strcmp(disabled,"0"))tty_chaos_echo(echoes[h->echo_pending]);
  h->echo_delivered=1;
 }
}
void chaos_haunt_tick(int dir) {
 struct chaos_haunt_state *h=&u.haunt;int i,x,y,fd,found=0,back=0;ssize_t n;
 struct trial_input where={0,0};struct chaos_shadow_report report;char receipt[512];
 if(chaos_shadow_active())return;
 /* Admitted behavior and its lifecycle must not depend on transport health. */
 if(h->active && (moves>=h->until || h->dnum!=u.uz.dnum || h->dlevel!=u.uz.dlevel))h->active=0;
 if(h->last_turn!=moves) {
  if(h->dnum!=u.uz.dnum || h->dlevel!=u.uz.dlevel)h->count=0;
  if(h->count && (h->history[h->count-1].x!=u.ux || h->history[h->count-1].y!=u.uy))
   for(i=0;i<h->count-1;++i)if(h->history[i].x==u.ux && h->history[i].y==u.uy)back=1;
  h->dnum=u.uz.dnum;h->dlevel=u.uz.dlevel;h->last_turn=moves;
  remember_position();
  if(back){h->backtracks=1;chaos_event("backtrack","result","");}
 }
 recollect();
 if(dir<0 || h->checked || !h->backtracks || h->count<4 || chaos_budget(&u.chaos,u.usanity)<2 || multi<0)return;
 for(y=u.uy-5;y<=u.uy+5&&!found;++y)for(x=u.ux-5;x<=u.ux+5;++x)
  if(simple_floor(x,y) && cansee(x,y) && !m_at(x,y) && distmin(x,y,u.ux,u.uy)>=3 &&
     goodpos(x,y,NULL,0)){where.x=x;where.y=y;found=1;break;}
 if(!found)return;
 fd=private_file(dir,"haunting.lua",O_RDONLY);if(fd<0)return;
 n=read(fd,h->source,CHAOS_LUA_SOURCE+1);close(fd);
 if(n<1 || n>CHAOS_LUA_SOURCE || memchr(h->source,0,n)){
  memset(h->source,0,sizeof h->source);h->source_len=0;h->checked=1;
  chaos_event("haunting","result","source_rejected");return;
 }
 h->source[n]=0;h->source_len=(int)n;h->checked=1;
 fd=private_file(dir,"haunting-used.lua",O_WRONLY|O_CREAT|O_EXCL);
 if(fd<0)return;
 if(write(fd,h->source,n)!=n || fsync(fd)){close(fd);return;}close(fd);
 if(!chaos_shadow_run(trial,&where,&report)){chaos_event("haunting","result","shadow_failed");return;}
 snprintf(receipt,sizeof receipt,"{\"accepted\":%d,\"sandboxed\":%d,\"steps\":%d,\"moved\":%d,\"blocked\":%d,\"contacts\":%d,\"died\":%d,\"script_errors\":%d,\"escaped\":%d,\"max_damage\":%d}\n",
  report.ok,report.sandboxed,report.steps,report.moved,report.blocked,report.contacts,report.died,report.script_errors,report.escaped,report.max_damage);
 fd=private_file(dir,"dreamlands.json",O_WRONLY|O_CREAT|O_EXCL);
 if(fd<0)return;
 n=strlen(receipt);if(write(fd,receipt,n)!=n || fsync(fd)){close(fd);return;}close(fd);
 if(report.steps || report.died || report.script_errors)h->echo_pending=report.died?3:report.script_errors?2:1;
 if(report.ok) {
  struct monst *m;
  if(!chaos_event_checked("haunting","result","pre_admitted"))return;
  pline("Something has learned the rhythm of your footsteps.");
  m=spawn_hound(where.x,where.y);
  if(m){h->target=m->m_id;h->active=1;h->until=moves+60;u.chaos.spent+=2;chaos_event("haunting","result","accepted");}
  else chaos_event("haunting","result","spawn_failed");
 } else chaos_event("haunting","result","rejected");
 recollect();
}
