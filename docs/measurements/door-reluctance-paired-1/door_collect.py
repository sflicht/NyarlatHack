"""#1 paired sweep: per-game door_reluctance / hound facts from a sweep work dir.

Reads only public run files (events.jsonl) of each game directory and writes
one JSON row per game: door acks (turn, status, reason), the first resisted
door notice under an active door effect, and the first level-entry safe
points. Dlvl is joined later from the sweep report's dlvl_timeline.
"""

import json
import sys
from pathlib import Path

work, out = Path(sys.argv[1]), Path(sys.argv[2])
rows = []
for game in sorted(
    p for p in work.iterdir() if p.is_dir() and not p.name.startswith(".")
):
    start, seed = game.name.rsplit("-", 1)
    ev = game / "run" / "events.jsonl"
    events = [json.loads(x) for x in ev.read_text().splitlines()] if ev.exists() else []
    acks = [
        {
            k: e.get(k)
            for k in ("turn", "status", "reason", "mutation", "detail", "expires")
        }
        for e in events
        if e["event"] == "ack"
    ]
    door_until, felt = None, None
    for e in events:
        if (
            e["event"] == "ack"
            and e.get("status") == "accepted"
            and e.get("mutation") == "door_reluctance"
        ):
            door_until = e["expires"]
        elif e["event"] == "expiry" and e.get("detail") == "door_reluctance":
            door_until = None
        o = e.get("observation")
        if (
            felt is None
            and o
            and door_until is not None
            and e["turn"] < door_until
            and o["operation"] == "door_open"
            and o["stage"] == "notice"
            and o.get("fact") == "resisted"
        ):
            felt = e["turn"]
    rows.append(
        {
            "start": start,
            "seed": int(seed),
            "acks": acks,
            "door_felt_turn": felt,
            "door_attempts": sum(
                1
                for e in events
                if (o := e.get("observation"))
                and o["operation"] == "door_open"
                and o["stage"] == "started"
            ),
            "level_entries": [
                e["turn"]
                for e in events
                if e["event"] == "safe_point" and e["detail"] == "level_enter"
            ][:6],
        }
    )
out.write_text(json.dumps(rows))
print(f"{len(rows)} games collected into {out}")
