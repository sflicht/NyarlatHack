"""Render the README tables from funnel.json and estimate.json.

Usage: tables.py FUNNEL_JSON ESTIMATE_JSON > tables.md
"""

import json
import sys

ST = ["bard-default-path", "bard", "bard-inherited", "madman", "wizard-default-path"]
f = json.load(open(sys.argv[1]))
E = json.load(open(sys.argv[2]))
L = []


def t(h, rows):
    L.append("| " + " | ".join(h) + " |")
    L.append("|" + "---|" * len(h))
    for r in rows:
        L.append("| " + " | ".join(str(x) for x in r) + " |")
    L.append("")


def kv(d, sep=": "):
    return ", ".join(f"{k}{sep}{v}" for k, v in d.items()) or "—"


L.append("<!-- Q1 -->")
for st in ST:
    v = f["starts"][st]["q1"]
    rows = []
    for k in (1, 2, 3):
        q = v[f"program_{k}"]
        o = q["outcomes"]
        if not q["reached_callback"]:
            rows.append((k, 0, "", "", "", ""))
            continue
        other = {
            a: b
            for a, b in o.items()
            if a not in ("W:delivered", "W:blocked", "F:delivered")
        }
        first = dict(sorted(q["blocked_first_failing"].items(), key=lambda x: -x[1]))
        rows.append(
            (
                k,
                q["reached_callback"],
                o.get("W:delivered", 0) + o.get("F:delivered", 0),
                o.get("W:blocked", 0),
                kv(first, " "),
                kv(other, " "),
            )
        )
    L += [f"**{st}**", ""]
    t(
        [
            "program",
            "uses reaching callback",
            "delivered",
            "blocked",
            "blocked: first failing term",
            "quiet / other",
        ],
        rows,
    )
L.append("<!-- Q2 -->")
rows = []
for st in ST:
    q = f["starts"][st]["q2"]
    if not q["n"]:
        rows.append((st, 0, "", "", "", "", "", ""))
        continue
    m, lag = q["moves_admission_to_origin_expiry"], q["origin_lag_at_admission"]
    rows.append(
        (
            st,
            q["n"],
            f"{m['min']} / {m['median']} / {m['max']}",
            f"{lag['min']} / {lag['median']} / {lag['max']}",
            f"{q['whistle_uses']} in {q['with_any_whistle']}",
            f"{q['whistle_uses_companion_in_view']} in {q['with_whistle_companion_in_view']}",
            f"{q['fountain_drinks']} in {q['with_any_fountain']}",
            q["with_callback"],
        )
    )
t(
    [
        "start",
        "later programs ended at origin expiry",
        "moves admission → origin expiry (min / median / max)",
        "origin age at admission (min / median / max)",
        "whistle uses in window (in N programs)",
        "of those, companion in view (in N programs)",
        "fountain drinks in window (in N programs)",
        "programs with ≥ 1 callback",
    ],
    rows,
)
L.append("<!-- Q2-detail -->")
rows = []
for x in f["starts"]["bard-default-path"]["q2"]["programs"]:
    civ = (
        "".join(
            "Y" if c == 1 else ("n" if c == 0 else "?")
            for c in x["companion_in_view_at_whistle"]
        )
        or "—"
    )
    rows.append(
        (
            x["game"].rsplit("-", 1)[1].lstrip("0"),
            x["ordinal"],
            x["origin_move"],
            x["admission_move"],
            x["origin_deadline"],
            x["program_expiry"],
            x["moves_admission_to_origin_expiry"],
            x["whistle_uses"],
            civ,
            x["fountain_drinks"],
            ", ".join(x["callback_outcomes"]) or "—",
        )
    )
t(
    [
        "seed",
        "program",
        "origin move",
        "admitted",
        "origin deadline",
        "program expiry",
        "moves admitted → origin expiry",
        "whistles",
        "companion in view at each",
        "fountain drinks",
        "callback outcomes",
    ],
    rows,
)
L.append("<!-- Q3 -->")
rows = []
for st in ST:
    q = f["starts"][st]["q3"]
    rows.append(
        (
            st,
            q["refusals"],
            q["only_reason_budget"],
            kv(q["by_lost_sanity"]),
            kv(q["by_spent"]),
            kv(q["spent_by_source"], " "),
            kv(q["by_available"]),
            q["admitted_at_plus1"],
            q["admitted_at_plus2"],
            f"{q['sanity_only_admitted_at_plus1']} / {q['sanity_only_admitted_at_plus2']}",
        )
    )
t(
    [
        "start",
        "later refusals for budget",
        "budget the only reason",
        "lost Sanity (value: count)",
        "cruelty spent (value: count)",
        "spent by source (points)",
        "engine budget available (value: count)",
        "admitted at +1",
        "admitted at +2",
        "Sanity-only bound: +1 / +2",
    ],
    rows,
)
L.append("<!-- Q3-detail -->")
rows = [
    (
        r["game"].rsplit("-", 1)[1].lstrip("0"),
        r["ordinal"],
        r["move"],
        r["lost_sanity"],
        r["sanity_budget"],
        r["spent"],
        kv(dict(sorted(r["spent_by"].items())), " "),
        r["budget_available"],
        r["cost"],
        "yes" if r["admit_plus1"] else "no",
    )
    for r in f["starts"]["bard-default-path"]["q3"]["rows"]
]
t(
    [
        "seed",
        "program",
        "move",
        "lost Sanity",
        "Sanity budget (2 + lost/10)",
        "spent",
        "spent by source",
        "engine budget available",
        "cost",
        "admitted at +1",
    ],
    rows,
)
L.append("<!-- Q4 -->")
t(
    [
        "start",
        "program-1 refusals, no companion in view",
        "games",
        "games with a later whistle in the 100-move lifetime and a qualifying companion in view",
    ],
    [
        (
            st,
            f["starts"][st]["q4"]["refusal_decisions"],
            f["starts"][st]["q4"]["games"],
            f["starts"][st]["q4"]["games_later_whistle_with_companion_in_view"],
        )
        for st in ST
    ],
)
L.append("<!-- Q5 -->")
for st in ["bard-default-path", "bard", "bard-inherited"]:
    e = E[st]
    lv, g = e["levers"], e["gate_now"]
    b, p1 = lv["budget"], lv["program1_whistle_check"]
    bl, og = lv["blocked_callbacks"], lv["origin_deadline"]
    L += [
        f"**{st}** (gate now: part 1 {g['part1']} of 10, part 3 {g['part3']} of 3)",
        "",
    ]
    t(
        [
            "lever",
            "measured: programs affected",
            "estimate: part 1 gain",
            "estimate: part 3 gain",
            "p",
        ],
        [
            (
                "budget +1",
                f"{b['measured']['admitted_at_plus1']} of {b['measured']['later_refusals_budget']} "
                f"refused later programs admitted ({b['estimate_plus1']['games']} games)",
                b["estimate_plus1"]["part1_gain"],
                b["estimate_plus1"]["part3_gain"],
                b["estimate_plus1"]["p"],
            ),
            (
                "program-1 whistle-time check (upper bound)",
                f"{p1['measured']['games_later_whistle_companion_in_view']} games of "
                f"{p1['measured']['refusals_no_companion']} refused",
                p1["estimate_upper_bound"]["part1_gain"],
                p1["estimate_upper_bound"]["part3_gain"],
                p1["estimate_upper_bound"]["p"],
            ),
            (
                "blocked callbacks (upper bound)",
                f"{bl['measured']['later_programs_blocked_never_delivered']} later programs blocked, never "
                f"delivered ({bl['measured']['blocked_callbacks_all_programs']} blocked callbacks, all programs)",
                bl["estimate_upper_bound"]["part1_gain"],
                bl["estimate_upper_bound"]["part3_gain"],
                "1",
            ),
            (
                "origin deadline",
                f"{og['measured']['with_companion_whistle_after_origin_deadline']} of "
                f"{og['measured']['later_programs_origin_expired']} origin-expired programs had a "
                "companion-in-view whistle after the deadline",
                og["estimate"]["part1_gain"],
                og["estimate"]["part3_gain"],
                og["estimate"]["p"],
            ),
        ],
    )
print("\n".join(L))
