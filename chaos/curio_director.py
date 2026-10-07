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

The authoring deadline (480 s, regeneration included) is the lane's own: it
is measured on the lane's monotonic clock from the request, independent of
the transport. A hung or trickling request cannot keep the lane requested.
Once the deadline passes with no settled result, poll() records failed with
outcome "deadline" and error_type "LaneDeadline". Whatever the authoring
thread produces afterwards is ignored: its final receipt is written as that
deadline failure (never "ready"), so nothing is published and no restore or
replay can take it as ready. The thread may still finish its ledger row.
"""

import json
import os
import threading
import time
from pathlib import Path

from . import curio_author, curio_store as store

TRIGGER_TURNS = 150
TRIGGER_EPISODES = 2
LANE = "curio-lane.json"
DUE = "curio-safe"
EVIDENCE = ("curio-evidence", "curio-evidence-2")
ADMISSION = "admission.json"
_STEPS = ("idle", "requested", "ready", "failed", "published", "no_model")
_KEYS = {"v", "game", "seed", "step", "safe", "outcome", "evidence"}
# Optional: only the lane-clock deadline failure names its error type.
_ERROR_TYPES = ("LaneDeadline",)
LANE_DEADLINE = "LaneDeadline"
_REGENERATE = ("envelope_rejected",)  # 3.8: not JSON, or over size
_PHASES = {
    "pre_admitted": "ADMITTED",
    "admitted": "ADMITTED",
    "placed": "PLACED",
    "placement_unavailable": "ADMITTED",
    "placement_failed": "EXPIRED",
    "rejected": "REJECTED",
    "expired": "EXPIRED",
}


def _encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_path(path, cap=store.MAX_SOURCE_BYTES):
    path = Path(path)
    with store._directory(path.parent) as d:
        return store._read(d, path.name, cap)


def _rename_publish(directory, name, raw, *, replace):
    """Write a private temporary, fsync, rename(2). The final name never has a
    second link and never holds a partial file."""
    path = Path(directory)
    temporary = path / (".publish-" + os.urandom(8).hex())
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        view = memoryview(raw)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        if not replace:
            with store._directory(path) as d:
                if store._exists(d, name):
                    raise FileExistsError(name + " already published")
        # The director is the run directory's single writer (it shares the
        # supervisor's .director.lock), so check-then-rename cannot race.
        os.rename(temporary, path / name)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    _sync_directory(path)


def publish_source(directory, raw, *, name="curio.lua"):
    """Publish once; an identical existing file is an earlier completed
    publish (crash before the lane record), anything else is a conflict."""
    try:
        _rename_publish(directory, name, raw, replace=False)
    except FileExistsError:
        if _read_path(Path(directory) / name) != raw:
            raise ValueError(name + " conflicts with the evidence") from None


def read_lane(directory):
    """The last durable lane record, or None when this game never asked."""
    with store._directory(directory) as d:
        if not store._exists(d, LANE):
            return None
        raw = store._read(d, LANE, 4096)
    record = json.loads(raw)
    if (
        type(record) is not dict
        or set(record) - {"error_type"} != _KEYS
        or record.get("error_type", _ERROR_TYPES[0]) not in _ERROR_TYPES
        or ("error_type" in record and record["step"] != "failed")
        or record["v"] != 1
        or record["step"] not in _STEPS
        or record["evidence"] not in (None, *EVIDENCE)
        or type(record["game"]) is not str
        or not 1 <= len(record["game"]) <= 64
        or not set(record["game"]) <= set("0123456789abcdef")
        or type(record["seed"]) is not int
        or not 0 <= record["seed"] < 2**63
    ):
        raise ValueError("invalid curio lane record")
    return record


def _write_lane(
    directory, record, step, safe, outcome=None, evidence=None, error_type=None
):
    record = dict(record, step=step, safe=safe, outcome=outcome, evidence=evidence)
    record.pop("error_type", None)
    if error_type is not None:
        record["error_type"] = error_type
    _rename_publish(directory, LANE, _encode(record), replace=True)
    return record


def new_lane(directory, *, game=None, seed=None):
    """Fresh game with authoring configured: the per-game identity (ledger
    run id) and the literary-layer seed, durable before anything else."""
    record = dict(
        v=1,
        game=game or os.urandom(16).hex(),
        seed=int.from_bytes(os.urandom(8), "big") >> 1 if seed is None else seed,
        step="idle",
        safe=None,
        outcome=None,
        evidence=None,
    )
    _rename_publish(directory, LANE, _encode(record), replace=False)
    return record


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


class CurioLane:
    """One background authoring request per game; poll() never blocks."""

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
        self.directory = Path(directory)
        self.backend = backend
        self.validator = validator
        self.role = role
        self.deadline_s = deadline_s
        self.clock = clock
        # Shared with the authoring thread: _started, _expired, _settled.
        self._lock = threading.Lock()
        self._started = None
        self._expired = False  # the lane's clock gave up; results are void
        self._settled = False  # a ready receipt was written in time
        # The engine's curio phase: read once, then kept current by note()
        # from the events the director loop already ingests.
        self._phase = curio_phase(self.directory)
        self.phase = phase or (lambda: self._phase)
        self._last_safe = None
        if snapshot is None:
            from .history import snapshot_history

            snapshot = snapshot_history
        self._snapshot = snapshot
        self.thread = None
        self.receipts = []
        self.record = read_lane(self.directory)
        self.state = self.record["step"] if self.record else "off"
        if self.record is not None:
            self.game_seed = self.record["seed"]
            if backend is not None and hasattr(backend, "run_id"):
                backend.run_id = self.record["game"]  # the ledger's game
        if self.state == "requested":
            self._restore_in_flight()
        if self.state == "idle" and (backend is None or validator is None):
            self.mark_no_model("no_backend" if backend is None else "no_validator")

    def _restore_in_flight(self):
        """Never ask again. Keep a completed ready answer; abandon the rest."""
        for name in reversed(EVIDENCE):
            try:
                receipt = curio_author.read_evidence(self.directory / name)
            except (OSError, ValueError):
                continue
            self.record = _write_lane(
                self.directory, self.record, "ready", self.record["safe"], "ready", name
            )
            self.state = "ready"
            self.receipts.append(receipt)
            return
        self.record = _write_lane(
            self.directory,
            self.record,
            "failed",
            self.record["safe"],
            "abandoned_on_restore",
        )
        self.state = "failed"

    def mark_no_model(self, reason):
        """A configured provider proved unusable: no model content this game."""
        if self.state == "idle":
            self.record = _write_lane(
                self.directory, self.record, "no_model", None, reason
            )
            self.state = "no_model"

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
            if not self.thread.is_alive():
                self._finished(safe)
            else:
                self._check_deadline(safe)
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
        # Durable BEFORE any send: a restore after this never asks again.
        self.record = _write_lane(
            self.directory, self.record, "requested", history.safe
        )
        self.state = "requested"
        self._started = self.clock()  # the deadline runs from the request
        self.thread = threading.Thread(target=self._author, daemon=True)
        self.thread.start()

    def _remaining(self):
        return self.deadline_s - (self.clock() - self._started)

    def _author(self):
        for name in EVIDENCE:
            # One total deadline: a regeneration gets only what is left.
            remaining = self._remaining()
            if remaining <= 0 or self._expired:
                break
            try:
                receipt = curio_author.author_curio(
                    self.backend,
                    events_dir=self.directory,
                    evidence_dir=self.directory / name,
                    game_seed=self.game_seed,
                    validator=self.validator,
                    role=self.role,
                    deadline_s=remaining,
                    gate=self._gate,
                )
            except Exception as exc:  # recorded, never raised into the loop
                receipt = dict(outcome="lane_error", error_type=type(exc).__name__)
            receipt["evidence"] = name
            self.receipts.append(receipt)
            if receipt["outcome"] not in _REGENERATE:
                break  # at most one regeneration, and only for 3.8's row

    def _gate(self, outcome, fields, write):
        """Called by author_curio for its final receipt, on the authoring
        thread. Past the lane's deadline the receipt is written as the lane's
        deadline failure, never as ready; in time, a ready receipt settles
        the request so poll() no longer expires it."""
        with self._lock:
            if self._expired or self._remaining() <= 0:
                self._expired = True
                # What the late thread would have reported, kept for the
                # record only; the outcome is the lane's deadline.
                late = dict(fields, error_type=LANE_DEADLINE, late_outcome=outcome)
                return write("deadline", late)
            if outcome == "ready":
                self._settled = True
            return write(outcome, fields)

    def _check_deadline(self, safe):
        """The thread is still running: fail durably once the lane's own
        clock passes the deadline, whatever the transport is doing."""
        with self._lock:
            if self._settled or self._remaining() > 0:
                return
            self._expired = True
        self.record = _write_lane(
            self.directory,
            self.record,
            "failed",
            safe,
            "deadline",
            error_type=LANE_DEADLINE,
        )
        self.state = "failed"
        # The daemon thread is left to finish its own ledger row; its result
        # is void (see _gate) and nothing reads self.receipts any more.

    def _finished(self, safe):
        last = self.receipts[-1] if self.receipts else dict(outcome="lane_error")
        ready = last["outcome"] == "ready"
        self.record = _write_lane(
            self.directory,
            self.record,
            "ready" if ready else "failed",
            safe,
            last["outcome"],
            last.get("evidence") if ready else None,
            error_type=(
                LANE_DEADLINE if last.get("error_type") == LANE_DEADLINE else None
            ),
        )
        self.state = self.record["step"]
        self.thread = None

    def _publish(self, safe):
        if self.phase() != "VIRGIN":
            # DL3 (native expiry) or another admission came first: nothing
            # is published and the player sees nothing.
            self.record = _write_lane(
                self.directory,
                self.record,
                "failed",
                safe,
                "closed_before_publish",
                self.record["evidence"],
            )
            self.state = "failed"
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
        self.record = _write_lane(
            self.directory,
            self.record,
            "published",
            safe,
            "ready",
            self.record["evidence"],
        )
        self.state = "published"

    def wait(self, timeout=None):
        if self.thread is not None:
            self.thread.join(timeout)


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
