"""Slice 5a live generation pilot: free-design hounds through the product
path, each run through the engine's real shadow trial (NGPL).

generate: every job goes through chaos.hound_author.author_hound exactly as
the director's hound lane would: provider xai-oauth with the configured model,
the shared xAI ledger (surface "haunt", its per-game and per-day caps), the
480 s deadline, the free-design prompt on a recorded public history, the
seeded literary layer, and the host pre-check (HoundValidator). At most one
regeneration, only for an envelope rejection, as in the lane. Each job writes
a standard evidence directory under runs/<run>/jobs/<job>/.

trial: links tests/chaos/haunt_room.c against the built engine objects (the
same command as tests/chaos/test_haunt_room.py) and runs every envelope-valid
source, plus footsteps.lua as the baseline, through the real haunt tick and
forked shadow trial in a fixed set of rooms and native RNG seeds.

analyze: summary.json (outcomes, latency, pre-check, shadow pass rate and
failure reasons).

Run generate under Hermes's runtime (it imports hermes_bootstrap first) and
inside hermes-heavy:

  pilot.py generate --lib <curio-validator.so> --out <dir> --model <id>
  pilot.py trial <dir> --work <scratch dir>
  pilot.py analyze <dir>
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/chaos"))

PILOT = ROOT / "docs/measurements/model-authoring-pilot"
JOBS = 20
FOOTSTEPS = ROOT / "chaos/packs/footsteps.lua"
CORNERED = ROOT / "tests/chaos/haunt_maps/cornered-190-game24.txt"
# Rooms (haunt_room arguments W H PX PY) and seeds for the shadow trial. The
# 12x6 room is the one test_haunt_room's bare-room case passes; 6x4 is a small
# start room; 20x8 a large one; "cornered" is the recorded #194 map.
ROOMS = (
    ("bare-6x4", [6, 4, 2, 1], None),
    ("bare-12x6", [12, 6, 5, 3], None),
    ("bare-20x8", [20, 8, 10, 4], None),
    ("cornered-194", [1, 1, 0, 0], CORNERED),
)
SEEDS = (1, 2, 3)


def histories():
    """Recorded public histories (#241's projection) that show a backtrack:
    the lane only ever asks after one, and the prompt says it was seen."""
    public = json.loads((PILOT / "histories-public.json").read_text())
    return {
        name: h
        for name, h in sorted(public.items())
        if any(
            e["event"] == "backtrack" for e in h["public_context"]["summary"]["recent"]
        )
    }


def plan(names):
    jobs = []
    for i in range(JOBS):
        name = names[i % len(names)]
        seed = 17 * i + 1  # synthetic game seed; layer = curio.seeded_layer(seed)
        jobs.append(dict(job=f"{i:02d}-{name}", history=name, seed=seed))
    return jobs


def _bootstrap():
    hermes = Path(
        os.environ.get("HERMES_AGENT_DIR") or Path.home() / ".hermes/hermes-agent"
    )
    sys.path.insert(0, str(hermes))
    import hermes_bootstrap  # noqa: F401  (may re-exec into Hermes's environment)


def generate(args):
    if not args.fake:
        _bootstrap()
    from chaos import hound_author, lane, xai
    from chaos.author_config import resolve

    config = resolve("xai-oauth", args.model)
    out = Path(args.out).absolute()
    (out / "jobs").mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    os.chmod(out / "jobs", 0o700)
    ledger = xai.XaiLedger(out / "fake-ledger.jsonl") if args.fake else xai.XaiLedger()
    validator = hound_author.HoundValidator(Path(args.lib).absolute())
    hist = histories()
    jobs = plan(sorted(hist))
    run = "pilot5a-" + time.strftime("%Y%m%d%H%M", time.gmtime())
    meta = dict(
        provider=config.provider,
        model=config.model,
        surface=hound_author.SURFACE,
        deadline_s=hound_author.DEADLINE_S,
        validator_sha256=validator.library_sha256,
        prompt_sha256=hashlib.sha256(
            (ROOT / "chaos/prompts/haunting.txt").read_bytes()
        ).hexdigest(),
        run=run,
        jobs=len(jobs),
        workers=args.workers,
        fake=args.fake,
        started=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    (out / "run-meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    def factory():
        from test_curio_grounding import FakeClient

        source = FOOTSTEPS.read_text()
        return FakeClient(json.dumps({"source": source})), args.model

    # Build every backend first: importing Hermes may re-exec the
    # interpreter, and must happen before any ledger reservation.
    backends = {
        job["job"]: hound_author.build_backend(
            config,
            ledger=ledger,
            run_id=f"{run}-{job['job'][:2]}",
            client_factory=factory if args.fake else None,
        )
        for job in jobs
    }
    lock = threading.Lock()
    validate_lock = threading.Lock()

    class Serialised:
        library_sha256 = validator.library_sha256

        def validate(self, source):
            with validate_lock:
                return validator.validate(source)

    def one(job):
        target = out / "jobs" / job["job"]
        if target.exists():
            return
        target.mkdir(mode=0o700)
        prepared = hound_author.prepare(
            hist[job["history"]]["public_context"],
            game_seed=job["seed"],
            event=dict(history=job["history"]),
        )
        started = time.monotonic()
        receipt = None
        for name in ("a", "b"):
            remaining = hound_author.DEADLINE_S - (time.monotonic() - started)
            if remaining <= 0:
                break
            receipt = hound_author.author_hound(
                backends[job["job"]],
                events_dir=None,
                evidence_dir=target / name,
                game_seed=job["seed"],
                validator=Serialised(),
                deadline_s=remaining,
                prepared=prepared,
            )
            if receipt["outcome"] not in lane.REGENERATE:
                break
        with lock:
            print(job["job"], receipt["outcome"], receipt["latency_s"], flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(one, jobs))
    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out / "run-meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    if not args.fake:
        rows = [r for r in ledger.rows() if r["run_id"].startswith(run)]
        (out / "ledger.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
        )


# ---------------------------------------------------------------- trial
def link(work):
    from native_rng import controlled_rng_objects

    work.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "objcopy",
            "--redefine-sym",
            "main=original_game_main",
            str(ROOT / "sys/unix/unixmain.o"),
            str(work / "unixmain.o"),
        ],
        check=True,
    )
    objects = (
        sorted((ROOT / "src").glob("*.o"))
        + [
            ROOT / "sys/unix/unixres.o",
            ROOT / "sys/unix/unixunix.o",
            work / "unixmain.o",
            ROOT / "sys/share/ioctl.o",
            ROOT / "sys/share/unixtty.o",
        ]
        + sorted((ROOT / "win/tty").glob("*.o"))
        + sorted((ROOT / "win/curses").glob("*.o"))
    )
    exe = work / "haunt_room"
    subprocess.run(
        [
            "cc",
            "-g",
            "-DCHAOS",
            "-I" + str(ROOT / "include"),
            str(ROOT / "tests/chaos/haunt_room.c"),
            *map(str, controlled_rng_objects(objects, work)),
            "-Wl,--wrap=pline",
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["pkg-config", "--libs", "lua5.4"], text=True
            ).split(),
            "-o",
            str(exe),
        ],
        check=True,
        timeout=120,
    )
    return exe


def shadow(exe, source, room, seed, work):
    name, args, path = room
    with tempfile.TemporaryDirectory(dir=work) as case:
        run = Path(case) / "run"
        (run / "diag").mkdir(parents=True)
        run.chmod(0o700)
        (run / "haunting.lua").write_bytes(source)
        (run / "haunting.lua").chmod(0o600)
        env = dict(os.environ, NYARLATHACK_ECHOES="0", NYARLATHACK_RUN_DIR=str(run))
        if path is not None:
            env["HAUNT_ROOM_MAP"] = str(path)
        p = subprocess.run(
            [str(exe), *map(str, args), str(seed)],
            cwd=run / "diag",
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=60,
        )
        report = run / "dreamlands.json"
        result = json.loads(report.read_text()) if report.exists() else None
    return dict(room=name, seed=seed, exit=p.returncode, report=result)


def reason(report):
    if report is None:
        return "no_trial"
    if report["accepted"]:
        return None
    if report["script_errors"]:
        return "script_error"
    if report["died"]:
        return "died"
    if report["moved"] == 0:
        return "stuck"
    if report["max_damage"] > 4:
        return "damage"
    if not report["escaped"]:
        return "cornered"
    return "short"


def trial(args):
    out = Path(args.out)
    exe = link(Path(args.work))
    sources = {"footsteps": FOOTSTEPS.read_bytes()}
    for job in sorted((out / "jobs").iterdir()):
        final = sorted(p for p in job.iterdir() if (p / "receipt.json").exists())[-1]
        if (final / "source.lua").exists():
            sources[job.name] = (final / "source.lua").read_bytes()
    results = {}
    for name, source in sources.items():
        rows = [
            shadow(exe, source, room, seed, Path(args.work))
            for room in ROOMS
            for seed in SEEDS
        ]
        for row in rows:
            row["reason"] = reason(row["report"])
        results[name] = dict(
            source_sha256=hashlib.sha256(source).hexdigest(), trials=rows
        )
        passed = sum(r["reason"] is None for r in rows)
        print(name, f"{passed}/{len(rows)}", flush=True)
    (out / "trials.json").write_text(
        json.dumps(results, indent=1, sort_keys=True) + "\n"
    )


# ---------------------------------------------------------------- analyze
def _spread(values):
    if not values:
        return None
    return dict(min=min(values), median=statistics.median(values), max=max(values))


def analyze(args):
    from chaos import hound_author

    out = Path(args.out)
    trials = json.loads((out / "trials.json").read_text())
    rows = []
    for job in sorted((out / "jobs").iterdir()):
        attempts = sorted(p for p in job.iterdir() if (p / "receipt.json").exists())
        receipts = [json.loads((p / "receipt.json").read_text()) for p in attempts]
        final = receipts[-1]
        if final["outcome"] == "ready":
            hound_author.read_evidence(attempts[-1])  # hash chain verifies
        t = trials.get(job.name)
        rows.append(
            dict(
                job=job.name,
                attempts=len(receipts),
                outcome=final["outcome"],
                layer=final["layer"],
                latency_s=[r["latency_s"] for r in receipts],
                precheck=final["native"],
                shadow=None
                if t is None
                else dict(
                    passed=sum(x["reason"] is None for x in t["trials"]),
                    trials=len(t["trials"]),
                    reasons=sorted({x["reason"] for x in t["trials"] if x["reason"]}),
                    by_room={
                        room: sum(
                            x["reason"] is None
                            for x in t["trials"]
                            if x["room"] == room
                        )
                        for room, _, _ in ROOMS
                    },
                ),
            )
        )
    latencies = [x for r in rows for x in r["latency_s"] if x is not None]
    shadowed = [r for r in rows if r["shadow"]]
    reasons = {}
    for name, t in trials.items():
        if name == "footsteps":
            continue
        for x in t["trials"]:
            if x["reason"]:
                reasons[x["reason"]] = reasons.get(x["reason"], 0) + 1
    base = trials["footsteps"]["trials"]
    summary = dict(
        jobs=len(rows),
        requests=sum(r["attempts"] for r in rows),
        outcomes={
            o: sum(r["outcome"] == o for r in rows) for o in hound_author.OUTCOMES
        },
        latency_s=dict(
            **_spread(latencies),
            p90=sorted(latencies)[int(0.9 * (len(latencies) - 1))],
            over_deadline=sum(x > hound_author.DEADLINE_S for x in latencies),
        ),
        shadow=dict(
            rooms=[r for r, _, _ in ROOMS],
            seeds=list(SEEDS),
            candidates=len(shadowed),
            trials=sum(r["shadow"]["trials"] for r in shadowed),
            passed=sum(r["shadow"]["passed"] for r in shadowed),
            pass_all=sum(
                r["shadow"]["passed"] == r["shadow"]["trials"] for r in shadowed
            ),
            pass_none=sum(r["shadow"]["passed"] == 0 for r in shadowed),
            failure_reasons=reasons,
            ready_pass_all=sum(
                r["outcome"] == "ready"
                and r["shadow"]["passed"] == r["shadow"]["trials"]
                for r in shadowed
            ),
            footsteps=dict(
                passed=sum(x["reason"] is None for x in base), trials=len(base)
            ),
        ),
        rows=rows,
    )
    text = json.dumps(summary, indent=1) + "\n"
    (out / "summary.json").write_text(text)
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=1))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--lib", required=True)
    g.add_argument("--out", required=True)
    g.add_argument("--model", required=True)
    g.add_argument("--workers", type=int, default=4)
    g.add_argument("--fake", action="store_true", help="plumbing check: no model")
    t = sub.add_parser("trial")
    t.add_argument("out")
    t.add_argument("--work", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("out")
    args = parser.parse_args(argv)
    {"generate": generate, "trial": trial, "analyze": analyze}[args.cmd](args)


if __name__ == "__main__":
    main()
