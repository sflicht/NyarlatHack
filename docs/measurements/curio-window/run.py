"""Run the paired curio-window games (see PREREGISTERED.md).

usage: run.py BEFORE_TREE AFTER_TREE RESULTS FIRST_SEED LAST_SEED [JOBS] [START_BUDGET_S]

Order: seed, then pace (1, 3), then tree (before, after); up to JOBS games at
once (default 8). No new seed starts after START_BUDGET_S seconds (default
5700), so started seeds finish inside about 2 hours. Builds the sweep clock
once from the after tree. Each game is a separate measure.py process (the
sweep clock reads its seed from the environment).
"""

import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
before, after, results = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
first, last = int(sys.argv[4]), int(sys.argv[5])
jobs = int(sys.argv[6]) if len(sys.argv) > 6 else 8
budget = float(sys.argv[7]) if len(sys.argv) > 7 else 5700.0
work = Path(os.environ["TMPDIR"])
clock = work / "sweep_clock.so"
subprocess.run(
    [
        "cc",
        "-shared",
        "-fPIC",
        "-O2",
        str(after / "tests/chaos/sweep_clock.c"),
        "-o",
        str(clock),
    ],
    check=True,
)
env = dict(os.environ, CURIO_WINDOW_CLOCK=str(clock))
tasks = [
    (seed, pace, label, tree)
    for seed in range(first, last + 1)
    for pace in (1, 3)
    for label, tree in (("before", before), ("after", after))
]
start = time.monotonic()
running = []
logs = work / "logs"
logs.mkdir(exist_ok=True)
while tasks or running:
    running = [(t, pr) for t, pr in running if pr.poll() is None]
    while tasks and len(running) < jobs:
        seed = tasks[0][0]
        if time.monotonic() - start > budget and all(t[0] != seed for t, _ in running):
            print("start budget reached; not starting seed", seed, flush=True)
            tasks = []
            break
        if time.monotonic() - start > budget:
            # finish the current seed's remaining games only
            if not any(t[0] == seed for t, _ in running):
                tasks = []
                break
        task = tasks.pop(0)
        seed, pace, label, tree = task
        log = (logs / f"{label}-p{pace}-s{seed}.log").open("w")
        pr = subprocess.Popen(
            [
                "/usr/bin/python3",
                str(HERE / "measure.py"),
                str(tree),
                label,
                str(seed),
                str(pace),
                str(results),
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        running.append((task, pr))
        print(f"{time.monotonic() - start:7.0f}s start", task[:3], flush=True)
    time.sleep(2)
print(f"done in {time.monotonic() - start:.0f}s", flush=True)
