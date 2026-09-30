#!/usr/bin/env python3
"""Alert rules for the scheduled seed sweep (#180).

    sweep_alert.py check REPORT.json
        Exit 1 if any game has a new harness error, a nonzero exit, a
        director sync timeout, or a failed restore. Anything else, including
        deaths and low delivery, is a measurement, not an alert.

    sweep_alert.py compare FIRST.json SECOND.json
        Reproducibility: every game present in SECOND must have a per-game
        entry identical to the same (start, seed) in FIRST. Exit 1 otherwise.

Reads only reports written by scripts/seed_sweep.py. Writes nothing.
"""

import argparse
import json
import sys
from pathlib import Path

# Known harness errors, accepted with sweep v2 on 2026-09-29 (see
# docs/measurements/seed-sweep-v2-179/README.md, "Limits"). The scripted
# player misreads the "Please follow me" exchange on these two seeds. Each
# entry must match start, seed AND the error text; anything else alerts.
KNOWN_HARNESS_ERRORS = {
    ("bard", 48): "Please follow me",
    ("bard", 75): "Please follow me",
}


def _games(path):
    report = json.loads(Path(path).read_text())
    return report["games"]


def known(game):
    text = KNOWN_HARNESS_ERRORS.get((game["start"], game["seed"]))
    return text is not None and text in (game.get("error") or "")


def problems(games):
    """One line per alert-worthy problem, in report order."""
    out = []
    for g in games:
        where = f"{g['start']} seed {g['seed']}"
        if g["outcome"] == "harness_error" and not known(g):
            out.append(f"{where}: new harness error: {(g.get('error') or '')[:160]}")
        if g.get("exit_code") not in (0, None):
            out.append(f"{where}: nonzero exit {g['exit_code']}")
        if g.get("sync_timeouts"):
            out.append(f"{where}: {g['sync_timeouts']} director sync timeout(s)")
        sr = g.get("save_restore") or {}
        if sr.get("attempted") and sr.get("session_detail") != "restore":
            out.append(f"{where}: restore failed ({sr.get('session_detail')!r})")
    return out


def differences(first, second):
    """(start, seed) keys whose per-game entries differ or are missing."""
    base = {(g["start"], g["seed"]): g for g in first}
    out = []
    for g in second:
        key = (g["start"], g["seed"])
        if key not in base:
            out.append(f"{key[0]} seed {key[1]}: missing from the first pass")
        elif base[key] != g:
            fields = sorted(
                k for k in set(g) | set(base[key]) if g.get(k) != base[key].get(k)
            )
            out.append(f"{key[0]} seed {key[1]}: differs in {', '.join(fields)}")
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Alert rules for the scheduled seed sweep (#180)."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("report")
    p = sub.add_parser("compare")
    p.add_argument("first")
    p.add_argument("second")
    args = parser.parse_args(argv)

    if args.cmd == "check":
        games = _games(args.report)
        found = problems(games)
        allowed = sum(1 for g in games if g["outcome"] == "harness_error" and known(g))
        print(f"{len(games)} games; {allowed} known harness error(s) allowlisted")
        label = "ALERT"
    else:
        second = _games(args.second)
        found = differences(_games(args.first), second)
        print(f"{len(second)} games compared")
        label = "NOT REPRODUCIBLE"
    for line in found:
        print(f"{label}: {line}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
