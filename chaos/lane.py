"""Shared director authoring lane: durable record, one background request,
the lane's own deadline, atomic publication (NGPL).

Factored out of chaos/curio_director.py (slice 3a, #248) so the hound lane
(slice 5a, chaos/hound_director.py) follows the same rules without a copy:

- The lane record (one JSON file per surface, replaced atomically by
  rename(2)) is written BEFORE any send, so a restored game never makes a
  second model request. A restore abandons an in-flight request (its ledger
  reservation still counts) and keeps a completed ready answer.
- The authoring deadline is measured on the lane's own monotonic clock from
  the request, independent of the transport. Once it passes with no settled
  result, poll() records failed / "deadline" / error_type "LaneDeadline";
  anything the authoring thread produces afterwards is written as that
  deadline failure (never ready), so nothing late is published.
- At most one regeneration, and only for an envelope rejection.

A surface subclass supplies its lane file and evidence names
(LANE, EVIDENCE), _author_once(evidence_dir, remaining) (one evidence
directory, final receipt through self._gate), _read_evidence(evidence_dir)
for restore, and its own trigger and publication.
"""

import json
import os
import threading
import time
from pathlib import Path

from . import curio_store as store

LANE_DEADLINE = "LaneDeadline"
ERROR_TYPES = (LANE_DEADLINE,)  # optional key: only the lane-clock failure
# Steps that may carry it: the failure, and the hound's fallback after it.
ERROR_STEPS = ("failed", "fallback")
REGENERATE = ("envelope_rejected",)  # proposal 3.8: not JSON, or over size
KEYS = {"v", "game", "seed", "step", "safe", "outcome", "evidence"}


class SendFailed(Exception):
    """send() gave up: outcome "deadline" or "transport_failed", with the
    receipt fields to record."""

    def __init__(self, outcome, fields):
        super().__init__(outcome)
        self.outcome = outcome
        self.fields = fields


def send(backend, instructions, prompt, *, started, deadline_s):
    """Up to three ledgered sends within one deadline; returns (raw,
    transport, attempts). Backends without an explicit retry hint are never
    retried; all known send receipts are kept in attempts."""
    backend.deadline = started + deadline_s
    attempts = []
    for attempt in range(3):
        # A backend must opt in after a known-durable transport failure;
        # never retry arbitrary validation, credential or ledger errors.
        backend.retry_delay = None
        try:
            raw, transport = backend.generate(instructions, prompt, return_receipt=True)
            attempts.append(transport)
            return raw, transport, attempts
        except Exception as exc:
            transport = getattr(backend, "last_receipt", None)
            attempts.append(transport)
            delay = getattr(backend, "retry_delay", None)
            remaining = backend.deadline - time.monotonic()
            timed_out = isinstance(exc, TimeoutError) or remaining <= 0
            if (
                not timed_out
                and attempt < 2
                and delay is not None
                and delay >= 0
                and delay < remaining
            ):
                time.sleep(delay)
                continue
            raise SendFailed(
                "deadline" if timed_out else "transport_failed",
                dict(
                    error_type=type(exc).__name__[:80],
                    latency_s=round(time.monotonic() - started, 3),
                    transport=transport,
                    transport_attempts=attempts,
                ),
            ) from None
    raise AssertionError("unreachable: the last attempt returns or raises")


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def read_path(path, cap=store.MAX_SOURCE_BYTES):
    path = Path(path)
    with store._directory(path.parent) as d:
        return store._read(d, path.name, cap)


def rename_publish(directory, name, raw, *, replace):
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
    sync_directory(path)


def publish_source(directory, raw, *, name):
    """Publish once; an identical existing file is an earlier completed
    publish (crash before the lane record), anything else is a conflict."""
    try:
        rename_publish(directory, name, raw, replace=False)
    except FileExistsError:
        if read_path(Path(directory) / name) != raw:
            raise ValueError(name + " conflicts with the evidence") from None


def read_record(directory, name, *, steps, evidence, label):
    """The last durable lane record, or None when this game never asked."""
    with store._directory(directory) as d:
        if not store._exists(d, name):
            return None
        raw = store._read(d, name, 4096)
    record = json.loads(raw)
    if (
        type(record) is not dict
        or set(record) - {"error_type"} != KEYS
        or record.get("error_type", ERROR_TYPES[0]) not in ERROR_TYPES
        or ("error_type" in record and record["step"] not in ERROR_STEPS)
        or record["v"] != 1
        or record["step"] not in steps
        or record["evidence"] not in (None, *evidence)
        or type(record["game"]) is not str
        or not 1 <= len(record["game"]) <= 64
        or not set(record["game"]) <= set("0123456789abcdef")
        or type(record["seed"]) is not int
        or not 0 <= record["seed"] < 2**63
    ):
        raise ValueError("invalid " + label + " lane record")
    return record


def write_record(
    directory, name, record, step, safe, outcome=None, evidence=None, error_type=None
):
    record = dict(record, step=step, safe=safe, outcome=outcome, evidence=evidence)
    record.pop("error_type", None)
    if error_type is not None:
        record["error_type"] = error_type
    rename_publish(directory, name, encode(record), replace=True)
    return record


def new_record(directory, name, *, game=None, seed=None):
    """Fresh game with authoring configured: the per-game identity (ledger
    run id) and seed, durable before anything else."""
    record = dict(
        v=1,
        game=game or os.urandom(16).hex(),
        seed=int.from_bytes(os.urandom(8), "big") >> 1 if seed is None else seed,
        step="idle",
        safe=None,
        outcome=None,
        evidence=None,
    )
    rename_publish(directory, name, encode(record), replace=False)
    return record


class AuthoringLane:
    """One background authoring request per game; poll() never blocks."""

    LANE = None
    EVIDENCE = ()
    STEPS = ()
    LABEL = None
    # Outcomes that earn the one regeneration (inside the same lane-clock
    # deadline). A surface may widen it; see HoundLane.
    REGENERATE = REGENERATE

    def __init__(self, directory, backend, *, validator, deadline_s, clock):
        """Follows the run's lane record. No record: authoring was never
        configured for this surface, the lane is off. clock is the lane's
        monotonic clock; the deadline is measured on it."""
        self.directory = Path(directory)
        self.backend = backend
        self.validator = validator
        self.deadline_s = deadline_s
        self.clock = clock
        # Shared with the authoring thread: _started, _expired, _settled.
        self._lock = threading.Lock()
        self._started = None
        self._expired = False  # the lane's clock gave up; results are void
        self._settled = False  # a ready receipt was written in time
        self.thread = None
        self.receipts = []
        self.record = read_record(
            self.directory,
            self.LANE,
            steps=self.STEPS,
            evidence=self.EVIDENCE,
            label=self.LABEL,
        )
        self.state = self.record["step"] if self.record else "off"
        if self.record is not None:
            self.game_seed = self.record["seed"]
            if backend is not None and hasattr(backend, "run_id"):
                backend.run_id = self.record["game"]  # the ledger's game
        if self.state == "requested":
            self._restore_in_flight()
        if self.state == "idle" and (backend is None or validator is None):
            self.mark_no_model("no_backend" if backend is None else "no_validator")

    def _author_once(self, evidence_dir, remaining):
        """One authoring request into a fresh evidence directory; returns its
        final receipt, written through self._gate."""
        raise NotImplementedError

    def _read_evidence(self, evidence_dir):
        """Verify a ready evidence directory read-only; return its receipt."""
        raise NotImplementedError

    def _write(self, step, safe, outcome=None, evidence=None, error_type=None):
        self.record = write_record(
            self.directory,
            self.LANE,
            self.record,
            step,
            safe,
            outcome,
            evidence,
            error_type,
        )
        self.state = step

    def _restore_in_flight(self):
        """Never ask again. Keep a completed ready answer; abandon the rest."""
        for name in reversed(self.EVIDENCE):
            try:
                receipt = self._read_evidence(self.directory / name)
            except (OSError, ValueError):
                continue
            self._write("ready", self.record["safe"], "ready", name)
            self.receipts.append(receipt)
            return
        self._write("failed", self.record["safe"], "abandoned_on_restore")

    def mark_no_model(self, reason):
        """A configured provider proved unusable: no model content this game."""
        if self.state == "idle":
            self._write("no_model", None, reason)

    def _start(self, safe):
        # Durable BEFORE any send: a restore after this never asks again.
        self._write("requested", safe)
        self._started = self.clock()  # the deadline runs from the request
        self.thread = threading.Thread(target=self._author, daemon=True)
        self.thread.start()

    def _advance(self, safe):
        """The requested step: settle a finished thread, or expire it."""
        if not self.thread.is_alive():
            self._finished(safe)
        else:
            self._check_deadline(safe)

    def _remaining(self):
        return self.deadline_s - (self.clock() - self._started)

    def _author(self):
        for name in self.EVIDENCE:
            # One total deadline: a regeneration gets only what is left.
            remaining = self._remaining()
            if remaining <= 0 or self._expired:
                break
            try:
                receipt = self._author_once(self.directory / name, remaining)
            except Exception as exc:  # recorded, never raised into the loop
                receipt = dict(outcome="lane_error", error_type=type(exc).__name__)
            receipt["evidence"] = name
            self.receipts.append(receipt)
            if receipt["outcome"] not in self.REGENERATE:
                break  # at most one regeneration, only for this lane's rows

    def _gate(self, outcome, fields, write):
        """Called by the surface's author function for its final receipt, on
        the authoring thread. Past the lane's deadline the receipt is written
        as the lane's deadline failure, never as ready; in time, a ready
        receipt settles the request so poll() no longer expires it."""
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
        self._write("failed", safe, "deadline", error_type=LANE_DEADLINE)
        # The daemon thread is left to finish its own ledger row; its result
        # is void (see _gate) and nothing reads self.receipts any more.

    def _finished(self, safe):
        last = self.receipts[-1] if self.receipts else dict(outcome="lane_error")
        ready = last["outcome"] == "ready"
        self._write(
            "ready" if ready else "failed",
            safe,
            last["outcome"],
            last.get("evidence") if ready else None,
            error_type=(
                LANE_DEADLINE if last.get("error_type") == LANE_DEADLINE else None
            ),
        )
        self.thread = None

    def wait(self, timeout=None):
        if self.thread is not None:
            self.thread.join(timeout)
