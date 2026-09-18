/* NetHack General Public License: small upstream-facing hook surface. */
#ifndef CHAOS_H
#define CHAOS_H
#include "chaos_protocol.h"
#include "chaos_next_use_contract.h"
/* Transient, unsaved delivery identity; available in CHAOS-off callers too. */
struct obj;
struct monst;
struct chaos_observation_token { long root; int fact; };
struct chaos_whistle_witness {
    long root, notice_seq;
    struct chaos_observation_token message_token;
    xchar oldx, oldy, newx, newy;
    int pre_glyph, post_glyph;
    boolean production, active, classifier_ok, pre_public;
    boolean manifestation_delivered, displaced, invalid, finalized;
};
#ifdef CHAOS
#include "chaos_shadow.h"
void chaos_start(void);
void chaos_observe(void);
void chaos_event(const char *, const char *, const char *);
int chaos_event_checked(const char *, const char *, const char *);
void chaos_safe(const char *);
int chaos_ward_count(int);
int chaos_food(int);
long chaos_observation_begin(int);
void chaos_observation_end(long);
void chaos_observation_arm(int, int);
void chaos_observation_disarm(void);
struct chaos_observation_token chaos_observation_take_message(void);
struct chaos_observation_token chaos_observation_take_map(void);
void chaos_observation_delivered(struct chaos_observation_token);
void chaos_observation_map_delivered(struct chaos_observation_token);
void chaos_observation_blocked(void);
boolean chaos_observation_begin_exclusive(int operation, long *root_out);
boolean chaos_observation_finish(long root, int stage, long *end_seq_out);
void chaos_next_use_whistle_completed(struct obj *obj, long completed_root);
boolean chaos_next_use_fountain_contact(long completed_root,
                                        struct chaos_fountain_token *token_out);
void chaos_next_use_fountain_clear(struct chaos_fountain_token *token);
/* Implemented by the later runtime slice; host bridge passes copied/public identity only. */
boolean chaos_next_use_action_preflight(int family, long completed_root);
boolean chaos_next_use_on_action(int family, long completed_root,
                                 struct chaos_fountain_token *token_out);
void chaos_next_use_whistle_unavailable(long completed_root);
void chaos_next_use_capture_whistle(long completed_root, unsigned m_id,
                                    long at_move);
boolean chaos_next_use_whistle_decision_ready(unsigned m_id);
void chaos_next_use_whistle_no_root(unsigned m_id);
boolean chaos_next_use_whistle_attention(unsigned m_id, long decision_root);
boolean chaos_next_use_manifestation_begin(unsigned m_id, long root);
void chaos_next_use_manifestation_notice(long root, long notice_seq);
void chaos_next_use_manifestation_end(long root, long notice_seq,
                                      long end_seq, int success);
boolean chaos_whistle_attention_message(struct chaos_whistle_witness *witness);
void chaos_whistle_witness_finalize(struct monst *mtmp,
                                    struct chaos_whistle_witness *witness);
void chaos_next_use_on_manifestation(const struct chaos_whistle_witness *witness,
                                      long end_seq);
boolean tty_snapshot_projectable(xchar x, xchar y, int glyph);
boolean chaos_tty_publication_certificate(xchar x, xchar y,
                                           int expected_glyph);
#else
#define chaos_shadow_active() (0)
#define chaos_shadow_end(died) ((void)0)
#define chaos_start() ((void)0)
#define chaos_observe() ((void)0)
#define chaos_event(a,b,c) ((void)0)
#define chaos_safe(a) ((void)0)
#define chaos_ward_count(n) (n)
#define chaos_food(n) (n)
#define chaos_observation_begin(operation) (0L)
#define chaos_observation_end(root) ((void)0)
#define chaos_observation_arm(operation,fact) ((void)0)
#define chaos_observation_disarm() ((void)0)
#define chaos_observation_take_message() ((struct chaos_observation_token){0L, CHAOS_OBS_FACT_NONE})
#define chaos_observation_take_map() ((struct chaos_observation_token){0L, CHAOS_OBS_FACT_NONE})
#define chaos_observation_delivered(token) ((void)0)
#define chaos_observation_map_delivered(token) ((void)0)
#define chaos_observation_blocked() ((void)0)
#define chaos_observation_begin_exclusive(operation,root_out) (FALSE)
#define chaos_observation_finish(root,stage,end_seq_out) (FALSE)
#define chaos_next_use_whistle_completed(obj,completed_root) ((void)0)
#define chaos_next_use_fountain_contact(completed_root,token_out) (FALSE)
#define chaos_next_use_fountain_clear(token) ((void)0)
#define chaos_next_use_action_preflight(family,completed_root) (FALSE)
#define chaos_next_use_on_action(family,completed_root,token_out) (FALSE)
#define chaos_next_use_whistle_unavailable(completed_root) ((void)0)
#define chaos_next_use_capture_whistle(completed_root,m_id,at_move) ((void)0)
#define chaos_next_use_whistle_decision_ready(m_id) (FALSE)
#define chaos_next_use_whistle_no_root(m_id) ((void)0)
#define chaos_next_use_whistle_attention(m_id,decision_root) (FALSE)
#define chaos_next_use_manifestation_begin(m_id,root) (FALSE)
#define chaos_next_use_manifestation_notice(root,notice_seq) ((void)0)
#define chaos_next_use_manifestation_end(root,notice_seq,end_seq,success) ((void)0)
#define chaos_whistle_attention_message(witness) (FALSE)
#define chaos_whistle_witness_finalize(mtmp,witness) ((void)0)
#define chaos_next_use_on_manifestation(witness,end_seq) ((void)0)
#define chaos_tty_publication_certificate(x,y,expected_glyph) (FALSE)
#define tty_snapshot_projectable(x,y,glyph) (FALSE)
#define chaos_next_use_fountain_result(token,outcome) ((void)0)
#endif
#endif
