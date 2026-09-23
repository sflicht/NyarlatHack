"""Bounded, one-decision next-use scheduling. Publication is not admission."""

import os
from pathlib import Path

from .curio_store import _directory
from .director import EventReader, Mailbox
from .episodes import parse_episode_event
from .history import HistoryState, public_context
from .history_choice import RandomHistoryBackend
from .next_use_history import next_use_menu
from .protocol import strict_json

_KEYS = frozenset(
    (
        "next_use_schedule_v",
        "family",
        "move",
        "level_dnum",
        "level_dlevel",
        "root",
        "notice_seq",
        "end_seq",
    )
)
_MAX_BYTES = 16384
_MAX_LINE = 256
_MAX_RECORDS = 32


def parse_schedule_line(raw):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise ValueError("schedule line")
    row = strict_json(raw, _MAX_LINE)
    if type(row) is not dict or set(row) != _KEYS:
        raise ValueError("schedule schema")
    if (
        type(row["next_use_schedule_v"]) is not int
        or row["next_use_schedule_v"] != 1
        or row["family"] not in ("W", "F")
    ):
        raise ValueError("schedule schema")
    for key in ("move", "level_dnum", "level_dlevel", "root", "notice_seq", "end_seq"):
        if type(row[key]) is not int:
            raise ValueError("schedule schema")
    if not (
        0 <= row["move"] <= 2147483547
        and 0 <= row["level_dnum"] <= 255
        and 0 <= row["level_dlevel"] <= 255
        and 1 <= row["root"] < row["notice_seq"] < row["end_seq"] <= 2147483647
    ):
        raise ValueError("schedule bounds")
    return row


def _schedule_reader(path):
    return EventReader(
        path,
        _MAX_BYTES,
        _MAX_RECORDS,
        max_line=_MAX_LINE - 1,
        parser=lambda line: parse_schedule_line(line + b"\n"),
    )


def _unique(rows):
    # Sequence identities are run-global, not family-local. Conflicting clocks,
    # levels or endpoint claims for the same root are not alternative origins.
    seen = set()
    for row in rows:
        refs = {row["root"], row["notice_seq"], row["end_seq"]}
        if seen & refs:
            raise ValueError("schedule duplicate or conflicting identity")
        seen.update(refs)
    return rows


def read_schedule_rows(path):
    """One bounded snapshot. Polling callers must retain NextUseScheduler."""
    path = Path(path)
    with _directory(path.parent) as directory:
        return _unique(_schedule_reader(path.name).read(dir_fd=directory))


def host_from_schedule(row, run_hex, at, program_id):
    """Host fields for an envelope. move is monstermoves, not turn."""
    if (
        type(run_hex) is not str
        or len(run_hex) != 64
        or not set(run_hex) <= set("0123456789abcdef")
    ):
        raise ValueError("schedule run")
    if (
        type(at) is not int
        or type(program_id) is not int
        or not 1 <= at <= 2147483647
        or not 1 <= program_id <= 2147483647
    ):
        raise ValueError("schedule host")
    return dict(
        at=at,
        id=program_id,
        level_dlevel=row["level_dlevel"],
        level_dnum=row["level_dnum"],
        move=row["move"],
        run=run_hex,
        variant=0,
    )


def _matches(row, selected):
    origin = selected["origin"]
    return (
        row["family"] == selected["family"]
        and row["root"] == origin["root_seq"]
        and row["notice_seq"] == origin["notice_seq"]
        and row["end_seq"] == origin["end_seq"]
    )


def publish_scheduled(directory, selected, run_hex, at, program_id, box=None):
    """One-shot exact-reference publication; the engine still revalidates."""
    from .next_use_compose import validate_next_use_row
    from .next_use_envelope import publish_envelope

    validate_next_use_row(selected)
    matches = [
        row
        for row in read_schedule_rows(Path(directory) / "next_use-schedule.jsonl")
        if _matches(row, selected)
    ]
    if len(matches) != 1:
        raise ValueError("origin schedule mismatch")
    return publish_envelope(
        directory,
        selected,
        host_from_schedule(matches[0], run_hex, at, program_id),
        box,
    )


def _history_line(line):
    parse_episode_event(line)
    return line + b"\n"  # Preserve exact source bytes, not reserialized evidence.


class NextUseScheduler:
    """One seeded decision for a launcher lifetime, including abstention/failure.

    Retain the existing EventReader prefix/identity checks for BOTH inputs.
    History work/storage is bounded by its 16 MiB/50000-record contract; schedule
    by 16 KiB/32 records/256-byte lines. Partial input is pending, not failure.
    Latest public qualifying origin per family mirrors engine-owned slots; among
    matching live origins select the earliest end sequence, then choose its op.
    Safe index and ID are bound to that origin's completed observation, never
    retimed to a later safe point. No retry or substitution after a decision.
    """

    def __init__(self, directory, *, seed):
        self.path = Path(directory).absolute()
        self.schedule = _schedule_reader("next_use-schedule.jsonl")
        self.events = EventReader("events.jsonl", parser=_history_line, max_line=4096)
        self.selector = RandomHistoryBackend(seed)
        self.rows = []
        self.lines = []
        self.history = None
        self.identity = None
        self.terminal = None

    def poll(self, box=None):
        if self.terminal:
            return {"status": self.terminal}
        try:
            if box is None:
                with Mailbox(self.path) as held:
                    return self._poll(held)
            if box.path != self.path or box.lock is None:
                raise ValueError("matching held mailbox required")
            return self._poll(box)
        except (OSError, ValueError, TimeoutError):
            self.terminal = "failed"
            raise  # Existing launcher failure diagnostics must see real failure.

    def _read(self, directory):
        self.rows.extend(self.schedule.read(dir_fd=directory))
        _unique(self.rows)
        new = self.events.read(dir_fd=directory)
        self.lines.extend(new)
        # A complete enabled marker awaiting its session is also pending. Validate
        # all earlier chronology, so a tail cannot hide malformed complete input.
        lines = self.lines
        marker = bool(
            lines
            and parse_episode_event(lines[-1]).get("observation", {}).get("stage")
            == "enabled"
        )
        complete = lines[:-1] if marker else lines
        if new or self.history is None:
            self.history = HistoryState(b"".join(complete)) if complete else None
        return bool(self.events.tail or marker)

    def _poll(self, box):
        from .next_use_envelope import engine_run_hex, publish_envelope

        with _directory(self.path) as directory:
            st = os.fstat(directory)
            identity = (st.st_dev, st.st_ino)
            if self.identity is not None and self.identity != identity:
                raise ValueError("schedule directory replaced")
            self.identity = identity
            if os.path.lexists(self.path / "next_use-envelope.json"):
                self.terminal = "already_published"
                return {"status": self.terminal}
            pending = self._read(directory)
            history = self.history
            if pending or not history:
                return {"status": "pending"}
            if (
                history.ended
                or history.safe >= 2147483647
                or history.last_id >= 2147483647
            ):
                return {"status": "no_eligible_origin"}
            menu = next_use_menu(history)
            for row in sorted(self.rows, key=lambda r: r["end_seq"]):
                choices = [choice for choice in menu if _matches(row, choice)]
                if not choices:
                    continue
                end = parse_episode_event(self.lines[row["end_seq"] - 1])
                # Binding to completion prevents a delayed first poll from
                # fishing for a later admission window after missing this one.
                if end["safe"] != history.safe or end["last_id"] != history.last_id:
                    continue
                self.terminal = "abstained"  # Even a null choice is final.
                selected = self.selector.choose_next_use(
                    public_context(history), choices
                )
                if selected is None:
                    return {"status": self.terminal}
                before = (self.schedule.offset, self.events.offset)
                self._read(directory)
                if before != (self.schedule.offset, self.events.offset):
                    raise ValueError("schedule/history changed during selection")
                with _directory(self.path) as current:
                    now = os.fstat(current)
                    if (now.st_dev, now.st_ino) != identity:
                        raise ValueError("schedule directory replaced during selection")
                result = publish_envelope(
                    self.path,
                    selected,
                    host_from_schedule(
                        row,
                        engine_run_hex(self.path),
                        end["safe"] + 1,
                        end["last_id"] + 1,
                    ),
                    box,
                )
                self.terminal = "already_published"
                return result
            return {"status": "pending" if self.schedule.tail else "no_eligible_origin"}


def consider_next_use(directory, box=None):
    """Compatibility one-shot helper, NOT a polling API. Failures propagate."""
    result = NextUseScheduler(directory, seed=0).poll(box)
    return result if result["status"] == "envelope_published_not_admitted" else None
