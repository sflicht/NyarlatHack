/* Test-only clock/seed control for comparing unmodified stock and fork. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdlib.h>
#include <time.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
/* dNetHack also draws fresh entropy to schedule periodic reseeding. */
FILE *fopen(const char *path, const char *mode) {
    static uint32_t state=987654321U;
    static uint32_t entropy[2];
    if (!strcmp(path,"/dev/urandom")) {
        for (int i=0;i<2;i++) { state^=state<<13; state^=state>>17; state^=state<<5; entropy[i]=state; }
        return fmemopen(entropy,sizeof entropy,"r");
    }
    FILE *(*real)(const char*,const char*)=dlsym(RTLD_NEXT,"fopen");
    return real(path,mode);
}
time_t time(time_t *out) { time_t t = 1700000000; if (out) *out=t; return t; }
void srand(unsigned int ignored) { void (*real)(unsigned int)=dlsym(RTLD_NEXT,"srand"); (void)ignored; real(1234567U); }
void srandom(unsigned int ignored) { void (*real)(unsigned int)=dlsym(RTLD_NEXT,"srandom"); (void)ignored; real(7654321U); }
