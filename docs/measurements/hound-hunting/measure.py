"""Hounds that hunt: shadow-trial pressure metrics (NGPL).

baseline: footsteps.lua and the retained #251 pilot sources
(docs/measurements/hound-free-pilot/run/jobs/*/<last attempt>/source.lua)
through the engine's real shadow trial, with the same 4 rooms x 3 seeds as
the #251 pilot (pilot.ROOMS, pilot.SEEDS, pilot.link, pilot.shadow). One row
per trial: moved, blocked, contacts, max_damage, escaped, min_dist,
median_dist and the engine's own accepted bit.

pilot: the same for a new generation run directory (pilot.py layout).

table: a Markdown table of per-source medians from a trials file.

Run inside hermes-heavy after a CHAOS=1 dev install of the tree being
measured (the link uses its src/*.o):

  measure.py baseline --out <file.json> --work <scratch dir>
  measure.py pilot <run dir> --out <file.json> --work <scratch dir>
  measure.py table <file.json>
"""

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "docs/measurements/hound-free-pilot"))

import pilot  # noqa: E402

OLD = ROOT / "docs/measurements/hound-free-pilot/run"
FIELDS = (
    "accepted",
    "moved",
    "blocked",
    "contacts",
    "max_damage",
    "escaped",
    "min_dist",
    "median_dist",
)


def sources_of(run):
    out = {}
    for job in sorted((run / "jobs").iterdir()):
        final = sorted(p for p in job.iterdir() if (p / "receipt.json").exists())[-1]
        if (final / "source.lua").exists():
            out[job.name] = (final / "source.lua").read_bytes()
    return out


def measure(sources, out, work):
    exe = pilot.link(work)
    results = {}
    for name, source in sources.items():
        rows = []
        for room in pilot.ROOMS:
            for seed in pilot.SEEDS:
                row = pilot.shadow(exe, source, room, seed, work)
                row["reason"] = pilot.reason(row["report"])
                rows.append(row)
        results[name] = dict(source_sha256=hashlib.sha256(source).hexdigest(), trials=rows)
        print(name, sum(r["reason"] is None for r in rows), "/", len(rows), flush=True)
    Path(out).write_text(json.dumps(results, indent=1, sort_keys=True) + "\n")


def baseline(args):
    sources = {"footsteps": pilot.FOOTSTEPS.read_bytes(), **sources_of(OLD)}
    measure(sources, args.out, Path(args.work))


def new_pilot(args):
    sources = {"footsteps": pilot.FOOTSTEPS.read_bytes(), **sources_of(Path(args.run))}
    measure(sources, args.out, Path(args.work))


def _med(xs):
    return statistics.median(xs) if xs else None


def table(args):
    data = json.loads(Path(args.file).read_text())
    print(
        "| source | accepted | moved med (min) | blocked med | contacts med (trials >0) "
        "| max_damage max | escaped | min_dist med (max) | median_dist med |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for name, t in data.items():
        reps = [r["report"] for r in t["trials"] if r["report"]]
        col = {f: [r[f] for r in reps] for f in FIELDS}
        print(
            f"| {name} | {sum(col['accepted'])}/{len(reps)} "
            f"| {_med(col['moved'])} ({min(col['moved'])}) | {_med(col['blocked'])} "
            f"| {_med(col['contacts'])} ({sum(c > 0 for c in col['contacts'])}) "
            f"| {max(col['max_damage'])} | {sum(col['escaped'])}/{len(reps)} "
            f"| {_med(col['min_dist'])} ({max(col['min_dist'])}) | {_med(col['median_dist'])} |"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baseline")
    b.add_argument("--out", required=True)
    b.add_argument("--work", required=True)
    p = sub.add_parser("pilot")
    p.add_argument("run")
    p.add_argument("--out", required=True)
    p.add_argument("--work", required=True)
    t = sub.add_parser("table")
    t.add_argument("file")
    args = parser.parse_args(argv)
    {"baseline": baseline, "pilot": new_pilot, "table": table}[args.cmd](args)


if __name__ == "__main__":
    main()
