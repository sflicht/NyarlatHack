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
W_ARMED, W_WITNESSED, F_REMAPPED = 1, 3, 12
ORIGIN_TTL = 100  # engine: origin expiry is move + 100


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


def _publication_loss(events, envelope, origin_turn):
    """Why a published envelope was not admitted, from public timing only.

    The engine checks an envelope once, at the safe point whose index equals
    envelope["at"], and rejects it if that safe point is on another level or
    more than 100 moves after the origin. Events carry `turn` (moves), which
    this inference uses in place of the engine's monstermoves.
    """
    at = envelope["at"]
    for e in events:
        if e["event"] == "safe_point" and e["safe"] == at:
            if e["detail"] == "level_enter":
                return "level_changed_before_safe_point"
            if origin_turn is not None and e["turn"] > origin_turn + ORIGIN_TTL:
                return "origin_expired_before_safe_point"
            if e["budget"] < envelope["cost"]:
                return "budget"
            return "rejected_at_safe_point_other"
    return "no_safe_point_before_game_end"


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

    journal_status = None
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

    origin_turn = None
    if envelope is not None:
        origin = envelope["origin_refs"][0]
        by_seq = {e["seq"]: e for e in events}
        if origin["end_seq"] in by_seq:
            origin_turn = by_seq[origin["end_seq"]]["turn"]

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
        loss = _publication_loss(events, envelope, origin_turn)
    elif not counts["trigger"]:
        loss = "admitted_no_trigger:" + (
            TERMINATION.get(terminations[0]["data"]["reason"], "?")
            if terminations
            else "game_ended"
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
        "terminations": [
            TERMINATION.get(t["data"]["reason"], "?") for t in terminations
        ],
        "public_attention_completed": len(public_attention),
        "ordinary_whispers_admitted": sum(
            1 for w in ordinary_whispers if w.get("status") == "admitted"
        ),
        "last_turn": events[-1]["turn"] if events else None,
    }
