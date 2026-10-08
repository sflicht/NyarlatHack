"""Summarise the curio-window games (see PREREGISTERED.md).

usage: analyze.py RESULTS.jsonl [SUMMARY.json]

Uses only seeds whose four games (before/after x pace 1/3) are all present.
Prints a table and writes the summary JSON (sorted keys) when a path is given.
"""

from collections import Counter
import json
from pathlib import Path
import sys

rows = [json.loads(s) for s in Path(sys.argv[1]).read_text().splitlines() if s.strip()]
games = {}
for r in rows:
    key = (r["tree"], float(r["pace"]), int(r["seed"]))
    if key in games:
        raise SystemExit(f"duplicate game {key}")
    games[key] = r
seeds = sorted(
    {
        s
        for (_, _, s) in games
        if all((t, p, s) in games for t in ("before", "after") for p in (1.0, 3.0))
    }
)


def first(r, detail):
    return next((c for c in r.get("curio", []) if c["detail"] == detail), None)


def lane_step(r, step):
    return next((x for x in r.get("lane", []) if x["step"] == step), None)


def facts(r):
    placed = [c for c in r.get("curio", []) if c["detail"] == "placed"]
    ready = lane_step(r, "published") or lane_step(r, "ready")
    return dict(
        requested=lane_step(r, "requested") is not None,
        ready=ready is not None and ready.get("outcome") == "ready",
        admitted=first(r, "admitted"),
        placed=placed[0] if placed else None,
        placed_count=len(placed),
        expired=first(r, "expired"),
        on_screen=bool(r.get("name_on_screen")),
        died=r.get("outcome") == "died",
        error=r.get("outcome") == "harness_error",
        mines=r.get("branch") == "mines",
    )


def where(c):
    return None if c is None else f"{c['branch']} {c['dlvl']}"


summary = dict(seeds=seeds, n_seeds=len(seeds), cells={}, paired={}, anomalies=[])
for pace in (1.0, 3.0):
    for tree in ("before", "after"):
        fs = [facts(games[tree, pace, s]) for s in seeds]
        rs = [games[tree, pace, s] for s in seeds]
        cell = dict(
            games=len(fs),
            requested=sum(f["requested"] for f in fs),
            ready=sum(f["ready"] for f in fs),
            admitted=sum(f["admitted"] is not None for f in fs),
            placed=sum(f["placed"] is not None for f in fs),
            expired=sum(f["expired"] is not None for f in fs),
            name_on_screen=sum(f["on_screen"] for f in fs),
            entered_mines=sum(f["mines"] for f in fs),
            died=sum(f["died"] for f in fs),
            harness_errors=sum(f["error"] for f in fs),
            admitted_at=dict(
                sorted(
                    Counter(where(f["admitted"]) for f in fs if f["admitted"]).items()
                )
            ),
            placed_at=dict(
                sorted(Counter(where(f["placed"]) for f in fs if f["placed"]).items())
            ),
            expired_at=dict(
                sorted(Counter(where(f["expired"]) for f in fs if f["expired"]).items())
            ),
            outcomes=dict(sorted(Counter(r.get("outcome") for r in rs).items())),
            achieved_pace_median=sorted(r.get("achieved_pace") or 0 for r in rs)[
                len(rs) // 2
            ]
            if rs
            else None,
        )
        summary["cells"][f"{tree} pace {pace:g}"] = cell
        for s, f, r in zip(seeds, fs, rs):
            if f["placed_count"] > 1:
                summary["anomalies"].append(
                    f"{tree} pace {pace:g} seed {s}: placed twice"
                )
            p = f["placed"]
            if p is not None and (p["dlvl"] or 0) > 5:
                summary["anomalies"].append(
                    f"{tree} pace {pace:g} seed {s}: placed below 5"
                )
            if r.get("ledger_files"):
                summary["anomalies"].append(
                    f"{tree} pace {pace:g} seed {s}: ledger file"
                )
            rec = r.get("receipt") or {}
            if rec and rec.get("provider") != "fake":
                summary["anomalies"].append(
                    f"{tree} pace {pace:g} seed {s}: non-fake provider"
                )
    pair = Counter()
    for s in seeds:
        b = facts(games["before", pace, s])["placed"] is not None
        a = facts(games["after", pace, s])["placed"] is not None
        pair[
            "both"
            if a and b
            else "after only"
            if a
            else "before only"
            if b
            else "neither"
        ] += 1
    summary["paired"][f"pace {pace:g}"] = dict(sorted(pair.items()))

print(
    f"seeds with all four games: {len(seeds)} ({seeds[0] if seeds else '-'}..{seeds[-1] if seeds else '-'})"
)
cols = (
    "requested",
    "ready",
    "admitted",
    "placed",
    "expired",
    "name_on_screen",
    "entered_mines",
    "died",
    "harness_errors",
)
print("cell".ljust(18) + "".join(c[:9].rjust(10) for c in cols))
for name, cell in summary["cells"].items():
    print(name.ljust(18) + "".join(str(cell[c]).rjust(10) for c in cols))
for name, cell in summary["cells"].items():
    print(
        name,
        "admitted",
        cell["admitted_at"],
        "placed",
        cell["placed_at"],
        "expired",
        cell["expired_at"],
    )
print("paired placement:", summary["paired"])
print("anomalies:", summary["anomalies"] or "none")
if len(sys.argv) > 2:
    Path(sys.argv[2]).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
