/* NetHack General Public License. Post-mortem reveal core: read-only, no RNG.
 * Facts come only from engine-owned records: the admitted journal, the event
 * log's acknowledgement/expiry/curio/haunting rows, and host-copied engine
 * state. A candidate is an entry only after the engine's own final admission
 * record; everything refused is one count and is never narrated. */
#ifndef CHAOS_REVEAL_H
#define CHAOS_REVEAL_H
#include <stddef.h>

#define CHAOS_REVEAL_MAX 64
#define CHAOS_REVEAL_JOURNAL 256
#define CHAOS_REVEAL_LINE 4096
#define CHAOS_REVEAL_BYTES_MAX (16L * 1024L * 1024L)
#define CHAOS_REVEAL_TEXT 200

enum chaos_reveal_kind {
    CHAOS_REVEAL_WHISPER = 1,
    CHAOS_REVEAL_CURIO,
    CHAOS_REVEAL_HAUNT,
    CHAOS_REVEAL_NEXT_USE
};
enum chaos_reveal_placement {
    CHAOS_REVEAL_UNPLACED = 0,
    CHAOS_REVEAL_PLACED,
    CHAOS_REVEAL_NO_ROOM,
    CHAOS_REVEAL_PLACE_FAILED
};

struct chaos_reveal_entry {
    int kind, id, mutation, value, duration, telegraph, cost;
    long turn, expires, end_turn;
    int ended;                   /* an engine expiry/expired row exists */
    char why[24];                /* safe-point reason (whispers) */
    int steps;                   /* haunt: scripted steps committed in view */
    int uses, actual;            /* curio: application receipts, Sanity sum */
    int placement;
    long placed_turn;
};

/* Engine-state facts copied by the game host; text is engine-owned wording. */
struct chaos_reveal_host {
    int haunt_active;            /* u.haunt still active at the end */
    long haunt_until;
    int curio_charges, curio_placed;
    int next_use;                /* an installed next-use program exists */
    int next_use_delivered;      /* engine publication record (witnessed) */
    long next_use_turn;
    char next_use_origin[CHAOS_REVEAL_TEXT];
    char next_use_telegraph[CHAOS_REVEAL_TEXT];
    char next_use_effect[CHAOS_REVEAL_TEXT];
    char next_use_ended[CHAOS_REVEAL_TEXT];
};

struct chaos_reveal {
    int count, overflow, rejected, admitted, delivered, spent;
    int truncated;               /* a record file exceeded the read bound */
    long final_turn;
    struct chaos_reveal_entry e[CHAOS_REVEAL_MAX];
    struct chaos_reveal_host host;
    /* parser scratch */
    char last_why[24];
    int journal_count;
    struct { int id, mutation; long turn, safe; } journal[CHAOS_REVEAL_JOURNAL];
};

typedef void (*chaos_reveal_emit)(void *, const char *);

void chaos_reveal_init(struct chaos_reveal *, long final_turn, int spent);
/* Parse one engine-written row; exposed for bounded file reading and tests. */
void chaos_reveal_journal_line(struct chaos_reveal *, const char *);
void chaos_reveal_event_line(struct chaos_reveal *, const char *);
/* Read whispers.jsonl then events.jsonl from an open run directory fd. */
int chaos_reveal_read(struct chaos_reveal *, int dir);
/* Apply host facts, order chronologically and compute the tallies. */
void chaos_reveal_finish(struct chaos_reveal *);
void chaos_reveal_render(const struct chaos_reveal *, chaos_reveal_emit, void *);
/* ":chaos_admitted=..." suffix, or "" when nothing was admitted. */
int chaos_reveal_xlog_fields(const struct chaos_reveal *, char *, size_t);
#endif
