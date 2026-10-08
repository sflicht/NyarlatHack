"""Pets never attack the echo hound: how long does it live in real play?

usage: measure.py TREE LABEL INDEX RESULTS

One real nonwizard `python3 -m chaos play --ordinary` game (#198 defaults:
hound and next-use on) from the git export TREE (built there with
`make -j2 install CHAOS=1`), on a fresh random map, driven by the #190
screen driver (`tests/chaos/haunt_explorer.Player`), exactly as #201's
`baseline.py`: pace the start room until the trial is decided (at most 40
keys); if the hound is admitted, keep pacing until the haunt expires or 90
keys pass. Appends one JSON line to RESULTS.

No model: the game is launched with no NYARLATHACK_AUTHOR_* settings, so the
hound is footsteps.lua and there is no curio or hound lane. The script
refuses to run if any author setting is present, and records whether a hound
lane file appeared (it must not).
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

tree, label, index, results = (
    Path(sys.argv[1]),
    sys.argv[2],
    int(sys.argv[3]),
    Path(sys.argv[4]),
)
if any(k.startswith("NYARLATHACK_AUTHOR") for k in os.environ):
    sys.exit(
        "refusing: an author setting is present; this measurement makes no model calls"
    )
sys.path.insert(0, str(tree / "tests/chaos"))
from gameplay_support import Game  # noqa: E402
from haunt_explorer import Player  # noqa: E402

work = Path(os.environ["TMPDIR"]) / "games" / label
work.mkdir(parents=True, exist_ok=True)
empty = work / "noclock.so"
if not empty.exists():
    (work / "noclock.c").write_text("int nyarl_noclock;\n")
    subprocess.run(
        ["cc", "-shared", "-fPIC", str(work / "noclock.c"), "-o", str(empty)],
        check=True,
    )
TURN = re.compile(r"T:(\d+)")
KILL = re.compile(
    r"(You kill|You destroy|[Tt]he [a-z ]+? (?:kills|destroys)|[A-Z][a-z]+ (?:kills|destroys)) (?:the )?echo hound"
)


def snap(p):
    text = p.screen.text()
    rows = text.splitlines()
    m = TURN.search(text)
    ds = [
        (x, y)
        for y, row in enumerate(rows[1:22], 1)
        for x, ch in enumerate(row)
        if ch == "d"
    ]
    return {
        "turn": int(m.group(1)) if m else None,
        "msg": rows[0].rstrip() if rows else "",
        "me": p.me(),
        "d": ds,
    }


root = Path(tempfile.mkdtemp(prefix=f"g{index}-", dir=work))
game = Game(
    tree / "dnethackdir",
    empty,
    root=root,
    ordinary=True,
    launcher_fresh=True,
    launcher_options=["--ordinary", "--max-runtime", "300"],
)
rec = {"tree": label, "i": index, "root": str(root)}
trace = []
try:
    game.start()
    p = Player(game)
    rec["start_squares"] = len(p.start_room)

    def ev(kind):
        return [e for e in game.events() if e["event"] == kind]

    def decided():
        return any(
            e["detail"] in ("accepted", "rejected", "shadow_failed", "spawn_failed")
            for e in ev("haunting")
        )

    def watch():
        trace.append(snap(p))
        return decided()

    p.pace(watch, limit=40)
    rec["haunting"] = [e["detail"] for e in ev("haunting")]
    acc = [e for e in ev("haunting") if e["detail"] == "accepted"]
    if acc:
        rec["accepted_turn"] = acc[0]["turn"]
        trace.append(dict(snap(p), mark="accepted"))
        start = len(bytes(game.raw))

        def done():
            trace.append(snap(p))
            text = bytes(game.raw)[start:].decode("utf-8", "replace")
            details = [e["detail"] for e in ev("haunting")]
            return (
                "expired" in details or "killed" in details or bool(KILL.search(text))
            )

        p.pace(done, limit=90)
        text = bytes(game.raw)[start:].decode("utf-8", "replace")
        k = KILL.search(text)
        rec["kill"] = k.group(0) if k else None
        rec["steps"] = [e["turn"] for e in ev("haunt_step")]
        details = [e["detail"] for e in ev("haunting")]
        rec["expired"] = "expired" in details
        rec["killed_event"] = [
            e["turn"] for e in ev("haunting") if e["detail"] == "killed"
        ]
        rec["hound_hits_you"] = len(re.findall(r"echo hound (?:bites|hits)", text))
        rec["you_hit_hound"] = len(
            re.findall(r"You (?:hit|smite|bite) (?:the )?echo hound", text)
        )
        rec["pet_hits_hound"] = len(
            re.findall(
                r"[Tt]he [a-z ]+? (?:bites|hits|kicks) (?:the )?echo hound", text
            )
        )
        rec["hound_hits_pet"] = len(
            re.findall(
                r"echo hound (?:bites|hits) (?:the |your )?(?:little dog|dog|large dog)",
                text,
            )
        )
        rec["noises"] = len(re.findall(r"You hear some noises", text))
    d = game.run / "dreamlands.json"
    rec["report"] = json.loads(d.read_text()) if d.exists() else None
    rec["hound_lane"] = (game.run / "haunt-lane.json").exists()
    c = game.run / "ordinary-choice.json"
    rec["choice"] = json.loads(c.read_text()) if c.exists() else None
except Exception as e:  # keep going; record the failure
    rec["error"] = repr(e)[:500]
finally:
    rec["trace"] = trace
    try:
        game.close()
    except Exception:
        pass
with results.open("a") as res:
    res.write(json.dumps(rec) + "\n")
print(
    label,
    index,
    rec.get("haunting"),
    rec.get("kill"),
    len(rec.get("steps", [])),
    rec.get("error"),
    flush=True,
)
