/* NetHack General Public License. Bounded next-use v2 value interface. */
#ifndef CHAOS_NEXT_USE_H
#define CHAOS_NEXT_USE_H

#include <stddef.h>

#define CHAOS_NEXT_USE_SOURCE_MAX 4096
#define CHAOS_NEXT_USE_RECORD_MAX 4096
#define CHAOS_NEXT_USE_CONTEXT_MAX 6144
#define CHAOS_NEXT_USE_ENVELOPE_MAX 8192
#define CHAOS_NEXT_USE_AUTHOR_MAX 8192
#define CHAOS_NEXT_USE_SHA256_BYTES 32
#define CHAOS_NEXT_USE_SHA256_HEX 64
#define CHAOS_NEXT_USE_RUN_HEX 64
#define CHAOS_NEXT_USE_LOGICAL_HEX 16

/* Parse/JCS failures are closed and stable. No input is repaired. */
enum chaos_next_use_error {
    CHAOS_NEXT_USE_OK = 0,
    CHAOS_NEXT_USE_NULL_ARGUMENT,
    CHAOS_NEXT_USE_LIMIT,
    CHAOS_NEXT_USE_UTF8,
    CHAOS_NEXT_USE_JSON,
    CHAOS_NEXT_USE_DUPLICATE_KEY,
    CHAOS_NEXT_USE_NONCHARACTER,
    CHAOS_NEXT_USE_IJSON,
    CHAOS_NEXT_USE_SCHEMA,
    CHAOS_NEXT_USE_VERSION,
    CHAOS_NEXT_USE_HASH,
    CHAOS_NEXT_USE_OUTPUT
};

enum chaos_next_use_family {
    CHAOS_NEXT_USE_FAMILY_W = 1,
    CHAOS_NEXT_USE_FAMILY_F = 2
};

enum chaos_next_use_intent_op {
    CHAOS_NEXT_USE_INTENT_QUIET = 0,
    CHAOS_NEXT_USE_INTENT_DELAY,
    CHAOS_NEXT_USE_INTENT_WHISTLE_ATTENTION,
    CHAOS_NEXT_USE_INTENT_FOUNTAIN_REFRESH
};

struct chaos_next_use_author {
    int abstain;
    size_t source_length;
    char source[CHAOS_NEXT_USE_SOURCE_MAX + 1];
};

struct chaos_next_use_origin_ref {
    int end_seq;
    char fact[18];
    int family;
    int level_dlevel;
    int level_dnum;
    int move;
    int notice_seq;
    int root;
    char run[CHAOS_NEXT_USE_RUN_HEX + 1];
};

struct chaos_next_use_envelope {
    int at;
    int cost;
    int id;
    int operation_count;
    int operations[2];
    struct chaos_next_use_origin_ref origin_refs[2];
    size_t source_length;
    char source[CHAOS_NEXT_USE_SOURCE_MAX + 1];
    char source_sha256[CHAOS_NEXT_USE_SHA256_HEX + 1];
    char telegraph[15];
    int ttl;
    int variant;
};

struct chaos_next_use_context {
    int age;
    int fountain_count;
    int own_witnessed;
    char source_sha256[CHAOS_NEXT_USE_SHA256_HEX + 1];
    int state;
    int trigger;
    int variant;
    int whistle_count;
};

struct chaos_next_use_intent {
    int op;
    int state;
};

int chaos_next_use_parse_author(const char *, size_t,
                                struct chaos_next_use_author *);
int chaos_next_use_parse_envelope(const char *, size_t,
                                  struct chaos_next_use_envelope *);
int chaos_next_use_parse_context(const char *, size_t,
                                 struct chaos_next_use_context *);
int chaos_next_use_parse_intent(const char *, size_t,
                                struct chaos_next_use_intent *);
int chaos_next_use_jcs(const char *, size_t, char *, size_t, size_t *);
int chaos_next_use_sha256(const void *, size_t,
                          unsigned char [CHAOS_NEXT_USE_SHA256_BYTES]);
int chaos_next_use_format_logical_id(unsigned long long,
                                     char [CHAOS_NEXT_USE_LOGICAL_HEX + 1]);

#endif
