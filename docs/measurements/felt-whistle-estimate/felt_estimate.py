"""Felt-whistle proposal: measured precondition counts and gate ESTIMATES.

Tier B, measurement only. Post-run only. Reads:

* PLAIN_RUNS: #236's retained per-game copies of the C gate sweep re-run at
  3f067b65 (baseline-v2, seeds 1-100, five starts);
* PROBE_RUNS: an instrumented twin of the same sweep, built from a
  git-archive export of 8d2c8df3 (game and harness sources identical to
  3f067b65) with felt-probe.patch applied. The probe writes one
  ``felt-probe.log`` line per completed whistle, keyed by the action's
  public root. It reads state only and draws no random numbers;
* SWEEP_REPORT: the plain sweep's report JSON (felt programs, distinct_felt).

Everything here reads private journals and engine probes. It is analysis,
not player knowledge, and none of it reaches the director.

Usage:
  felt_estimate.py PLAIN_RUNS PROBE_RUNS SWEEP_REPORT_JSON > felt-estimate.json
Run from the repository root (or with it on PYTHONPATH).
"""

import collections
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
for parent in HERE.parents:
    if (parent / "chaos" / "next_use_journal.py").exists():
        sys.path[:0] = [str(parent)]
        break
_spec = importlib.util.spec_from_file_location(
    "funnel", HERE.parent / "arc-later-program-funnel" / "funnel.py"
)
fn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fn)

STARTS = fn.STARTS
WHISTLE, MAGIC_WHISTLE = 530, 531  # src/objects.c:1493-1494


def kv(line):
    return {k: int(v) for k, v in (p.split("=", 1) for p in line.split())}


def probes(run):
    p = run / "felt-probe.log"
    if not p.exists():
        return {}
    return {x["root"]: x for x in map(kv, p.read_text().splitlines())}


def valid_whistle(p):
    """The engine's trigger at src/chaos_engine.c:657-661 (tin whistle, or a
    magic whistle while a broad program runs; known, quantity 1, no
    artifact, still in inventory)."""
    return (
        p["inv"] == 1
        and (p["otyp"] == WHISTLE or (p["otyp"] == MAGIC_WHISTLE and p["broad"]))
        and p["known"] == 1
        and p["quan"] == 1
        and p["art"] == 0
    )


# Candidate preconditions, all on public state at the whistle. A and C also
# need the effect to change something on screen, which is part of "felt".
CANDIDATES = {
    # A: the visible companion is called to the player's side (mnexto).
    # Felt only if it actually moves: not already adjacent (dist2 > 2).
    "A_call": lambda p: p["pick"] == 1 and p["pick_d2"] > 2,
    # B: the whistle rings on in the player's head (make_confused, 5 moves).
    # Guards, all public: not already confused (else nothing changes), no
    # visible hostile adjacent, not engulfed, not hallucinating, HP above a
    # third. The proposal's water/lava guard is NOT probed: upper bound.
    "B_ring": lambda p: (
        p["conf"] == 0
        and p["adj_hostile"] == 0
        and p["swallow"] == 0
        and p["halluc"] == 0
        and p["hp"] * 3 > p["hpmax"]
    ),
    # C: the whistle carries farther (wake_nearto at 4x the radius). Felt only
    # if a visible sleeping monster lies in the extended band.
    "C_carry": lambda p: p["sl_vis"] > 0,
    # Today's companion condition at the whistle, for comparison (the
    # classifier further narrows these).
    "today_companion_in_view": lambda p: p["pick"] == 1,
}


def program_windows(g, run):
    """Admitted programs with their counterfactual window: from admission to
    the earliest of origin expiry (src/chaos_next_use_runtime.c:926-934),
    program expiry, and the game's last turn. Today's own early endings
    (two delivered uses, an invalid callback) are not applied: a new effect
    would change them."""
    out = []
    for p in g["programs"]:
        h = p["head"]
        adm = h["admission_move"]
        end = min(h["origin_w_deadline"] + 1, h["program_expiry"], g["last_turn"] or 0)
        out.append(
            dict(ordinal=p["ordinal"], admission=adm, end=end, uses_today=p["uses"])
        )
    return out


LIFETIME_FIRST = 100  # include/chaos_next_use.h:130
BROAD_USES = 2  # include/chaos_next_use.h:144, chaos/next_use_envelope.py:19


def main(plain, probe_runs, report_path):
    plain, probe_runs = Path(plain), Path(probe_runs)
    twin = fn.twin_match(plain, probe_runs)
    excluded = set(twin["games_differing"])
    rep = json.loads(Path(report_path).read_text())
    by_game = {f"{x['start']}-{x['seed']:05d}": x["funnel"] for x in rep["games"]}
    gated = [c for c in CANDIDATES if c != "today_companion_in_view"]
    res = {}
    for st in STARTS:
        per = {
            k: dict(
                admitted_programs=0,
                reached_callback_today=0,
                delivered_today=0,
                admitted_programs_probed=0,
                whistles_in_window=0,
                valid_whistles_in_window=0,
                **{f"{c}_uses": 0 for c in CANDIDATES},
                **{f"{c}_programs": 0 for c in CANDIDATES},
                **{f"{c}_deliverable": 0 for c in CANDIDATES},
            )
            for k in (1, 2, 3)
        }
        refused = dict(
            program1_refused_no_companion_only=0,
            probed=0,
            **{f"{c}_programs": 0 for c in gated},
        )
        gate_now = dict(part1=0, part3=0)
        gate = {c: dict(part1=0, part3=0) for c in gated}
        gate_drop = {c: dict(part1=0, part3=0) for c in gated}
        games_excluded = 0
        names = sorted(
            d.name
            for d in plain.iterdir()
            if d.name.startswith(st + "-") and d.name[len(st) + 1 :].isdigit()
        )
        for name in names:
            gdir = plain / name
            fun = by_game[name]
            # Part 1 starts from the reported distinct_felt sources (the #231
            # metric, unchanged), which also count unattributed next-use rows
            # (program None) as one source. A candidate adds one source per
            # program newly felt that today's report does not already credit.
            base = sum(1 for x in fun["distinct_felt"] if x["kind"] != "hound")
            felt_today = {p["program"] for p in fun["programs"] if p["felt"]}
            gate_now["part1"] += base >= 2
            gate_now["part3"] += len(felt_today) >= 2
            g = fn.game(gdir, None)
            probed = name not in excluded
            games_excluded += not probed
            pr = probes(fn.rundir(probe_runs / name)) if probed else {}
            newly = {c: set() for c in gated}
            for w in program_windows(g, gdir):
                row = per[w["ordinal"]]
                row["admitted_programs"] += 1
                row["reached_callback_today"] += len(w["uses_today"])
                row["delivered_today"] += sum(
                    u["outcome"] == "delivered" for u in w["uses_today"]
                )
                if not probed:
                    continue
                row["admitted_programs_probed"] += 1
                ws = [
                    x for x in g["whistles"] if w["admission"] < x["turn"] <= w["end"]
                ]
                row["whistles_in_window"] += len(ws)
                hit = collections.Counter()
                for x in ws:
                    p = pr.get(x["root"])
                    if p is None or not valid_whistle(p):
                        continue
                    row["valid_whistles_in_window"] += 1
                    for c, cond in CANDIDATES.items():
                        if cond(p):
                            row[f"{c}_uses"] += 1
                            hit[c] += 1
                for c in CANDIDATES:
                    # a broad program delivers at most BROAD_USES effects
                    row[f"{c}_deliverable"] += min(BROAD_USES, hit[c])
                    if hit[c]:
                        row[f"{c}_programs"] += 1
                        if c in newly:
                            newly[c].add(w["ordinal"])
            # Program 1 refused only for no companion in view (#196 C3). A
            # companion-free effect would not need that check: count the tin
            # whistles meeting each precondition in the 100 moves after the
            # refused decision (no program runs then, so a magic whistle is
            # not a valid trigger). Upper bound: origin and budget not rechecked.
            extra = {c: False for c in gated}
            for r in g["receipts"]:
                if (
                    r["program_ordinal"] == 1
                    and r.get("decision") == "rejected"
                    and r.get("reasons") == ["no_companion_in_view"]
                ):
                    refused["program1_refused_no_companion_only"] += 1
                    if not probed:
                        continue
                    refused["probed"] += 1
                    ws = [
                        x
                        for x in g["whistles"]
                        if r["move"] < x["turn"] <= r["move"] + LIFETIME_FIRST
                    ]
                    for c in gated:
                        if any(
                            (p := pr.get(x["root"])) is not None
                            and p["otyp"] == WHISTLE
                            and valid_whistle(p)
                            and CANDIDATES[c](p)
                            for x in ws
                        ):
                            refused[f"{c}_programs"] += 1
                            extra[c] = True
            for c in gated:
                if probed:
                    felt = felt_today | newly[c]
                    felt_drop = felt | ({1} if extra[c] else set())
                else:  # excluded twin game: counted as today
                    felt = felt_drop = felt_today
                gate[c]["part1"] += base + len(felt - felt_today) >= 2
                gate[c]["part3"] += len(felt) >= 2
                gate_drop[c]["part1"] += base + len(felt_drop - felt_today) >= 2
                gate_drop[c]["part3"] += len(felt_drop) >= 2
        res[st] = dict(
            games=len(names),
            per_program=per,
            program1_refused_no_companion=refused,
            gate_now=gate_now,
            gate_reported=dict(
                part1=rep["aggregate"][st]["distinct_felt"][
                    "games_2plus_excluding_hound"
                ]
            ),
            gate_now_matches_report=gate_now["part1"]
            == rep["aggregate"][st]["distinct_felt"]["games_2plus_excluding_hound"],
            gate_estimate=gate,
            gate_estimate_without_companion_admission_check=gate_drop,
            games_excluded_twin=games_excluded,
        )
    return dict(twin=twin, starts=res)


if __name__ == "__main__":
    json.dump(main(*sys.argv[1:4]), sys.stdout, indent=1, sort_keys=True)
    print()
