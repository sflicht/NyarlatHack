"""Read a bounded next-use origin schedule. Not an observation event."""

import json
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
    matches = []
    for line in path.read_bytes().splitlines(keepends=True):
        row = parse_schedule_line(line)
        if row["family"] == family:
            matches.append(row)
    if len(matches) != 1 or type(origin) is not dict:
        raise ValueError("origin schedule mismatch")
    row = matches[0]
    if (
        row["root"] != origin.get("root_seq")
        or row["notice_seq"] != origin.get("notice_seq")
        or row["end_seq"] != origin.get("end_seq")
    ):
        raise ValueError("origin schedule mismatch")
    return publish_envelope(
        directory, selected, host_from_schedule(row, run_hex, at, program_id), box
    )


def consider_next_use(directory, box=None):
    """Host-built quiet selection from one matching schedule. No model call.

    Missing, extra, or unmatched schedules publish nothing. An existing
    envelope is left alone. This does not admit. ``box`` is the lock the
    caller already holds; opening a second mailbox would fail.
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
        schedules = [
            parse_schedule_line(line)
            for line in schedule_path.read_bytes().splitlines(keepends=True)
        ]
    except (OSError, ValueError):
        return None
    if (
        len(schedules) != 1
        or history.safe >= 2147483647
        or history.last_id >= 2147483647
    ):
        return None
    schedule = schedules[0]
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
