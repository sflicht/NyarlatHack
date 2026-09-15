/* NetHack General Public License. Standalone read-only layout reporter.
 * Links no engine objects, runs outside the game, and never reads/writes u. */
#include <stddef.h>
#include "hack.h"
#include "date.h"

#define FIELD(type, field) \
    printf("\"" #field "\":{\"offset\":%zu,\"size\":%zu},", \
           offsetof(type, field), sizeof(((type *)0)->field))

int main(void)
{
    unsigned endian = 1;
    printf("{\"byteorder\":\"%s\",\"int_size\":%zu,\"unsigned_size\":%zu,",
           *(unsigned char *)&endian ? "little" : "big", sizeof(int), sizeof(unsigned));
#ifdef COMPRESS
    printf("\"external_compression\":true,");
#else
    printf("\"external_compression\":false,");
#endif
#ifdef INTERNAL_COMP
    printf("\"internal_compression\":true,");
#else
    printf("\"internal_compression\":false,");
#endif
    printf("\"version\":%d,\"placed\":%d,\"source_limit\":%d,",
           CHAOS_CURIO_VERSION, CHAOS_CURIO_PLACED, CHAOS_CURIO_SOURCE);
    printf("\"record_size\":%zu,\"record\":{", sizeof(struct chaos_curio_state));
    FIELD(struct chaos_curio_state, version);
    FIELD(struct chaos_curio_state, phase);
    FIELD(struct chaos_curio_state, source_len);
    FIELD(struct chaos_curio_state, owner);
    FIELD(struct chaos_curio_state, charges);
    FIELD(struct chaos_curio_state, state);
    FIELD(struct chaos_curio_state, disabled);
    FIELD(struct chaos_curio_state, name);
    printf("\"source\":{\"offset\":%zu,\"size\":%zu}},",
           offsetof(struct chaos_curio_state, source),
           sizeof(((struct chaos_curio_state *)0)->source));
    printf("\"you_size\":%zu,\"you\":{", sizeof(struct you));
    FIELD(struct you, curio);
    FIELD(struct you, chaos);
    FIELD(struct you, usanity);
    printf("\"uinsight\":{\"offset\":%zu,\"size\":%zu}},",
           offsetof(struct you, uinsight), sizeof(((struct you *)0)->uinsight));
    printf("\"spent_offset\":%zu,\"spent_size\":%zu,",
           offsetof(struct chaos_state, spent), sizeof(((struct chaos_state *)0)->spent));
    printf("\"save_header_size\":%zu,\"save_header\":{", sizeof(struct version_info));
    FIELD(struct version_info, incarnation);
    FIELD(struct version_info, feature_set);
    FIELD(struct version_info, entity_count);
    printf("\"struct_sizes\":{\"offset\":%zu,\"size\":%zu}},",
           offsetof(struct version_info, struct_sizes),
           sizeof(((struct version_info *)0)->struct_sizes));
    printf("\"save_header_values\":{\"incarnation\":%llu,\"feature_set\":%llu,"
           "\"entity_count\":%llu,\"struct_sizes\":%llu}}\n",
           (unsigned long long)VERSION_NUMBER, (unsigned long long)VERSION_FEATURES,
           (unsigned long long)VERSION_SANITY1, (unsigned long long)VERSION_SANITY2);
    return 0;
}
