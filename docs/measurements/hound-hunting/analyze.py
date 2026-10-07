"""Hounds that hunt: pilot analysis (NGPL).

  analyze.py <run dir> <new trials.json>

Reads the new run's jobs (receipts, pre-check rehearsals), the engine
shadow metrics for its sources (measure.py pilot), and the old pilot's
metrics (baseline/trials.json, same rooms, seeds and instrument). Writes
<run dir>/summary.json and prints it without the per-job rows.

Per-trial distributions are over every engine shadow trial (4 rooms x 3
seeds per source). "Hunting" = admitted by the pre-registered pre-check
AND accepted by the engine shadow trial in every one of its 12 trials.
"""

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDS = ("moved", "contacts", "min_dist", "median_dist", "max_damage", "escaped")


def spread(xs):
    if not xs:
        return None
    xs = sorted(xs)
    return dict(
        n=len(xs),
        min=xs[0],
        p25=xs[len(xs) // 4],
        median=statistics.median(xs),
        p75=xs[(3 * len(xs)) // 4],
        max=xs[-1],
    )


def dist(trials, names):
    reps = [t["report"] for n in names for t in trials[n]["trials"] if t["report"]]
    out = {f: spread([r[f] for r in reps]) for f in FIELDS}
    out["trials"] = len(reps)
    out["accepted"] = sum(r["accepted"] for r in reps)
    out["contact_trials"] = sum(r["contacts"] > 0 for r in reps)
    out["reached_within_1"] = sum(r["min_dist"] <= 1 for r in reps)
    return out


def main():
    run, new_trials = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())
    old = json.loads((HERE / "baseline/trials.json").read_text())
    rows = []
    for job in sorted((run / "jobs").iterdir()):
        attempts = sorted(p for p in job.iterdir() if (p / "receipt.json").exists())
        receipts = [json.loads((p / "receipt.json").read_text()) for p in attempts]
        final = receipts[-1]
        engine = new_trials.get(job.name)
        engine_ok = engine and all(t["report"]["accepted"] for t in engine["trials"])
        rows.append(
            dict(
                job=job.name,
                attempts=len(receipts),
                outcomes=[r["outcome"] for r in receipts],
                precheck=[(r.get("native") or {}).get("failure") for r in receipts],
                latency_s=[r["latency_s"] for r in receipts],
                final=final["outcome"],
                engine_accepted=None
                if engine is None
                else sum(t["report"]["accepted"] for t in engine["trials"]),
                hunting=final["outcome"] == "ready" and bool(engine_ok),
                tokens=[
                    ((r.get("transport") or {}).get("record") or {}).get("usage")
                    for r in receipts
                ],
            )
        )
    new_names = [n for n in new_trials if n != "footsteps"]
    ready_names = [r["job"] for r in rows if r["final"] == "ready"]
    old_names = [n for n in old if n != "footsteps"]
    all_receipts = [o for r in rows for o in r["outcomes"]]
    failures = [f for r in rows for f in r["precheck"] if f]
    latencies = [x for r in rows for x in r["latency_s"] if x is not None]
    summary = dict(
        jobs=len(rows),
        requests=len(all_receipts),
        outcomes={o: all_receipts.count(o) for o in sorted(set(all_receipts))},
        final_outcomes={
            o: sum(r["final"] == o for r in rows) for o in sorted({r["final"] for r in rows})
        },
        regenerations=sum(r["attempts"] > 1 for r in rows),
        regenerated_then_ready=sum(r["attempts"] > 1 and r["final"] == "ready" for r in rows),
        precheck_failures={f: failures.count(f) for f in sorted(set(failures))},
        latency_s=spread(latencies),
        hunting_end_to_end=sum(r["hunting"] for r in rows),
        distributions=dict(
            new_ready=dist(new_trials, ready_names),
            new_all_sources=dist(new_trials, new_names),
            old_pilot=dist(old, old_names),
            footsteps=dist(old, ["footsteps"]),
        ),
        rows=rows,
    )
    (run / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()
