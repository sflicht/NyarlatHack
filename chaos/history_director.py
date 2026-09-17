"""Opt-in checked history runner. NGPL; see dat/license.

The final full read verifies publication eligibility at an instant, not an atomic
binding to C admission. Native schedule/budget/active guards remain authoritative.
The returned host-only receipt is not model context or witnessed rule application.
"""

import copy
import os
from pathlib import Path
import time

from . import curio_continuity as continuity, curio_store as store
from .director import (
    DEFAULT_BYTES,
    DEFAULT_EVENTS,
    Mailbox,
    ScheduleBackend,
    secure_open,
    require_current_replay,
    replay_request,
)
from .history import (
    IncompleteHistory,
    candidate_requests,
    public_context,
    snapshot_history,
)
from .protocol import encode_request, parse_request, strict_json


def _exact_source(directory, proof, max_bytes):
    with store._directory(directory) as fd:
        _, event = continuity._file(fd, "events.jsonl", max_bytes)
        return dict(directory=continuity._inode(os.fstat(fd)), event=event) == proof


def load_history_replay(journal, evidence):
    """Require original mixed native accepted ACKs, never journal-only proof."""
    evidence = Path(evidence)
    if evidence.name != "events.jsonl":
        raise ValueError("original events.jsonl evidence required")
    state, proof = snapshot_history(evidence.parent)
    require_current_replay(state)
    requests = []
    with os.fdopen(secure_open(journal), "rb") as f:
        if os.fstat(f.fileno()).st_size > DEFAULT_BYTES:
            raise ValueError("journal byte cap exceeded")
        total = 0
        while line := f.readline(4097):
            total += len(line)
            if total > DEFAULT_BYTES or len(requests) >= DEFAULT_EVENTS:
                raise ValueError("journal cap exceeded")
            if not line.endswith(b"\n"):
                raise ValueError("partial admission journal")
            row = strict_json(line, 4096)
            requests.append(replay_request(row, state))
    ScheduleBackend(requests)
    if not _exact_source(evidence.parent, proof, DEFAULT_BYTES):
        raise ValueError("original replay evidence changed")
    return requests


def run_history(
    directory,
    backend,
    *,
    ordinary_food=False,
    max_runtime=300.0,
    poll=0.25,
    max_bytes=DEFAULT_BYTES,
    max_events=DEFAULT_EVENTS,
    install_only=False,
):
    """One selector attempt, or exact schedule replay; no retry or retiming."""
    if (
        type(ordinary_food) is not bool
        or type(install_only) is not bool
        or type(max_runtime) not in (int, float)
        or not 0 < max_runtime <= 86400
        or type(poll) not in (int, float)
        or not 0.01 <= poll <= 60
        or type(max_bytes) is not int
        or not 0 < max_bytes <= DEFAULT_BYTES
        or type(max_events) is not int
        or not 0 < max_events <= DEFAULT_EVENTS
    ):
        raise ValueError("invalid history limits")
    deadline = time.monotonic() + max_runtime
    if hasattr(backend, "deadline"):
        backend.deadline = min(backend.deadline, deadline)
    replay = isinstance(backend, ScheduleBackend)
    proof = state = known = decision = None
    submitted = accepted = rejected = 0
    reason = "runtime_cap"

    def snapshot():
        if proof is not None:
            snapshot_history(directory, checkpoint=proof)
        current, checkpoint = snapshot_history(directory)
        if proof is not None:
            # Do not adopt a replacement prefix raced between the old check
            # and this full read, even while the candidate domain is quiet.
            snapshot_history(directory, checkpoint=proof)
        if (
            checkpoint["event"]["length"] > max_bytes
            or current.latest["seq"] > max_events
        ):
            raise ValueError("history runtime source cap exceeded")
        return current, checkpoint

    with Mailbox(directory) as box:
        while time.monotonic() < deadline:
            try:
                state, proof = snapshot()
            except FileNotFoundError:
                if proof is not None:
                    raise
                time.sleep(min(poll, max(0, deadline - time.monotonic())))
                continue
            except IncompleteHistory:
                time.sleep(min(poll, max(0, deadline - time.monotonic())))
                continue
            pending = box.pending(state, known=known)
            if known is not None and pending is None:
                admission = state.acks.get(known["id"])
                if admission is None or admission["request"] != known:
                    raise ValueError("missing exact pending ACK")
                outcome = (
                    "accepted"
                    if state.accepted.get(known["id"]) == known
                    else "rejected"
                )
                accepted += outcome == "accepted"
                rejected += outcome == "rejected"
                if decision is not None:
                    decision["outcome"] = outcome
                known = None
                if not replay:
                    reason = outcome
                    break
                if outcome == "rejected":
                    raise ValueError("replay request rejected")
            known = dict(pending) if pending is not None else None
            if state.ended:
                reason = "death"
                break
            if pending is None and state.enabled:
                if replay:
                    selected = backend.next(state)
                    if selected is None:
                        reason = "schedule_complete"
                        break
                    menu = [parse_request(encode_request(selected))]
                else:
                    menu = candidate_requests(state, ordinary_food)
                    selected = None
                if menu:
                    if not replay and getattr(backend, "attempts", 0) >= getattr(
                        backend, "max_attempts", 1
                    ):
                        reason = "exhausted"
                        break
                    frozen = copy.deepcopy(menu)
                    checkpoint = copy.deepcopy(proof)
                    decision = dict(
                        checkpoint=checkpoint,
                        candidates=frozen,
                        selected=None,
                        outcome="pending",
                    )
                    if not replay:
                        selected = backend.choose(
                            public_context(state), copy.deepcopy(frozen)
                        )
                    if selected is None:
                        reason = "abstained"
                        break
                    selected = parse_request(encode_request(selected))
                    if selected not in frozen:
                        raise ValueError("selection outside frozen history menu")
                    decision["selected"] = selected
                    try:
                        current, new_proof = snapshot()
                    except IncompleteHistory:
                        reason = "stale"
                        break
                    if new_proof != checkpoint:
                        reason = "stale"
                        break
                    if (
                        not current.enabled
                        or box.pending(current) is not None
                        or (
                            not replay
                            and candidate_requests(current, ordinary_food) != frozen
                        )
                        or not _exact_source(directory, checkpoint, max_bytes)
                    ):
                        reason = "stale"
                        break
                    if time.monotonic() >= deadline:
                        break
                    box.submit(selected, current)
                    known = dict(selected)
                    submitted += 1
                    decision["outcome"] = "submitted"
                    if install_only:
                        reason = "installed_pending_ack"
                        break
            time.sleep(min(poll, max(0, deadline - time.monotonic())))
        if reason == "runtime_cap" and known is not None:
            state, proof = snapshot()
            box.pending(state, known=known)
            # The live pre-ACK grace ends at the deadline. A consumed request
            # without exact evidence is a reconciliation error, not acceptance.
            if box.pending(state) is None:
                admission = state.acks.get(known["id"])
                if admission is None or admission["request"] != known:
                    raise ValueError("missing exact pending ACK at deadline")
                reason = (
                    "accepted"
                    if state.accepted.get(known["id"]) == known
                    else "rejected"
                )
                accepted += reason == "accepted"
                rejected += reason == "rejected"
                if replay and reason == "rejected":
                    raise ValueError("replay request rejected")
                if decision is not None:
                    decision["outcome"] = reason
    if decision is not None and decision["outcome"] == "pending":
        decision["outcome"] = reason
    return dict(
        reason=reason,
        submitted=submitted,
        accepted=accepted,
        rejected=rejected,
        events=state.latest["seq"] if state else 0,
        last_id=state.last_id if state else 0,
        safe=state.safe if state else 0,
        decision=decision,
    )
