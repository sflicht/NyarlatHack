"""M2 PR 1: measure next_use-schedule.jsonl rows against its 32-row bound.

Reads only the committed paired-sweep reports for #1
(docs/measurements/door-reluctance-paired-1/{main,branch}-seeds-1-100.json).
Each qualifying whistle or fountain notice appends one schedule row, so the
per-game `qualifying_history` count is the number of rows the engine tried to
write; `candidate` is the number it managed to write before the bound.

    python3 docs/measurements/next-use-schedule-bound-m2/schedule_bound.py
"""

import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
SWEEP = HERE.parent / "door-reluctance-paired-1"
STARTS = (
    "bard-default-path",
    "wizard-default-path",
    "bard",
    "bard-inherited",
    "madman",
)
BOUND = 32  # rows; include/chaos_next_use_schedule.h, chaos/next_use_schedule.py


def summarize(games):
    out = {}
    for start in STARTS + ("all",):
        rows = [g for g in games if start in ("all", g["start"])]
        want = sorted(g["funnel"]["counts"]["qualifying_history"] for g in rows)
        wrote = [g["funnel"]["counts"]["candidate"] for g in rows]
        out[start] = dict(
            games=len(rows),
            median=statistics.median(want),
            p90=want[int(0.9 * len(want)) - 1],
            max=want[-1],
            over_bound=sum(w > BOUND for w in want),
            at_or_over_bound=sum(w >= BOUND for w in want),
            over_64=sum(w > 64 for w in want),
            truncated_writes=sum(
                c < q
                for c, q in zip(
                    wrote, (g["funnel"]["counts"]["qualifying_history"] for g in rows)
                )
            ),
            writes_match_min_bound=all(
                g["funnel"]["counts"]["candidate"]
                == min(g["funnel"]["counts"]["qualifying_history"], BOUND)
                for g in rows
            ),
        )
    return out


PROGRAM_LIFETIME = 100  # moves; program 1 is terminal by admission + 100


def fresh_rows(kept):
    """Rows a second program could bind under the fresh-origin rule.

    `kept` is qualifying-turns.json: per-game qualifying notice turns, read
    from the 149 kept branch games' events.jsonl (see README). A row is fresh
    for program 2 if it completed after program 1 must have terminated
    (admission + program lifetime; earlier termination only adds rows).
    """
    games = [g for g in kept if g["first_admission_move"] is not None]
    rows = []
    for g in games:
        end = g["first_admission_move"] + PROGRAM_LIFETIME
        turns = g["qualifying_turns"]
        rows.append(
            dict(
                start=g["start"],
                seed=g["seed"],
                qualifying=len(turns),
                fresh_unbounded=sum(t > end for t in turns),
                fresh_within_bound=sum(t > end for t in turns[:BOUND]),
            )
        )
    return dict(
        games_with_program_1=len(rows),
        no_fresh_row=sum(r["fresh_within_bound"] == 0 for r in rows),
        bound_removes_fresh_rows=[
            r for r in rows if r["fresh_unbounded"] != r["fresh_within_bound"]
        ],
        bound_leaves_fewer_than_2=sum(
            r["fresh_within_bound"] < 2 <= r["fresh_unbounded"] for r in rows
        ),
        thirty_second_row_turns=sorted(
            g["qualifying_turns"][BOUND - 1]
            for g in kept
            if len(g["qualifying_turns"]) > BOUND
        ),
    )


def main():
    result = {}
    for side in ("main", "branch"):
        games = json.loads((SWEEP / f"{side}-seeds-1-100.json").read_text())["games"]
        result[side] = summarize(games)
    kept = json.loads((HERE / "qualifying-turns.json").read_text())
    result["branch_kept_fresh_rows"] = fresh_rows(kept)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
