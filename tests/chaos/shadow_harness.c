/* NGPL test: child memory mutation and filesystem writes must not escape. */
#include "chaos_shadow.h"
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <string.h>
static void probe(void *v,struct chaos_shadow_report *r) {
 int *parent=v;*parent=999;
 int fd=open("/tmp/nyarl-shadow-must-not-create",O_WRONLY|O_CREAT,0600);
 r->ok=(fd<0);r->steps=64;
 if(fd>=0)close(fd);
}
static void loop(void *v,struct chaos_shadow_report *r) {(void)v;(void)r;for(;;){} }
int main(int argc,char **argv) {
 int value=7;struct chaos_shadow_report r={0};
 int ok=chaos_shadow_run(argc>1&&!strcmp(argv[1],"loop")?loop:probe,&value,&r);
 printf("%d %d %d %d\n",ok,value,r.ok,r.sandboxed);
 return 0;
}
