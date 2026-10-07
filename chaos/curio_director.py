"""Director-side curio lane: trigger, background authoring, publish (NGPL).

Proposal 3.1. One curio request per game, at the first safe point where the
public history shows at least 150 turns and either 2 completed episodes or a
whisper the player saw, the game is on DL1-2, the budget is at least 1 with no
planned whisper needing the last unit, and the curio phase is VIRGIN.

Timing is engine-authoritative, like whispers; there is no lock between the
director and the engine.

- Live play. The lane publishes curio.lua (write a temporary, then rename(2))
  whenever authoring finishes. The engine admits it at the next eligible safe
  point and logs that itself: the curio "pre_admitted" event carries the safe
  index at which chaos_curio_safe read the source, and curio-used.lua holds the
  exact bytes. The director-observed index in install.json is advisory only.
  A publish racing the engine's poll only moves admission between safe N and
  N+1; whichever it is, the engine's log is the truth.
- Replay. record_admission() copies the engine's admission (safe index and
  SHA-256) into the evidence. stage_replay() publishes the logged source and
  that index (curio-safe) before the replay game starts. The engine admits iff
  its safe index equals the logged one, exactly like a whisper's "at": no
  timing between processes and no model call. verify_replay() cross-checks the
  replay's own admission event against the record.

Lifecycle, durable in curio-lane.json (replaced atomically by rename):
idle -> requested -> (ready | failed) -> published; or idle -> no_model.
No lane file at all means authoring was never configured for this game.
The record is written BEFORE any send, so a restored game never makes a
second model request: an in-flight generation is abandoned on restore (its
reservation still counts in the ledger), and a ready-but-unpublished curio is
published from its verified evidence with no model call.

The lane mechanics (record, deadline, regeneration) are shared with the hound
lane in chaos/lane.py. The authoring deadline (480 s, regeneration included)
is the lane's own: it
is measured on the lane's monotonic clock from the request, independent of
the transport. A hung or trickling request cannot keep the lane requested.
Once the deadline passes with no settled result, poll() records failed with
outcome "deadline" and error_type "LaneDeadline". Whatever the authoring
thread produces afterwards is ignored: its final receipt is written as that
deadline failure (never "ready"), so nothing is published and no restore or
replay can take it as ready. The thread may still finish its ledger row.
"""

import json
import time
from pathlib import Path

from . import curio_author, curio_store as store, lane as shared
from .lane import LANE_DEADLINE  # noqa: F401  (re-exported for callers)

TRIGGER_TURNS = 150
TRIGGER_EPISODES = 2
LANE = "curio-lane.json"
DUE = "curio-safe"
EVIDENCE = ("curio-evidence", "curio-evidence-2")
ADMISSION = "admission.json"
_STEPS = ("idle", "requested", "ready", "failed", "published", "no_model")
_PHASES = {
    "pre_admitted": "ADMITTED",
    "admitted": "ADMITTED",
    "placed": "PLACED",
    "placement_unavailable": "ADMITTED",
    "placement_failed": "EXPIRED",
    "rejected": "REJECTED",
    "expired": "EXPIRED",
}

# The lane mechanics live in chaos/lane.py (shared with the hound lane).
_encode = shared.encode
_sync_directory = shared.sync_directory
_read_path = shared.read_path
_rename_publish = shared.rename_publish


def publish_source(directory, raw, *, name="curio.lua"):
    """Publish once; an identical existing file is an earlier completed
    publish (crash before the lane record), anything else is a conflict."""
    shared.publish_source(directory, raw, name=name)


def read_lane(directory):
    """The last durable lane record, or None when this game never asked."""
    return shared.read_record(
        directory, LANE, steps=_STEPS, evidence=EVIDENCE, label="curio"
    )


def _write_lane(
    directory, record, step, safe, outcome=None, evidence=None, error_type=None
):
    return shared.write_record(
        directory, LANE, record, step, safe, outcome, evidence, error_type
    )


def new_lane(directory, *, game=None, seed=None):
    """Fresh game with authoring configured: the per-game identity (ledger
    run id) and the literary-layer seed, durable before anything else."""
    return shared.new_record(directory, LANE, game=game, seed=seed)


def curio_phase(directory):
    """The engine's curio phase as its own events report it (VIRGIN if none).

    Native expiry on DL3+ reports "expired", so VIRGIN also means the game has
    not reached DL3 at a safe point. The engine re-checks everything anyway.
    """
    phase = "VIRGIN"
    path = Path(directory) / "events.jsonl"
    if not path.exists():
        return phase
    with open(path, "rb") as f:
        for line in f:
            if b'"event":"curio"' not in line or not line.endswith(b"\n"):
                continue
            phase = _PHASES.get(json.loads(line)["detail"], phase)
    return phase


def trigger_ready(history, *, planned_cost=0):
    """3.1 on a checked HistoryState (depth and curio phase checked apart)."""
    latest = history.latest
    if latest is None or history.ended:
        return False
    episodes = sum(group["count"] for group in history.episodes["episodes"])
    seen = len(history.prior_whispers) + history.prior_coverage["omitted"]
    return (
        latest["turn"] >= TRIGGER_TURNS
        and (episodes >= TRIGGER_EPISODES or seen >= 1)
        and latest["budget"] - planned_cost >= 1
    )


class CurioLane(shared.AuthoringLane):
    """One background authoring request per game; poll() never blocks."""

    LANE = LANE
    EVIDENCE = EVIDENCE
    STEPS = _STEPS
    LABEL = "curio"

    def __init__(
        self,
        directory,
        backend,
        *,
        validator,
        role=None,
        deadline_s=curio_author.DEADLINE_S,
        phase=None,
        snapshot=None,
        clock=time.monotonic,
    ):
        """Follows the run's lane record (new_lane() writes it for a fresh
        game). No record: authoring was never configured, the lane is off.
        clock is the lane's monotonic clock; the deadline is measured on it."""
        self.role = role
        # The engine's curio phase: read once, then kept current by note()
        # from the events the director loop already ingests.
        self._phase = curio_phase(directory)
        self.phase = phase or (lambda: self._phase)
        self._last_safe = None
        if snapshot is None:
            from .history import snapshot_history

            snapshot = snapshot_history
        self._snapshot = snapshot
        super().__init__(
            directory, backend, validator=validator, deadline_s=deadline_s, clock=clock
        )

    def _read_evidence(self, evidence_dir):
        return curio_author.read_evidence(evidence_dir)

    def _author_once(self, evidence_dir, remaining):
        return curio_author.author_curio(
            self.backend,
            events_dir=self.directory,
            evidence_dir=evidence_dir,
            game_seed=self.game_seed,
            validator=self.validator,
            role=self.role,
            deadline_s=remaining,
            gate=self._gate,
        )

    def note(self, event):
        """Feed one ingested event; keeps the curio phase current."""
        if event.get("event") == "curio":
            self._phase = _PHASES.get(event.get("detail"), self._phase)

    @property
    def active(self):
        """Whether the lane still needs the director loop to keep polling."""
        if self.state in ("requested", "ready"):
            return True
        return self.state == "idle" and self.phase() == "VIRGIN"

    def poll(self, *, planned_cost=0, safe=None, latest=None):
        """Called from the director's mailbox loop; returns the lane state.

        latest (the director's last event) is a cheap pre-check: the full
        checked history is read only at a new safe index that could qualify.
        """
        if self.state == "idle" and self._worth_checking(latest, planned_cost):
            self._maybe_request(planned_cost)
        elif self.state == "requested":
            self._advance(safe)
        if self.state == "ready":
            self._publish(safe)
        return self.state

    def _worth_checking(self, latest, planned_cost):
        if latest is None:
            return True
        if latest["safe"] == self._last_safe:
            return False
        if (
            latest["turn"] < TRIGGER_TURNS
            or latest["budget"] - planned_cost < 1
            or latest["safe"] < 1
        ):
            return False
        self._last_safe = latest["safe"]
        return True

    def _maybe_request(self, planned_cost):
        if self.phase() != "VIRGIN":
            return
        try:
            history, _ = self._snapshot(self.directory)
        except ValueError:
            return  # incomplete tail; the next poll sees it whole
        if not trigger_ready(history, planned_cost=planned_cost):
            return
        self._start(history.safe)

    def _publish(self, safe):
        if self.phase() != "VIRGIN":
            # DL3 (native expiry) or another admission came first: nothing
            # is published and the player sees nothing.
            self._write(
                "failed", safe, "closed_before_publish", self.record["evidence"]
            )
            return
        evidence = self.directory / self.record["evidence"]
        curio_author.read_evidence(evidence)  # re-verify the chain before use
        source = _read_path(evidence / "source.lua")
        publish_source(self.directory, source)
        with store._directory(evidence) as d:
            if not store._exists(d, "install.json"):
                # Advisory only; the engine's events are the authority.
                store._publish(
                    d,
                    "install.json",
                    curio_author._encode(
                        dict(
                            v=1,
                            safe=safe,  # director-observed: advisory only
                            source_sha256=curio_author._sha(source),
                        )
                    ),
                )
        self._write("published", safe, "ready", self.record["evidence"])


def engine_admission(directory):
    """The engine's own admission: {"safe", "source_sha256"} or None."""
    admitted = None
    with open(Path(directory) / "events.jsonl", "rb") as f:
        for line in f:
            e = json.loads(line)
            if (e["event"], e["phase"], e["detail"]) == (
                "curio",
                "result",
                "pre_admitted",
            ):
                if admitted is not None:
                    raise ValueError("two curio admissions in one game")
                admitted = e["safe"]
    if admitted is None:
        return None
    used = _read_path(Path(directory) / "curio-used.lua")
    return dict(safe=admitted, source_sha256=curio_author._sha(used))


def record_admission(directory, evidence_dir):
    """After the recorded game: bind the engine's admission into the evidence."""
    admission = engine_admission(directory)
    if admission is None:
        raise ValueError("the engine never admitted this curio")
    receipt = curio_author.read_evidence(evidence_dir)
    if admission["source_sha256"] != receipt["lua_source_sha256"]:
        raise ValueError("admitted bytes differ from the evidence")
    with store._directory(evidence_dir) as d:
        store._publish(d, ADMISSION, _encode(dict(v=1, **admission)))
    return admission


def read_admission(evidence_dir):
    record = json.loads(_read_path(Path(evidence_dir) / ADMISSION, 4096))
    if (
        type(record) is not dict
        or set(record) != {"v", "safe", "source_sha256"}
        or record["v"] != 1
        or type(record["safe"]) is not int
        or not 1 <= record["safe"] < 2**31
    ):
        raise ValueError("invalid recorded admission")
    return dict(safe=record["safe"], source_sha256=record["source_sha256"])


def stage_replay(directory, evidence_dir):
    """Before the replay game starts: the logged source and the ENGINE's
    logged admission index. Never a transport, never the advisory index."""
    receipt = curio_author.read_evidence(evidence_dir)
    admission = read_admission(evidence_dir)
    source = _read_path(Path(evidence_dir) / "source.lua")
    if not (
        curio_author._sha(source)
        == admission["source_sha256"]
        == receipt["lua_source_sha256"]
    ):
        raise ValueError("recorded admission does not match the evidence")
    publish_source(directory, b"%d\n" % admission["safe"], name=DUE)
    publish_source(directory, source)
    return admission


def verify_replay(directory, evidence_dir):
    """After replay: the engine admitted the same bytes at the same index."""
    expected = read_admission(evidence_dir)
    replayed = engine_admission(directory)
    if replayed != expected:
        raise ValueError("replay admission differs from the record")
    return replayed
