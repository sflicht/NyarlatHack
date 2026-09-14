/* NetHack General Public License. Test the real Lua runtime. */
#include "chaos_lua.h"
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv) {
 char source[CHAOS_LUA_SOURCE+2]; size_t n=fread(source,1,sizeof source,stdin);
 struct chaos_lua_context c={0}; struct chaos_lua_intent r={0};
 c.mx=4;c.my=4;c.state=7;c.count=1;c.history[0].x=5;c.history[0].y=4;
 if(argc>1 && !strcmp(argv[1],"delay")){c.count=4;c.history[1].x=4;c.history[2].x=3;c.history[3].x=3;}
 int status=chaos_lua_step(source,n,&c,&r);
 if(argc>1 && !strcmp(argv[1],"repeat"))status=chaos_lua_step(source,n,&c,&r);
 printf("{\"status\":%d,\"dx\":%d,\"dy\":%d,\"state\":%d}\n",status,r.dx,r.dy,r.state);
 return 0;
}
