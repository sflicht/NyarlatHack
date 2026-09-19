/* NetHack General Public License. Closed next-use JSON/JCS/SHA interface. */
#include "chaos_next_use.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define J_NULL 0
#define J_BOOL 1
#define J_NUMBER 2
#define J_STRING 3
#define J_ARRAY 4
#define J_OBJECT 5
#define JSON_ARENA_BYTES 524288

struct json_arena {
    union {
        uint64_t alignment;
        unsigned char bytes[JSON_ARENA_BYTES];
    } storage;
    size_t used;
};

struct json_value;
struct json_member {
    char *key;
    size_t key_length;
    struct json_value *value;
};
struct json_value {
    int type;
    int boolean;
    int32_t number;
    char *string;
    size_t string_length;
    struct json_value **items;
    size_t item_count;
    size_t item_capacity;
    struct json_member *members;
    size_t member_count;
    size_t member_capacity;
};
struct json_parser {
    const unsigned char *text;
    size_t length;
    size_t offset;
    int error;
    struct json_arena *arena;
};
struct json_output {
    char *text;
    size_t capacity;
    size_t length;
    int failed;
    struct json_arena *arena;
};

static void *json_arena_take(struct json_arena *arena, size_t size, int clear)
{
    size_t alignment = sizeof(uint64_t);
    size_t start, padded;
    void *result;
    if (!arena || size > JSON_ARENA_BYTES) return NULL;
    start = (arena->used + alignment - 1) & ~(alignment - 1);
    if (start > JSON_ARENA_BYTES || size > JSON_ARENA_BYTES - start) return NULL;
    padded = start + size;
    result = arena->storage.bytes + start;
    arena->used = padded;
    if (clear) memset(result, 0, size);
    return result;
}

static void json_free(struct json_value *value)
{
    (void)value;
}

static int utf8_scalar(const unsigned char *, size_t, size_t *, uint32_t *);
static int utf8_scalar(const unsigned char *text, size_t length,
                       size_t *used, uint32_t *scalar)
{
    unsigned char a, b, c, d;
    uint32_t cp;
    if (!length) return 0;
    a = text[0];
    if (a < 0x80) { *used = 1; *scalar = a; return 1; }
    if (a < 0xC0) return 0;
    if (a < 0xE0) {
        if (length < 2 || a < 0xC2 || (text[1] & 0xC0) != 0x80) return 0;
        cp = ((uint32_t)(a & 0x1F) << 6) | (uint32_t)(text[1] & 0x3F);
        *used = 2; *scalar = cp; return 1;
    }
    if (a < 0xF0) {
        if (length < 3 || (text[1] & 0xC0) != 0x80 ||
            (text[2] & 0xC0) != 0x80) return 0;
        b = text[1]; c = text[2];
        if ((a == 0xE0 && b < 0xA0) || (a == 0xED && b >= 0xA0)) return 0;
        cp = ((uint32_t)(a & 0x0F) << 12) |
             ((uint32_t)(b & 0x3F) << 6) | (uint32_t)(c & 0x3F);
        if (cp >= 0xD800 && cp <= 0xDFFF) return 0;
        *used = 3; *scalar = cp; return 1;
    }
    if (a <= 0xF4) {
        if (length < 4 || (text[1] & 0xC0) != 0x80 ||
            (text[2] & 0xC0) != 0x80 || (text[3] & 0xC0) != 0x80) return 0;
        b = text[1]; c = text[2]; d = text[3];
        if ((a == 0xF0 && b < 0x90) || (a == 0xF4 && b >= 0x90)) return 0;
        cp = ((uint32_t)(a & 7) << 18) | ((uint32_t)(b & 0x3F) << 12) |
             ((uint32_t)(c & 0x3F) << 6) | (uint32_t)(d & 0x3F);
        if (cp > 0x10FFFF) return 0;
        *used = 4; *scalar = cp; return 1;
    }
    return 0;
}

static int json_utf8_validate(const unsigned char *, size_t);
static int json_utf8_validate(const unsigned char *text, size_t length)
{
    size_t offset = 0, used;
    uint32_t scalar;
    if (length >= 3 && text[0] == 0xEF && text[1] == 0xBB && text[2] == 0xBF)
        return 0;
    while (offset < length) {
        if (!utf8_scalar(text + offset, length - offset, &used, &scalar)) return 0;
        offset += used;
    }
    return 1;
}

static void json_space(struct json_parser *parser)
{
    while (parser->offset < parser->length) {
        unsigned char c = parser->text[parser->offset];
        if (c != ' ' && c != '\t' && c != '\r' && c != '\n') break;
        ++parser->offset;
    }
}

static int json_hex(unsigned char c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static int json_append_scalar(struct json_arena *arena,
                              char **buffer, size_t *length, size_t *capacity,
                              uint32_t scalar)
{
    unsigned char encoded[4];
    size_t count, next;
    if (scalar <= 0x7F) { encoded[0] = (unsigned char)scalar; count = 1; }
    else if (scalar <= 0x7FF) {
        encoded[0] = (unsigned char)(0xC0 | (scalar >> 6));
        encoded[1] = (unsigned char)(0x80 | (scalar & 0x3F)); count = 2;
    } else if (scalar <= 0xFFFF) {
        encoded[0] = (unsigned char)(0xE0 | (scalar >> 12));
        encoded[1] = (unsigned char)(0x80 | ((scalar >> 6) & 0x3F));
        encoded[2] = (unsigned char)(0x80 | (scalar & 0x3F)); count = 3;
    } else {
        encoded[0] = (unsigned char)(0xF0 | (scalar >> 18));
        encoded[1] = (unsigned char)(0x80 | ((scalar >> 12) & 0x3F));
        encoded[2] = (unsigned char)(0x80 | ((scalar >> 6) & 0x3F));
        encoded[3] = (unsigned char)(0x80 | (scalar & 0x3F)); count = 4;
    }
    if (*length > (size_t)-1 - count - 1) return 0;
    next = *length + count + 1;
    if (next > *capacity) {
        size_t grown = *capacity ? *capacity : 32;
        char *replacement;
        while (grown < next) {
            if (grown > (size_t)-1 / 2) return 0;
            grown *= 2;
        }
        replacement = (char *)json_arena_take(arena, grown, 0);
        if (!replacement) return 0;
        if (*buffer && *length) memcpy(replacement, *buffer, *length);
        *buffer = replacement; *capacity = grown;
    }
    memcpy(*buffer + *length, encoded, count);
    *length += count; (*buffer)[*length] = '\0';
    return 1;
}

static int json_parse_string(struct json_parser *parser, char **result,
                             size_t *result_length)
{
    char *buffer = NULL;
    size_t length = 0, capacity = 0, used;
    uint32_t scalar;
    if (parser->offset >= parser->length || parser->text[parser->offset++] != '"')
        return 0;
    while (parser->offset < parser->length) {
        unsigned char c = parser->text[parser->offset];
        if (c == '"') {
            ++parser->offset;
            if (!buffer) {
                buffer = (char *)json_arena_take(parser->arena, 1, 1);
                if (!buffer) return 0;
            }
            *result = buffer; *result_length = length; return 1;
        }
        if (c < 0x20) break;
        if (c == '\\') {
            uint32_t high, low;
            int i, h;
            ++parser->offset;
            if (parser->offset >= parser->length) break;
            c = parser->text[parser->offset++];
            if (c == '"' || c == '\\' || c == '/') scalar = c;
            else if (c == 'b') scalar = 8;
            else if (c == 'f') scalar = 12;
            else if (c == 'n') scalar = 10;
            else if (c == 'r') scalar = 13;
            else if (c == 't') scalar = 9;
            else if (c == 'u') {
                if (parser->length - parser->offset < 4) break;
                high = 0;
                for (i = 0; i < 4; ++i) {
                    h = json_hex(parser->text[parser->offset++]);
                    if (h < 0) goto invalid_string;
                    high = (high << 4) | (uint32_t)h;
                }
                if (high >= 0xD800 && high <= 0xDBFF) {
                    if (parser->length - parser->offset < 6 ||
                        parser->text[parser->offset++] != '\\' ||
                        parser->text[parser->offset++] != 'u') break;
                    low = 0;
                    for (i = 0; i < 4; ++i) {
                        h = json_hex(parser->text[parser->offset++]);
                        if (h < 0) goto invalid_string;
                        low = (low << 4) | (uint32_t)h;
                    }
                    if (low < 0xDC00 || low > 0xDFFF) break;
                    scalar = 0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00);
                } else {
                    if (high >= 0xDC00 && high <= 0xDFFF) break;
                    scalar = high;
                }
            } else break;
            if (!json_append_scalar(parser->arena, &buffer, &length, &capacity, scalar)) break;
            continue;
        }
        if (!utf8_scalar(parser->text + parser->offset,
                         parser->length - parser->offset, &used, &scalar)) break;
        parser->offset += used;
        if (!json_append_scalar(parser->arena, &buffer, &length, &capacity, scalar)) break;
    }
invalid_string:
    return 0;
}

static struct json_value *json_parse_value(struct json_parser *parser, int depth);

static int json_reject_duplicate_keys(const struct json_value *object,
                                      const char *key, size_t key_length)
{
    size_t i;
    for (i = 0; i < object->member_count; ++i)
        if (object->members[i].key_length == key_length &&
            !memcmp(object->members[i].key, key, key_length)) return 0;
    return 1;
}

static struct json_value *json_parse_array(struct json_parser *, int);
static struct json_value *json_parse_array(struct json_parser *parser, int depth)
{
    struct json_value *array;
    if (depth > 64 || parser->text[parser->offset++] != '[') return NULL;
    array = (struct json_value *)json_arena_take(parser->arena, sizeof *array, 1);
    if (!array) return NULL;
    array->type = J_ARRAY; json_space(parser);
    if (parser->offset < parser->length && parser->text[parser->offset] == ']') {
        ++parser->offset; return array;
    }
    for (;;) {
        struct json_value *item;
        struct json_value **grown;
        item = json_parse_value(parser, depth + 1);
        if (!item) break;
        if (array->item_count == array->item_capacity) {
            size_t capacity = array->item_capacity ? array->item_capacity * 2 : 4;
            grown = (struct json_value **)json_arena_take(
                parser->arena, capacity * sizeof *grown, 0);
            if (!grown) { json_free(item); break; }
            if (array->items)
                memcpy(grown, array->items, array->item_count * sizeof *grown);
            array->items = grown; array->item_capacity = capacity;
        }
        array->items[array->item_count++] = item;
        json_space(parser);
        if (parser->offset >= parser->length) break;
        if (parser->text[parser->offset] == ']') {
            ++parser->offset; return array;
        }
        if (parser->text[parser->offset++] != ',') break;
        json_space(parser);
    }
    json_free(array); return NULL;
}

static struct json_value *json_parse_object(struct json_parser *, int);
static struct json_value *json_parse_object(struct json_parser *parser, int depth)
{
    struct json_value *object;
    if (depth > 64 || parser->text[parser->offset++] != '{') return NULL;
    object = (struct json_value *)json_arena_take(parser->arena, sizeof *object, 1);
    if (!object) return NULL;
    object->type = J_OBJECT; json_space(parser);
    if (parser->offset < parser->length && parser->text[parser->offset] == '}') {
        ++parser->offset; return object;
    }
    for (;;) {
        char *key = NULL;
        size_t key_length = 0;
        struct json_value *value;
        struct json_member *grown;
        if (!json_parse_string(parser, &key, &key_length)) break;
        if (!json_reject_duplicate_keys(object, key, key_length)) {
            parser->error = CHAOS_NEXT_USE_DUPLICATE_KEY;
            break;
        }
        json_space(parser);
        if (parser->offset >= parser->length || parser->text[parser->offset++] != ':')
            break;
        json_space(parser); value = json_parse_value(parser, depth + 1);
        if (!value) break;
        if (object->member_count == object->member_capacity) {
            size_t capacity = object->member_capacity ? object->member_capacity * 2 : 4;
            grown = (struct json_member *)json_arena_take(
                parser->arena, capacity * sizeof *grown, 0);
            if (!grown) { json_free(value); break; }
            if (object->members)
                memcpy(grown, object->members,
                       object->member_count * sizeof *grown);
            object->members = grown; object->member_capacity = capacity;
        }
        object->members[object->member_count].key = key;
        object->members[object->member_count].key_length = key_length;
        object->members[object->member_count].value = value;
        ++object->member_count;
        json_space(parser);
        if (parser->offset >= parser->length) break;
        if (parser->text[parser->offset] == '}') {
            ++parser->offset; return object;
        }
        if (parser->text[parser->offset++] != ',') break;
        json_space(parser);
    }
    json_free(object); return NULL;
}

static struct json_value *json_parse_number(struct json_parser *parser)
{
    struct json_value *number;
    size_t start = parser->offset;
    int negative = 0;
    int64_t value = 0;
    if (parser->text[parser->offset] == '-') { negative = 1; ++parser->offset; }
    if (parser->offset >= parser->length) return NULL;
    if (parser->text[parser->offset] == '0') {
        ++parser->offset;
        if (parser->offset < parser->length &&
            parser->text[parser->offset] >= '0' && parser->text[parser->offset] <= '9')
            return NULL;
    } else {
        if (parser->text[parser->offset] < '1' || parser->text[parser->offset] > '9')
            return NULL;
        while (parser->offset < parser->length &&
               parser->text[parser->offset] >= '0' && parser->text[parser->offset] <= '9') {
            value = value * 10 + (parser->text[parser->offset++] - '0');
            if (value > 2147483648LL) return NULL;
        }
    }
    if (parser->offset < parser->length &&
        (parser->text[parser->offset] == '.' || parser->text[parser->offset] == 'e' ||
         parser->text[parser->offset] == 'E')) return NULL;
    if (parser->offset == start || (negative && value == 0)) return NULL;
    if (negative) value = -value;
    if (value < -2147483647LL - 1 || value > 2147483647LL) return NULL;
    number = (struct json_value *)json_arena_take(parser->arena, sizeof *number, 1);
    if (!number) return NULL;
    number->type = J_NUMBER; number->number = (int32_t)value; return number;
}

static struct json_value *json_parse_value(struct json_parser *parser, int depth)
{
    struct json_value *value;
    json_space(parser);
    if (parser->offset >= parser->length) return NULL;
    if (parser->text[parser->offset] == '{') return json_parse_object(parser, depth);
    if (parser->text[parser->offset] == '[') return json_parse_array(parser, depth);
    if (parser->text[parser->offset] == '-' ||
        (parser->text[parser->offset] >= '0' && parser->text[parser->offset] <= '9'))
        return json_parse_number(parser);
    value = (struct json_value *)json_arena_take(parser->arena, sizeof *value, 1);
    if (!value) return NULL;
    if (parser->text[parser->offset] == '"') {
        value->type = J_STRING;
        if (!json_parse_string(parser, &value->string, &value->string_length))
            return NULL;
        return value;
    }
    if (parser->length - parser->offset >= 4 &&
        !memcmp(parser->text + parser->offset, "true", 4)) {
        parser->offset += 4; value->type = J_BOOL; value->boolean = 1; return value;
    }
    if (parser->length - parser->offset >= 5 &&
        !memcmp(parser->text + parser->offset, "false", 5)) {
        parser->offset += 5; value->type = J_BOOL; return value;
    }
    if (parser->length - parser->offset >= 4 &&
        !memcmp(parser->text + parser->offset, "null", 4)) {
        parser->offset += 4; value->type = J_NULL; return value;
    }
    return NULL;
}

static int json_string_noncharacter(const char *, size_t);
static int json_string_noncharacter(const char *text, size_t length)
{
    size_t offset = 0, used;
    uint32_t scalar;
    while (offset < length) {
        if (!utf8_scalar((const unsigned char *)text + offset, length - offset,
                         &used, &scalar)) return 1;
        if ((scalar >= 0xFDD0 && scalar <= 0xFDEF) ||
            ((scalar & 0xFFFF) == 0xFFFE) || ((scalar & 0xFFFF) == 0xFFFF))
            return 1;
        offset += used;
    }
    return 0;
}

static int json_reject_noncharacters(const struct json_value *);
static int json_reject_noncharacters(const struct json_value *value)
{
    size_t i;
    int NONCHARACTER = 0;
    uint32_t highest_scalar = 0x10FFFF;
    if (!value || highest_scalar != 0x10FFFF || 0xFDD0 > 0xFDEF ||
        (0xFFFE & 0xFFFF) != 0xFFFE || (0xFFFF & 0xFFFF) != 0xFFFF)
        return 0;
    if (value->type == J_STRING)
        NONCHARACTER = json_string_noncharacter(value->string, value->string_length);
    else if (value->type == J_ARRAY) {
        for (i = 0; i < value->item_count; ++i)
            if (!json_reject_noncharacters(value->items[i])) NONCHARACTER = 1;
    } else if (value->type == J_OBJECT) {
        for (i = 0; i < value->member_count; ++i)
            if (json_string_noncharacter(value->members[i].key,
                                         value->members[i].key_length) ||
                !json_reject_noncharacters(value->members[i].value)) NONCHARACTER = 1;
    }
    return NONCHARACTER ? 0 : 1;
}

static int json_validate_ijson(const struct json_value *);
static int json_validate_ijson(const struct json_value *value)
{
    size_t i;
    double scalar;
    if (!value) return 0;
    if (value->type == J_NULL || value->type == J_BOOL) return 1;
    if (value->type == J_NUMBER) {
        scalar = (double)value->number;
        return isfinite(scalar) && !(signbit(scalar) && scalar == 0.0) &&
               value->number >= (-2147483647 - 1) && value->number <= 2147483647;
    }
    if (value->type == J_STRING) {
        if (memchr(value->string, 0, value->string_length)) return 0;
        return 1;
    }
    if (value->type == J_ARRAY) {
        for (i = 0; i < value->item_count; ++i)
            if (!json_validate_ijson(value->items[i])) return 0;
        return 1;
    }
    if (value->type == J_OBJECT) {
        for (i = 0; i < value->member_count; ++i) {
            if (memchr(value->members[i].key, 0, value->members[i].key_length) ||
                !json_validate_ijson(value->members[i].value)) return 0;
        }
        return 1;
    }
    return 0;
}

static int json_parse_document(const char *, size_t, struct json_arena *,
                               struct json_value **);
static int json_parse_document(const char *text, size_t length,
                               struct json_arena *arena,
                               struct json_value **result)
{
    struct json_parser parser;
    struct json_value *value;
    if (!text || !result || !arena || !length ||
        !json_utf8_validate((const unsigned char *)text, length))
        return CHAOS_NEXT_USE_UTF8;
    arena->used = 0;
    parser.text = (const unsigned char *)text; parser.length = length;
    parser.offset = 0; parser.error = 0; parser.arena = arena;
    value = json_parse_value(&parser, 0);
    if (!value) return parser.error ? parser.error : CHAOS_NEXT_USE_JSON;
    json_space(&parser);
    if (parser.offset != length) { json_free(value); return CHAOS_NEXT_USE_JSON; }
    if (!json_reject_noncharacters(value)) {
        json_free(value); return CHAOS_NEXT_USE_NONCHARACTER;
    }
    if (!json_validate_ijson(value)) {
        json_free(value); return CHAOS_NEXT_USE_IJSON;
    }
    *result = value; return CHAOS_NEXT_USE_OK;
}

static const struct json_value *json_member(const struct json_value *object,
                                            const char *name)
{
    size_t i, length = strlen(name);
    if (!object || object->type != J_OBJECT) return NULL;
    for (i = 0; i < object->member_count; ++i)
        if (object->members[i].key_length == length &&
            !memcmp(object->members[i].key, name, length))
            return object->members[i].value;
    return NULL;
}

static int json_integer(const struct json_value *value, int low, int high, int *out)
{
    if (!value || value->type != J_NUMBER || value->number < low || value->number > high)
        return 0;
    *out = (int)value->number; return 1;
}

static int json_text(const struct json_value *value, const char *literal)
{
    size_t length = strlen(literal);
    return value && value->type == J_STRING && value->string_length == length &&
           !memcmp(value->string, literal, length);
}

static int lowercase_hex(const struct json_value *value, size_t length)
{
    size_t i;
    if (!value || value->type != J_STRING || value->string_length != length) return 0;
    for (i = 0; i < length; ++i)
        if (!((value->string[i] >= '0' && value->string[i] <= '9') ||
              (value->string[i] >= 'a' && value->string[i] <= 'f'))) return 0;
    return 1;
}

static int schema_author(const struct json_value *,
                         struct chaos_next_use_author *);
static int schema_author(const struct json_value *root,
                         struct chaos_next_use_author *out)
{
    const struct json_value *version, *source, *abstain;
    int v;
    if (!root || root->type != J_OBJECT || root->member_count != 2) return 0;
    version = json_member(root, "next_use_author_v");
    source = json_member(root, "source"); abstain = json_member(root, "abstain");
    if (!json_integer(version, 2, 2, &v)) return 0;
    if (source && !abstain && source->type == J_STRING &&
        source->string_length >= 1 && source->string_length <= 4096) {
        memcpy(out->source, source->string, source->string_length);
        out->source[source->string_length] = '\0';
        out->source_length = source->string_length; return 1;
    }
    if (abstain && !source && abstain->type == J_BOOL && abstain->boolean) {
        out->abstain = 1; return 1;
    }
    return 0;
}

static int schema_origin(const struct json_value *root,
                         struct chaos_next_use_origin_ref *out, int family)
{
    static const char *const names[] = {"end_seq","fact","family","level_dlevel",
        "level_dnum","move","notice_seq","root","run"};
    const struct json_value *fact, *family_value, *run;
    size_t i;
    int n;
    if (!root || root->type != J_OBJECT || root->member_count != 9) return 0;
    for (i = 0; i < 9; ++i) if (!json_member(root, names[i])) return 0;
    if (!json_integer(json_member(root,"end_seq"),1,2147483647,&out->end_seq) ||
        !json_integer(json_member(root,"level_dlevel"),0,255,&out->level_dlevel) ||
        !json_integer(json_member(root,"level_dnum"),0,255,&out->level_dnum) ||
        !json_integer(json_member(root,"move"),0,2147483647,&out->move) ||
        !json_integer(json_member(root,"notice_seq"),1,2147483647,&out->notice_seq) ||
        !json_integer(json_member(root,"root"),1,2147483647,&out->root)) return 0;
    if (!(out->root < out->notice_seq && out->notice_seq < out->end_seq)) return 0;
    family_value = json_member(root,"family"); fact = json_member(root,"fact");
    if (family == CHAOS_NEXT_USE_FAMILY_W) {
        if (!json_text(family_value,"W") || !json_text(fact,"ordinary_whistle")) return 0;
        n = 17;
    } else {
        if (!json_text(family_value,"F") || !json_text(fact,"water_refreshed")) return 0;
        n = 15;
    }
    memcpy(out->fact, fact->string, (size_t)n); out->fact[n] = '\0';
    out->family = family;
    run = json_member(root,"run");
    if (!lowercase_hex(run,64)) return 0;
    memcpy(out->run,run->string,64); out->run[64]='\0'; return 1;
}

static void digest_hex(const unsigned char digest[32], char output[65])
{
    static const char hex[] = "0123456789abcdef";
    int i;
    for (i = 0; i < 32; ++i) {
        output[i * 2] = hex[digest[i] >> 4];
        output[i * 2 + 1] = hex[digest[i] & 15];
    }
    output[64] = '\0';
}

static int schema_envelope(const struct json_value *,
                           struct chaos_next_use_envelope *);
static int schema_envelope(const struct json_value *root,
                           struct chaos_next_use_envelope *out)
{
    static const char *const names[] = {"at","cost","id","next_use_program_v",
        "operations","origin_refs","source","source_sha256","telegraph","ttl","variant"};
    const struct json_value *operations, *origins, *source, *sha, *telegraph;
    unsigned char digest[32]; char calculated[65];
    size_t i; int v, family;
    if (!root || root->type != J_OBJECT || root->member_count != 11) return 0;
    for (i = 0; i < 11; ++i) if (!json_member(root,names[i])) return 0;
    if (!json_integer(json_member(root,"next_use_program_v"),2,2,&v) ||
        !json_integer(json_member(root,"at"),0,2147483647,&out->at) ||
        !json_integer(json_member(root,"id"),1,2147483647,&out->id) ||
        !json_integer(json_member(root,"ttl"),100,100,&out->ttl) ||
        !json_integer(json_member(root,"variant"),0,2,&out->variant)) return 0;
    operations=json_member(root,"operations"); origins=json_member(root,"origin_refs");
    if (!operations || operations->type != J_ARRAY || operations->item_count < 1 ||
        operations->item_count > 2 || !origins || origins->type != J_ARRAY ||
        origins->item_count != operations->item_count) return 0;
    out->operation_count=(int)operations->item_count;
    for (i=0;i<operations->item_count;++i) {
        if (json_text(operations->items[i],"W")) family=CHAOS_NEXT_USE_FAMILY_W;
        else if (json_text(operations->items[i],"F")) family=CHAOS_NEXT_USE_FAMILY_F;
        else return 0;
        if (i==1 && family!=CHAOS_NEXT_USE_FAMILY_F) return 0;
        if (i==0 && operations->item_count==2 && family!=CHAOS_NEXT_USE_FAMILY_W) return 0;
        out->operations[i]=family;
        if (!schema_origin(origins->items[i],&out->origin_refs[i],family)) return 0;
    }
    if (!json_integer(json_member(root,"cost"),out->operation_count,out->operation_count,&out->cost))
        return 0;
    source=json_member(root,"source"); sha=json_member(root,"source_sha256");
    if (!source || source->type!=J_STRING || source->string_length<1 ||
        source->string_length>4096 || !lowercase_hex(sha,64)) return 0;
    if (chaos_next_use_sha256(source->string,source->string_length,digest)!=CHAOS_NEXT_USE_OK)
        return 0;
    digest_hex(digest,calculated);
    if (memcmp(calculated,sha->string,64)) return 0;
    memcpy(out->source,source->string,source->string_length);
    out->source[source->string_length]='\0'; out->source_length=source->string_length;
    memcpy(out->source_sha256,sha->string,64); out->source_sha256[64]='\0';
    telegraph=json_member(root,"telegraph");
    if (out->operation_count==2) { if (!json_text(telegraph,"next-use-v2-WF")) return 0; }
    else if (out->operations[0]==CHAOS_NEXT_USE_FAMILY_W) {
        if (!json_text(telegraph,"next-use-v2-W")) return 0;
    } else if (!json_text(telegraph,"next-use-v2-F")) return 0;
    memcpy(out->telegraph,telegraph->string,telegraph->string_length);
    out->telegraph[telegraph->string_length]='\0'; return 1;
}

static int schema_context(const struct json_value *root,
                          struct chaos_next_use_context *out)
{
    static const char *const names[]={"age","fountain_count","next_use_context_v",
        "own_witnessed","source_sha256","state","trigger","variant","whistle_count"};
    const struct json_value *own,*trigger,*sha; size_t i; int v;
    if (!root || root->type!=J_OBJECT || root->member_count!=9) return 0;
    for(i=0;i<9;++i) if(!json_member(root,names[i])) return 0;
    if(!json_integer(json_member(root,"next_use_context_v"),2,2,&v) ||
       !json_integer(json_member(root,"age"),0,99,&out->age) ||
       !json_integer(json_member(root,"fountain_count"),0,3,&out->fountain_count) ||
       !json_integer(json_member(root,"state"),0,3,&out->state) ||
       !json_integer(json_member(root,"variant"),0,2,&out->variant) ||
       !json_integer(json_member(root,"whistle_count"),0,3,&out->whistle_count)) return 0;
    own=json_member(root,"own_witnessed"); trigger=json_member(root,"trigger");
    if(json_text(own,"none")) out->own_witnessed=0;
    else if(json_text(own,"W")) out->own_witnessed=1; else return 0;
    if(json_text(trigger,"W")) out->trigger=CHAOS_NEXT_USE_FAMILY_W;
    else if(json_text(trigger,"F")) out->trigger=CHAOS_NEXT_USE_FAMILY_F; else return 0;
    sha=json_member(root,"source_sha256"); if(!lowercase_hex(sha,64)) return 0;
    memcpy(out->source_sha256,sha->string,64); out->source_sha256[64]='\0'; return 1;
}

static int schema_intent(const struct json_value *root,
                         struct chaos_next_use_intent *out)
{
    const struct json_value *op; int v;
    if(!root || root->type!=J_OBJECT || root->member_count!=3 ||
       !json_integer(json_member(root,"next_use_intent_v"),2,2,&v) ||
       !json_integer(json_member(root,"state"),0,3,&out->state)) return 0;
    op=json_member(root,"op");
    if(json_text(op,"quiet")) out->op=CHAOS_NEXT_USE_INTENT_QUIET;
    else if(json_text(op,"delay")) out->op=CHAOS_NEXT_USE_INTENT_DELAY;
    else if(json_text(op,"whistle_attention")) out->op=CHAOS_NEXT_USE_INTENT_WHISTLE_ATTENTION;
    else if(json_text(op,"fountain_refresh")) out->op=CHAOS_NEXT_USE_INTENT_FOUNTAIN_REFRESH;
    else return 0;
    return 1;
}

static void jcs_emit_value(struct json_output *, const struct json_value *);
static int json_require_canonical(const struct json_value *root,
                                  const char *wire, size_t wire_length,
                                  size_t limit, struct json_arena *arena)
{
    char canonical[8192];
    struct json_output output;
    if (!root || !wire || !arena || limit > sizeof canonical) return 0;
    output.text = canonical; output.capacity = limit; output.length = 0;
    output.failed = 0; output.arena = arena;
    jcs_emit_value(&output, root);
    return !output.failed && output.length <= limit &&
           output.length == wire_length && !memcmp(canonical, wire, wire_length);
}

int chaos_next_use_parse_author(const char *, size_t, struct chaos_next_use_author *);
int chaos_next_use_parse_author(const char *text, size_t length,
                                struct chaos_next_use_author *out)
{
    struct json_arena arena;
    struct json_value *root=NULL; int status;
    if (!out || length > 8192) return CHAOS_NEXT_USE_LIMIT;
    memset(out,0,sizeof *out);
    status=json_parse_document(text,length,&arena,&root);
    if(status!=CHAOS_NEXT_USE_OK) return status;
    status=schema_author(root,out)?CHAOS_NEXT_USE_OK:CHAOS_NEXT_USE_SCHEMA;
    json_free(root); if(status) memset(out,0,sizeof *out); return status;
}

int chaos_next_use_parse_envelope(const char *, size_t, struct chaos_next_use_envelope *);
int chaos_next_use_parse_envelope(const char *text, size_t length,
                                  struct chaos_next_use_envelope *out)
{
    struct json_arena arena;
    struct json_value *root=NULL; int status;
    if (!out || length > 8192) return CHAOS_NEXT_USE_LIMIT;
    memset(out,0,sizeof *out);
    status=json_parse_document(text,length,&arena,&root);
    if(status!=CHAOS_NEXT_USE_OK) return status;
    if(!json_require_canonical(root,text,length,8192,&arena))
        return CHAOS_NEXT_USE_JSON;
    status=schema_envelope(root,out)?CHAOS_NEXT_USE_OK:CHAOS_NEXT_USE_SCHEMA;
    json_free(root); if(status) memset(out,0,sizeof *out); return status;
}

int chaos_next_use_parse_context(const char *, size_t, struct chaos_next_use_context *);
int chaos_next_use_parse_context(const char *text, size_t length,
                                 struct chaos_next_use_context *out)
{
    struct json_arena arena;
    struct json_value *root=NULL; int status;
    if (!out || length > 6144) return CHAOS_NEXT_USE_LIMIT;
    memset(out,0,sizeof *out);
    status=json_parse_document(text,length,&arena,&root);
    if(status!=CHAOS_NEXT_USE_OK) return status;
    if(!json_require_canonical(root,text,length,6144,&arena))
        return CHAOS_NEXT_USE_JSON;
    status=schema_context(root,out)?CHAOS_NEXT_USE_OK:CHAOS_NEXT_USE_SCHEMA;
    json_free(root); if(status) memset(out,0,sizeof *out); return status;
}

int chaos_next_use_parse_intent(const char *, size_t, struct chaos_next_use_intent *);
int chaos_next_use_parse_intent(const char *text, size_t length,
                                struct chaos_next_use_intent *out)
{
    struct json_arena arena;
    struct json_value *root=NULL; int status;
    if (!out || length > 4096) return CHAOS_NEXT_USE_LIMIT;
    memset(out,0,sizeof *out);
    status=json_parse_document(text,length,&arena,&root);
    if(status!=CHAOS_NEXT_USE_OK) return status;
    if(!json_require_canonical(root,text,length,4096,&arena))
        return CHAOS_NEXT_USE_JSON;
    status=schema_intent(root,out)?CHAOS_NEXT_USE_OK:CHAOS_NEXT_USE_SCHEMA;
    json_free(root); if(status) memset(out,0,sizeof *out); return status;
}

static void jcs_append(struct json_output *out,const char *text,size_t length)
{
    if(out->failed || length>out->capacity-out->length){out->failed=1;return;}
    memcpy(out->text+out->length,text,length); out->length+=length;
}
static void jcs_escape_string(struct json_output *out,const char *text,size_t length)
{
    static const char hex[]="0123456789abcdef"; size_t offset=0,used; uint32_t scalar;
    jcs_append(out,"\"",1);
    while(offset<length){
        unsigned char c=(unsigned char)text[offset]; char escaped[6];
        if(c=='\"') jcs_append(out,"\\\"",2);
        else if(c=='\\') jcs_append(out,"\\\\",2);
        else if(c=='\b') jcs_append(out,"\\b",2);
        else if(c=='\t') jcs_append(out,"\\t",2);
        else if(c=='\n') jcs_append(out,"\\n",2);
        else if(c=='\f') jcs_append(out,"\\f",2);
        else if(c=='\r') jcs_append(out,"\\r",2);
        else if(c<0x20){escaped[0]='\\';escaped[1]='u';escaped[2]='0';escaped[3]='0';
            escaped[4]=hex[c>>4];escaped[5]=hex[c&15];jcs_append(out,escaped,6);}
        else { if(!utf8_scalar((const unsigned char*)text+offset,length-offset,&used,&scalar)){out->failed=1;return;}
            jcs_append(out,text+offset,used); offset+=used; continue; }
        ++offset;
    }
    jcs_append(out,"\"",1);
}
struct utf16_cursor{const unsigned char *text;size_t length,offset;uint16_t pending;};
static int utf16_next(struct utf16_cursor *cursor,uint16_t *unit)
{
    size_t used;uint32_t scalar;
    if(cursor->pending){*unit=cursor->pending;cursor->pending=0;return 1;}
    if(cursor->offset>=cursor->length)return 0;
    if(!utf8_scalar(cursor->text+cursor->offset,cursor->length-cursor->offset,&used,&scalar))return -1;
    cursor->offset+=used;
    if(scalar<=0xFFFF){*unit=(uint16_t)scalar;return 1;}
    scalar-=0x10000;*unit=(uint16_t)(0xD800+(scalar>>10));
    cursor->pending=(uint16_t)(0xDC00+(scalar&0x3FF));return 1;
}
static int utf16_member_compare(const void *, const void *);
static int utf16_member_compare(const void *left,const void *right)
{
    const struct json_member *a=*(const struct json_member *const*)left;
    const struct json_member *b=*(const struct json_member *const*)right;
    struct utf16_cursor ca,cb;uint16_t ua,ub;int ha,hb;
    memset(&ca,0,sizeof ca);memset(&cb,0,sizeof cb);
    ca.text=(const unsigned char*)a->key;ca.length=a->key_length;
    cb.text=(const unsigned char*)b->key;cb.length=b->key_length;
    for(;;){ha=utf16_next(&ca,&ua);hb=utf16_next(&cb,&ub);
        if(ha<=0||hb<=0)return ha-hb;if(ua<ub)return -1;if(ua>ub)return 1;}
}
static void jcs_emit_value(struct json_output *, const struct json_value *);
static void jcs_emit_value(struct json_output *out,const struct json_value *value)
{
    size_t i;char number[32];int count;
    if(out->failed)return;
    if(value->type==J_NULL)jcs_append(out,"null",4);
    else if(value->type==J_BOOL)jcs_append(out,value->boolean?"true":"false",value->boolean?4:5);
    else if(value->type==J_NUMBER){count=snprintf(number,sizeof number,"%d",(int)value->number);
        if(count<0||(size_t)count>=sizeof number)out->failed=1;else jcs_append(out,number,(size_t)count);}
    else if(value->type==J_STRING)jcs_escape_string(out,value->string,value->string_length);
    else if(value->type==J_ARRAY){jcs_append(out,"[",1);for(i=0;i<value->item_count;++i){if(i)jcs_append(out,",",1);jcs_emit_value(out,value->items[i]);}jcs_append(out,"]",1);}
    else if(value->type==J_OBJECT){struct json_member **sorted;
        sorted=(struct json_member**)json_arena_take(
            out->arena,value->member_count*sizeof *sorted,0);
        if(value->member_count&&!sorted){out->failed=1;return;}
        for(i=0;i<value->member_count;++i)sorted[i]=&value->members[i];
        for(i=1;i<value->member_count;++i){
            struct json_member *member=sorted[i];size_t position=i;
            while(position>0&&utf16_member_compare(&member,&sorted[position-1])<0){
                sorted[position]=sorted[position-1];--position;
            }
            sorted[position]=member;
        }
        jcs_append(out,"{",1);for(i=0;i<value->member_count;++i){if(i)jcs_append(out,",",1);
            jcs_escape_string(out,sorted[i]->key,sorted[i]->key_length);jcs_append(out,":",1);jcs_emit_value(out,sorted[i]->value);}jcs_append(out,"}",1);}
    else out->failed=1;
}

int chaos_next_use_jcs(const char *, size_t, char *, size_t, size_t *);
int chaos_next_use_jcs(const char *text,size_t length,char *output,size_t capacity,size_t *written)
{
    struct json_arena arena;
    struct json_value *root=NULL;struct json_output out;int status;
    if(!output||!written||length>8192)return CHAOS_NEXT_USE_LIMIT;
    *written=0;status=json_parse_document(text,length,&arena,&root);if(status)return status;
    out.text=output;out.capacity=capacity;out.length=0;out.failed=0;out.arena=&arena;
    jcs_emit_value(&out,root);json_free(root);
    if(out.failed)return CHAOS_NEXT_USE_OUTPUT;*written=out.length;return CHAOS_NEXT_USE_OK;
}

struct sha256_state{uint32_t h[8];uint64_t bits;unsigned char block[64];size_t used;};
static uint32_t sha256_rotr(uint32_t x,unsigned n){return(x>>n)|(x<<(32-n));}
static void sha256_transform(struct sha256_state *, const unsigned char [64]);
static void sha256_transform(struct sha256_state *s,const unsigned char block[64])
{
    static const uint32_t k[64]={
0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U};
    uint32_t w[64],a,b,c,d,e,f,g,h,t1,t2;int i;
    for(i=0;i<16;++i)w[i]=((uint32_t)block[i*4]<<24)|((uint32_t)block[i*4+1]<<16)|((uint32_t)block[i*4+2]<<8)|block[i*4+3];
    for(i=16;i<64;++i){uint32_t x=w[i-15],y=w[i-2];w[i]=w[i-16]+(sha256_rotr(x,7)^sha256_rotr(x,18)^(x>>3))+w[i-7]+(sha256_rotr(y,17)^sha256_rotr(y,19)^(y>>10));}
    a=s->h[0];b=s->h[1];c=s->h[2];d=s->h[3];e=s->h[4];f=s->h[5];g=s->h[6];h=s->h[7];
    for(i=0;i<64;++i){t1=h+(sha256_rotr(e,6)^sha256_rotr(e,11)^sha256_rotr(e,25))+((e&f)^((~e)&g))+k[i]+w[i];t2=(sha256_rotr(a,2)^sha256_rotr(a,13)^sha256_rotr(a,22))+((a&b)^(a&c)^(b&c));h=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;}
    s->h[0]+=a;s->h[1]+=b;s->h[2]+=c;s->h[3]+=d;s->h[4]+=e;s->h[5]+=f;s->h[6]+=g;s->h[7]+=h;
}
static void sha256_update(struct sha256_state *, const unsigned char *, size_t);
static void sha256_update(struct sha256_state *s,const unsigned char *data,size_t length)
{
    size_t take;s->bits+=(uint64_t)length*8;
    while(length){take=64-s->used;if(take>length)take=length;memcpy(s->block+s->used,data,take);s->used+=take;data+=take;length-=take;if(s->used==64){sha256_transform(s,s->block);s->used=0;}}
}
static void sha256_final(struct sha256_state *, unsigned char [32]);
static void sha256_final(struct sha256_state *s,unsigned char digest[32])
{
    int i;s->block[s->used++]=0x80;if(s->used>56){memset(s->block+s->used,0,64-s->used);sha256_transform(s,s->block);s->used=0;}memset(s->block+s->used,0,56-s->used);
    for(i=0;i<8;++i)s->block[63-i]=(unsigned char)(s->bits>>(i*8));sha256_transform(s,s->block);
    for(i=0;i<8;++i){digest[i*4]=(unsigned char)(s->h[i]>>24);digest[i*4+1]=(unsigned char)(s->h[i]>>16);digest[i*4+2]=(unsigned char)(s->h[i]>>8);digest[i*4+3]=(unsigned char)s->h[i];}
}
int chaos_next_use_sha256(const void *, size_t, unsigned char [32]);
int chaos_next_use_sha256(const void *data,size_t length,unsigned char digest[32])
{
    struct sha256_state state;static const uint32_t initial[8]={0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U};
    if((!data&&length)||!digest)return CHAOS_NEXT_USE_NULL_ARGUMENT;memset(&state,0,sizeof state);memcpy(state.h,initial,sizeof initial);sha256_update(&state,(const unsigned char*)data,length);sha256_final(&state,digest);memset(&state,0,sizeof state);return CHAOS_NEXT_USE_OK;
}

int chaos_next_use_format_logical_id(unsigned long long birthday,
                                    char out[CHAOS_NEXT_USE_LOGICAL_HEX + 1])
{
    if (!out) return 0;
    if (snprintf(out, CHAOS_NEXT_USE_LOGICAL_HEX + 1, "%016llx", birthday)
        != CHAOS_NEXT_USE_LOGICAL_HEX)
        return 0;
    return 1;
}
