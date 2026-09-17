"""Bounded observer, private mailbox and offline directors (NGPL)."""

from collections import deque
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import stat
import tempfile
import time

from .protocol import (
    FIELDS,
    REGISTRY,
    VITALS,
    encode_request,
    parse_event,
    parse_request,
    strict_json,
)

from ._protocol_contract import MUTATIONS, EVENT_CAP, REQUEST_CAP, REQUEST_VERSION

DEFAULT_BYTES = 16 * 1024 * 1024
DEFAULT_EVENTS = 50000


def secure_open(path, flags=os.O_RDONLY, mode=0o600):
    fd = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, mode)
    s = os.fstat(fd)
    if (
        not stat.S_ISREG(s.st_mode)
        or s.st_uid != os.getuid()
        or s.st_mode & 0o077
        or s.st_nlink != 1
    ):
        os.close(fd)
        raise ValueError("file must be private, owned, regular and singly linked")
    return fd


class EventReader:
    """Keep partial bytes; verify consumed prefix to detect rewrite/rollback.

    Total read/hash work is bounded by max_bytes per poll. No silent dedup.
    """

    def __init__(self, path, max_bytes=DEFAULT_BYTES, max_events=DEFAULT_EVENTS):
        self.path = Path(path)
        self.max_bytes, self.max_events = max_bytes, max_events
        self.offset = self.count = 0
        self.tail = b""
        self.identity = None
        self.digest = hashlib.sha256(b"").digest()

    def read(self):
        try:
            fd = secure_open(self.path)
        except FileNotFoundError:
            if self.identity is not None:
                raise ValueError("event log disappeared")
            return []
        with os.fdopen(fd, "rb") as f:
            s = os.fstat(f.fileno())
            identity = (s.st_dev, s.st_ino)
            if self.identity is not None and self.identity != identity:
                raise ValueError("event log replaced")
            if s.st_size < self.offset or s.st_size > self.max_bytes:
                raise ValueError("event log truncated or byte cap exceeded")
            h = hashlib.sha256()
            remaining = self.offset
            while remaining:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    raise ValueError("event log changed while reading")
                remaining -= len(chunk)
                h.update(chunk)
            if h.digest() != self.digest:
                raise ValueError("event log prefix rewritten")
            # Only snapshot bytes; growth is read at the next poll.
            records = []
            remaining = s.st_size - self.offset
            tail = self.tail
            while remaining:
                chunk = f.read(min(65536, remaining))
                if not chunk:
                    raise ValueError("event log changed while reading")
                remaining -= len(chunk)
                h.update(chunk)
                parts = (tail + chunk).split(b"\n")
                tail = parts.pop()
                if len(tail) > EVENT_CAP:
                    raise ValueError("event line exceeds byte cap")
                for line in parts:
                    records.append(parse_event(line))
                    if self.count + len(records) > self.max_events:
                        raise ValueError("event count cap exceeded")
            self.tail, self.offset, self.digest, self.identity = (
                tail,
                s.st_size,
                h.digest(),
                identity,
            )
            self.count += len(records)
            return records


class State:
    def __init__(self):
        self.latest = None
        self.recent = deque(maxlen=12)
        self.acks = {}  # bounded by reader's event cap
        self.accepted = {}
        self.active = {}
        self.ended = False

    def ingest(self, event):
        e = parse_event(json.dumps(event).encode())
        p = self.latest
        if p and (
            e["seq"] <= p["seq"]
            or any(e[k] < p[k] for k in ("safe", "turn", "spent", "last_id"))
        ):
            raise ValueError(
                "sequence rollback/reset: use a separate reconciled run directory"
            )
        if self.ended:
            raise ValueError("events after final death")
        self.latest = e
        recent = {k: e[k] for k in ("event", "phase", "turn", "safe")}
        if "vitals" in e:
            recent["vitals"] = {k: e["vitals"][k] for k in VITALS}
        if e["event"] == "pray" and (e["phase"], e["detail"]) in (
            ("attempt", "confirmed"),
            ("result", "cancelled"),
        ):
            recent["prayer"] = e["detail"]
        self.recent.append(recent)
        self.active = {k: v for k, v in self.active.items() if v > e["turn"]}
        if e["event"] == "ack" and e["id"]:
            # Repeated duplicate ACKs must not erase accepted evidence.
            r = {k: e[k] for k in FIELDS}
            previous = self.acks.get(e["id"])
            if previous and previous["request"] != r:
                raise ValueError("conflicting acknowledgement ID")
            if previous is None or e["detail"] != "duplicate":
                self.acks[e["id"]] = {
                    "request": r,
                    "status": e["status"],
                    "detail": e["detail"],
                }
            if e["status"] == "accepted":
                self.accepted[e["id"]] = r
                if MUTATIONS[r["mutation"]]["persistent"]:
                    self.active[r["mutation"]] = e["expires"]
        if e["event"] == "death" and e["phase"] == "result":
            self.ended = True

    @property
    def last_id(self):
        return self.latest["last_id"] if self.latest else 0

    @property
    def safe(self):
        return self.latest["safe"] if self.latest else 0

    def summary(self):
        # No arbitrary detail, ACK extras, journal, or source keys reach a model.
        # Only exact prayer disclosure enums and validated status vitals are added.
        observed = (
            {
                k: self.latest[k]
                for k in (
                    "turn",
                    "safe",
                    "sanity",
                    "insight",
                    "budget",
                    "spent",
                    "reserved",
                )
            }
            if self.latest
            else {}
        )
        if self.latest and "vitals" in self.latest:
            observed["vitals"] = {k: self.latest["vitals"][k] for k in VITALS}
        return json.dumps(
            {"observed": observed, "recent": list(self.recent)},
            separators=(",", ":"),
            ensure_ascii=True,
        )


class Mailbox:
    """Single cooperating writer, held for the whole director lifetime."""

    def __init__(self, directory):
        self.path = Path(directory).absolute()
        s = self.path.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
            raise ValueError("run directory must be owned, non-symlink and mode 0700")
        self.lock = secure_open(self.path / ".director.lock", os.O_RDWR | os.O_CREAT)
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.close()
            raise ValueError("another director holds the run directory") from None

    def close(self):
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def existing(self):
        try:
            fd = secure_open(self.path / "whisper.json")
        except FileNotFoundError:
            return None
        with os.fdopen(fd, "rb") as f:
            return parse_request(f.read(REQUEST_CAP + 1))

    def pending(self, state, *, known=None):
        """Resolve ACK evidence, with a narrow live-only pre-ACK wait.

        ``known`` is a copy of the exact request previously observed as future
        or published by this loop, never reconstructed from a consumed mailbox.
        The engine emits its telegraph after consuming last_id but before the
        warning UI returns and writes the ACK. That window is pending, NOT
        acceptance, and is bounded by the caller's existing runtime deadline.
        Startup callers omit ``known`` and retain strict reconciliation.
        """
        r = self.existing()
        if known is not None and r != known:
            raise ValueError("mailbox changed while awaiting exact ACK evidence")
        if r is None:
            return None
        a = state.acks.get(r["id"])
        if a and a["request"] == r:
            return None
        if r["id"] <= state.last_id:
            e = state.latest
            if (
                known is not None
                and a is None
                and state.last_id == r["id"]
                and state.safe == r["at"]
                and e["event"] == "telegraph"
                and e["phase"] == "result"
                and e["detail"] == r["mutation"]
            ):
                return r
            raise ValueError(
                "consumed mailbox lacks exact ACK evidence; manual reconciliation required"
            )
        if a:
            raise ValueError("mailbox lacks exact ACK evidence")
        if r["at"] < state.safe or (known is None and r["at"] == state.safe):
            raise ValueError("pending request has missed its safe index")
        return r

    def submit(self, request, state):
        raw = encode_request(request)
        if state.ended:
            raise ValueError("game has ended")
        if self.pending(state):
            raise ValueError("unacknowledged mailbox must not be overwritten")
        if request["id"] <= state.last_id or request["at"] <= state.safe:
            raise ValueError("request ID or safe index already consumed")
        fd, name = tempfile.mkstemp(prefix=".whisper-", dir=self.path)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            # Validate target again: never replace a symlink/device even if raced.
            self.existing()
            os.replace(name, self.path / "whisper.json")
            dfd = os.open(self.path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
            if self.existing() != request:
                raise ValueError("mailbox verification failed")
        finally:
            if os.path.exists(name):
                os.unlink(name)


def eligible(state, ordinary_food=False):
    if state.ended or state.latest is None:
        return []
    e = state.latest
    return [
        name
        for name, (cost, sanity, _) in REGISTRY.items()
        if cost <= e["budget"]
        and e["sanity"] <= sanity
        and name not in state.active
        and (not MUTATIONS[name]["ordinary_food"] or ordinary_food)
    ]


class RandomBackend:
    def __init__(self, seed=0, ordinary_food=False):
        self.rng = random.Random(seed)
        self.ordinary_food = ordinary_food

    def choose(self, state, ident, at):
        options = eligible(state, self.ordinary_food)
        if not options:
            return None
        name = self.rng.choice(options)
        row = MUTATIONS[name]
        return dict(
            v=REQUEST_VERSION,
            id=ident,
            at=at,
            mutation=name,
            value=self.rng.randint(*row["value"])
            if row["value"][0] != row["value"][1]
            else row["value"][0],
            duration=self.rng.randint(*row["duration"])
            if row["duration"][0] != row["duration"][1]
            else row["duration"][0],
            telegraph=REGISTRY[name][2],
        )


class ScheduleBackend:
    def __init__(self, requests):
        self.requests = requests
        previous = (0, 0)
        for r in requests:
            encode_request(r)
            if r["id"] <= previous[0] or r["at"] <= previous[1]:
                raise ValueError("schedule IDs and safe indices must strictly increase")
            previous = r["id"], r["at"]

    def next(self, state):
        for r in self.requests:
            if state.accepted.get(r["id"]) == r:
                continue
            if r["id"] <= state.last_id or r["at"] <= state.safe:
                raise ValueError(
                    "schedule missed or rejected; replay cannot be silently retimed"
                )
            return r
        return None


def load_replay(journal, evidence):
    reader = EventReader(evidence)
    state = State()
    for e in reader.read():
        state.ingest(e)
    if reader.tail:
        raise ValueError("incomplete ACK evidence")
    requests = []
    fd = secure_open(journal)
    with os.fdopen(fd, "rb") as f:
        if os.fstat(f.fileno()).st_size > DEFAULT_BYTES:
            raise ValueError("journal byte cap exceeded")
        for line in f:
            if len(requests) >= DEFAULT_EVENTS:
                raise ValueError("journal count cap exceeded")
            if not line.endswith(b"\n"):
                raise ValueError("partial admission journal")
            row = strict_json(line, 4096)
            if row.get("status") != "admitted" or any(k not in row for k in FIELDS):
                raise ValueError("invalid admission record")
            r = {k: row[k] for k in FIELDS}
            encode_request(r)
            if state.accepted.get(r["id"]) != r:
                raise ValueError(
                    "admission journal is not proof of application: matching accepted ACK required"
                )
            requests.append(r)
    ScheduleBackend(requests)
    return requests


def run(
    directory,
    backend,
    max_runtime=300.0,
    poll=0.25,
    max_events=DEFAULT_EVENTS,
    max_bytes=DEFAULT_BYTES,
    max_submissions=12,
    install_only=False,
):
    if not 0 < max_runtime <= 86400 or not 0.01 <= poll <= 60 or max_submissions < 1:
        raise ValueError("invalid runtime, poll or submission cap")
    deadline = time.monotonic() + max_runtime
    if hasattr(backend, "deadline"):
        backend.deadline = deadline
    reader = EventReader(Path(directory) / "events.jsonl", max_bytes, max_events)
    state = State()
    submitted = 0
    last_choice = None
    known_pending = None
    reason = "runtime_cap"
    with Mailbox(directory) as box:
        while time.monotonic() < deadline:
            for e in reader.read():
                state.ingest(e)
            if state.ended:
                reason = "death"
                break
            pending = box.pending(state, known=known_pending)
            known_pending = dict(pending) if pending is not None else None
            if not pending:
                if isinstance(backend, ScheduleBackend):
                    r = backend.next(state)
                    if r is None:
                        reason = "schedule_complete"
                        break
                else:
                    r = None
                    if (
                        state.latest
                        and last_choice != state.safe
                        and eligible(state, getattr(backend, "ordinary_food", False))
                    ):
                        last_choice = state.safe
                        r = backend.choose(state, state.last_id + 1, state.safe + 1)
                if r:
                    if submitted >= max_submissions:
                        reason = "submission_cap"
                        break
                    if time.monotonic() >= deadline:
                        break
                    box.submit(r, state)
                    known_pending = dict(r)
                    submitted += 1
                    if install_only:
                        reason = "installed_pending_ack"
                        break
            time.sleep(min(poll, max(0, deadline - time.monotonic())))
    return dict(
        reason=reason,
        submitted=submitted,
        events=reader.count,
        last_id=state.last_id,
        safe=state.safe,
    )
