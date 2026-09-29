"""Per-game engine-stage funnel for the seed sweep (#167).

Reads only files a game already writes: events.jsonl, next_use-schedule.jsonl,
next_use-envelope.json, next_use-receipt.jsonl, next_use-journal.jsonl and
director.log. Engine stages only; player notice, attribution and decision
change are human-only (#44) and are never inferred here.
"""

import json
from pathlib import Path

from chaos.next_use_journal import JournalError, read_journal

QUALIFYING = {
    "whistling": {
        "sound_high",
        "sound_shrill",
        "sound_normal",
        "sound_strange",
        "sound_humming",
    },
    "fountain_drink": {"water_refreshed"},
}
STAGES = (
    "qualifying_history",
    "candidate",
    "published",
    "admitted",
    "trigger",
    "native_effect",
    "delivered",
)
TERMINATION = {
    1: "completed",
    2: "level_departure",
    3: "origin_evicted",
    4: "origin_expired",
    5: "program_expired",
    6: "invalid_callback",
    7: "identity_unsafe",
}
W_ARMED, W_CAPTURE_SUPPRESSED, W_WITNESSED, F_REMAPPED = 1, 2, 3, 12
# #196: chaos_next_use_w_suppression, recorded on the W_CAPTURE_SUPPRESSED row.
W_SUPPRESSION = {
    0: "unrecorded",
    1: "none_in_view",
    2: "not_eligible",
    3: "recheck_failed",
}
FAMILY_OPERATION = {"W": "whistling", "F": "fountain_drink"}
ORIGIN_TTL = 300  # engine: CHAOS_NEXT_USE_ORIGIN_LIFETIME


def _rows(path):
    return (
        [json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
    )


def _director_statuses(run):
    log = run / "director.log"
    if not log.exists():
        return []
    prefix = "chaos: next-use: "
    return [
        s[len(prefix) :] for s in log.read_text().splitlines() if s.startswith(prefix)
    ]


def _publication_loss(events, envelope, qualifying):
    """Likely reason a published envelope was not admitted. INFERRED; used
    only when the engine wrote no decision row (the envelope was never
    evaluated, or the run predates #177's recorded reasons).

    The engine checks an envelope at the safe point whose index equals
    envelope["at"]; it rejects it if any origin is on another level, older than
    ORIGIN_TTL monster moves, or no longer the bound origin for its family (a newer
    qualifying notice replaces it). This uses public `turn` for monstermoves,
    and the safe_point event's budget, which is read before ordinary whisper
    admission and so may exceed the budget at the next-use debit. Every label
    is prefixed "inferred:".
    """
    at = envelope["at"]
    target = next(
        (e for e in events if e["event"] == "safe_point" and e["safe"] == at), None
    )
    if target is None:
        return "inferred:no_safe_point_before_game_end"
    by_seq = {e["seq"]: e for e in events}
    for origin in envelope["origin_refs"]:
        op = FAMILY_OPERATION.get(origin.get("family"))
        if any(
            origin["end_seq"] < q["seq"] < target["seq"]
            and q["observation"]["operation"] == op
            for q in qualifying
        ):
            return "inferred:origin_superseded_before_safe_point"
    if target["detail"] == "level_enter":
        return "inferred:level_changed_before_safe_point"
    for origin in envelope["origin_refs"]:
        start = by_seq.get(origin["end_seq"])
        if start is not None and target["turn"] > start["turn"] + ORIGIN_TTL:
            return "inferred:origin_expired_before_safe_point"
    if target["budget"] < envelope["cost"]:
        return "inferred:budget"
    return "inferred:rejected_at_safe_point_other"


def analyse(game_root):
    root = Path(game_root)
    run = root / "run"
    events = _rows(run / "events.jsonl")
    sessions = [e for e in events if e["event"] == "session"]
    safe_points = [e for e in events if e["event"] == "safe_point"]
    completed = [
        e
        for e in events
        if (o := e.get("observation"))
        and o["stage"] == "completed"
        and o["operation"] in QUALIFYING
    ]
    # A notice and its completion both carry root_seq = the started event.
    notice_facts = {}
    for e in events:
        o = e.get("observation")
        if o and o["stage"] == "notice":
            notice_facts.setdefault(o["root_seq"], set()).add(o["fact"])
    qualifying = [
        e
        for e in completed
        if notice_facts.get(e["observation"]["root_seq"], set())
        & QUALIFYING[e["observation"]["operation"]]
    ]
    actions = {
        op: sum(
            1
            for e in events
            if (o := e.get("observation"))
            and o["stage"] == "started"
            and o["operation"] == op
        )
        for op in QUALIFYING
    }
    schedule = _rows(run / "next_use-schedule.jsonl")
    statuses = _director_statuses(run)
    envelope_path = run / "next_use-envelope.json"
    envelope = json.loads(envelope_path.read_text()) if envelope_path.exists() else None
    receipts = _rows(run / "next_use-receipt.jsonl")
    decisions = [r for r in receipts if "next_use_decision_v" in r]

    journal_status = "missing"
    private, transitions = [], []
    journal = run / "next_use-journal.jsonl"
    if journal.exists():
        try:
            decoded = read_journal(journal)
            journal_status = decoded["status"]
            for r in decoded["records"]:
                private.extend(r["data"].get("private_records", []))
                if r["kind"] == "transition":
                    transitions.append(r["data"])
        except JournalError as exc:
            journal_status = "invalid: " + str(exc)[:80]
    admissions = [p for p in private if p["kind"] == 2]
    intents = [p for p in private if p["kind"] == 3]
    effects = [p for p in private if p["kind"] == 4]
    terminations = [p for p in private if p["kind"] == 5]
    public_attention = [
        e
        for e in events
        if (o := e.get("observation"))
        and o["operation"] == "whistle_attention"
        and o["stage"] == "completed"
    ]
    native = [e for e in effects if e["data"]["outcome"] in (W_ARMED, F_REMAPPED)]
    delivered = [
        e for e in effects if e["data"]["outcome"] in (W_WITNESSED, F_REMAPPED)
    ]

    counts = {
        "qualifying_history": len(qualifying),
        "candidate": len(schedule),
        "published": int(envelope is not None),
        "admitted": max(
            len(admissions), sum(1 for r in receipts if r.get("kind") == 2)
        ),
        "trigger": len(intents),
        "native_effect": len(native),
        "delivered": len(delivered),
    }

    # Later stages come only from the journal. Absent or partial evidence is
    # unknown, not zero: a game is a definite zero-delivery game only when it
    # was never admitted, or its journal is structurally complete.
    if not counts["admitted"] or counts["delivered"]:
        delivery_known = True
    else:
        delivery_known = journal_status == "structurally_complete"

    if not counts["qualifying_history"]:
        loss = "no_qualifying_action"
    elif not counts["candidate"]:
        loss = "no_engine_candidate"
    elif not counts["published"]:
        loss = (
            "director_abstained"
            if "abstained" in statuses
            else "director_failed"
            if "failed" in statuses
            else "not_published_before_game_end"
        )
    elif not counts["admitted"]:
        # #177: the engine writes a decision row with every failing check.
        # Only games without one (not yet evaluated) fall back to inference.
        loss = (
            "rejected:" + "+".join(decisions[-1]["reasons"])
            if decisions
            else _publication_loss(events, envelope, qualifying)
        )
    elif not delivery_known:
        loss = "admitted_trace_" + (
            "invalid" if journal_status.startswith("invalid") else journal_status
        )
    elif not counts["trigger"]:
        if any(e["data"]["outcome"] == W_CAPTURE_SUPPRESSED for e in effects):
            # Engine skips the callback when there is not exactly one target.
            loss = "admitted_no_trigger:whistle_capture_suppressed"
        else:
            loss = "admitted_no_trigger:" + (
                TERMINATION.get(terminations[0]["data"]["reason"], "?")
                if terminations
                else "no_termination_record"
            )
    elif not counts["native_effect"]:
        loss = "trigger_no_native_effect"
    elif not counts["delivered"]:
        loss = "native_effect_not_delivered"
    else:
        loss = None

    first_admission = min((a["at_move"] for a in admissions), default=None)
    ordinary_whispers = _rows(run / "whispers.jsonl")
    return {
        "counts": counts,
        "delivery_known": delivery_known,
        "loss": loss,
        "first_admission_move": first_admission,
        "qualifying_actions": actions,
        "safe_points": {
            d: sum(1 for e in safe_points if e["detail"] == d)
            for d in sorted({e["detail"] for e in safe_points})
        },
        "start_budget": sessions[0]["budget"] if sessions else None,
        "start_sanity": sessions[0]["sanity"] if sessions else None,
        "session_details": [e["detail"] for e in sessions],
        "journal_status": journal_status,
        "effect_outcomes": sorted(e["data"]["outcome"] for e in effects),
        # #196: why each W capture was suppressed (the effect row's recorded
        # reason; "unrecorded" for journals written before #196).
        "w_suppressions": [
            W_SUPPRESSION.get(e["data"].get("suppression", 0), "?")
            for e in effects
            if e["data"]["outcome"] == W_CAPTURE_SUPPRESSED
        ],
        "terminations": [
            TERMINATION.get(t["data"]["reason"], "?") for t in terminations
        ],
        "public_attention_completed": len(public_attention),
        "ordinary_whispers_admitted": sum(
            1 for w in ordinary_whispers if w.get("status") == "admitted"
        ),
        "recorded_decisions": [
            {k: d[k] for k in ("at", "safe", "move", "reasons")} for d in decisions
        ],
        "last_turn": events[-1]["turn"] if events else None,
    }
