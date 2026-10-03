"""Render the README tables from felt-estimate.json.

Usage: tables.py FELT_ESTIMATE_JSON > tables.md
"""

import json
import sys

ST = ["bard-default-path", "bard", "bard-inherited", "madman", "wizard-default-path"]
CANDS = ("A_call", "B_ring", "C_carry")
E = json.load(open(sys.argv[1]))
L = []


def t(h, rows):
    L.append("| " + " | ".join(h) + " |")
    L.append("|" + "---|" * len(h))
    for r in rows:
        L.append("| " + " | ".join(str(x) for x in r) + " |")
    L.append("")


def ratio(r, c):
    return f"{r[c + '_uses']} / {r[c + '_programs']}"


L.append("<!-- T1 -->")
rows = []
for st in ST:
    v = E["starts"][st]
    for k in ("1", "2", "3"):
        r = v["per_program"][k]
        if not r["admitted_programs"]:
            continue
        rows.append(
            (
                st,
                k,
                f"{r['admitted_programs']} ({r['admitted_programs_probed']})",
                f"{r['delivered_today']} of {r['reached_callback_today']}",
                r["valid_whistles_in_window"],
                *(ratio(r, c) for c in CANDS),
                ratio(r, "today_companion_in_view"),
            )
        )
t(
    [
        "start",
        "program",
        "admitted (probed)",
        "today: delivered of reached callback",
        "valid whistles in window",
        "A call: uses / programs",
        "B ring: uses / programs",
        "C carry: uses / programs",
        "reference: companion in view, uses / programs",
    ],
    rows,
)
L.append("<!-- T2 -->")
rows = []
for st in ST:
    r = E["starts"][st]["program1_refused_no_companion"]
    rows.append(
        (
            st,
            r["program1_refused_no_companion_only"],
            r["probed"],
            *(r[c + "_programs"] for c in CANDS),
        )
    )
t(
    [
        "start",
        "program 1 refused, no companion only",
        "probed",
        "A precondition met",
        "B precondition met",
        "C precondition met",
    ],
    rows,
)
L.append("<!-- T3 -->")
rows = []
for st in ST:
    v = E["starts"][st]
    n, e = v["gate_now"], v["gate_estimate"]
    d = v["gate_estimate_without_companion_admission_check"]["B_ring"]
    rows.append(
        (
            st,
            f"{n['part1']} / {n['part3']}",
            *(f"{e[c]['part1']} / {e[c]['part3']}" for c in CANDS),
            f"{d['part1']} / {d['part3']}",
            v["games_excluded_twin"],
        )
    )
t(
    [
        "start",
        "today: part 1 / part 3",
        "A estimate",
        "B estimate",
        "C estimate",
        "B upper bound, program 1 without the companion admission check",
        "twin games excluded (counted as today)",
    ],
    rows,
)
print("\n".join(L))
