"""Later-program funnel: lever table and gate-effect ESTIMATES. Post-run only.

Inputs: funnel.json (funnel.py output), the plain sweep report JSON, and the
retained plain/instrumented per-game copies (for the blocked-callback lever).

Every gate figure here is an estimate, not a measurement. Assumptions:
* A lever adds at most one newly felt next-use program per game (games are
  de-duplicated), and adding one changes nothing else in that game.
* Gate part 1 (games with 2+ distinct felt whispers, excluding the hound)
  gains a game only where that game had exactly 1 such whisper.
  Gate part 3 (games feeling two next-use programs) gains a game only where
  exactly 1 program was felt.
* Each newly admitted or rescued program is felt with probability p:
  - budget +k: p = later programs felt / later programs admitted (this start);
  - program-1 whistle-time check: p = program-1 felt / program-1 admitted;
  - origin deadline: p = later-program delivered callbacks / later callbacks,
    applied once per program that had a companion-in-view whistle between the
    origin deadline and its own expiry;
  - blocked callbacks: p = 1 (UPPER BOUND: as if every blocked later program
    had delivered; it would also make those moves unattributable to the
    program, which is why the rule exists).

Usage: estimate.py FUNNEL_JSON SWEEP_REPORT_JSON PLAIN_RUNS DIAG_RUNS > estimate.json
"""

import importlib.util
import json
from pathlib import Path
import sys

STARTS = ["bard-default-path", "bard", "bard-inherited"]


def main(funnel_path, report_path, plain, diag):
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("funnel", here / "funnel.py")
    fn = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fn)
    f = json.loads(Path(funnel_path).read_text())
    rep = json.loads(Path(report_path).read_text())
    plain, diag = Path(plain), Path(diag)
    excluded = set(f["twin"]["games_differing"])
    by_game = {f"{g['start']}-{g['seed']:05d}": g["funnel"] for g in rep["games"]}

    def state(name):
        g = by_game[name]
        distinct = sum(1 for x in g["distinct_felt"] if x["kind"] != "hound")
        programs = sum(1 for p in g["programs"] if p["felt"])
        return distinct, programs

    out = {}
    for st in STARTS:
        a = rep["aggregate"][st]
        progs = {p["program"]: p for p in a["programs"]}
        later_adm = sum(progs[k]["admitted"] for k in (2, 3))
        later_felt = sum(progs[k]["felt"] for k in (2, 3))
        p_later = later_felt / later_adm if later_adm else 0.0
        p_first = (
            progs[1]["felt"] / progs[1]["admitted"] if progs[1]["admitted"] else 0.0
        )
        dirs = sorted(d for d in plain.iterdir() if d.name.rsplit("-", 1)[0] == st)
        games = [
            fn.game(d, None if d.name in excluded else diag / d.name) for d in dirs
        ]
        later = [
            (g["name"], p) for g in games for p in g["programs"] if p["ordinal"] >= 2
        ]
        cb = [u for _, p in later for u in p["uses"]]
        p_cb = sum(u["outcome"] == "delivered" for u in cb) / len(cb) if cb else 0.0
        blocked = [
            n
            for n, p in later
            if any(u["outcome"] == "blocked" for u in p["uses"])
            and not any(u["outcome"] == "delivered" for u in p["uses"])
        ]
        v = f["starts"][st]
        origin = [
            x["game"]
            for x in v["q2"]["programs"]
            if x["whistles_after_origin_expiry_companion_in_view"] > 0
        ]
        plus1 = [r["game"] for r in v["q3"]["rows"] if r["admit_plus1"]]
        plus2 = [r["game"] for r in v["q3"]["rows"] if r["admit_plus2"]]
        p1 = [
            x["game"]
            for x in v["q4"]["games_detail"]
            if x["later_whistle_companion_in_view"]
        ]

        def est(names, p):
            gs = sorted(set(names))
            return dict(
                programs=len(names),
                games=len(gs),
                p=round(p, 3),
                part1_gain=round(p * sum(state(n)[0] == 1 for n in gs), 1),
                part3_gain=round(p * sum(state(n)[1] == 1 for n in gs), 1),
            )

        two = sum(
            1
            for g in rep["games"]
            if g["start"] == st
            and sum(1 for p in g["funnel"]["programs"] if p["felt"]) >= 2
        )
        blocked_callbacks = sum(
            v["q1"][k]["outcomes"].get("W:blocked", 0)
            for k in ("program_1", "program_2", "program_3")
        )
        out[st] = dict(
            gate_now=dict(
                part1=a["distinct_felt"]["games_2plus_excluding_hound"],
                part3=two,
                targets=dict(part1=10, part3=3),
            ),
            levers=dict(
                blocked_callbacks=dict(
                    measured=dict(
                        blocked_callbacks_all_programs=blocked_callbacks,
                        later_programs_blocked_never_delivered=len(blocked),
                    ),
                    estimate_upper_bound=est(blocked, 1.0),
                ),
                origin_deadline=dict(
                    measured=dict(
                        later_programs_origin_expired=v["q2"]["n"],
                        with_companion_whistle_after_origin_deadline=len(origin),
                    ),
                    estimate=est(origin, p_cb),
                ),
                budget=dict(
                    measured=dict(
                        later_refusals_budget=v["q3"]["refusals"],
                        admitted_at_plus1=len(plus1),
                        admitted_at_plus2=len(plus2),
                        sanity_only_view_plus1=v["q3"]["sanity_only_admitted_at_plus1"],
                        sanity_only_view_plus2=v["q3"]["sanity_only_admitted_at_plus2"],
                    ),
                    estimate_plus1=est(plus1, p_later),
                    estimate_plus2=est(plus2, p_later),
                ),
                program1_whistle_check=dict(
                    measured=dict(
                        refusals_no_companion=v["q4"]["refusal_decisions"],
                        games_later_whistle_companion_in_view=len(p1),
                    ),
                    estimate_upper_bound=est(p1, p_first),
                ),
            ),
        )
    return out


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:5]), indent=1, sort_keys=True))
