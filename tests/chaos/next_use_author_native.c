/* ENGINE-UNIT: bridge to real parser/sandbox, not admission or gameplay. */
#include "chaos_next_use.h"
#include <stddef.h>

size_t author_fixture_size(void) { return sizeof(struct chaos_next_use_author); }
size_t author_fixture_length_offset(void) {
    return offsetof(struct chaos_next_use_author, source_length);
}
size_t author_fixture_source_offset(void) {
    return offsetof(struct chaos_next_use_author, source);
}
int author_fixture_parse_envelope(const char *bytes, size_t length) {
    struct chaos_next_use_envelope envelope;
    return chaos_next_use_parse_envelope(bytes, length, &envelope);
}
