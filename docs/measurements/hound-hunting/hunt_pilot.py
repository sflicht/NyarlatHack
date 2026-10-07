"""Hounds that hunt: live generation pilot (NGPL).

generate: the #251 pilot's generate (same 20 jobs, same histories, same
synthetic game seeds, same author path, ledger surface "haunt"), with two
differences: the prompt is the revised haunting.txt, and the regeneration
rule is the hound lane's own (hound_director.HoundLane.REGENERATE: an
envelope or pre-check rejection earns one regeneration inside the 480 s
deadline). The pre-check is HoundValidator with the pre-registered pressure
floor (PREREGISTERED.md).

trial / analyze: measure.py pilot <run> (engine shadow metrics with
instrument.patch applied) and the analysis in analyze.py.

  hunt_pilot.py generate --lib <curio-validator.so> --out <dir> --model <id> [--fake]
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/chaos"))
sys.path.insert(0, str(ROOT / "docs/measurements/hound-free-pilot"))

import pilot  # noqa: E402


def generate(args):
    if not args.fake:
        pilot._bootstrap()
    from chaos import hound_author, hound_director, xai
    from chaos.author_config import resolve

    regenerate = hound_director.HoundLane.REGENERATE
    config = resolve("xai-oauth", args.model)
    out = Path(args.out).absolute()
    (out / "jobs").mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    os.chmod(out / "jobs", 0o700)
    ledger = xai.XaiLedger(out / "fake-ledger.jsonl") if args.fake else xai.XaiLedger()
    validator = hound_author.HoundValidator(Path(args.lib).absolute())
    import subprocess

    rev = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout
    if dirty and not args.fake:
        raise SystemExit("refusing a live pilot from an uncommitted tree")
    hist = pilot.histories()
    jobs = pilot.plan(sorted(hist))
    if args.only:
        jobs = [j for j in jobs if j["job"] in args.only]
    run = "hunt-" + time.strftime("%Y%m%d%H%M", time.gmtime())
    meta = dict(
        provider=config.provider,
        model=config.model,
        surface=hound_author.SURFACE,
        deadline_s=hound_author.DEADLINE_S,
        regenerate=list(regenerate),
        floor=dict(
            rooms=[r[0] for r in hound_author.REHEARSAL_ROOMS],
            steps=hound_author.REHEARSAL_STEPS,
            min_moved=hound_author.MIN_MOVED,
            contact=hound_author.CONTACT,
            escape=hound_author.ESCAPE,
        ),
        validator_sha256=validator.library_sha256,
        prompt_sha256=hashlib.sha256(
            (ROOT / "chaos/prompts/haunting.txt").read_bytes()
        ).hexdigest(),
        run=run,
        rev=rev,
        clean=not dirty,
        jobs=len(jobs),
        workers=args.workers,
        fake=args.fake,
        started=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    (out / "run-meta.json").write_text(json.dumps(meta, indent=2) + "\n")

    def factory():
        from test_curio_grounding import FakeClient

        return FakeClient(json.dumps({"source": pilot.FOOTSTEPS.read_text()})), args.model

    # Every backend first: importing Hermes may re-exec the interpreter.
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
            with lock:
                print(job["job"], name, receipt["outcome"], receipt["latency_s"],
                      (receipt.get("native") or {}).get("failure"), flush=True)
            if receipt["outcome"] not in regenerate:
                break

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(one, jobs))
    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out / "run-meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    if not args.fake:
        rows = [r for r in ledger.rows() if r["run_id"].startswith(run)]
        (out / "ledger.jsonl").write_text(
            "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows)
        )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--lib", required=True)
    g.add_argument("--out", required=True)
    g.add_argument("--model", required=True)
    g.add_argument("--workers", type=int, default=4)
    g.add_argument("--fake", action="store_true", help="plumbing check: no model")
    g.add_argument("--only", nargs="*", help="run only these job names (latency probe)")
    args = parser.parse_args(argv)
    generate(args)


if __name__ == "__main__":
    main()
