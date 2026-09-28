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
int main(int argc,char **argv) {
 int w,h,px,py,seed,ticks=1,dir,i,count;long seq;
 if(argc!=6 && argc!=7){fprintf(stderr,"usage: haunt_room W H PX PY SEED [TICKS]\n");return 2;}
 w=atoi(argv[1]);h=atoi(argv[2]);px=atoi(argv[3]);py=atoi(argv[4]);seed=atoi(argv[5]);
 if(argc==7)ticks=atoi(argv[6]);
 assert(w>=1 && h>=1 && w<=40 && h<=12 && px>=0 && px<w && py>=0 && py<h && ticks>=1);
 fqn_prefix[TROUBLEPREFIX]="./";
 test_rng_control();id_permonst();init_objects();init_gods();init_artifacts();
 memset(&u,0,sizeof u);urace=races[str2race("human")];urole=roles[str2role("Bard")];
 u.umonnum=u.umonster=PM_HUMAN;youmonst.data=&mons[PM_HUMAN];
 u.usanity=100;u.ulevel=1;u.uhp=u.uhpmax=14;u.ux=X0+px;u.uy=Y0+py;
 n_dgns=2;dungeons[1].depth_start=1;dungeons[1].num_dunlevs=20;
 u.uz.dnum=1;u.uz.dlevel=1;moves=monstermoves=10;flags.ident=1;
 windowprocs.win_print_glyph=quietglyph;
 vision_init();room(w,h);
 /* Real line-of-sight tables for monster-to-monster checks (clear_path);
  * the player's view stays the fixed lit room above. */
 vision_reset();viz_array=rows;
 /* Optional furniture, as in a real start room: an up staircase (not
  * simple_floor) and the starting pet, at 0-based room offsets. */
 if(getenv("HAUNT_ROOM_STAIRS")) {
  int sx,sy;assert(sscanf(getenv("HAUNT_ROOM_STAIRS"),"%d,%d",&sx,&sy)==2 && sx>=0 && sx<w && sy>=0 && sy<h);
  levl[X0+sx][Y0+sy].typ=STAIRS;
 }
 if(getenv("HAUNT_ROOM_PET")) {
  int qx,qy;struct monst *pet;
  assert(sscanf(getenv("HAUNT_ROOM_PET"),"%d,%d",&qx,&qy)==2 && qx>=0 && qx<w && qy>=0 && qy<h);
  test_rng_reset();
  pet=makemon(&mons[PM_LITTLE_DOG],X0+qx,Y0+qy,MM_NOGROUP|MM_NOWAIT|NO_MINVENT|MM_EDOG);
  assert(pet);initedog(pet);
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
