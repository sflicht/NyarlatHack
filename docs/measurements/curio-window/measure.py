"""One paced, no-model curio-window game (see PREREGISTERED.md).

usage: measure.py TREE LABEL SEED PACE RESULTS

TREE is a git-archive export built with `make -j2 install CHAOS=1`. The driver
classes are imported from TREE/tests/chaos, which is byte-identical in both
trees, so the harness's launcher (`-m chaos` with PYTHONPATH=TREE) is the tree's
own. sys.executable points at a wrapper that runs fake_chaos.py (from this
directory) in place of `-m chaos`: the curio author is fake, and nothing calls a
model. Appends one JSON line to RESULTS.
"""

import json
import os
from pathlib import Path
import random
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
tree, label, seed, pace, results = (
    Path(sys.argv[1]).resolve(),
    sys.argv[2],
    int(sys.argv[3]),
    float(sys.argv[4]),
    Path(sys.argv[5]),
)
if any(k.startswith("NYARLATHACK_AUTHOR") for k in os.environ):
    sys.exit(
        "refusing: an author setting is present; this measurement makes no model calls"
    )
ROOT = HERE.parents[2]  # the export carrying this script (the "after" tree)
RAW = (
    ROOT
    / "docs/evidence/curio-live-capture/attempt-013/run/curio-evidence/raw-response.txt"
)
NAME = b"glass reed locket"
MAX_WALL_S = 1800
AFTER_PLACEMENT_TURNS = 150


def latencies():
    out = []
    for run in ("pilot", "smoke"):
        path = (
            ROOT / "docs/measurements/model-authoring-pilot/runs" / run / "ledger.jsonl"
        )
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row.get("surface") == "curio_history" and row.get("latency_s"):
                out.append(float(row["latency_s"]))
    if len(out) != 33:
        raise SystemExit(
            f"expected 33 committed curio_history latencies, found {len(out)}"
        )
    return sorted(out)


DELAY = random.Random(f"curio-window-v1:{seed}").choice(latencies())

sys.path[:0] = [str(tree), str(tree / "tests/chaos")]  # the tree's own chaos/
from curio_capture_player import CapturePlayer  # noqa: E402
from sweep_screen import status  # noqa: E402

work = Path(os.environ["TMPDIR"]) / "games"
work.mkdir(parents=True, exist_ok=True)
wrapper = work / f"fakepy-{os.getpid()}"
wrapper.write_text(
    "#!/bin/sh\nexec /usr/bin/python3 " + str(HERE / "fake_chaos.py") + ' "$@"\n'
)
wrapper.chmod(0o700)
sys.executable = str(wrapper)
clock = Path(os.environ["CURIO_WINDOW_CLOCK"])
os.environ["NYARLATHACK_SWEEP_SEED"] = str(seed)
os.environ["CURIO_WINDOW_DELAY_S"] = repr(DELAY)
os.environ["CURIO_WINDOW_RAW"] = str(RAW)


class WindowPlayer(CapturePlayer):
    """The #247 curio-capture player, paced in wall time, that never climbs
    back from a branch staircase (so it enters the Mines when the Mines
    staircase is the first '>' it takes)."""

    def __init__(self, *a):
        super().__init__(*a)
        self.params = dict(
            self.params, max_dlvl=7, max_turns=1500, save_restore_turn=10**9
        )
        self.branch = "main"
        self.mines_entry = None
        self.t0 = None
        self.curio = []  # engine curio events with public turn/depth/branch
        self.lane = []  # curio lane steps with public turn/depth/branch
        self.final = None
        self.placed_at = None
        self.ev_off = 0

    def _start(self):
        r = super()._start()
        self.t0 = time.monotonic()
        return r

    def where(self):
        s = status(self.screen)
        return (None, None) if s is None else (s["turn"], s["dlvl"])

    def observe(self):
        turn, dlvl = self.where()
        wall = round(time.monotonic() - self.t0, 1)
        path = self.game.run / "events.jsonl"
        if path.exists():
            data = path.read_bytes()
            new, self.ev_off = data[self.ev_off :], len(data)
            for line in new.splitlines():
                e = json.loads(line)
                if e.get("event") != "curio":
                    continue
                row = dict(
                    detail=e.get("detail"),
                    event_turn=e.get("turn"),
                    turn=turn,
                    dlvl=dlvl,
                    branch=self.branch,
                    wall=wall,
                )
                self.curio.append(row)
                if row["detail"] == "placed" and self.placed_at is None:
                    self.placed_at = row
                if row["detail"] in ("expired", "rejected", "placement_failed"):
                    self.final = self.final or "curio_" + row["detail"]
        lane = self.game.run / "curio-lane.json"
        if lane.exists():
            try:
                record = json.loads(lane.read_text())
            except ValueError:
                record = None
            if record and (not self.lane or self.lane[-1]["step"] != record["step"]):
                self.lane.append(
                    dict(
                        step=record["step"],
                        outcome=record.get("outcome"),
                        turn=turn,
                        dlvl=dlvl,
                        branch=self.branch,
                        wall=wall,
                    )
                )
                if record["step"] in ("failed", "no_model"):
                    self.final = self.final or "lane_" + record["step"]

    def window_stop(self):
        turn, dlvl = self.where()
        if time.monotonic() - self.t0 > MAX_WALL_S:
            return "wall_cap"
        if self.final:
            return self.final
        p = self.placed_at
        if p is not None and turn is not None:
            if turn >= (p["turn"] or 0) + AFTER_PLACEMENT_TURNS:
                return "after_placement"
            if dlvl != p["dlvl"] or self.branch != p["branch"]:
                return "left_placement_level"
        return None

    def pace(self):
        turn, _ = self.where()
        if turn is None:
            return
        wait = self.t0 + turn / pace - time.monotonic()
        if wait > 0:
            time.sleep(wait)

    def step(self):
        self.observe()
        reason = self.window_stop()
        if reason:
            return reason
        result = super().step()
        self.pace()
        return result

    def descend(self, level, hero):
        """Take '>'. On arrival from the main dungeon, ask the game what is
        underfoot (':' takes no game time); "branch staircase up" means this
        is the first Mines level. Never climb back."""
        result = self.act(">")
        if result:
            return result
        s = status(self.screen)
        if s is None or s["dlvl"] != level + 1 or self.branch != "main":
            return None
        here = self.look_here()
        if b"staircase up" not in here:
            # Fell beside the stairs: wait briefly for a visible '<', walk to it.
            for _ in range(3):
                if self.find("<"):
                    break
                result = self.act("s")
                if result:
                    return result
            hero_now = self.hero()
            ups = sorted(
                self.find("<"),
                key=lambda t: (
                    abs(t[0] - hero_now[0]) + abs(t[1] - hero_now[1]) if hero_now else 0
                ),
            )
            if hero_now and ups and ups[0] != hero_now:
                result = self.travel(ups[0])
                if result:
                    return result
            here = self.look_here()
        if b"branch staircase up" in here:
            self.branch = "mines"
            self.mines_entry = self.where()
        return None


root = Path(tempfile.mkdtemp(prefix=f"{label}-p{pace:g}-s{seed}-", dir=work))
rec = dict(tree=label, seed=seed, pace=pace, delay_s=DELAY, root=str(root))
started = time.monotonic()
p = None
try:
    p = WindowPlayer(
        tree / "dnethackdir",
        clock,
        root,
        seed,
        "bard-default-path",
        "curio-capture-v1",
        None,
    )
    p.game.launcher_options = list(p.game.launcher_options) + [
        "--author-provider",
        "openai-codex",
        "--author-model",
        "fake-locket-247",
        "--curio-validator",
        str(tree / "dnethackdir" / "curio-validator.so"),
    ]
    p.play()
    rec["outcome"] = p.outcome
    rec["error"] = getattr(p, "error", None)
except Exception as exc:  # recorded, never retried
    rec["outcome"] = "harness_error"
    rec["error"] = f"{type(exc).__name__}: {exc}"[:300]
finally:
    if p is not None:
        try:
            p.observe()
        except Exception:
            pass
        s = status(p.screen) or {}
        rec.update(
            final_turn=s.get("turn"),
            final_dlvl=s.get("dlvl"),
            branch=p.branch,
            mines_entry=p.mines_entry,
            dlvl_timeline=p.dlvl_timeline,
            curio=p.curio,
            lane=p.lane,
            name_on_screen=NAME in bytes(p.game.raw),
            commands=p.commands,
            wall_s=round(time.monotonic() - started, 1),
        )
        if p.t0 is not None and s.get("turn"):
            rec["achieved_pace"] = round(
                s["turn"] / max(1e-9, time.monotonic() - p.t0), 3
            )
        receipt = p.game.run / "curio-evidence" / "receipt.json"
        if receipt.exists():
            r = json.loads(receipt.read_text())
            rec["receipt"] = {
                k: r.get(k)
                for k in (
                    "provider",
                    "model",
                    "outcome",
                    "latency_s",
                    "error_type",
                    "transport",
                )
            }
        ledgers = [
            str(q.relative_to(root)) for q in root.rglob("*ledger*") if q.is_file()
        ]
        rec["ledger_files"] = ledgers
with results.open("a") as out:
    out.write(json.dumps(rec) + "\n")
print(
    label,
    pace,
    seed,
    rec.get("outcome"),
    [c["detail"] for c in rec.get("curio", [])],
    rec.get("error"),
    flush=True,
)
