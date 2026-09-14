"""Generate one candidate with the authorized subscription model; never execute here."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from chaos.oauth import OAuthBackend, MODEL, PROVIDER
    from chaos.director import EventReader, State
    from chaos.protocol import strict_json

    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute-live", action="store_true", required=True)
    args = parser.parse_args()
    state = State()
    reader = EventReader(args.events)
    events = reader.read()
    if reader.tail or not any(e["event"] == "backtrack" for e in events):
        raise ValueError("actual backtracking evidence required")
    for event in events:
        state.ingest(event)
    prompt = (ROOT / "chaos/prompts/haunting.txt").read_text()
    evidence = Path.home() / ".local/share/nyarlathack/milestone2"
    args.output.mkdir(parents=True, mode=0o700, exist_ok=False)
    response = OAuthBackend(evidence / "model-ledger.json").generate(
        prompt, state.summary()
    )
    data = strict_json(response.encode(), 8192)
    if set(data) != {"source"} or not isinstance(data["source"], str):
        raise ValueError("source-only object required")
    source = data["source"].encode()
    if not 0 < len(source) <= 4096 or b"\0" in source:
        raise ValueError("source bounds violated")
    path = args.output / "haunting.lua"
    path.write_bytes(source)
    path.chmod(0o600)
    receipt = {
        "requested_model": MODEL,
        "provider": PROVIDER,
        "live_model": True,
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "events_sha256": hashlib.sha256(args.events.read_bytes()).hexdigest(),
        "source_file": str(path),
        "validation": "candidate only; engine shadow validation still required",
    }
    (args.output / "generation.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(
            "Generation stopped: "
            + type(exc).__name__
            + "; no fallback or automatic retry",
            file=sys.stderr,
        )
        raise SystemExit(2)
