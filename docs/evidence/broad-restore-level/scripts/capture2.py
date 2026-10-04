"""Real nonwizard ordinary game: save on the first descent past a live broad
program's admission level, restore, play on.

`python3 -m chaos play --ordinary` (bard-default-path launcher: ordinary
defaults, hound and next-use on), driven by the sweep bot's public keystrokes
(whistle, #pray, explore, descend). The only change from the sweep bot is WHEN
it saves: not at turn 700 but on the first status line whose Dlvl is deeper
than the admission level of a program whose journal is still live. The harness
reads run files only to choose that moment; it never alters game state. No
clock shim (an empty preload stands in: unseeded games), no wizard mode, no
model call. Every attempt is recorded.
Usage: capture2.py <export-root> <out-dir> <attempt-number>
"""

import json
import os
import sys
from pathlib import Path

root, out, n = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
sys.path[:0] = [str(root / "tests" / "chaos"), str(root)]
import sweep_player  # noqa: E402

LEVEL_BASE = 100000  # level_token = LEVEL_BASE + dlvl on the main dungeon


def live_programs(run):
    live = []
    for f in sorted(run.glob("next_use-journal*.jsonl")):
        rows = [json.loads(line)["payload"] for line in f.read_text().splitlines()]
        head = rows[0]["data"]["snapshot"]
        if not head.get("broad_uses"):
            continue
        ended = any(r.get("kind") == "end" for r in rows) or any(
            (r.get("data", {}).get("post") or {}).get("phase") == 4
            for r in rows
            if r.get("kind") == "transition"
        )
        if not ended:
            live.append((f.name, head["level_token"] - LEVEL_BASE, head))
    return live


class Driver(sweep_player.Player):
    def __init__(self, *a):
        super().__init__(*a)
        self.params = dict(
            self.params,
            save_restore_turn=10**9,
            min_turns_per_level=int(os.environ.get("CAPTURE_MIN_TURNS", "300")),
        )
        self.cross = None

    def step(self):
        s = sweep_player.status(self.screen)
        if s and not self.saved:
            for name, admitted_dlvl, head in live_programs(self.game.run):
                if s["dlvl"] > admitted_dlvl:
                    self.cross = {
                        "journal": name,
                        "admitted_dlvl": admitted_dlvl,
                        "saved_dlvl": s["dlvl"],
                        "saved_turn": s["turn"],
                        "snapshot": head,
                    }
                    return "save_restore"
        return super().step()


out.mkdir(parents=True, exist_ok=True)
case = out / f"attempt{os.environ.get('CAPTURE_TAG', '2')}-{n:02d}"
player = Driver(
    root / "dnethackdir",
    Path(os.environ["CAPTURE_PRELOAD"]),
    case,
    n,
    "bard-default-path",
    "baseline-v2",
    None,
)
player.play()
sessions = [
    (e.get("turn"), e.get("detail"))
    for e in player.game.events()
    if e.get("event") == "session"
]
final = sweep_player.status(player.screen) or {}
result = {
    "attempt": n,
    "outcome": player.outcome,
    "error": getattr(player, "error", None),
    "saved": player.saved,
    "cross_level_save": player.cross,
    "restore_detail": player.restore_detail,
    "sessions": sessions,
    "final_status": {k: final.get(k) for k in ("turn", "dlvl")},
}
(case / "result.json").write_text(json.dumps(result, indent=1, default=str))
print(json.dumps(result, default=str))
