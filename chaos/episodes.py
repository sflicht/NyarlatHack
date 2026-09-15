"""Offline row schemas and episode projection; NGPL, see dat/license.

Row parsing validates only a row, not history, root existence, same-operation/turn
linkage, marker sequencing, completion, or actual native delivery. Projection
validates history and links, but cannot authenticate the source or delivery.
Whistling facts never establish ordinary/magic identity or obedience.
"""

from collections import deque
import json

from .director import DEFAULT_BYTES, DEFAULT_EVENTS
from .protocol import MAX_INT, NUMBERS, VITALS, integer, parse_event, strict_json

_ENVELOPE = frozenset((*NUMBERS, "event", "phase", "detail", "vitals", "observation"))
_OBSERVATION = frozenset(("operation", "stage", "root_seq", "fact"))
_FACTS = {
    "whistling": frozenset(
        ("sound_high", "sound_shrill", "sound_normal", "sound_strange", "sound_humming")
    ),
    "fountain_drink": frozenset(
        ("water_refreshed", "water_foul", "cannot_reach", "detection_presented")
    ),
}


def parse_episode_event(raw) -> dict:
    """Validate one bounded JSON row, preserving the legacy v1 parser contract.

    V2 has a 4096-byte cap, including UTF-8 encoding of string input. V1 retains
    its original raw-input semantics, including optional vitals and extra keys.
    Returned legacy fields are not a redacted public projection.
    """
    if not isinstance(raw, (str, bytes, bytearray)):
        raise ValueError("JSON text or bytes required")
    row = strict_json(raw, 4096)
    integer(row.get("v"))
    if row["v"] == 1:
        # The legacy parser indexes/hashes event directly. Validate this one
        # prerequisite so malformed rows raise ValueError, not KeyError/TypeError;
        # do not catch exceptions that could mask implementation bugs.
        if type(row.get("event")) is not str:
            raise ValueError("invalid legacy event name")
        return parse_event(raw)
    if row["v"] != 2:
        raise ValueError("unsupported observation version")
    if isinstance(raw, str):
        try:
            size = len(raw.encode("utf-8"))
        except UnicodeError as exc:
            raise ValueError("invalid observation encoding") from exc
        if size > 4096:
            raise ValueError("JSON byte cap exceeded")
    if set(row) != _ENVELOPE:
        raise ValueError("invalid observation envelope fields")
    for key in NUMBERS:
        integer(row[key], 1 if key == "seq" else 0)
    if row["event"] != "observation" or row["detail"] != "":
        raise ValueError("invalid observation envelope")
    if row["sanity"] > 100 or any(
        row[key] > 12 for key in ("budget", "spent", "reserved")
    ):
        raise ValueError("invalid event budget or sanity")
    if row["reserved"] > row["spent"]:
        raise ValueError("invalid reservation")
    vitals = row["vitals"]
    if type(vitals) is not dict or set(vitals) != set(VITALS):
        raise ValueError("invalid vitals fields")
    for key in VITALS:
        integer(vitals[key], -MAX_INT if key == "power" else 0)
    payload = row["observation"]
    if type(payload) is not dict or set(payload) != _OBSERVATION:
        raise ValueError("invalid observation fields")
    operation, stage, fact = (payload[key] for key in ("operation", "stage", "fact"))
    if any(type(value) is not str for value in (operation, stage, fact)):
        raise ValueError("observation enums must be strings")
    root = integer(payload["root_seq"])
    if stage == "enabled":
        valid = operation == "none" and root == 0 and fact == "none"
    elif stage == "started":
        valid = operation in _FACTS and root == 0 and fact == "none"
    elif stage in ("notice", "completed", "blocked"):
        valid = operation in _FACTS and 0 < root < row["seq"]
        if stage == "notice":
            valid = valid and fact in _FACTS[operation]
        else:
            valid = valid and fact == "none"
            if stage == "blocked":
                valid = valid and operation == "fountain_drink"
    else:
        valid = False
    if not valid or row["phase"] != ("attempt" if stage == "started" else "result"):
        raise ValueError("invalid observation combination")
    return row


def _count(value):
    return dict(count=min(3, value), saturated=value > 3)


def project_episodes(raw: bytes) -> dict:
    """Validate complete native chronology, then project only selected evidence.

    Like the authoring history validator, the first session is result/new and
    later sessions are result/restore. No save event is required: native saves
    have no dedicated event. Counters never reset, even when observations turn
    off on restore. Schema/history validation is not source authentication.
    """
    if not isinstance(raw, bytes) or not raw or not raw.endswith(b"\n"):
        raise ValueError("complete nonempty native bytes required")
    if len(raw) > DEFAULT_BYTES or raw.count(b"\n") > DEFAULT_EVENTS:
        raise ValueError("native history cap exceeded")
    previous = active = None
    roots = deque(maxlen=32)
    omitted = 0
    seen_session = opted = pending_marker = ended = False
    for seq, line in enumerate(raw.split(b"\n")[:-1], 1):
        row = parse_episode_event(line)
        if row["seq"] != seq or ended:
            raise ValueError("sequence gap or event after death")
        if previous and any(
            row[k] < previous[k] for k in ("turn", "safe", "spent", "last_id")
        ):
            raise ValueError("native counter rollback")
        marker = row["v"] == 2 and row["observation"]["stage"] == "enabled"
        native_session = row["v"] == 1 and row["event"] == "session"
        if pending_marker and not native_session:
            raise ValueError("enabled marker must immediately precede session")
        if not seen_session:
            if not (marker or native_session):
                raise ValueError("full new-session history required")
            if any(row[k] for k in ("safe", "spent", "reserved", "last_id")):
                raise ValueError("invalid fresh counters")
        if native_session:
            if row["phase"] != "result" or row["detail"] != (
                "restore" if seen_session else "new"
            ):
                raise ValueError("conflicting session chain")
            seen_session = True
            roots.clear()
            omitted = 0
            opted, pending_marker = pending_marker, False
        elif marker:
            pending_marker = True
        elif row["v"] == 2:
            if not opted:
                raise ValueError("observation requires session marker")
            payload = row["observation"]
            operation, stage = payload["operation"], payload["stage"]
            if stage == "started":
                active = dict(
                    root_seq=seq,
                    turn=row["turn"],
                    operation=operation,
                    notice_seq=None,
                    fact=None,
                    end_seq=None,
                    stage="incomplete",
                )
                omitted += len(roots) == roots.maxlen
                roots.append(active)
            else:
                if (
                    active is None
                    or payload["root_seq"] != active["root_seq"]
                    or operation != active["operation"]
                    or row["turn"] != active["turn"]
                    or active["end_seq"] is not None
                ):
                    raise ValueError("invalid active root reference")
                if stage == "notice":
                    if active["notice_seq"] is not None:
                        raise ValueError("duplicate notice")
                    active.update(notice_seq=seq, fact=payload["fact"])
                else:
                    if stage == "completed" and active["fact"] == "cannot_reach":
                        raise ValueError("cannot_reach requires blocked terminal")
                    active.update(end_seq=seq, stage=stage)
        if row["v"] == 1 and row["event"] in (
            "session",
            "level_enter",
            "level_leave",
            "death",
        ):
            active = None
        if row["event"] == "death" and row["phase"] == "result":
            ended = True
        previous = row
    if pending_marker:
        raise ValueError("dangling enabled marker")
    groups = []
    coverage = dict(
        incomplete=sum(r["stage"] == "incomplete" for r in roots),
        blocked=sum(r["stage"] == "blocked" for r in roots),
        completed_without_notice=sum(
            r["stage"] == "completed" and r["notice_seq"] is None for r in roots
        ),
        omitted_roots=omitted,
    )
    coverage = {key: _count(value) for key, value in coverage.items()}
    for operation in sorted(_FACTS):
        qualifying = [
            r
            for r in roots
            if r["operation"] == operation
            and r["stage"] == "completed"
            and r["notice_seq"] is not None
        ]
        if qualifying:
            selected = (
                qualifying if len(qualifying) <= 3 else qualifying[:2] + qualifying[-1:]
            )
            groups.append(
                dict(
                    operation=operation,
                    **_count(len(qualifying)),
                    evidence=[
                        {k: r[k] for k in ("root_seq", "notice_seq", "end_seq", "fact")}
                        for r in selected
                    ],
                )
            )
    public = dict(
        episode_context_v=1,
        scope="selected_whistle_fountain",
        lookback_roots=32,
        episodes=groups,
        coverage=coverage,
    )
    encoded = json.dumps(
        public, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    if len(encoded) > 4096:
        raise ValueError("episode summary byte cap exceeded")
    return public
