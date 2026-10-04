"""Summarise pilot ledgers (no model calls). Usage:
  python3 docs/measurements/model-authoring-pilot/analyze.py <run-dir> [<run-dir> ...]
Writes nothing; prints JSON. Rows from several run directories are pooled.
"""

import collections
import json
import statistics
import sys
from pathlib import Path

# Words that would tie a curio to the recorded histories (whistles, backtracking,
# fountains, praying, eating, the roles) rather than to any player.
MOTIFS = ("whistl", "door", "pray", "fountain", "hound", "step", "back", "retrac",
          "hunger", "eat", "bard", "wizard", "mad", "song", "note", "tune", "echo")


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))]


def main(dirs):
    rows = []
    for d in dirs:
        for line in open(Path(d) / "ledger.jsonl"):
            row = json.loads(line)
            row["_dir"] = str(d)
            rows.append(row)
    out = {}
    by = collections.defaultdict(list)
    for r in rows:
        by[r["surface"]].append(r)
    for surface, rs in sorted(by.items()):
        lat = [r["latency_s"] for r in rs if r.get("latency_s")]
        rt = [r["reasoning_tokens"] for r in rs if r.get("reasoning_tokens") is not None]
        ct = [r["usage"]["completion_tokens"] for r in rs if r.get("usage")]
        fails = collections.Counter(r["outcome"].get("failure") for r in rs
                                    if not r["outcome"].get("admitted"))
        s = dict(
            calls=len(rs),
            transport_failures=sum(1 for r in rs if r["outcome"].get("failure") == "transport"),
            transport_retries=sum(len(r["transport_attempts"]) - 1 for r in rs),
            admitted=sum(1 for r in rs if r["outcome"].get("admitted")),
            failure_kinds=dict(fails),
            histories=len({r["history"] for r in rs}),
            latency_s=dict(median=pct(lat, .5), p90=pct(lat, .9), max=max(lat) if lat else None),
            reasoning_tokens_median=pct(rt, .5),
            completion_tokens_median=pct(ct, .5),
            served_models=dict(collections.Counter(str(r.get("served_model")) for r in rs)),
        )
        ok = [r["outcome"] for r in rs if r["outcome"].get("admitted")]
        if surface.startswith("curio"):
            s["layers"] = dict(collections.Counter(r["arg"] for r in rs))
            s["admitted_by_layer"] = dict(collections.Counter(
                r["arg"] for r in rs if r["outcome"].get("admitted")))
            s["grid_runtime_failures_any"] = sum(1 for o in ok if o["grid_failures"])
            s["distinct_inspect_median"] = pct([o["distinct_inspect"] for o in ok], .5)
            s["distinct_apply_median"] = pct([o["distinct_apply"] for o in ok], .5)
            s["single_inspect_text"] = sum(1 for o in ok if o["distinct_inspect"] == 1)
            s["first_apply_delta"] = dict(collections.Counter(
                o["apply"]["sanity_delta"] for o in ok))
            text = [(o["inspect"] + " " + o["apply"]["text"] + " " + o["name"]).lower()
                    for o in ok]
            s["motif_mentions"] = {m: sum(1 for t in text if m in t) for m in MOTIFS}
            s["names"] = sorted(o["name"] for o in ok)
        if surface in ("hound", "hound_free"):
            s["identical_to_footsteps_pack_all_cases"] = sum(
                1 for o in ok if o["agrees_with_footsteps_pack"] == o["step_calls"])
            s["agreement_median"] = pct([o["agrees_with_footsteps_pack"] / o["step_calls"]
                                         for o in ok], .5)
            s["distinct_sources"] = len({o["source_sha256"] for o in ok})
        if surface == "next_use":
            s["never_acts"] = sum(1 for o in ok if not o["effect_ops"])
            s["effect_op_share_median"] = pct([o["effect_ops"] / o["on_action_calls"]
                                               for o in ok], .5)
            s["uses_delay"] = sum(1 for o in ok if o["op_counts"].get("delay"))
            s["distinct_sources"] = len({o["source_sha256"] for o in ok})
        if surface == "flavour":
            s["stray_numbers"] = [r["outcome"].get("stray") for r in rs
                                  if r["outcome"].get("failure") == "number_not_in_reveal"]
        out[surface] = s
    out["_total"] = dict(calls=len(rows), run_dirs=[Path(d).name for d in dirs])
    print(json.dumps(out, indent=1, sort_keys=True))


if __name__ == "__main__":
    main(sys.argv[1:])
