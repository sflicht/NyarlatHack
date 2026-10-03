"""Later-program funnel diagnosis (Tier B, measurement only). Post-run only.

Reads one seed sweep's retained per-game work dirs and, optionally, the
work dirs of its instrumented twin (same seeds, same revision, plus two
fprintf probes that write ``classifier.log`` and ``whistle-probe.log`` into
each game's run dir). The probes read state only; ``twin_match`` checks that
every game's public outputs are byte-identical between the two sweeps.

Everything here reads private journals and engine probes. It is analysis,
not player knowledge.

Usage: funnel.py PLAIN_RUNS [DIAG_RUNS] > funnel.json

PLAIN_RUNS/DIAG_RUNS: a sweep's --work dir, or the retained per-game copies
(~/.hermes/reports/nyarlathack-arc-later-funnel/runs-plain and runs-diag).
Run from the repository root (or with it on PYTHONPATH).
"""

import collections
import hashlib
import json
from pathlib import Path
import statistics
import sys

R = Path(__file__).resolve()
for parent in R.parents:
    if (parent / "chaos" / "next_use_journal.py").exists():
        sys.path[:0] = [str(parent)]
        break
from chaos.next_use_journal import read_journal  # noqa: E402

STARTS = [
    "bard-default-path",
    "bard",
    "bard-inherited",
    "madman",
    "wizard-default-path",
]

# include/chaos_next_use_runtime.h
OP_ACTION, OP_W_UNAVAILABLE, OP_W_CAPTURE, OP_W_DECISION = 1, 2, 3, 4
EFFECT_KIND = 4
W_ARMED, W_SUPPRESSED, W_WITNESSED, W_AFTER, W_NO_WITNESS, W_UNSAFE = 1, 2, 3, 4, 5, 6
F_NAMES = {
    7: "natural",
    8: "early_return",
    9: "native_19_30",
    10: "default_without_intent",
    11: "guard_suppressed",
    12: "remapped",
}
SUPPRESSION = {
    1: "no_tame_companion_in_view",
    2: "none_qualifying",
    3: "recheck_failed",
}
UNDEF = 6  # include/exstruct.h
GOAL = {
    0: "dogfood",
    1: "cadaver",
    2: "accfood",
    3: "manfood",
    4: "apport",
    5: "poison",
    7: "tabu",
}
BUDGET_BASE, BUDGET_STEP, SANITY_MAX, CEILING = 2, 10, 100, 12  # chaos_protocol.h


def rows(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def kv(line):
    return {k: int(v) for k, v in (p.split("=", 1) for p in line.split())}


def jname(k):
    return "next_use-journal.jsonl" if k == 1 else f"next_use-journal.{k}.jsonl"


def blocked_reason(c):
    """First failing term of src/dogmove.c:1258-1260, plus all failing terms."""
    terms = []
    if c["whappr"]:
        terms.append("ordinary_whistle_pull_active")
    if c["extra"] == 0:
        terms.append("no_extra_attention")
    if c["appr"] == -2:
        terms.append("already_close_not_moving")
    if c["gtyp"] != UNDEF:
        terms.append("goal_" + GOAL.get(c["gtyp"], str(c["gtyp"])))
    elif (c["gx"], c["gy"]) != (c["ux"], c["uy"]):
        terms.append("goal_not_player_square")
    if not c["pre_public"]:
        terms.append("not_publicly_visible_before_move")
    # All terms passed: the move was classified, but the end-of-move check in
    # chaos_whistle_witness_finalize (src/chaos_engine.c:569-578) did not
    # publish it (companion not displaced, not seen after, or presentation
    # not delivered). The probes do not split those three.
    return (terms[0] if terms else "classified_but_move_not_published"), terms


def program(run, k, classifier_by_move):
    path = run / jname(k)
    if not path.exists():
        return None
    dec = read_journal(path)
    head = dec["records"][0]["data"]["snapshot"]
    uses, cur = [], None
    for rec in dec["records"][1:]:
        if rec["kind"] != "transition":
            continue
        d = rec["data"]
        if d["operation"] == OP_ACTION and d["family"] in (1, 2):
            cur = dict(
                family="W" if d["family"] == 1 else "F",
                move=d["at_move"],
                root=d["root"],
                outcome=None,
                decisions=[],
            )
            uses.append(cur)
        if cur is None:
            continue
        if d["operation"] == OP_W_DECISION and cur["family"] == "W":
            c = classifier_by_move.get(d["at_move"])
            cur["decisions"].append(dict(move=d["at_move"], classifier=c))
        for q in d["private_records"]:
            if q["kind"] != EFFECT_KIND:
                continue
            o = q["data"].get("outcome")
            if cur["family"] == "W":
                if o == W_SUPPRESSED:
                    cur["outcome"] = "suppressed_at_callback:" + SUPPRESSION.get(
                        q["data"].get("suppression"), "unrecorded"
                    )
                elif o == W_WITNESSED:
                    cur["outcome"] = "delivered"
                elif o == W_NO_WITNESS and cur["outcome"] in (None, "armed"):
                    cur["outcome"] = "ended_no_witness"
                elif o == W_UNSAFE:
                    cur["outcome"] = "identity_unsafe"
                elif o == W_ARMED and cur["outcome"] is None:
                    cur["outcome"] = "armed"
            elif o in F_NAMES:
                cur["outcome"] = "delivered" if o == 12 else "fountain_" + F_NAMES[o]
    for u in uses:
        if u["family"] != "W":
            continue
        if u["outcome"] == "ended_no_witness":
            if u["decisions"]:
                c = u["decisions"][-1]["classifier"]
                u["outcome"] = "blocked"
                u["blocked_reason"] = blocked_reason(c)[0] if c else "unlogged"
                u["blocked_terms"] = blocked_reason(c)[1] if c else []
            else:
                u["outcome"] = "no_decision_in_window"
        elif u["outcome"] == "armed":
            u["outcome"] = "armed_open_at_end"
    return dict(ordinal=k, head=head, uses=uses)


def rundir(d):
    """A sweep work dir keeps files under <game>/run/; retained copies are flat."""
    return d / "run" if (d / "run").is_dir() else d


def game(gdir, ddir):
    run = rundir(gdir)
    ddir = rundir(ddir) if ddir is not None else None
    events = rows(run / "events.jsonl")
    clf = {}
    probes = {}
    if ddir is not None:
        for line in (
            (ddir / "classifier.log").read_text().splitlines()
            if (ddir / "classifier.log").exists()
            else []
        ):
            c = kv(line)
            clf[c["mm"]] = c
        for line in (
            (ddir / "whistle-probe.log").read_text().splitlines()
            if (ddir / "whistle-probe.log").exists()
            else []
        ):
            p = kv(line)
            probes[p["root"]] = p
    whistles, fountains = [], []
    for e in events:
        o = e.get("observation") or {}
        if o.get("stage") == "completed" and o.get("operation") == "whistling":
            whistles.append(dict(turn=e["turn"], root=o["root_seq"]))
        if o.get("stage") == "completed" and o.get("operation") == "fountain_drink":
            fountains.append(dict(turn=e["turn"], root=o["root_seq"]))
    by_seq = {e.get("seq"): e for e in events}
    life = {r["program_ordinal"]: r for r in rows(run / "next_use-lifecycle.jsonl")}
    receipts = [r for r in rows(run / "next_use-receipt.jsonl") if "decision" in r]
    return dict(
        name=gdir.name,
        events=events,
        by_seq=by_seq,
        whistles=whistles,
        fountains=fountains,
        probes=probes,
        life=life,
        receipts=receipts,
        programs=[p for p in (program(run, k, clf) for k in (1, 2, 3)) if p],
        last_turn=events[-1]["turn"] if events else None,
        classifier_lines=len(clf),
        has_diag=ddir is not None,
    )


def state_at(g, move, safe):
    """The engine's budget columns at the admission decision: the last event
    row at or before the decision move and safe point."""
    best = None
    for e in g["events"]:
        if e.get("turn", 0) <= move and e.get("safe", 0) <= safe:
            best = e
    return best


def counts(c):
    return dict(sorted(c.items()))


def q1(games):
    out = {}
    for k in (1, 2, 3):
        c, reasons, terms = (
            collections.Counter(),
            collections.Counter(),
            collections.Counter(),
        )
        for g in games:
            for p in g["programs"]:
                if p["ordinal"] != k:
                    continue
                for u in p["uses"]:
                    c[u["family"] + ":" + u["outcome"]] += 1
                    if u["outcome"] == "blocked":
                        reasons[u["blocked_reason"]] += 1
                        for t in u["blocked_terms"]:
                            terms[t] += 1
        out[f"program_{k}"] = dict(
            reached_callback=sum(c.values()),
            outcomes=counts(c),
            blocked_first_failing=counts(reasons),
            blocked_all_failing=counts(terms),
        )
    return out


def q2(games):
    progs = []
    for g in games:
        for p in g["programs"]:
            if p["ordinal"] < 2:
                continue
            term = g["life"].get(p["ordinal"])
            if not term or term["reason"] != "origin_expired":
                continue
            h = p["head"]
            adm, odl, pexp = (
                h["admission_move"],
                h["origin_w_deadline"],
                h["program_expiry"],
            )
            # origin expires at the first boundary with monstermoves > deadline
            # (src/chaos_next_use_runtime.c:926-928).
            hi = odl + 1
            ws = [w for w in g["whistles"] if adm < w["turn"] <= hi]
            fs = [f for f in g["fountains"] if adm < f["turn"] <= hi]
            ev = g["by_seq"].get(term["terminal_seq"])
            progs.append(
                dict(
                    game=g["name"],
                    ordinal=p["ordinal"],
                    admission_move=adm,
                    origin_move=odl - 300,
                    origin_deadline=odl,
                    program_expiry=pexp,
                    moves_admission_to_origin_expiry=hi - adm,
                    moves_program_would_have_left=pexp - hi,
                    terminal_turn=ev.get("turn") if ev else None,
                    whistle_uses=len(ws),
                    fountain_drinks=len(fs),
                    companion_in_view_at_whistle=[
                        (
                            g["probes"][w["root"]]["pick"]
                            if w["root"] in g["probes"]
                            else None
                        )
                        for w in ws
                    ],
                    callbacks=len(p["uses"]),
                    callback_outcomes=[u["outcome"] for u in p["uses"]],
                    # what the origin deadline cut off: uses between origin expiry
                    # and the program's own expiry
                    whistles_after_origin_expiry=len(
                        [w for w in g["whistles"] if hi < w["turn"] <= pexp]
                    ),
                    whistles_after_origin_expiry_companion_in_view=len(
                        [
                            w
                            for w in g["whistles"]
                            if hi < w["turn"] <= pexp
                            and g["probes"].get(w["root"], {}).get("pick")
                        ]
                    ),
                    fountains_after_origin_expiry=len(
                        [f for f in g["fountains"] if hi < f["turn"] <= pexp]
                    ),
                    game_ended_before_program_expiry=(g["last_turn"] or 0) < pexp,
                )
            )
    if not progs:
        return dict(programs=[], n=0)
    a = [x["moves_admission_to_origin_expiry"] for x in progs]
    return dict(
        n=len(progs),
        moves_admission_to_origin_expiry=dict(
            min=min(a), median=statistics.median(a), max=max(a)
        ),
        with_any_whistle=sum(x["whistle_uses"] > 0 for x in progs),
        with_whistle_companion_in_view=sum(
            any(v == 1 for v in x["companion_in_view_at_whistle"]) for x in progs
        ),
        with_any_fountain=sum(x["fountain_drinks"] > 0 for x in progs),
        whistle_uses=sum(x["whistle_uses"] for x in progs),
        whistle_uses_companion_in_view=sum(
            v == 1 for x in progs for v in x["companion_in_view_at_whistle"]
        ),
        fountain_drinks=sum(x["fountain_drinks"] for x in progs),
        origin_lag_at_admission=dict(
            min=min(x["admission_move"] - x["origin_move"] for x in progs),
            median=statistics.median(
                x["admission_move"] - x["origin_move"] for x in progs
            ),
            max=max(x["admission_move"] - x["origin_move"] for x in progs),
        ),
        with_callback=sum(x["callbacks"] > 0 for x in progs),
        after_expiry_programs_with_companion_whistle=sum(
            x["whistles_after_origin_expiry_companion_in_view"] > 0 for x in progs
        ),
        after_expiry_programs_with_fountain=sum(
            x["fountains_after_origin_expiry"] > 0 for x in progs
        ),
        programs=progs,
    )


def q3(games):
    """Budget refusals of programs 2-3.

    The engine refuses when cost > chaos_budget() (src/chaos_next_use_admission.c:103-105).
    chaos_budget() (src/chaos_protocol.c:214-228) is logged as "budget" on every
    event row (src/chaos_io.c:61); pacing (#164, on by default) adds descent and
    witnessed credits and a per-level cap inside it. "Budget +k" here means
    chaos_budget() + k at the decision: the exact admission counterfactual.

    The Sanity-only view (base 2 + lost Sanity / 10, no pacing credits) is
    also given, as the shortfall it implies; it is a bound, not the engine rule.
    """
    rows_ = []
    for g in games:
        for r in g["receipts"]:
            if r["program_ordinal"] < 2 or "budget" not in r["reasons"]:
                continue
            e = state_at(g, r["move"], r["safe"])
            sanity, spent, avail = e["sanity"], e["spent"], e["budget"]
            lost = SANITY_MAX - max(0, min(SANITY_MAX, sanity))
            base = BUDGET_BASE + lost // BUDGET_STEP
            cost = 1
            # cruelty already spent, by source (rows where "spent" rose)
            by, prev = collections.Counter(), 0
            for x in g["events"]:
                if x.get("turn", 0) > r["move"]:
                    break
                if x["spent"] > prev:
                    src = (
                        "hound"
                        if x["event"] == "haunting"
                        else "ordinary_whisper"
                        if x["event"] == "ack" and x.get("mutation")
                        else "next_use_program"
                    )
                    by[src] += x["spent"] - prev
                prev = x["spent"]
            rows_.append(
                dict(
                    game=g["name"],
                    ordinal=r["program_ordinal"],
                    move=r["move"],
                    reasons=r["reasons"],
                    lost_sanity=lost,
                    sanity_budget=base,
                    spent=spent,
                    spent_by=dict(by),
                    budget_available=avail,
                    cost=cost,
                    admit_plus1=cost <= avail + 1 and spent <= CEILING - cost,
                    admit_plus2=cost <= avail + 2 and spent <= CEILING - cost,
                    sanity_only_shortfall=spent + cost - base,
                )
            )
    agg = collections.Counter()
    for r in rows_:
        agg.update(r["spent_by"])
    return dict(
        refusals=len(rows_),
        only_reason_budget=sum(r["reasons"] == ["budget"] for r in rows_),
        refused_with_available_ge_cost=sum(
            r["budget_available"] >= r["cost"] for r in rows_
        ),
        admitted_at_plus1=sum(r["admit_plus1"] for r in rows_),
        admitted_at_plus2=sum(r["admit_plus2"] for r in rows_),
        sanity_only_admitted_at_plus1=sum(
            r["sanity_only_shortfall"] <= 1 for r in rows_
        ),
        sanity_only_admitted_at_plus2=sum(
            r["sanity_only_shortfall"] <= 2 for r in rows_
        ),
        by_available=counts(collections.Counter(r["budget_available"] for r in rows_)),
        by_lost_sanity=counts(collections.Counter(r["lost_sanity"] for r in rows_)),
        by_spent=counts(collections.Counter(r["spent"] for r in rows_)),
        spent_by_source=counts(agg),
        games_with_hound_spend=sum("hound" in r["spent_by"] for r in rows_),
        rows=rows_,
    )


def q4(games):
    refusals, games_hit, games_hit_tin, detail = 0, 0, 0, []
    for g in games:
        rs = [
            r
            for r in g["receipts"]
            if r["program_ordinal"] == 1 and "no_companion_in_view" in r["reasons"]
        ]
        if not rs:
            continue
        refusals += len(rs)
        hit = hit_tin = False
        for r in rs:
            lo, hi = (
                r["move"],
                r["move"] + 100,
            )  # program 1 lifetime (chaos_next_use.h:130)
            for w in g["whistles"]:
                p = g["probes"].get(w["root"])
                if lo < w["turn"] <= hi and p and p["pick"]:
                    hit = True
                    hit_tin = hit_tin or p["otyp"] != MAGIC_WHISTLE_OTYP
        games_hit += hit
        games_hit_tin += hit_tin
        detail.append(
            dict(game=g["name"], refusals=len(rs), later_whistle_companion_in_view=hit)
        )
    return dict(
        refusal_decisions=refusals,
        games=len(detail),
        games_later_whistle_with_companion_in_view=games_hit,
        games_same_tin_whistle_only=games_hit_tin,
        games_detail=detail,
    )


MAGIC_WHISTLE_OTYP = None  # filled from probes: the whistle otyp seen most


def twin_match(plain, diag):
    """Game for game: receipts, lifecycle, schedule, whispers byte-identical
    and the same last turn. Strict extra: events and journals too."""

    def h(p):
        return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None

    def last_turn(run):
        ev = rows(run / "events.jsonl")
        return ev[-1].get("turn") if ev else None

    # events.jsonl is required too (stricter than receipts/lifecycle/schedule/
    # whispers/turn count). Journals differ in every game by the per-process
    # run_token, so they are not compared.
    req = (
        "next_use-receipt.jsonl",
        "next_use-lifecycle.jsonl",
        "next_use-schedule.jsonl",
        "whispers.jsonl",
        "events.jsonl",
    )
    strict = (
        "next_use-journal.jsonl",
        "next_use-journal.2.jsonl",
        "next_use-journal.3.jsonl",
    )
    same, strict_same, differ = 0, 0, {}
    for d in sorted(
        x for x in plain.iterdir() if x.is_dir() and not x.name.startswith(".")
    ):
        a, b = rundir(d), rundir(diag / d.name)
        if not b.is_dir():
            differ[d.name] = ["missing_in_instrumented"]
            continue
        bad = [f for f in req if h(a / f) != h(b / f)]
        if last_turn(a) != last_turn(b):
            bad.append("last_turn")
        if bad:
            differ[d.name] = bad
            continue
        same += 1
        strict_same += all(h(a / f) == h(b / f) for f in strict)
    return dict(
        games_identical=same,
        games_identical_incl_events_and_journals=strict_same,
        games_differing=differ,
    )


def levers(games):
    """Per-program counts for the summary table (programs 2-3 unless noted)."""
    later = [(g, p) for g in games for p in g["programs"] if p["ordinal"] >= 2]
    blocked_only = sum(
        1
        for g, p in later
        if any(u["outcome"] == "blocked" for u in p["uses"])
        and not any(u["outcome"] == "delivered" for u in p["uses"])
    )
    felt = sum(
        1 for g, p in later if any(u["outcome"] == "delivered" for u in p["uses"])
    )
    return dict(
        later_admitted=len(later),
        later_felt=felt,
        later_blocked_never_delivered=blocked_only,
    )


def main(plain, diag=None):
    global MAGIC_WHISTLE_OTYP
    plain = Path(plain)
    diag = Path(diag) if diag else None
    twin = twin_match(plain, diag) if diag else None
    excluded = set(twin["games_differing"]) if twin else set()
    out = dict(twin=twin, starts={})
    for start in STARTS:
        dirs = sorted(d for d in plain.iterdir() if d.name.rsplit("-", 1)[0] == start)
        # A game whose instrumented twin differs gets no probe data: it is
        # excluded from every classifier/probe-derived count (q1 blocked
        # reasons, q2 companion-in-view, q4), and listed under "twin".
        games = [
            game(d, (diag / d.name) if diag and d.name not in excluded else None)
            for d in dirs
        ]
        if MAGIC_WHISTLE_OTYP is None:
            otyps = collections.Counter(
                p["otyp"] for g in games for p in g["probes"].values()
            )
            if otyps:
                tin = otyps.most_common(1)[0][0]
                MAGIC_WHISTLE_OTYP = tin + 1  # objects.c: MAGIC_WHISTLE follows WHISTLE
        out["starts"][start] = dict(
            games=len(games),
            q1=q1(games),
            q2=q2(games),
            q3=q3(games),
            q4=q4(games),
            levers=levers(games),
        )
    return out


if __name__ == "__main__":
    print(json.dumps(main(*sys.argv[1:3]), indent=1, sort_keys=True))
