#!/usr/bin/env python3
"""Seeded scripted-player sweep with an engine-stage funnel report (#167).

One command plays every (start, seed) pair with a declared policy through the
ordinary launcher (`chaos play --ordinary --next-use`), then writes a JSON and
a Markdown funnel report. Engine stages only: notice, attribution and changed
decisions are human-only (#44) and are never inferred from these numbers.

No model calls, no wizard mode, no hidden-state lookahead, no retries and no
discarded seeds. Per-game artifacts stay under --work (not committed). The
default mkdtemp work dir is removed after a clean sweep and kept on failure or
with NYARLATHACK_KEEP_ARTIFACTS=1; an explicit --work dir is always kept.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests/chaos")]

import sweep_funnel  # noqa: E402
import sweep_player  # noqa: E402
from artifact_hygiene import keep_requested, remove_tree  # noqa: E402

REPORT_V = 2


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_clock(directory):
    out = Path(directory) / "sweep_clock.so"
    subprocess.run(
        [
            "cc",
            "-shared",
            "-fPIC",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(ROOT / "tests/chaos/sweep_clock.c"),
            "-ldl",
            "-o",
            str(out),
        ],
        check=True,
        timeout=60,
    )
    return out


def one(job):
    start, seed, policy, work, clock, gamedir = job
    root = Path(work) / f"{start}-{seed:05d}"
    # One immutable asset pool per worker process: concurrent hardlinking into
    # a shared pool changes inode ctime mid-hash and is rejected by the harness.
    pool = Path(work) / f".assets-{os.getpid()}"
    played = sweep_player.play(gamedir, clock, root, seed, start, policy, pool)
    v2 = "v2" in played
    funnel = sweep_funnel.analyse(root, felt=v2)
    if v2 and funnel["first_felt"] is not None:
        funnel["first_felt"]["dlvl"] = sweep_funnel.dlvl_at(
            played["v2"]["dlvl_timeline"], funnel["first_felt"]["turn"]
        )
    return {
        "start": start,
        "seed": seed,
        **played,
        "funnel": funnel,
    }


def _dist(values):
    if not values:
        return None
    values = sorted(values)
    return {
        "n": len(values),
        "min": values[0],
        "median": statistics.median(values),
        "max": values[-1],
    }


def aggregate(games):
    out = {}
    for start in sorted({g["start"] for g in games}):
        rows = [g for g in games if g["start"] == start]
        reached = {
            s: sum(1 for g in rows if g["funnel"]["counts"][s] > 0)
            for s in sweep_funnel.STAGES
        }
        totals = {
            s: sum(g["funnel"]["counts"][s] for g in rows) for s in sweep_funnel.STAGES
        }
        losses = {}
        for g in rows:
            key = g["funnel"]["loss"] or "delivered"
            losses[key] = losses.get(key, 0) + 1
        outcomes = {}
        for g in rows:
            outcomes[g["outcome"]] = outcomes.get(g["outcome"], 0) + 1
        # #196: recorded W suppression reasons, and safe-point refusals whose
        # recorded reasons include no_companion_in_view (C3).
        suppressions = {}
        for g in rows:
            for why in g["funnel"].get("w_suppressions", []):
                suppressions[why] = suppressions.get(why, 0) + 1
        c3 = [
            sum(
                1
                for d in g["funnel"].get("recorded_decisions", [])
                if "no_companion_in_view" in d["reasons"]
            )
            for g in rows
        ]
        out[start] = {
            "games": len(rows),
            "outcomes": dict(sorted(outcomes.items())),
            "games_reaching_stage": reached,
            "stage_totals": totals,
            "zero_delivered_games": sum(
                1
                for g in rows
                if g["funnel"]["delivery_known"]
                and not g["funnel"]["counts"]["delivered"]
            ),
            "delivery_unknown_games": sum(
                1 for g in rows if not g["funnel"]["delivery_known"]
            ),
            "loss_reasons": dict(
                sorted(losses.items(), key=lambda kv: (-kv[1], kv[0]))
            ),
            "w_suppressions_by_reason": dict(sorted(suppressions.items())),
            "no_companion_refusals": {
                "games": sum(1 for n in c3 if n),
                "decisions": sum(c3),
            },
            "first_admission_move": _dist(
                [
                    g["funnel"]["first_admission_move"]
                    for g in rows
                    if g["funnel"]["first_admission_move"] is not None
                ]
            ),
            "start_budget": sorted(
                {
                    g["funnel"]["start_budget"]
                    for g in rows
                    if g["funnel"]["start_budget"] is not None
                }
            ),
            "start_sanity": sorted(
                {
                    g["funnel"]["start_sanity"]
                    for g in rows
                    if g["funnel"]["start_sanity"] is not None
                }
            ),
            "last_turn": _dist(
                [
                    g["funnel"]["last_turn"]
                    for g in rows
                    if g["funnel"]["last_turn"] is not None
                ]
            ),
            "max_dlvl": _dist(
                [
                    g["final_status"].get("dlvl")
                    for g in rows
                    if g["final_status"].get("dlvl")
                ]
            ),
            "qualifying_actions": {
                op: sum(g["funnel"]["qualifying_actions"][op] for g in rows)
                for op in sweep_funnel.QUALIFYING
            },
            "save_restore": {
                "attempted": sum(1 for g in rows if g["save_restore"]["attempted"]),
                "restored": sum(
                    1 for g in rows if g["save_restore"]["session_detail"] == "restore"
                ),
            },
            "nonzero_exit": sum(1 for g in rows if g["exit_code"] not in (0, None)),
            "harness_errors": sum(1 for g in rows if g["outcome"] == "harness_error"),
            "director_sync_timeouts": sum(g["sync_timeouts"] for g in rows),
            "ordinary_whispers_admitted": sum(
                g["funnel"]["ordinary_whispers_admitted"] for g in rows
            ),
        }
        if all("v2" in g for g in rows):
            out[start].update(aggregate_v2(rows))
    return out


def aggregate_v2(rows):
    """#179 (and #164's rates): only in baseline-v2 reports."""
    felt = [g["funnel"]["first_felt"] for g in rows if g["funnel"]["first_felt"]]
    turns = sum(g["funnel"]["last_turn"] or 0 for g in rows)
    levels = sum(len({d for _, d in g["v2"]["dlvl_timeline"]}) for g in rows)
    admitted = sum(g["funnel"]["counts"]["admitted"] for g in rows)
    delivered = sum(g["funnel"]["counts"]["delivered"] for g in rows)
    hound = sum(g["funnel"]["haunt"].get("accepted", 0) for g in rows)
    return {
        "first_felt": {
            "games": len(felt),
            "turn": _dist([f["turn"] for f in felt]),
            "dlvl": _dist([f["dlvl"] for f in felt if f["dlvl"] is not None]),
            "by_kind": {
                k: sum(1 for f in felt if f["kind"] == k)
                for k in ("hound", "next_use_W", "next_use_F", "door")
            },
        },
        "turns_played": turns,
        "levels_visited": levels,
        "per_1000_turns": {
            "admitted": round(1000 * admitted / turns, 3) if turns else None,
            "delivered": round(1000 * delivered / turns, 3) if turns else None,
            "hound_accepted": round(1000 * hound / turns, 3) if turns else None,
        },
        "per_level": {
            "admitted": round(admitted / levels, 3) if levels else None,
            "delivered": round(delivered / levels, 3) if levels else None,
            "hound_accepted": round(hound / levels, 3) if levels else None,
        },
        "hound": {
            "games_accepted": sum(
                1 for g in rows if g["funnel"]["haunt"].get("accepted")
            ),
            "steps": sum(g["funnel"]["haunt_steps"] for g in rows),
        },
        "policy": {
            k: sum(g["v2"][k] for g in rows)
            for k in ("prayers", "flees", "rests", "whistles_found")
        },
        "games_with_whistle": sum(1 for g in rows if g["whistle_in_inventory"]),
    }


def markdown(report):
    ident, agg = report["identity"], report["aggregate"]
    lines = [
        f"# Seed sweep funnel: {ident['policy']}, seeds {ident['seeds'][0]}-{ident['seeds'][1]}",
        "",
        "Engine stages only, from a scripted player (not an AI and not a human proxy).",
        "Player notice, attribution and changed decisions are not measured (#44).",
        "",
        f"- Revision: `{ident['revision']}`; `dnethack` sha256 `{ident['dnethack_sha256'][:16]}`",
        f"- Policy `{ident['policy']}`: `{json.dumps(ident['policy_params'], sort_keys=True)}`",
        f"- Command: `{ident['command']}`",
        f"- Report digest (sha256 of canonical JSON without this field): `{report['report_sha256']}`",
        "",
        "Stages: qualifying history, engine candidate (schedule row), published envelope,",
        "admitted, trigger (Lua callback ran), native effect (W armed or F remapped),",
        "delivered (W witnessed or F remapped).",
        "",
    ]
    for start, a in agg.items():
        n = a["games"]
        lines += [
            f"## {start} ({n} games; start Sanity {a['start_sanity']}, budget {a['start_budget']})",
            "",
        ]
        lines.append(
            "- Games reaching each stage: "
            + ", ".join(
                f"{s} {a['games_reaching_stage'][s]}" for s in sweep_funnel.STAGES
            )
        )
        lines.append(
            "- Stage totals: "
            + ", ".join(f"{s} {a['stage_totals'][s]}" for s in sweep_funnel.STAGES)
        )
        lines.append(
            f"- Zero delivered effects: {a['zero_delivered_games']}/{n}; "
            f"delivery unknown (admitted, journal missing/incomplete/invalid): "
            f"{a['delivery_unknown_games']}"
        )
        lines.append(
            "- Loss reasons (first lost stage per game): "
            + ", ".join(f"{k} {v}" for k, v in a["loss_reasons"].items())
        )
        lines.append(
            "- W capture suppressions by recorded reason: "
            + (
                ", ".join(f"{k} {v}" for k, v in a["w_suppressions_by_reason"].items())
                or "none"
            )
        )
        lines.append(
            "- Safe-point refusals for no companion in view: "
            f"{a['no_companion_refusals']['decisions']} decisions in "
            f"{a['no_companion_refusals']['games']} games"
        )
        lines.append(f"- First admission move: {a['first_admission_move']}")
        lines.append(
            "- Outcomes: " + ", ".join(f"{k} {v}" for k, v in a["outcomes"].items())
        )
        lines.append(f"- Last turn: {a['last_turn']}; final Dlvl: {a['max_dlvl']}")
        if "first_felt" in a:
            f = a["first_felt"]
            lines.append(
                f"- First felt consequence (#179): {f['games']}/{n} games; "
                f"turn {f['turn']}; Dlvl {f['dlvl']}; by kind {f['by_kind']}"
            )
            lines.append(
                f"- Rates (#164): per 1000 turns {a['per_1000_turns']}; per level "
                f"visited {a['per_level']} ({a['turns_played']} turns, "
                f"{a['levels_visited']} levels)"
            )
            lines.append(
                f"- Hound: accepted in {a['hound']['games_accepted']} games, "
                f"{a['hound']['steps']} visible steps"
            )
            lines.append(
                f"- Policy v2 actions: {a['policy']}; games holding a whistle: "
                f"{a['games_with_whistle']}"
            )
        lines.append(f"- Qualifying-action attempts: {a['qualifying_actions']}")
        lines.append(
            f"- Save/restore: {a['save_restore']['restored']}/{a['save_restore']['attempted']} restored; "
            f"nonzero exits {a['nonzero_exit']}; harness errors {a['harness_errors']}; "
            f"director sync timeouts {a['director_sync_timeouts']}"
        )
        lines.append("")
    lines += [
        "## Limits",
        "",
        "- One simple fixed policy. Numbers describe this policy, not human play.",
        "- `rejected:` loss reasons are the engine's recorded decision row (every failing",
        "  check, #177). Reasons marked `inferred:` are guesses from public event timing",
        "  (`turn`, not monstermoves), used only where the engine wrote no decision row.",
        "- `whistle_capture_suppressed`: admitted, but at the first whistle no qualifying",
        "  companion was in view, so the engine skipped the callback (by design, #196).",
        "  The recorded reason says whether none was in view, only ineligible ones were,",
        "  or the chosen one stopped qualifying before capture.",
        "- A single one-shot next-use program per game (the launcher's current design).",
        "- The inherited start fixes one artifact (Vampire Killer); others are untested.",
        "- In-game mail is off (`!mail`): it reads the host mail spool, not the seed.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", required=True, help="inclusive range, e.g. 1-100")
    parser.add_argument(
        "--policy", default="baseline-v1", choices=sorted(sweep_player.POLICIES)
    )
    parser.add_argument("--starts", default="bard,madman,bard-inherited")
    parser.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--work", type=Path, help="per-game artifacts; default mkdtemp")
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="report path stem (.json/.md added); committed reports go under "
        "docs/measurements/<name>/",
    )
    parser.add_argument("--game-dir", type=Path, default=ROOT / "dnethackdir")
    args = parser.parse_args()

    lo, hi = (int(x) for x in args.seeds.split("-"))
    starts = args.starts.split(",")
    for start in starts:
        if start not in sweep_player.START_OPTIONS:
            raise SystemExit(f"unknown start {start}")
    if (ROOT / ".chaos-build").read_text().strip() != "1":
        raise SystemExit("CHAOS=1 build required")
    owned = args.work is None
    if owned:
        work = Path(tempfile.mkdtemp(prefix="nyarl-sweep-"))
    else:
        work = args.work
        work.mkdir(parents=True, exist_ok=False)  # never reuse an occupied dir
    print(f"SWEEP_WORK={work}", flush=True)
    games = None
    try:
        clock = build_clock(work)
        jobs = [
            (s, seed, args.policy, str(work), str(clock), str(args.game_dir))
            for s in starts
            for seed in range(lo, hi + 1)
        ]
        with ProcessPoolExecutor(max_workers=args.jobs) as pool:
            games = list(pool.map(one, jobs))
        return write_report(args, lo, hi, starts, games)
    finally:
        tidy_work(work, owned, games)


def sweep_failed(games):
    """A sweep failed if it did not finish or any game hit a harness error."""
    return games is None or any(g["outcome"] == "harness_error" for g in games)


def tidy_work(work, owned, games, environ=None):
    """Remove a default (mkdtemp) work dir after success; keep it otherwise.

    An explicit --work directory always belongs to the caller and is kept.
    """
    if not owned:
        return False
    if sweep_failed(games) or keep_requested(environ):
        print(f"SWEEP_WORK_RETAINED={work}", flush=True)
        return False
    return remove_tree(work)


def write_report(args, lo, hi, starts, games):

    identity = {
        "report_v": REPORT_V
        + (1 if sweep_player.POLICIES[args.policy].get("version", 1) >= 2 else 0),
        "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "dnethack_sha256": sha256(args.game_dir / "dnethack"),
        "nhdat_sha256": sha256(args.game_dir / "nhdat"),
        "clock_source_sha256": sha256(ROOT / "tests/chaos/sweep_clock.c"),
        "player_source_sha256": sha256(ROOT / "tests/chaos/sweep_player.py"),
        "funnel_source_sha256": sha256(ROOT / "tests/chaos/sweep_funnel.py"),
        "policy": args.policy,
        "policy_params": sweep_player.POLICIES[args.policy],
        "starts": {
            s: (sweep_player.START_OPTIONS[s] or "chaos.ordinary_start.OPTIONS")
            + sweep_player.NO_HOST_MAIL
            for s in starts
        },
        "seeds": [lo, hi],
        "launcher": sweep_player.LAUNCHER,
        **(
            {
                "start_launchers": {
                    s: sweep_player.START_LAUNCHER[s]
                    for s in starts
                    if s in sweep_player.START_LAUNCHER
                }
            }
            if any(s in sweep_player.START_LAUNCHER for s in starts)
            else {}
        ),
        "command": f"python3 scripts/seed_sweep.py --seeds {lo}-{hi} --policy {args.policy} "
        f"--starts {','.join(starts)} --out <stem>",
    }
    report = {"identity": identity, "aggregate": aggregate(games), "games": games}
    canonical = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    report["report_sha256"] = hashlib.sha256(canonical).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.with_suffix(".json").write_text(
        json.dumps(report, indent=1, sort_keys=True) + "\n"
    )
    args.out.with_suffix(".md").write_text(markdown(report))
    print(f"REPORT_SHA256={report['report_sha256']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
