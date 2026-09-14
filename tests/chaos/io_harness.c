/* NGPL: exercise production transport and rule admission, without game globals. */
#include "chaos_io.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct fixture { struct chaos_io io; struct chaos_state s; struct chaos_context c; int messages; const char *mode; };
static int show(void *arg, int telegraph, int ambient) {
    struct fixture *f = arg;
    assert(f->s.spent == (!strcmp(f->mode,"poor") ? 12 : 0));
    assert(telegraph >= 1 && telegraph <= 3); (void)ambient;
    ++f->messages;
    if(!strcmp(f->mode,"reentrant")) chaos_io_safe(&f->io,&f->s,&f->c,"pray",show,f);
    return strcmp(f->mode,"fail_ui") != 0;
}
int main(int argc, char **argv) {
    struct fixture f;
    FILE *save;
    assert(argc == 3); memset(&f,0,sizeof f); f.mode=argv[2];
    chaos_state_init(&f.s); f.c.turn=10; f.c.sanity=0; f.c.insight=0; f.c.eligible=1;
    if(!strcmp(f.mode,"poor")) f.s.spent=12;
    if(!strcmp(f.mode,"ineligible")) f.c.eligible=0;
    if(!strcmp(f.mode,"nonfood")) f.c.eligible=2;
    chaos_io_open(&f.io,argv[1]);
    chaos_io_safe(&f.io,&f.s,&f.c,"level_enter",show,&f);
    if(!strcmp(f.mode,"restore")) {
        save=tmpfile(); assert(save);
        assert(fwrite(&f.s,sizeof f.s,1,save)==1); rewind(save);
        memset(&f.s,0,sizeof f.s); assert(fread(&f.s,sizeof f.s,1,save)==1); fclose(save);
        assert(chaos_state_valid(&f.s));
    }
    if(!strcmp(f.mode,"expire")) f.c.turn=11;
    chaos_io_safe(&f.io,&f.s,&f.c,"pray",show,&f);
    chaos_io_close(&f.io);
    printf("{\"spent\":%d,\"reserved\":%d,\"last_id\":%d,\"ward\":%d,\"hunger\":%d,\"telegraphs\":%d,\"safe\":%ld}\n",
        f.s.spent,f.s.reserved,f.s.last_id,chaos_rule(&f.s,CHAOS_WARD,f.c.turn,3),
        chaos_rule(&f.s,CHAOS_HUNGER,f.c.turn,3),f.messages,f.s.safe);
    return 0;
}
