"""Ring guard firing counts (#238), read from each game's private journal.

Usage (run with the ring export on sys.path):
  python3 guards.py <ring-export> <sweep-work-dir> > guards.json

Counts CHAOS_EFFECT_W_RING_DELIVERED (13) and _GUARDED (14) effect rows per
start, and guarded rows by their recorded guard (the row's "suppression").
Names follow enum chaos_next_use_ring_guard (include/chaos_next_use_runtime.h).
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

GUARDS = {
    1: "confused",
    2: "stunned",
    3: "hallucinating",
    4: "engulfed",
    5: "low_hp",
    6: "hostile_adjacent",
    7: "peaceful_adjacent",
    8: "water_adjacent",
}


def main(export, work):
    sys.path.insert(0, export)
    from chaos.next_use_journal import JournalError, read_journal

    out = defaultdict(
        lambda: dict(
            games=0,
            delivered=0,
            guarded=0,
            games_delivered=0,
            games_guarded=0,
            by_guard=Counter(),
            journal_errors=0,
        )
    )
    for gdir in sorted(Path(work).iterdir()):
        if not gdir.is_dir() or gdir.name.startswith("."):
            continue
        start, _, seed = gdir.name.rpartition("-")
        if not seed.isdigit():
            continue
        s = out[start]
        s["games"] += 1
        d = g = 0
        records = []
        # Program 1 writes next_use-journal.jsonl; programs 2-3 write
        # next_use-journal.<ordinal>.jsonl (tests/chaos/sweep_programs.py).
        for j in sorted((gdir / "run").glob("next_use-journal*.jsonl")):
            try:
                records.extend(read_journal(j)["records"])
            except JournalError:
                s["journal_errors"] += 1
        for r in records:
            for p in r["data"].get("private_records", []):
                if p["kind"] != 4:
                    continue
                o = p["data"]["outcome"]
                if o == 13:
                    d += 1
                elif o == 14:
                    g += 1
                    s["by_guard"][GUARDS.get(p["data"].get("suppression"), "?")] += 1
        s["delivered"] += d
        s["guarded"] += g
        s["games_delivered"] += d > 0
        s["games_guarded"] += g > 0
    print(
        json.dumps(
            {k: {**v, "by_guard": dict(v["by_guard"])} for k, v in sorted(out.items())},
            indent=1,
        )
    )


if __name__ == "__main__":
    main(*sys.argv[1:3])
