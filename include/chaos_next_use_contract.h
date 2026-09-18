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

enum chaos_next_use_fountain_outcome {
    CHAOS_FOUNTAIN_NATURAL = 1,
    CHAOS_FOUNTAIN_EARLY_RETURN,
    CHAOS_FOUNTAIN_NATIVE_19_30,
    CHAOS_FOUNTAIN_DEFAULT_WITHOUT_INTENT,
    CHAOS_FOUNTAIN_GUARD_SUPPRESSED,
    CHAOS_FOUNTAIN_REMAPPED
};

void chaos_next_use_mark_identity_unsafe(void);
int chaos_next_use_take_identity_unsafe(void);

#endif
