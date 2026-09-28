/* NGPL: #190 escape room. The real haunt tick and the real forked shadow
 * trial (nothing wrapped) in a lit W x H room enclosed by solid rock.
 *
 *   haunt_room W H PX PY SEED [TICKS]
 *
 * PX,PY are the player's 0-based offsets inside the room. SEED seeds the
 * native RNG the forked trial inherits. The tick is called TICKS times (default
 * 1). Prints one line: the room, whether the trial was spent (checked) and the
 * RNG draws the parent made. NYARLATHACK_RUN_DIR holds haunting.lua and
 * receives haunting-used.lua/dreamlands.json exactly as in play. */
#define _GNU_SOURCE
#include "hack.h"
#include "chaos.h"
#include "chaos_haunt.h"
#include "mfndpos.h"
#include <assert.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "native_rng.h"

extern int n_dgns;
/* Linked with -Wl,--wrap=pline: there is no terminal. The telegraph is counted. */
static int telegraphs;
void __wrap_pline(const char *fmt,...) {if(strstr(fmt,"learned the rhythm"))++telegraphs;}
static void quietglyph(winid w,XCHAR_P x,XCHAR_P y,int g){(void)w;(void)x;(void)y;(void)g;}
static char visible[ROWNO][COLNO],*rows[ROWNO];

/* Solid rock everywhere, one lit room of floor at (X0,Y0). */
#define X0 20
#define Y0 5
static void room(int w,int h) {
 int x,y;
 for(y=0;y<ROWNO;++y){rows[y]=visible[y];for(x=0;x<COLNO;++x){levl[x][y].typ=STONE;levl[x][y].lit=0;visible[y][x]=0;}}
 for(y=Y0-1;y<=Y0+h;++y)for(x=X0-1;x<=X0+w;++x) {
  levl[x][y].typ=(y==Y0-1||y==Y0+h)?HWALL:(x==X0-1||x==X0+w)?VWALL:ROOM;
  levl[x][y].lit=1;visible[y][x]=IN_SIGHT|COULD_SEE;
 }
 viz_array=rows;
}
/* HAUNT_ROOM_MAP=file: a recorded map instead of the W x H room. One text row
 * per level row from y=0, column x = level x. Glyphs: ' ' rock, '.' floor,
 * '#' corridor, '-' '|' walls, 'D' doorless doorway, 'O' open door, '+'
 * closed door, '~' pool, '{' fountain, '<' stairs, 'S' sink, '^' trap,
 * '@' the player (on floor), 'd' the pet (on floor). Every non-rock square
 * is lit and in sight. */
static int mapped(const char *path,int *px,int *py,int *qx,int *qy) {
 FILE *f=fopen(path,"r");char line[COLNO+4];int x,y=0,c;
 assert(f);*px=*py=*qx=*qy=-1;
 for(y=0;y<ROWNO;++y){rows[y]=visible[y];for(x=0;x<COLNO;++x){levl[x][y].typ=STONE;levl[x][y].lit=0;visible[y][x]=0;}}
 for(y=0;y<ROWNO && fgets(line,sizeof line,f);++y)for(x=1;x<COLNO && line[x] && line[x]!='\n';++x) {
  struct rm *l=&levl[x][y];c=line[x];
  if(c==' ')continue;
  l->lit=1;visible[y][x]=IN_SIGHT|COULD_SEE;
  switch(c) {
  case '.':l->typ=ROOM;break;
  case '@':l->typ=ROOM;*px=x;*py=y;break;
  case 'd':l->typ=ROOM;*qx=x;*qy=y;break;
  case '#':l->typ=CORR;break;
  case '-':l->typ=HWALL;break;
  case '|':l->typ=VWALL;break;
  case 'D':l->typ=DOOR;l->doormask=D_NODOOR;break;
  case 'O':l->typ=DOOR;l->doormask=D_ISOPEN;break;
  case '+':l->typ=DOOR;l->doormask=D_CLOSED;break;
  case '~':l->typ=POOL;break;
  case '{':l->typ=FOUNTAIN;break;
  case '<':l->typ=STAIRS;break;
  case 'S':l->typ=SINK;break;
  case '^':l->typ=ROOM;(void)maketrap(x,y,SQKY_BOARD);break;
  default:fprintf(stderr,"bad map glyph %c\n",c);exit(2);
  }
 }
 fclose(f);viz_array=rows;
 assert(*px>0);return 1;
}
int main(int argc,char **argv) {
 int w,h,px,py,seed,ticks=1,dir,i,count,qx=-1,qy=-1;long seq;const char *map=getenv("HAUNT_ROOM_MAP");
 if(argc!=6 && argc!=7){fprintf(stderr,"usage: haunt_room W H PX PY SEED [TICKS]\n");return 2;}
 w=atoi(argv[1]);h=atoi(argv[2]);px=atoi(argv[3]);py=atoi(argv[4]);seed=atoi(argv[5]);
 if(argc==7)ticks=atoi(argv[6]);
 assert(w>=1 && h>=1 && w<=40 && h<=12 && ticks>=1 && (map || (px>=0 && px<w && py>=0 && py<h)));
 fqn_prefix[TROUBLEPREFIX]="./";
 test_rng_control();id_permonst();init_objects();init_gods();init_artifacts();
 memset(&u,0,sizeof u);urace=races[str2race("human")];urole=roles[str2role("Bard")];
 u.umonnum=u.umonster=PM_HUMAN;youmonst.data=&mons[PM_HUMAN];
 u.usanity=100;u.ulevel=1;u.uhp=u.uhpmax=14;
 n_dgns=2;dungeons[1].depth_start=1;dungeons[1].num_dunlevs=20;
 u.uz.dnum=1;u.uz.dlevel=1;moves=monstermoves=10;flags.ident=1;
 windowprocs.win_print_glyph=quietglyph;
 vision_init();
 if(map){(void)mapped(map,&px,&py,&qx,&qy);u.ux=px;u.uy=py;}
 else{room(w,h);u.ux=X0+px;u.uy=Y0+py;}
 /* Real line-of-sight tables for monster-to-monster checks (clear_path);
  * the player's view stays the fixed lit room above. */
 vision_reset();viz_array=rows;
 if(qx>0) {
  struct monst *pet;test_rng_reset();
  pet=makemon(&mons[PM_LITTLE_DOG],qx,qy,MM_NOGROUP|MM_NOWAIT|NO_MINVENT|MM_EDOG);
  assert(pet);initedog(pet);
 }
 /* Optional furniture, as in a real start room: an up staircase (not
  * simple_floor) and the starting pet, at 0-based room offsets. */
 if(getenv("HAUNT_ROOM_STAIRS")) {
  int sx,sy;assert(sscanf(getenv("HAUNT_ROOM_STAIRS"),"%d,%d",&sx,&sy)==2 && sx>=0 && sx<w && sy>=0 && sy<h);
  levl[X0+sx][Y0+sy].typ=STAIRS;
 }
 if(getenv("HAUNT_ROOM_DOOR")) {
  /* A doorless doorway in the room's wall: offsets -1 or w (x), -1 or h (y). */
  int dx,dy;assert(sscanf(getenv("HAUNT_ROOM_DOOR"),"%d,%d",&dx,&dy)==2 && dx>=-1 && dx<=w && dy>=-1 && dy<=h &&
                   (dx==-1 || dx==w || dy==-1 || dy==h));
  levl[X0+dx][Y0+dy].typ=DOOR;levl[X0+dx][Y0+dy].doormask=D_NODOOR;
  vision_reset();viz_array=rows;
 }
 if(getenv("HAUNT_ROOM_PET")) {
  int qx,qy;struct monst *pet;
  assert(sscanf(getenv("HAUNT_ROOM_PET"),"%d,%d",&qx,&qy)==2 && qx>=0 && qx<w && qy>=0 && qy<h);
  test_rng_reset();
  pet=makemon(&mons[PM_LITTLE_DOG],X0+qx,Y0+qy,MM_NOGROUP|MM_NOWAIT|NO_MINVENT|MM_EDOG);
  assert(pet);initedog(pet);
 }
 if(getenv("HAUNT_ROOM_PICK")) {
  /* Direct handler check: an admitted hound at H, the footsteps trail aimed
   * at T (room offsets), one real chaos_haunt_pick over the game's own
   * mfndpos candidates. Prints the requested step and the chosen square. */
  int hx,hy,tx,ty,cnt,choice,fd,draw;struct monst *m;coord poss[9];long info[9];ssize_t n;
  assert(sscanf(getenv("HAUNT_ROOM_PICK"),"%d,%d,%d,%d",&hx,&hy,&tx,&ty)==4);
  hx+=X0;hy+=Y0;tx+=X0;ty+=Y0;
  test_rng_reset();
  m=makemon(&mons[PM_JACKAL],hx,hy,MM_NOGROUP|MM_NOWAIT|NO_MINVENT);assert(m && m->mx==hx && m->my==hy);
  setmangry(m);
  fd=open(getenv("HAUNT_ROOM_PACK"),O_RDONLY);assert(fd>=0);
  n=read(fd,u.haunt.source,CHAOS_LUA_SOURCE);close(fd);assert(n>0);u.haunt.source_len=(int)n;
  u.haunt.active=1;u.haunt.target=m->m_id;u.haunt.until=moves+60;u.haunt.dnum=1;u.haunt.dlevel=1;
  u.haunt.count=4;for(i=0;i<4;++i){u.haunt.history[i].x=tx;u.haunt.history[i].y=ty;}
  cnt=mfndpos(m,poss,info,ALLOW_U);
  draw=test_rng_begin();
  choice=chaos_haunt_pick(m,(struct nhcoord *)poss,cnt);
  test_rng_unchanged(draw);
  printf("pick hound=%d,%d target=%d,%d cands=%d choice=%d square=%d,%d adjacent=%d\n",
         hx-X0,hy-Y0,tx-X0,ty-Y0,cnt,choice,choice>=0?poss[choice].x-X0:-1,choice>=0?poss[choice].y-Y0:-1,
         choice>=0 && distmin(poss[choice].x,poss[choice].y,u.ux,u.uy)<=1);
  return 0;
 }
 chaos_state_init(&u.chaos);u.chaos.safe=1;
 chaos_start();
 /* Paced: a remembered backtrack and a four-square trail at the player. */
 u.haunt.count=4;u.haunt.backtracks=1;u.haunt.last_turn=moves;u.haunt.dnum=1;u.haunt.dlevel=1;
 for(i=0;i<4;++i){u.haunt.history[i].x=u.ux;u.haunt.history[i].y=u.uy;}
 dir=open(getenv("NYARLATHACK_RUN_DIR"),O_RDONLY|O_DIRECTORY);assert(dir>=0);
 reseed_period=INT_MAX;reseed_count=0;srandom((unsigned)seed);
 seq=u.chaos.seq;
 for(i=0;i<ticks;++i){chaos_haunt_tick(dir);u.haunt.last_turn=moves;}
 count=reseed_count;
 printf("room=%dx%d at=%d,%d seed=%d checked=%d active=%d spent=%d telegraphs=%d events=%ld rng=%d\n",
        w,h,px,py,seed,u.haunt.checked,u.haunt.active,u.chaos.spent,telegraphs,u.chaos.seq-seq,count);
 close(dir);return 0;
}
