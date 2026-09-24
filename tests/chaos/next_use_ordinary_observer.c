/* TEST-ONLY POST-HOC OBSERVER. No game-state writes or RNG calls.
 * Only two wrappers, each invokes the unchanged real hook first.
 * Outputs never guide gameplay decisions; they are read only posthoc.
 */
#include "hack.h"
#include "chaos.h"
#include "chaos_next_use_runtime.h"
#include <errno.h>

extern void __real_chaos_start(void);
extern void __real_chaos_observe(void);

static void export_observation(const char *hook)
{
    struct chaos_next_use_snapshot s;
    struct chaos_next_use_capture_status c;
    int saved_errno = errno;
    int valid = chaos_next_use_snapshot_export(&s);
    size_t i;
    FILE *f;
    chaos_next_use_capture_status(&c);
    f = fopen("ordinary-observer.jsonl", "a");
    if (f) {
        fprintf(f, "{\"hook\":\"%s\",\"moves\":%ld,\"monstermoves\":%ld,"
            "\"game_token\":%ld,\"sanity\":%d,\"budget\":%d,\"spent\":%d,"
            "\"attempted\":%d,\"wizard\":%d,\"discover\":%d,\"snapshot_valid\":%d,"
            "\"sink_connected\":%d,\"incomplete\":%d,\"transaction_open\":%d,"
            "\"acknowledged_cursor\":%lu,\"snapshot\":{\"present\":%d",
            hook, moves, monstermoves, u.chaos_game_token, u.usanity,
            chaos_budget(&u.chaos, u.usanity), u.chaos.spent,
            u.chaos_next_use_attempted, (int)wizard, (int)discover, valid,
            c.sink_connected, c.incomplete, c.transaction_open,
            c.acknowledged_cursor, valid);
        if (valid) {
#define N(k) fprintf(f, ",\"" #k "\":%ld", (long)s.k)
            N(snapshot_v); N(program_id); N(phase); N(slot_w); N(slot_f);
            N(w_runtime); N(state); N(delay_used); N(callback_ordinal);
            N(witnessed); N(attention_claimed); N(whistle_count); N(fountain_count);
            N(next_seq); N(termination_emitted); N(identity_unsafe);
            N(callback_w); N(callback_f); N(last_root); N(admission_move);
            N(program_expiry); N(delay_until); N(variant); N(origin_w_live);
            N(origin_f_live); N(armed_m_id); N(replay_cursor); N(journal_state);
            N(capture_incomplete); N(journal_bytes); N(origin_w); N(origin_f);
            N(origin_w_deadline); N(origin_f_deadline); N(run_token); N(level_token);
            N(activation_monstermoves); N(armed_root); N(source_length);
#undef N
            fprintf(f, ",\"journal_sha256\":\"%s\",\"source_sha256\":\"%s\","
                "\"binding_sha256\":\"%s\",\"source_hex\":\"",
                s.journal_sha256, s.source_sha256, s.binding_sha256);
            for (i = 0; i < s.source_length; ++i)
                fprintf(f, "%02x", (unsigned char)s.source[i]);
            fprintf(f, "\"");
        }
        fprintf(f, "}}\n");
        fclose(f);
    }
    errno = saved_errno;
}

void __wrap_chaos_start(void)
{
    __real_chaos_start();
    export_observation("start");
}

void __wrap_chaos_observe(void)
{
    __real_chaos_observe();
    export_observation("observe");
}
