/* NGPL. Reuse the UNCHANGED whole-level fixture and all its curio assertions.
 * This is controlled wizard savebones/getbones, not ordinary play or author
 * acceptance. Bootstrap identities/origins/receipt acknowledgement are synthetic.
 * Public parser/admission/runtime APIs execute real Lua to leave nonzero state
 * and a pending F capability. No witness, target or gameplay outcome is forged.
 * Wrappers only surround real native calls; no serializers are replaced.
 */
#define main curio_bones_main
#include "curio_bones_integration.c"
#undef main
#include "chaos_next_use_runtime.h"
#include "chaos_next_use_safe.h"

void __real_savebones(struct obj *);
int __real_getbones(void);
static int receiver_owned, receipt_count;
static const char donor_source[] =
    "return {on_action=function(c) return {next_use_intent_v=2,op='quiet',state=1} end} --NEXT_USE_BONES_DONOR";
static const char receiver_source[] =
    "return {on_action=function(c) return {next_use_intent_v=2,op='quiet',state=2} end} --NEXT_USE_BONES_RECEIVER";

static void retain(const char *name, const void *data, size_t length)
{
    FILE *f = fopen(name, "wb");
    assert(f && fwrite(data, 1, length, f) == length);
    assert(!fclose(f));
}

static int receipt(void *unused, const struct chaos_next_use_private_record *r)
{
    (void)unused;
    assert(r && r->kind == CHAOS_PRIVATE_ADMISSION);
    ++receipt_count;
    retain("synthetic-receipt.bin", r, sizeof *r);
    return 1; /* Explicit synthetic acknowledgement, NOT journal durability. */
}

static void bootstrap(int donor)
{
    const char *lua = donor ? donor_source : receiver_source;
    char raw[CHAOS_NEXT_USE_ENVELOPE_MAX + 1], canonical[CHAOS_NEXT_USE_ENVELOPE_MAX + 1];
    char hash[65], run[65];
    unsigned char sha[32];
    size_t length;
    int i, n;
    struct chaos_next_use_envelope env;
    struct chaos_next_use_admission initial, admitted;
    struct chaos_next_use_attempt_gate gate = {CHAOS_ATTEMPT_OPEN, 0};
    struct chaos_fountain_token unused;
    struct chaos_next_use_snapshot s;
    assert(chaos_next_use_save_status() == CHAOS_SNAPSHOT_ABSENT);
    assert(chaos_next_use_sha256(lua, strlen(lua), sha) == CHAOS_NEXT_USE_OK);
    for (i = 0; i < 32; ++i) sprintf(hash + i * 2, "%02x", sha[i]);
    /* Synthetic 64-hex origin transport identity, distinct from the native
     * logical game token; no pathname or same-candidate identity validation. */
    memset(run, donor ? 'a' : 'b', 64); run[64] = '\0';
    n = snprintf(raw, sizeof raw,
        "{\"at\":7,\"cost\":2,\"id\":1,\"next_use_program_v\":2,"
        "\"operations\":[\"W\",\"F\"],\"origin_refs\":["
        "{\"end_seq\":12,\"fact\":\"ordinary_whistle\",\"family\":\"W\","
        "\"level_dlevel\":2,\"level_dnum\":1,\"move\":%ld,"
        "\"notice_seq\":11,\"root\":10,\"run\":\"%s\"},"
        "{\"end_seq\":22,\"fact\":\"water_refreshed\",\"family\":\"F\","
        "\"level_dlevel\":2,\"level_dnum\":1,\"move\":%ld,"
        "\"notice_seq\":21,\"root\":20,\"run\":\"%s\"}],"
        "\"source\":\"%s\",\"source_sha256\":\"%s\","
        "\"telegraph\":\"next-use-v2-WF\",\"ttl\":100,\"variant\":0}",
        monstermoves, run, monstermoves, run, lua, hash);
    assert(n > 0 && (size_t)n < sizeof raw);
    assert(chaos_next_use_jcs(raw, (size_t)n, canonical, sizeof canonical, &length)
           == CHAOS_NEXT_USE_OK);
    assert(chaos_next_use_parse_envelope(canonical, length, &env) == CHAOS_NEXT_USE_OK);
    retain("synthetic-envelope.json", canonical, length);
    retain("programme.lua", lua, strlen(lua));
    memset(&initial, 0, sizeof initial);
    initial.budget_state = u.chaos;
    assert(chaos_next_use_admit(&admitted, &initial, &gate, &env, canonical,
           length, 0, (int)monstermoves, 1, receipt, NULL) == CHAOS_NEXT_USE_ADMISSION_OK);
    assert(chaos_next_use_runtime_install(&admitted, lua, strlen(lua), hash,
           u.chaos_game_token, chaos_next_use_pack_level(u.uz.dnum, u.uz.dlevel),
           10, monstermoves + 100, 20, monstermoves + 100, 0, 1, 1));
    /* Synthetic admission bridge, no production setter or ordinary safe point. */
    u.chaos = admitted.budget_state;
    u.chaos_next_use_attempted = 1;
    assert(chaos_next_use_safe_restore_attempted(1));
    assert(chaos_next_use_action_preflight(CHAOS_NEXT_USE_FAMILY_W, 30));
    /* Quiet executes Lua and commits state, but requests no native effect. */
    assert(!chaos_next_use_on_action(CHAOS_NEXT_USE_FAMILY_W, 30, &unused));
    assert(chaos_next_use_snapshot_export(&s));
    assert(s.state == (donor ? 1 : 2) && s.callback_ordinal == 1);
    assert(s.slot_w == CHAOS_SLOT_W_CONSUMED_QUIET && s.slot_f == CHAOS_SLOT_F_PENDING);
    assert(s.armed_m_id == 0 && !s.attention_claimed && !s.witnessed);
    assert(u.chaos.spent == 2 && receipt_count == 1);
}

static void snapshot(const char *name, struct chaos_next_use_snapshot *s)
{
    char path[80];
    int valid = chaos_next_use_snapshot_export(s);
    FILE *f;
    assert(chaos_next_use_save_status() == (valid ? CHAOS_SNAPSHOT_VALID : CHAOS_SNAPSHOT_ABSENT));
    snprintf(path, sizeof path, "%s.snapshot.bin", name);
    retain(path, s, sizeof *s); /* Native diagnostic struct, NOT a portable codec. */
    snprintf(path, sizeof path, "%s.json", name);
    f = fopen(path, "w"); assert(f);
    /* Fixture sources contain neither double quotes nor line breaks. */
    fprintf(f, "{\"valid\":%d,\"source\":\"%s\",\"source_sha256\":\"%s\","
        "\"binding_sha256\":\"%s\",\"run_token\":%ld,\"level_token\":%ld,"
        "\"player_token\":%ld,\"state\":%d,\"slot_w\":%d,\"slot_f\":%d,"
        "\"callback_ordinal\":%d,\"armed_m_id\":%u,\"attention_claimed\":%d,"
        "\"witnessed\":%d,\"spent\":%d,\"attempted\":%d,\"player_attempted\":%d,"
        "\"monstermoves\":%ld,\"admission_move\":%d,\"program_expiry\":%d,"
        "\"origin_w_deadline\":%ld,\"origin_f_deadline\":%ld,"
        "\"private_count\":%lu,\"public_count\":%lu,\"receipt_count\":%d}\n",
        valid, s->source, s->source_sha256, s->binding_sha256,
        s->run_token, s->level_token, u.chaos_game_token, s->state, s->slot_w, s->slot_f,
        s->callback_ordinal, s->armed_m_id, s->attention_claimed, s->witnessed,
        u.chaos.spent, chaos_next_use_safe_attempted(), u.chaos_next_use_attempted,
        monstermoves, s->admission_move, s->program_expiry,
        s->origin_w_deadline, s->origin_f_deadline,
        (unsigned long)chaos_next_use_runtime_private_count(),
        (unsigned long)chaos_next_use_runtime_public_count(), receipt_count);
    assert(!fclose(f));
}

static int boundary(int donor, struct obj *corpse)
{
    struct chaos_next_use_snapshot before, after;
    struct chaos_state budget;
    size_t private_count, public_count;
    int attempted, result = 0;
    long player_token;
    /* getbones entry is AFTER unchanged readback's monstermoves=200. Admit
     * the receiver here with the normal fixed 100-move TTL, never extend it. */
    assert(monstermoves == (donor ? 100 : 200));
    u.chaos_game_token = donor ? 111 : 222; /* Independently fixed fixture identity. */
    chaos_state_init(&u.chaos);
    if (donor || receiver_owned) bootstrap(donor);
    snapshot("before", &before);
    budget = u.chaos; player_token = u.chaos_game_token;
    attempted = chaos_next_use_safe_attempted();
    private_count = chaos_next_use_runtime_private_count();
    public_count = chaos_next_use_runtime_public_count();
    if (donor) __real_savebones(corpse);
    else {
        result = __real_getbones();
        assert(result == 1 && has_loaded_bones);
        puts("next-use: getbones=1; has_loaded_bones=1");
    }
    /* No runtime reset, import or normalization after the real bones call. */
    snapshot("after", &after);
    assert(!memcmp(&before, &after, sizeof before));
    assert(!memcmp(&budget, &u.chaos, sizeof budget));
    assert(u.chaos_game_token == player_token);
    assert(chaos_next_use_safe_attempted() == attempted);
    assert(chaos_next_use_runtime_private_count() == private_count);
    assert(chaos_next_use_runtime_public_count() == public_count);
    return result;
}
void __wrap_savebones(struct obj *corpse) { (void)boundary(1, corpse); }
int __wrap_getbones(void) { return boundary(0, NULL); }

int main(int argc, char **argv)
{
    char *args[3];
    assert(argc == 2);
    assert(!strcmp(argv[1], "publish") || !strcmp(argv[1], "absent") || !strcmp(argv[1], "owned"));
    receiver_owned = !strcmp(argv[1], "owned");
    args[0] = argv[0]; args[1] = !strcmp(argv[1], "publish") ? "publish" : "consume"; args[2] = NULL;
    return curio_bones_main(2, args);
}
