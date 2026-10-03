"""Paired main-vs-PR analysis for broad next-use (C). Post-run only.

Reads two retained baseline-v2 seed-sweep reports (5 starts x seeds 1-100):
main is #233's PR-side sweep (53acae76, game sources identical to main
1f51bfff after B), PR is this branch (dcd91662). It scores the adopted arc gate with the committed #231 metric
(``sweep_programs.distinct_felt`` over the stored public ``felt_events``):

1. bard-default-path games with 2+ distinct felt whispers excluding the hound
   (gate >= 10/100);
2. hound admission unchanged from main (games with an accepted hound, and
   per seed whether the hound was accepted);
3. bard-default-path games that feel two next-use programs (gate >= 3/100).

Usage: paired.py MAIN.json PR.json > paired.json. Prints sorted JSON.
"""

import json
from pathlib import Path
import sys

R = Path("/home/hermes/worktrees/NyarlatHack/hermes-session-nyarlathack-queue-2")
sys.path[:0] = [str(R), str(R / "tests/chaos")]
from sweep_programs import distinct_felt  # noqa: E402

GATE_START = "bard-default-path"


def per_game(game):
    funnel = game.get("funnel", {})
    if "felt_events" not in funnel:
        return None
    distinct = distinct_felt(funnel["felt_events"])
    programs = funnel.get("programs", [])
    return dict(
        distinct=len(distinct),
        distinct_excl_hound=sum(e["kind"] != "hound" for e in distinct),
        hound_accepted=bool(funnel.get("haunt", {}).get("accepted")),
        programs_felt=sum(bool(p.get("felt")) for p in programs),
        admitted=[p["program"] for p in programs if p.get("admitted")],
        felt=[p["program"] for p in programs if p.get("felt")],
        terminations={p["program"]: p.get("termination") for p in programs},
    )


def side(path):
    report = json.loads(Path(path).read_text())
    rows = {}
    for game in report["games"]:
        rows[(game["start"], game["seed"])] = (game["outcome"], per_game(game))
    return report, rows


def summary(report, rows, start):
    games = [v for (s, _), v in rows.items() if s == start]
    usable = [m for _, m in games if m is not None]
    agg = report["aggregate"][start]
    programs = {p["program"]: p for p in agg.get("programs", [])}
    return dict(
        games=len(games),
        harness_errors=sum(o == "harness_error" for o, _ in games),
        scored=len(usable),
        games_2plus_excl_hound=sum(m["distinct_excl_hound"] >= 2 for m in usable),
        games_2plus_distinct=sum(m["distinct"] >= 2 for m in usable),
        games_two_programs_felt=sum(m["programs_felt"] >= 2 for m in usable),
        hound_games_accepted=agg["hound"]["games_accepted"],
        hound_steps=agg["hound"]["steps"],
        per_program={
            k: dict(
                published=v["published"],
                admitted=v["admitted"],
                felt=v["felt"],
                terminations=v["terminations"],
            )
            for k, v in sorted(programs.items())
        },
    )


def main(main_path, pr_path):
    out = dict(gate_start=GATE_START, sides={}, starts={}, paired={})
    reports = {}
    for name, path in (("main", main_path), ("pr", pr_path)):
        report, rows = side(path)
        reports[name] = rows
        out["sides"][name] = dict(
            revision=report["identity"]["revision"],
            report_sha256=report.get("report_sha256"),
            games=len(rows),
        )
        for start in sorted(report["aggregate"]):
            out["starts"].setdefault(start, {})[name] = summary(report, rows, start)
    for start in out["starts"]:
        keys = sorted(
            k for k in reports["main"] if k[0] == start and k in reports["pr"]
        )
        pairs = [
            (k[1], reports["main"][k][1], reports["pr"][k][1])
            for k in keys
            if reports["main"][k][1] is not None and reports["pr"][k][1] is not None
        ]
        out["paired"][start] = dict(
            seeds_compared=len(pairs),
            hound_accepted_differs=[
                s for s, a, b in pairs if a["hound_accepted"] != b["hound_accepted"]
            ],
            excl_hound_up=[
                s
                for s, a, b in pairs
                if b["distinct_excl_hound"] > a["distinct_excl_hound"]
            ],
            excl_hound_down=[
                s
                for s, a, b in pairs
                if b["distinct_excl_hound"] < a["distinct_excl_hound"]
            ],
        )
    g = out["starts"][GATE_START]
    out["gate"] = dict(
        two_plus_excl_hound=dict(
            main=g["main"]["games_2plus_excl_hound"],
            pr=g["pr"]["games_2plus_excl_hound"],
            target=10,
            met=g["pr"]["games_2plus_excl_hound"] >= 10,
        ),
        hound_admission_unchanged=dict(
            main=g["main"]["hound_games_accepted"],
            pr=g["pr"]["hound_games_accepted"],
            seeds_differing=out["paired"][GATE_START]["hound_accepted_differs"],
            met=g["main"]["hound_games_accepted"] == g["pr"]["hound_games_accepted"]
            and not out["paired"][GATE_START]["hound_accepted_differs"],
        ),
        two_programs_felt=dict(
            main=g["main"]["games_two_programs_felt"],
            pr=g["pr"]["games_two_programs_felt"],
            target=3,
            met=g["pr"]["games_two_programs_felt"] >= 3,
        ),
    )
    return out


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), indent=1, sort_keys=True))
