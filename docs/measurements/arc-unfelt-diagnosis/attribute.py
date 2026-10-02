"""Post-run attribution (docs/measurements/arc-unfelt-diagnosis) of #231's admitted-but-unfelt later programs (2-3).

Reads only the retained #231 main-sweep report (per-game run directories were
removed at #231's cleanup, so later-program journals are gone). Writes JSON to
stdout: one row per admitted later program, with its binding, plus the
publication funnel for later programs and the per-option projections.
No game is run; no repository code path is changed.
"""

import json
import math
from collections import Counter
from pathlib import Path
import sys

R = Path(__file__).resolve().parents[3]  # repository root
sys.path.insert(0, str(R))
from chaos.history_choice import RandomHistoryBackend  # noqa: E402
from chaos.next_use_history import _FAMILIES  # noqa: E402

# The retained #231 main-sweep JSON report (not committed: 15.8 MB). Usage:
#   python3 attribute.py <baseline-v2-seeds-1-100-main.json> > attribution.json
REPORT = Path(sys.argv[1])
rep = json.loads(REPORT.read_text())
G = rep["games"]
BARDS = ("bard", "bard-default-path", "bard-inherited")

# Director op per program ordinal at the launcher default seed 0 (the sweep
# passes no --seed): NextUseScheduler uses RandomHistoryBackend(seed+ordinal-1)
# over the one origin's [quiet, effect] menu, in _FAMILIES order.
authored = {
    fam: [ops[RandomHistoryBackend(k).rng.choice(range(len(ops)))] for k in range(3)]
    for fam, _op, _facts, ops in _FAMILIES
}


def rate(g):
    f = g["funnel"]
    return f["qualifying_actions"]["whistling"] / max(1, f["last_turn"])


def binding(p):
    if p["trigger"]:
        return "triggered_quiet_authored"
    t = p["termination"]
    if t is None:
        return "open_at_game_end"
    if t == "completed":
        return "w_capture_suppressed_at_use"
    return {
        "program_expired": "program_expiry_100_no_use",
        "origin_expired": "origin_deadline_300_no_use",
        "level_departure": "level_departure",
    }.get(t, t)


rows = []
for g in G:
    for p in g["funnel"]["programs"][1:]:
        if p["admitted"]:
            rows.append(
                dict(
                    start=g["start"],
                    seed=g["seed"],
                    program=p["program"],
                    binding=binding(p),
                    termination=p["termination"],
                    trigger=p["trigger"],
                    native_effect=p["native_effect"],
                    program1_felt=bool(g["funnel"]["programs"][0]["felt"]),
                    outcome=g["outcome"],
                    last_turn=g["funnel"]["last_turn"],
                    whistles=g["funnel"]["qualifying_actions"]["whistling"],
                    fountain_drinks=g["funnel"]["qualifying_actions"]["fountain_drink"],
                    whistles_found=g["v2"]["whistles_found"],
                    levels=len(g["v2"]["dlvl_timeline"]),
                    whistles_per_100_turns=round(100 * rate(g), 2),
                )
            )

# Program 1 rates (same sweep, three bard starts) used by the projections.
P1 = [g["funnel"]["programs"][0] for g in G if g["start"] in BARDS]
trig1 = sum(p["trigger"] > 0 for p in P1)
supp1 = sum(
    1
    for p in P1
    if p["admitted"] and not p["trigger"] and p["termination"] == "completed"
)
native1 = sum(p["native_effect"] > 0 for p in P1)
felt1 = sum(p["felt"] > 0 for p in P1)
PC, PW = trig1 / (trig1 + supp1), felt1 / native1


def later_publications(start):
    c = Counter()
    for g in G:
        if g["start"] != start:
            continue
        for p in g["funnel"]["programs"][1:]:
            if not p["published"]:
                c["not_published"] += 1
            elif p["admitted"]:
                c["admitted"] += 1
            elif p["termination"] is None:
                c["no_decision_before_game_end"] += 1
            else:
                why = p["termination"].split(":", 1)[1].split("+")
                c[
                    "rejected:"
                    + (
                        "no_companion_in_view"
                        if "no_companion_in_view" in why
                        else "budget"
                        if "budget" in why
                        else "origin_or_index"
                    )
                ] += 1
    return dict(sorted(c.items()))


def p_felt(g, p, o):
    """P(program felt) under option o (see the diagnosis doc for each term)."""
    later = p["program"] > 1
    peff = o["effect"] if later else 1.0
    r, t = rate(g) * o["rate"], p["termination"]
    if p["admitted"]:
        if p["felt"]:
            return 1.0
        if p["trigger"]:
            if later:
                return peff * PW
            return 1 - math.exp(-r * o["life"] * PC * PW) if o["every_use"] else 0.0
        if t is None:
            return 0.0
        if t == "completed":
            return (
                (1 - math.exp(-r * o["life"] * PC * PW * peff))
                if o["every_use"]
                else 0.0
            )
        if not o["rescue_expired"]:
            return 0.0
    elif not (later and o["c3_at_use"] and t == "rejected:no_companion_in_view"):
        return 0.0
    if o["every_use"]:
        return 1 - math.exp(-r * o["life"] * PC * PW * peff)
    use = 1.0 if o["always_reuse"] else 1 - math.exp(-r * o["life"])
    return use * PC * PW * peff


def project(start, o):
    nh2 = two = 0.0
    for g in (g for g in G if g["start"] == start):
        other = sum(
            e["kind"] in ("door", "hunger") for e in g["funnel"]["distinct_felt"]
        )
        dist = [1.0]
        for p in g["funnel"]["programs"]:
            x = p_felt(g, p, o)
            nd = [0.0] * (len(dist) + 1)
            for k, v in enumerate(dist):
                nd[k] += v * (1 - x)
                nd[k + 1] += v * x
            dist = nd
        nh2 += sum(v for k, v in enumerate(dist) if k + other >= 2)
        two += sum(v for k, v in enumerate(dist) if k >= 2)
    return [round(nh2, 1), round(two, 1)]


def opt(**kw):
    base = dict(
        effect=0.0,
        life=100,
        every_use=False,
        c3_at_use=False,
        rescue_expired=False,
        always_reuse=False,
        rate=1.0,
    )
    base.update(kw)
    return base


OPTIONS = {
    "today": opt(),
    "1_policy_only": opt(effect=0.5, rescue_expired=True, always_reuse=True),
    "2_recurrence_repair": opt(
        effect=1.0, life=300, c3_at_use=True, rescue_expired=True
    ),
    "2_recurrence_repair_life100": opt(effect=1.0, c3_at_use=True, rescue_expired=True),
    "2_effect_authoring_only": opt(effect=1.0),
    "3_sam_as_worded_life100": opt(every_use=True, rescue_expired=True),
    "3_sam_as_worded_life300": opt(life=300, every_use=True, rescue_expired=True),
    "3_sam_plus_effect_life100": opt(effect=1.0, every_use=True, rescue_expired=True),
    "3_sam_plus_effect_life300": opt(
        effect=1.0, life=300, every_use=True, rescue_expired=True
    ),
    "3plus_sam_completed_life100": opt(
        effect=1.0, every_use=True, c3_at_use=True, rescue_expired=True
    ),
    "3plus_sam_completed_life300": opt(
        effect=1.0, life=300, every_use=True, c3_at_use=True, rescue_expired=True
    ),
    "3plus_sam_completed_life300_effect_half": opt(
        effect=0.5, life=300, every_use=True, c3_at_use=True, rescue_expired=True
    ),
}
projections = {
    name: {
        "bard-default-path": project("bard-default-path", o),
        "bard-default-path_half_reuse_rate": project(
            "bard-default-path", dict(o, rate=0.5)
        ),
        "bard": project("bard", o),
        "params": o,
    }
    for name, o in OPTIONS.items()
}

out = dict(
    source=dict(
        report_sha256=rep["report_sha256"], revision=rep["identity"]["revision"]
    ),
    authored_op_by_program_at_director_seed_0=authored,
    program1_rates=dict(
        triggered=trig1,
        w_suppressed_at_use=supp1,
        native=native1,
        felt=felt1,
        companion_ok_at_use=round(PC, 3),
        witnessed_given_armed=round(PW, 3),
    ),
    later_admitted=len(rows),
    later_admitted_games=len({(r["start"], r["seed"]) for r in rows}),
    binding_counts=dict(sorted(Counter(r["binding"] for r in rows).items())),
    binding_by_start={
        s: dict(sorted(Counter(r["binding"] for r in rows if r["start"] == s).items()))
        for s in BARDS
    },
    expired_no_use=dict(
        n=sum(r["binding"].endswith("_no_use") for r in rows),
        expected_no_whistle_in_100_moves_at_game_rate=round(
            sum(
                math.exp(-r["whistles_per_100_turns"])
                for r in rows
                if r["binding"].endswith("_no_use")
            ),
            1,
        ),
    ),
    later_publications={s: later_publications(s) for s in BARDS},
    projections=projections,
    rows=rows,
)
print(json.dumps(out, indent=1, sort_keys=True))
