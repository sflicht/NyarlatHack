/* ENGINE-UNIT: real intent/context hash path; not gameplay. */
#include "hack.h"
#include "chaos_next_use.h"
#include "chaos_next_use_runtime.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

long moves;
long monstermoves;
boolean panicking;

void panic(const char *str, ...)
{
    va_list args;
    va_start(args, str);
    fputs(" ERROR:  ", stderr);
    vfprintf(stderr, str, args);
    fputc('\n', stderr);
    va_end(args);
    abort();
}

int chaos_next_use_test_hash_intent(const struct chaos_next_use_intent *,
                                    char [65]);
int chaos_next_use_test_hash_context(const struct chaos_next_use_context *,
                                     char [65]);
int chaos_next_use_test_format_intent(const struct chaos_next_use_intent *,
                                      char *, size_t);

static int op_from_name(const char *name)
{
    if (!strcmp(name, "quiet")) return CHAOS_NEXT_USE_INTENT_QUIET;
    if (!strcmp(name, "delay")) return CHAOS_NEXT_USE_INTENT_DELAY;
    if (!strcmp(name, "whistle_attention"))
        return CHAOS_NEXT_USE_INTENT_WHISTLE_ATTENTION;
    if (!strcmp(name, "fountain_refresh"))
        return CHAOS_NEXT_USE_INTENT_FOUNTAIN_REFRESH;
    return -1;
}

int main(int argc, char **argv)
{
    char digest[65];
    int ok;
    if (argc < 2) return 2;
    memset(digest, 'X', 64);
    digest[64] = '\0';
    if (!strcmp(argv[1], "hash-intent")) {
        struct chaos_next_use_intent intent;
        if (argc != 4) return 2;
        memset(&intent, 0, sizeof intent);
        intent.op = op_from_name(argv[2]);
        intent.state = atoi(argv[3]);
        ok = chaos_next_use_test_hash_intent(&intent, digest);
        printf("{\"ok\":%d,\"digest\":\"%s\"}\n", ok, digest);
        return 0;
    }
    if (!strcmp(argv[1], "fail-intent")) {
        struct chaos_next_use_intent intent;
        memset(&intent, 0, sizeof intent);
        intent.op = -1;
        intent.state = 0;
        ok = chaos_next_use_test_hash_intent(&intent, digest);
        printf("{\"ok\":%d,\"digest\":\"%s\"}\n", ok, digest);
        return 0;
    }
    if (!strcmp(argv[1], "hash-context")) {
        struct chaos_next_use_context context;
        if (argc != 10) return 2;
        memset(&context, 0, sizeof context);
        context.age = atoi(argv[2]);
        context.fountain_count = atoi(argv[3]);
        context.own_witnessed = atoi(argv[4]);
        if (strlen(argv[5]) != 64) return 2;
        memcpy(context.source_sha256, argv[5], 65);
        context.state = atoi(argv[6]);
        context.trigger = atoi(argv[7]);
        context.variant = atoi(argv[8]);
        context.whistle_count = atoi(argv[9]);
        ok = chaos_next_use_test_hash_context(&context, digest);
        printf("{\"ok\":%d,\"digest\":\"%s\"}\n", ok, digest);
        return 0;
    }
    if (!strcmp(argv[1], "parse-intent")) {
        struct chaos_next_use_intent intent;
        char *text = NULL;
        size_t n = 0;
        ssize_t r;
        int status;
        r = getline(&text, &n, stdin);
        if (r < 0) return 2;
        if (r > 0 && text[r - 1] == '\n') text[--r] = '\0';
        memset(&intent, 0, sizeof intent);
        status = chaos_next_use_parse_intent(text, (size_t)r, &intent);
        printf("{\"status\":%d,\"op\":%d,\"state\":%d}\n", status, intent.op,
               intent.state);
        free(text);
        return 0;
    }
    if (!strcmp(argv[1], "format-intent")) {
        struct chaos_next_use_intent intent;
        char out[128];
        size_t capacity;
        if (argc != 5) return 2;
        memset(&intent, 0, sizeof intent);
        intent.op = op_from_name(argv[2]);
        intent.state = atoi(argv[3]);
        capacity = (size_t)atoi(argv[4]);
        memset(out, 'Y', sizeof out);
        if (capacity > sizeof out) return 2;
        if (capacity) out[capacity - 1] = 'Y';
        ok = chaos_next_use_test_format_intent(&intent, out, capacity);
        printf("{\"ok\":%d,\"out\":\"%s\"}\n", ok, out);
        return 0;
    }
    return 2;
}
