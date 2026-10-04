"""Slice 2b pilot rerun: curios through the product path (NGPL).

Every generation goes through chaos.curio_author exactly as a game would:
configured provider and model (AuthorConfig), XaiBackend for xai-oauth with
the shared xAI ledger, the 6-minute deadline, the history-grounded prompt with
no continuity notes, the seeded literary layer, native validation through the
engine's own Lua entry points, then the truthfulness check. Each job writes a
standard evidence directory under runs/<run>/jobs/<job>/.

The recorded histories carry no game seed, so each job gets a synthetic seed
(see SEEDS); its layer is curio.seeded_layer(seed), the product rule.

Run under Hermes's runtime for xai-oauth (a launcher that imports
hermes_bootstrap first), inside hermes-heavy:

  rerun.py generate --lib <validator.so> --out <dir> --model <id> [--workers N]
  rerun.py analyze <dir>
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))

from chaos import curio, curio_author, curio_truth  # noqa: E402
from chaos.author_config import resolve  # noqa: E402

PILOT = ROOT / "docs/measurements/model-authoring-pilot"
REPLICATES = 2


def histories(sweep_root):
    spec = json.loads((PILOT / "histories.json").read_text())
    public = json.loads((PILOT / "histories-public.json").read_text())
    out = {}
    for name, rel in spec.items():
        if rel.startswith("sweep:"):
            path = Path(sweep_root) / rel[len("sweep:") :]
        else:
            path = ROOT / rel
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != public[name]["events_sha256"]:
            raise ValueError(f"{name}: history differs from #241's projection")
        out[name] = dict(path=path, role=public[name]["role"])
    return out


def seed_for(index, replicate):
    """Synthetic per-job game seed; deterministic, documented in the README."""
    return 1000 * replicate + 17 * index + 1


def plan(names):
    jobs = []
    for replicate in range(REPLICATES):
        for index, name in enumerate(sorted(names)):
            seed = seed_for(index, replicate)
            jobs.append(
                dict(
                    job=f"{name}-r{replicate}",
                    history=name,
                    seed=seed,
                    layer=curio.seeded_layer(seed),
                )
            )
    return jobs


def generate(args):
    from chaos import xai
    from chaos.curio_native import CurioValidator

    config = resolve("xai-oauth", args.model)
    out = Path(args.out).absolute()
    # The evidence store requires private parents (curio_store._private).
    (out / "jobs").mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    os.chmod(out / "jobs", 0o700)
    ledger = xai.XaiLedger(out / "xai-ledger.jsonl")
    validator = CurioValidator(Path(args.lib).absolute())
    hist = histories(args.sweep_root)
    jobs = plan(hist)
    meta = dict(
        provider=config.provider,
        model=config.model,
        deadline_s=curio_author.DEADLINE_S,
        prompt_cap=curio.MAX_PROMPT_BYTES,
        validator_sha256=validator.library_sha256,
        jobs=len(jobs),
        workers=args.workers,
        started=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    (out / "run-meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    lock = threading.Lock()
    # Build every backend first: importing Hermes may re-exec the interpreter,
    # and must happen before any ledger reservation (slice 3's rule).
    backends = {}
    for job in jobs:
        backends[job["job"]] = curio_author.build_backend(
            config, ledger=ledger, run_id="rerun-" + job["job"]
        )
    # The validator (ctypes, Lua) is not shared across threads.
    validate_lock = threading.Lock()

    class Serialised:
        library_sha256 = validator.library_sha256

        def validate(self, *a):
            with validate_lock:
                return validator.validate(*a)

    def run(job):
        target = out / "jobs" / job["job"]
        if (target / "receipt.json").exists():
            return
        if target.exists():
            shutil.rmtree(target)
        with tempfile.TemporaryDirectory(prefix="rerun-h-") as d:
            os.chmod(d, 0o700)
            shutil.copyfile(hist[job["history"]]["path"], Path(d) / "events.jsonl")
            os.chmod(Path(d) / "events.jsonl", 0o600)
            receipt = curio_author.author_curio(
                backends[job["job"]],
                events_dir=d,
                evidence_dir=target,
                game_seed=job["seed"],
                validator=Serialised(),
                role=hist[job["history"]]["role"],
            )
        with lock:
            print(job["job"], receipt["outcome"], receipt["latency_s"], flush=True)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(run, jobs))
    meta["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    (out / "run-meta.json").write_text(json.dumps(meta, indent=2) + "\n")


def analyze(args):
    out = Path(args.out)
    rows = []
    for job in sorted((out / "jobs").iterdir()):
        receipt = json.loads((job / "receipt.json").read_text())
        name, replicate = job.name.rsplit("-r", 1)
        row = dict(job=job.name, history=name, replicate=int(replicate), **receipt)
        if receipt["outcome"] == "ready":
            curio_author.read_evidence(job)  # hash chain verifies
        rows.append(row)
    latencies = [r["latency_s"] for r in rows if r["latency_s"] is not None]
    outcomes = {}
    for r in rows:
        outcomes[r["outcome"]] = outcomes.get(r["outcome"], 0) + 1
    native_admitted = [r for r in rows if r["native"] and r["native"]["admitted"]]
    rejected = [
        dict(
            job=r["job"],
            name=r["native"]["name"],
            hits=r["truth_hits"],
        )
        for r in rows
        if r["outcome"] == "truth_rejected"
    ]
    # Rules re-applied to stored texts: confirms the receipt is reproducible.
    for r in native_admitted:
        assert curio_truth.check(curio_truth.curio_texts(r["native"])) == (
            r["truth_hits"] or []
        ), r["job"]
    summary = dict(
        jobs=len(rows),
        outcomes=outcomes,
        envelope_ok=sum(r["lua_source_sha256"] is not None for r in rows),
        native_admitted=len(native_admitted),
        truth_rejected=len(rejected),
        ready=outcomes.get("ready", 0),
        layers={
            layer: sum(r["layer"] == layer for r in rows) for layer in curio.LAYERS
        },
        latency_s=dict(
            median=statistics.median(latencies) if latencies else None,
            p90=sorted(latencies)[int(0.9 * (len(latencies) - 1))] if latencies else None,
            max=max(latencies) if latencies else None,
            over_deadline=sum(x > curio_author.DEADLINE_S for x in latencies),
        ),
        reasoning_tokens_median=statistics.median(
            r["transport"]["record"].get("reasoning_tokens") or 0
            for r in rows
            if r["transport"] and r["transport"].get("record")
        )
        if rows
        else None,
        truth_rejections=rejected,
    )
    text = json.dumps(summary, indent=2) + "\n"
    (out / "summary.json").write_text(text)
    print(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--lib", required=True)
    g.add_argument("--out", required=True)
    g.add_argument("--model", required=True)
    g.add_argument("--workers", type=int, default=4)
    g.add_argument(
        "--sweep-root",
        default=str(Path.home() / ".hermes/reports/nyarlathack-arc-later-funnel/runs-plain"),
    )
    a = sub.add_parser("analyze")
    a.add_argument("out")
    args = parser.parse_args(argv)
    (generate if args.cmd == "generate" else analyze)(args)


if __name__ == "__main__":
    main()
