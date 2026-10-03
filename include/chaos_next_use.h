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
    CHAOS_NEXT_USE_INTENT_FOUNTAIN_REFRESH,
    /* Ring (W effect v4): the whistle's note rings on in the player's head. */
    CHAOS_NEXT_USE_INTENT_WHISTLE_RING
};

/* Envelope W effect (next_use_program_v 4 key "w_effect"). Older envelopes
 * have no key and load as ATTENTION; a v4 envelope must name "ring". */
enum chaos_next_use_w_effect {
    CHAOS_NEXT_USE_W_EFFECT_ATTENTION = 0,
    CHAOS_NEXT_USE_W_EFFECT_RING = 1
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
    /* C (broad next-use): next_use_program_v 3 adds "uses", the most
     * effects the program may deliver. 0 for a v2 envelope. */
    int version;
    int uses;
    /* Ring: next_use_program_v 4 is v3 plus "w_effect":"ring"; 0 otherwise. */
    int w_effect;
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
/* Native save stream: 1 only after all decoded bytes, 0 on EOF/read error.
 * Shares the ZEROCOMP decoder with mread; never deletes or closes the save. */
#ifdef CHAOS
int chaos_next_use_mread(int fd, void *buf, unsigned int len);
#endif
long chaos_next_use_game_identity(void);
long chaos_next_use_pack_level(int dnum, int dlevel);
void chaos_next_use_identity_boundary(long run_token, long level_token);
const char *chaos_next_use_player_warning(const char *identifier);
/* Arc 1: recurrence telegraph identifiers (contract ids 5 W and 6 F). Shown
 * at admission, before the program's own telegraph, only for program 2+ of a
 * family an earlier closed program of this game delivered to the player. */
#define CHAOS_NEXT_USE_AGAIN_W "next-use-again-W"
#define CHAOS_NEXT_USE_AGAIN_F "next-use-again-F"
/* Recurrence repair (B). The envelope declares its program's ttl and the
 * engine validates it: program 1 always lives 100 native moves. Programs 2-3
 * live 100 under the pre-repair rules (a v3 ordinary-choice record, or any
 * game saved before the repair) or 300 under the repair, which also moves
 * their companion check from admission to the whistle. */
#define CHAOS_NEXT_USE_LIFETIME_FIRST 100
#define CHAOS_NEXT_USE_LIFETIME_LATER 300
#define CHAOS_NEXT_USE_LIFETIME_OK(ordinal, ttl) \
    ((ttl) == CHAOS_NEXT_USE_LIFETIME_FIRST \
     || ((ordinal) >= 2 && (ttl) == CHAOS_NEXT_USE_LIFETIME_LATER))
#define CHAOS_NEXT_USE_REPAIRED(ordinal, ttl) \
    ((ordinal) >= 2 && (ttl) == CHAOS_NEXT_USE_LIFETIME_LATER)
/* C (broad next-use). A next_use_program_v 3 envelope names one family and
 * declares "uses", the most effects (witnessed W, remapped F) the program may
 * deliver, 1..CHAOS_NEXT_USE_BROAD_USES_MAX, validated at load. The program
 * answers every use of that family (any whistle, tin or magic; any fountain
 * drink) on any level until it delivers "uses" effects, reaches
 * CHAOS_NEXT_USE_BROAD_CALLBACKS callbacks, or expires. The callback bound
 * keeps quiet and undelivered uses finite, and the runtime records bounded. */
#define CHAOS_NEXT_USE_BROAD_USES_MAX 2
#define CHAOS_NEXT_USE_BROAD_CALLBACKS 8
#define CHAOS_NEXT_USE_BROAD_W "next-use-v3-W"
#define CHAOS_NEXT_USE_BROAD_F "next-use-v3-F"
/* Ring (W effect). A next_use_program_v 4 envelope is a broad W program
 * (v3 rules) whose effect is "ring": at a valid whistle, if every public
 * guard passes, the engine prints the ring line and confuses the player for
 * CHAOS_NEXT_USE_RING_MOVES native moves, ended by the native message. Its
 * telegraph identifier is pinned to the effect at load. Telegraph contract
 * ids: 9 (single next whistle, registered, shown by no current program),
 * 10 (recurrence) and 11 (broad program line). */
#define CHAOS_NEXT_USE_RING_MOVES 5
#define CHAOS_NEXT_USE_RING_W "next-use-v4-Wr"
#define CHAOS_NEXT_USE_RING_NEXT_W "next-use-v2-Wr"
#define CHAOS_NEXT_USE_AGAIN_RING_W "next-use-again-Wr"

#endif
