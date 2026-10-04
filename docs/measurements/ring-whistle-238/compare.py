"""Paired ring sweep comparison (#238): main (C, attention) vs ring, same seeds.

Usage: python3 compare.py <main.json> <ring.json> > comparison.md

Gate (from docs/proposals/felt-whistle-effect.md):
  part 1 = games with 2+ distinct felt whispers excluding the hound (target 10)
  part 3 = games feeling two next-use programs (target 3)
Computed per game exactly as felt_estimate.py computes "today".
"""

import json
import sys
from collections import Counter

ESTIMATE = {  # proposal's B column (upper bound) and "today", part 1 / part 3
    "bard-default-path": ((6, 1), (12, 4)),
    "bard": ((13, 6), (31, 19)),
    "bard-inherited": ((3, 0), (6, 2)),
}
STARTS = [
    "bard-default-path",
    "bard",
    "bard-inherited",
    "madman",
    "wizard-default-path",
]


def per_game(report):
    out = {}
    for g in report["games"]:
        f = g.get("funnel") or {}
        distinct = f.get("distinct_felt") or []
        programs = f.get("programs") or []
        base = sum(1 for x in distinct if x["kind"] != "hound")
        felt_progs = {p["program"] for p in programs if p.get("felt")}
        felt_w = sum(1 for e in f.get("felt_events") or [] if e["kind"] == "next_use_W")
        out[(g["start"], g["seed"])] = dict(
            part1=base >= 2,
            part3=len(felt_progs) >= 2,
            felt_next_use=bool(felt_progs),
            felt_w=felt_w,
            delivered=sum(p.get("delivered", 0) for p in programs),
            admitted=sum(p.get("admitted", 0) for p in programs),
            outcome=g.get("outcome"),
            haunt=dict(f.get("haunt") or {}),
            haunt_steps=f.get("haunt_steps", 0),
            turn=f.get("last_turn"),
            last_turn=(
                f.get("last_turn") if isinstance(f.get("last_turn"), int) else None
            ),
            error=bool(g.get("error")),
        )
    return out


def main(a_path, b_path):
    A, B = (json.load(open(p)) for p in (a_path, b_path))
    ga, gb = per_game(A), per_game(B)
    print("# Paired sweep: main (C attention) vs ring\n")
    for name, rep in (("main", A), ("ring", B)):
        ident = rep.get("identity", {})
        print(
            f"- {name}: revision `{ident.get('revision', '?')}`, report sha256 `{rep.get('report_sha256', '?')}`"
        )
    print()
    print(
        "| start | games | part 1 main / ring | part 3 main / ring | proposal today / B estimate | games with a felt next-use program main / ring | delivered effects main / ring | admitted main / ring | felt W events main / ring | deaths main / ring | harness errors main / ring |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for st in STARTS:
        keys = sorted(k for k in ga if k[0] == st and k in gb)
        if not keys:
            continue

        def s(g, f):
            return sum(int(g[k][f]) for k in keys)

        def c(g, val):
            return sum(1 for k in keys if g[k]["outcome"] == val)

        est = ESTIMATE.get(st)
        est_s = f"{est[0][0]} / {est[0][1]} → {est[1][0]} / {est[1][1]}" if est else "–"
        print(
            f"| {st} | {len(keys)} | {s(ga, 'part1')} / {s(gb, 'part1')} | {s(ga, 'part3')} / {s(gb, 'part3')} | {est_s} "
            f"| {s(ga, 'felt_next_use')} / {s(gb, 'felt_next_use')} | {s(ga, 'delivered')} / {s(gb, 'delivered')} "
            f"| {s(ga, 'admitted')} / {s(gb, 'admitted')} | {s(ga, 'felt_w')} / {s(gb, 'felt_w')} "
            f"| {c(ga, 'died')} / {c(gb, 'died')} | {s(ga, 'error')} / {s(gb, 'error')} |"
        )
    print()
    print(
        "Hound admission by start (haunting event details summed over games; games with an accepted hound; visible steps):\n"
    )
    print(
        "| start | haunting details main | haunting details ring | games accepted main / ring | steps main / ring | seeds whose hound details differ |"
    )
    print("|---|---|---|---|---|---|")
    hound_changed = 0
    for st in STARTS:
        keys = sorted(k for k in ga if k[0] == st and k in gb)
        if not keys:
            continue

        def tot(g):
            c = Counter()
            for k in keys:
                c.update(g[k]["haunt"])
            return dict(sorted(c.items()))

        def acc(g):
            return sum(1 for k in keys if g[k]["haunt"].get("accepted"))

        def steps(g):
            return sum(g[k]["haunt_steps"] for k in keys)

        diff = [k[1] for k in keys if ga[k]["haunt"] != gb[k]["haunt"]]
        hound_changed += len(diff)
        print(
            f"| {st} | `{tot(ga)}` | `{tot(gb)}` | {acc(ga)} / {acc(gb)} | {steps(ga)} / {steps(gb)} | {diff or 'none'} |"
        )
    print(f"\nHOUND_CHANGED_SEEDS={hound_changed}\n")
    print("Final turn (status line T) by start, median main / ring:\n")
    import statistics

    for st in STARTS:
        keys = sorted(k for k in ga if k[0] == st and k in gb)
        ta = [ga[k]["turn"] for k in keys if isinstance(ga[k]["turn"], int)]
        tb = [gb[k]["turn"] for k in keys if isinstance(gb[k]["turn"], int)]
        if ta and tb:
            print(
                f"- {st}: median {statistics.median(ta)} / {statistics.median(tb)}; total {sum(ta)} / {sum(tb)}; seeds with a different final turn {sum(1 for k in keys if ga[k]['turn'] != gb[k]['turn'])}"
            )
    print()
    print("Outcome changes by start (main → ring, same seed):\n")
    for st in STARTS:
        keys = sorted(k for k in ga if k[0] == st and k in gb)
        ch = Counter(
            (ga[k]["outcome"], gb[k]["outcome"])
            for k in keys
            if ga[k]["outcome"] != gb[k]["outcome"]
        )
        same = sum(1 for k in keys if ga[k]["outcome"] == gb[k]["outcome"])
        seeds = [k[1] for k in keys if ga[k]["outcome"] != gb[k]["outcome"]]
        print(
            f"- {st}: same outcome {same}/{len(keys)}; changed {dict(ch) if ch else 'none'}"
            + (f"; seeds {seeds}" if seeds else "")
        )
    for st in STARTS:
        for name, rep in (("main", A), ("ring", B)):
            agg = rep["aggregate"].get(st)
            if agg and st in ("bard-default-path", "bard", "bard-inherited"):
                print(
                    f"\n<details><summary>{st} {name}: loss reasons</summary>\n\n`{json.dumps(agg.get('loss_reasons'))}`\n\n</details>"
                )


if __name__ == "__main__":
    main(*sys.argv[1:3])
