/* NGPL test: child memory mutation and filesystem writes must not escape. */
#include "chaos_shadow.h"
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/wait.h>
static void probe(void *v,struct chaos_shadow_report *r) {
 int *parent=v;*parent=999;
 int fd=open("/tmp/nyarl-shadow-must-not-create",O_WRONLY|O_CREAT,0600);
 r->ok=(fd<0);r->steps=64;
 int net=socket(AF_INET,SOCK_STREAM,0);r->ok &= net<0;if(net>=0)close(net);
 pid_t child=fork();if(child==0)_exit(3);if(child>0)waitpid(child,NULL,0);r->ok &= child<0;
 for(int i=0;i<100;++i)(void)rand();
 if(fd>=0)close(fd);
}
static void loop(void *v,struct chaos_shadow_report *r) {(void)v;(void)r;for(;;){} }
int main(int argc,char **argv) {
 int value=7;struct chaos_shadow_report r={0};
 srand(123);int expected=rand();srand(123);
 int ok=chaos_shadow_run(argc>1&&!strcmp(argv[1],"loop")?loop:probe,&value,&r);
 printf("%d %d %d %d %d\n",ok,value,r.ok,r.sandboxed,rand()==expected);
 return 0;
}
