#ifndef CHAOS_NEXT_USE_CONTRACT_H
#define CHAOS_NEXT_USE_CONTRACT_H

struct chaos_fountain_token {
    long root;
    int active;
    int remap;
    int consumed;
};

struct chaos_whistle_certificate {
    long root;
    long notice_seq;
    long end_seq;
    int completed;
    int published;
};

void chaos_next_use_mark_identity_unsafe(void);
int chaos_next_use_take_identity_unsafe(void);

#endif
