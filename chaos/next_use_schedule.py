"""Read a bounded next-use origin schedule. Not an observation event."""

import json
import os
from pathlib import Path

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
    row = json.loads(raw.decode("ascii"))
    if type(row) is not dict or set(row) != _KEYS:
        raise ValueError("schedule schema")
    if row["next_use_schedule_v"] != 1 or row["family"] not in ("W", "F"):
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


def read_schedule_rows(path):
    """Private bounded schedule lines. An incomplete tail is not a row."""
    from .director import secure_open

    fd = secure_open(path)
    with os.fdopen(fd, "rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        if size > _MAX_BYTES:
            raise ValueError("schedule byte cap")
        raw = handle.read(size + 1)
    if len(raw) != size:
        raise ValueError("schedule changed while reading")
    if raw and not raw.endswith(b"\n"):
        tail = raw.rsplit(b"\n", 1)[-1]
        if len(tail) > _MAX_LINE:
            raise ValueError("schedule tail")
        raw = raw[: len(raw) - len(tail)]
    lines = raw.splitlines(keepends=True) if raw else []
    if len(lines) > _MAX_RECORDS:
        raise ValueError("schedule record cap")
    rows = [parse_schedule_line(line) for line in lines]
    seen = set()
    for row in rows:
        identity = (row["family"], row["root"], row["notice_seq"], row["end_seq"])
        if identity in seen:
            raise ValueError("schedule duplicate")
        seen.add(identity)
    return rows


def host_from_schedule(row, run_hex, at, program_id):
    """Host fields for an envelope. move is monstermoves, not turn."""
    if type(run_hex) is not str or len(run_hex) != 64:
        raise ValueError("schedule run")
    if type(at) is not int or type(program_id) is not int or at < 1 or program_id < 1:
        raise ValueError("schedule host")
    return {
        "at": at,
        "id": program_id,
        "level_dlevel": row["level_dlevel"],
        "level_dnum": row["level_dnum"],
        "move": row["move"],
        "run": run_hex,
        "variant": 0,
    }


def publish_scheduled(directory, selected, run_hex, at, program_id, box=None):
    """Publish one envelope from a ready origin schedule. Never admits."""
    from .next_use_envelope import publish_envelope

    path = Path(directory) / "next_use-schedule.jsonl"
    if not path.is_file():
        raise ValueError("origin schedule missing")
    family = selected.get("family") if type(selected) is dict else None
    origin = selected.get("origin") if type(selected) is dict else None
    if type(origin) is not dict:
        raise ValueError("origin schedule mismatch")
    matches = [
        row
        for row in read_schedule_rows(path)
        if row["family"] == family
        and row["root"] == origin.get("root_seq")
        and row["notice_seq"] == origin.get("notice_seq")
        and row["end_seq"] == origin.get("end_seq")
    ]
    if len(matches) != 1:
        raise ValueError("origin schedule mismatch")
    row = matches[0]
    return publish_envelope(
        directory, selected, host_from_schedule(row, run_hex, at, program_id), box
    )


def consider_next_use(directory, box=None):
    """Publish one envelope from the earliest matching origin. No model call.

    Extra unmatched records do not block publication. A duplicate identity,
    a malformed complete line, or an existing envelope publishes nothing.
    ``box`` is the lock the caller already holds.
    """
    from .history import HistoryState, public_context
    from .history_choice import RandomHistoryBackend
    from .next_use_envelope import engine_run_hex
    from .next_use_history import next_use_menu

    directory = Path(directory)
    schedule_path = directory / "next_use-schedule.jsonl"
    if not schedule_path.is_file() or (directory / "next_use-envelope.json").exists():
        return None
    events = directory / "events.jsonl"
    if not events.is_file():
        return None
    try:
        history = HistoryState(events.read_bytes())
        schedules = read_schedule_rows(schedule_path)
    except (OSError, ValueError):
        return None
    if history.safe >= 2147483647 or history.last_id >= 2147483647 or not schedules:
        return None
    menu_rows = list(next_use_menu(history))
    schedule = None
    for candidate in schedules:
        if any(
            row["family"] == candidate["family"]
            and row["origin"]["root_seq"] == candidate["root"]
            and row["origin"]["notice_seq"] == candidate["notice_seq"]
            and row["origin"]["end_seq"] == candidate["end_seq"]
            for row in menu_rows
        ):
            schedule = candidate
            break
    if schedule is None:
        return None
    menu = [
        row
        for row in next_use_menu(history)
        if row["family"] == schedule["family"]
        and row["origin"]["root_seq"] == schedule["root"]
        and row["origin"]["notice_seq"] == schedule["notice_seq"]
        and row["origin"]["end_seq"] == schedule["end_seq"]
    ]
    if not menu:
        return None
    selected = RandomHistoryBackend(0).choose_next_use(public_context(history), menu)
    if selected is None:
        return None
    try:
        return publish_scheduled(
            directory,
            selected,
            engine_run_hex(directory),
            history.safe + 1,
            history.last_id + 1,
            box,
        )
    except (OSError, ValueError):
        return None
