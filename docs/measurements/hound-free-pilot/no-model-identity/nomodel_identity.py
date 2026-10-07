"""No-model byte identity: one ordinary nonwizard game through the launcher
(`chaos play --ordinary --no-next-use`, no author provider configured) under
the deterministic replay clock, with a fixed key tape that backtracks so the
footsteps hound is looked at, trialled and admitted.

Usage: nomodel_identity.py <tree> <out>   (run once per tree; diff the outs)
<tree> is a built checkout (its own chaos/ package and dnethackdir/).
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

tree = Path(sys.argv[1]).resolve()
out = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(tree / "tests/chaos"))
sys.path.insert(0, str(tree))
for name in ("NYARLATHACK_AUTHOR_PROVIDER", "NYARLATHACK_AUTHOR_MODEL"):
    os.environ.pop(name, None)

from gameplay_support import ROOT, Game  # noqa: E402
from haunt_explorer import Player  # noqa: E402

assert ROOT == tree, (ROOT, tree)
out.mkdir(parents=True)
clock = out / "clock.so"
subprocess.run(
    [
        "cc",
        "-shared",
        "-fPIC",
        str(tree / "tests/chaos/replay_clock.c"),
        "-ldl",
        "-o",
        str(clock),
    ],
    check=True,
)
game = Game(
    tree / "dnethackdir",
    clock,
    root=out / "game",
    ordinary=True,
    launcher_fresh=True,
    launcher_options=["--ordinary", "--no-next-use", "--max-runtime", "300"],
)
try:
    game.start()
    installed = (game.run / "haunting.lua").read_bytes()
    # The #165 ordinary-haunt route: leave the 4x3 start room, then pace in
    # the larger room until the engine has decided the trial.
    player = Player(game)
    player.leave()
    player.pace(
        lambda: any(
            e["event"] == "haunting" and e["detail"] in ("accepted", "rejected")
            for e in game.events()
        )
    )
    game.wait_turns(6)
    status = game.quit()
finally:
    game.close()


def sha(p):
    return (
        hashlib.sha256(Path(p).read_bytes()).hexdigest() if Path(p).exists() else None
    )


haunting = [e["detail"] for e in game.events() if e["event"] == "haunting"]
result = dict(
    quit=status,
    installed_sha256=hashlib.sha256(installed).hexdigest(),
    haunting=haunting,
    backtracks=sum(e["event"] == "backtrack" for e in game.events()),
    events_sha256=sha(game.run / "events.jsonl"),
    raw_sha256=hashlib.sha256(
        bytes(game.raw).replace(str(out).encode(), b"<OUT>")
    ).hexdigest(),
    inputs_sha256=hashlib.sha256(json.dumps(game.inputs).encode()).hexdigest(),
    xlogfile_sha256=sha(game.game / "xlogfile"),
    haunting_used_sha256=sha(game.run / "haunting-used.lua"),
    dreamlands_sha256=sha(game.run / "dreamlands.json"),
    run_files=sorted(p.name for p in game.run.iterdir()),
)
(out / "result.json").write_text(json.dumps(result, indent=1) + "\n")
(out / "raw.bin").write_bytes(bytes(game.raw))
print(json.dumps(result, indent=1))
