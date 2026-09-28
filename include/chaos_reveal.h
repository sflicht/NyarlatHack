/* NetHack General Public License. Post-mortem reveal core: read-only, no RNG.
 * Facts come only from engine-owned records: the admitted journal, the event
 * log's acknowledgement/expiry/curio/haunting/observation rows, the next-use
 * receipt, and host-copied engine state. A candidate is an entry only after
 * the engine's own final admission record; everything refused is one count
 * and is never narrated. */
#ifndef CHAOS_REVEAL_H
#define CHAOS_REVEAL_H
#include <stddef.h>

#define CHAOS_REVEAL_MAX 64
#define CHAOS_REVEAL_JOURNAL 256
#define CHAOS_REVEAL_ORIGINS 256
#define CHAOS_REVEAL_LINE 4096
#define CHAOS_REVEAL_BYTES_MAX (16L * 1024L * 1024L)

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

/* Mirrors of enum chaos_next_use_slot_w / _f (chaos_next_use_runtime.h). The
 * game host checks each value at compile time; this core stays free of the
 * game headers so it can be tested on its own. */
enum chaos_reveal_slot_w {
    CHAOS_REVEAL_W_UNDECLARED = 0,
    CHAOS_REVEAL_W_PENDING,
    CHAOS_REVEAL_W_CONSUMED_ARMED,
    CHAOS_REVEAL_W_CONSUMED_QUIET,
    CHAOS_REVEAL_W_CONSUMED_DELAY,
    CHAOS_REVEAL_W_CONSUMED_INVALID,
    CHAOS_REVEAL_W_CONSUMED_SUPPRESSED,
    CHAOS_REVEAL_W_TERMINATED_EXPIRY,
    CHAOS_REVEAL_W_TERMINATED_LEVEL,
    CHAOS_REVEAL_W_TERMINATED_TRANSPORT,
    CHAOS_REVEAL_W_COUNT
};
enum chaos_reveal_slot_f {
    CHAOS_REVEAL_F_UNDECLARED = 0,
    CHAOS_REVEAL_F_PENDING,
    CHAOS_REVEAL_F_CONSUMED_APPLIED,
    CHAOS_REVEAL_F_CONSUMED_NONREMAPPABLE,
    CHAOS_REVEAL_F_CONSUMED_QUIET,
    CHAOS_REVEAL_F_CONSUMED_DELAY,
    CHAOS_REVEAL_F_CONSUMED_INVALID,
    CHAOS_REVEAL_F_CONSUMED_SUPPRESSED,
    CHAOS_REVEAL_F_TERMINATED_EXPIRY,
    CHAOS_REVEAL_F_TERMINATED_LEVEL,
    CHAOS_REVEAL_F_TERMINATED_TRANSPORT,
    CHAOS_REVEAL_F_COUNT
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

/* Values copied verbatim from the engine's next-use runtime snapshot. */
struct chaos_reveal_next_use {
    int present;                 /* snapshot phase is committed or terminated */
    int terminated;              /* snapshot phase is terminated */
    int slot_w, slot_f;          /* chaos_next_use_slot_w / _f values */
    int witnessed;               /* engine publication record of delivery */
    long admission_move;
    long origin_w, origin_f;     /* bound origin roots: event sequence numbers */
    int depth;                   /* dungeon depth of the program's level, or 0 */
};

/* Engine-state facts copied by the game host. */
struct chaos_reveal_host {
    int haunt_active;            /* u.haunt still active at the end */
    long haunt_until;
    int curio_charges, curio_placed;
    int next_use_last_rejected;  /* the engine's last next-use attempt refused */
    struct chaos_reveal_next_use nu;
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
    /* Engine observation roots ("started" rows): most recent kept. */
    int origin_count;
    struct { long seq, turn; int fountain; } origin[CHAOS_REVEAL_ORIGINS];
    /* Last next-use admission receipt row; published/bound per family. */
    int receipt_ops;
    struct { int fountain; long published, bound; } receipt[2];
    int receipt_rejected;        /* recorded next-use rejection rows */
    int haunt_budget_seen;       /* #165: 0 none, 1 counted refusal, 2 later admitted */
};

typedef void (*chaos_reveal_emit)(void *, const char *);

void chaos_reveal_init(struct chaos_reveal *, long final_turn, int spent);
/* Parse one engine-written row; exposed for bounded file reading and tests. */
void chaos_reveal_journal_line(struct chaos_reveal *, const char *);
void chaos_reveal_event_line(struct chaos_reveal *, const char *);
void chaos_reveal_receipt_line(struct chaos_reveal *, const char *);
/* Read whispers.jsonl, events.jsonl and next_use-receipt.jsonl from an open
 * run directory fd. */
int chaos_reveal_read(struct chaos_reveal *, int dir);
/* Apply host facts, order chronologically and compute the tallies. */
void chaos_reveal_finish(struct chaos_reveal *);
void chaos_reveal_render(const struct chaos_reveal *, chaos_reveal_emit, void *);
/* ":chaos_admitted=...", or "" when nothing was admitted. */
int chaos_reveal_xlog_fields(const struct chaos_reveal *, char *, size_t);
#endif
