"""Restore the save file that main's build preserved (bard seed 10), with a
chosen binary, then play on a few turns. Usage:
  restore_preserved.py <export-root> <preserved-case-dir> <work-copy> <label>
Runs from <export-root> so tests.chaos and chaos import from that revision.
"""

import json
import re
import shutil
import sys
from pathlib import Path

root, case, work = (Path(a) for a in sys.argv[1:4])
label = sys.argv[4]
sys.path[:0] = [str(root / "tests" / "chaos"), str(root)]
import sweep_player  # noqa: E402
from gameplay_support import Game  # noqa: E402

if work.exists():
    shutil.rmtree(work)
shutil.copytree(
    case, work, symlinks=True, ignore=shutil.ignore_patterns("terminal.raw")
)
clock = case.parent / "sweep_clock.so"
gdir = root / "dnethackdir"
for name in ("dnethack", "nhdat"):  # the binary under test, same nhdat
    (work / "game" / name).unlink(missing_ok=True)
    shutil.copy2(gdir / name, work / "game" / name)
save_before = sorted(p.name for p in (work / "game" / "save").iterdir())
game = Game(
    gdir,
    clock,
    observe=True,
    ordinary=True,
    launcher_fresh=False,
    launcher_options=sweep_player.START_LAUNCHER.get("bard", sweep_player.LAUNCHER),
    root=work,
)
module, options = sweep_player._with_options(sweep_player.START_OPTIONS["bard"])
saved = module.OPTIONS
module.OPTIONS = options
try:
    text = game.start()
finally:
    module.OPTIONS = saved
plain = re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", bytes(game.raw)).decode("latin1")
refused = "Incompatible CHAOS save state" in plain
result = {"label": label, "save_before": save_before, "refused": refused}
if not refused and game.pid is not None:
    for _ in range(10):
        text = game.send("s")  # search: ten turns of play after the restore
        if b"--More--" in text:
            game.send(" ")
    plain = re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]", b"", bytes(game.raw)).decode("latin1")
    turns = [int(t) for t in re.findall(r"T:(\d+)", plain)]
    dl = re.findall(r"Dlvl:(\d+)", plain)
    result.update(
        turn_last=turns[-1] if turns else None, dlvl_last=dl[-1] if dl else None
    )
    result["save_exit"] = game.save()
else:
    result["exitcode"] = game.exitcode
sessions = [e.get("detail") for e in game.events() if e.get("event") == "session"]
result["sessions"] = sessions
(work / "terminal.raw").write_bytes(bytes(game.raw))
print(json.dumps(result))
