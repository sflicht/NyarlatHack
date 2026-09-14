/* NGPL: actual linked-engine lifecycle with absent or failed transport. */
#include "hack.h"
#include "chaos.h"
#include "chaos_haunt.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
int main(int argc,char **argv) {
 struct monst m;struct stat target,opened;int fd,closed=0;
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
