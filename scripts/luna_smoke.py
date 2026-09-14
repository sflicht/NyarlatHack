"""Explicit opt-in live Luna decision followed by real-game acceptance.
Run with the installed Hermes interpreter. Does not create an agent/tool loop.
"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests/chaos"))


def main():
    from gameplay_support import Game
    from chaos.director import State, Mailbox
    from chaos.oauth import OAuthBackend, MODEL, PROVIDER

    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-live", action="store_true", required=True)
    args = parser.parse_args()
    if not args.execute_live:
        return 2
    evidence = Path.home() / ".local/share/nyarlathack/milestone2"
    evidence.mkdir(parents=True, exist_ok=True)
    clock = evidence / "clock.so"
    subprocess.run(
        [
            "cc",
            "-shared",
            "-fPIC",
            str(ROOT / "tests/chaos/replay_clock.c"),
            "-ldl",
            "-o",
            str(clock),
        ],
        check=True,
    )
    runroot = Path(tempfile.mkdtemp(prefix="luna-smoke-", dir=evidence))
    game = Game(ROOT / "dnethackdir", clock, wizard=True, root=runroot)
    try:
        game.start()
        game.send("r")
        game.more(game.send("\x1b"))
        state = State()
        for event in game.events():
            state.ingest(event)
        request = OAuthBackend(evidence / "model-ledger.json", timeout=60).choose(
            state, state.last_id + 1, state.safe + 1
        )
        assert request is not None
        with Mailbox(game.run) as box:
            box.submit(request, state)
        game.sanity(60)
        accepted = [
            event
            for event in game.events()
            if event["event"] == "ack"
            and event["status"] == "accepted"
            and event["id"] == request["id"]
        ]
        assert len(accepted) == 1, game.events()
        assert accepted[0]["mutation"] == request["mutation"]
        assert game.quit() == 0
        receipt = {
            "requested_model": MODEL,
            "provider": PROVIDER,
            "route": "ChatGPT OAuth",
            "request": request,
            "accepted_ack": accepted[0],
            "game_exit": 0,
            "artifacts": str(runroot),
            "live_model": True,
            "cash_charge": "not reported by subscription transport",
        }
        (evidence / "luna-smoke.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt, indent=2))
    finally:
        game.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            "Live smoke stopped: "
            + type(exc).__name__
            + "; no provider fallback or automatic retry",
            file=sys.stderr,
        )
        raise SystemExit(2)
