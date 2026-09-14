"""Command line; errors never echo untrusted model/event strings."""

import argparse
import json
import os
from pathlib import Path
import signal
import sys

from .director import (
    DEFAULT_BYTES,
    DEFAULT_EVENTS,
    RandomBackend,
    ScheduleBackend,
    load_replay,
    run,
)
from .protocol import parse_request


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="The Crawling Chaos — bounded engine-protocol v1 director"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    from .launcher import add_parser

    add_parser(sub)
    installer = sub.add_parser(
        "haunt", help="install one Lua candidate; game validates it"
    )
    installer.add_argument("--run-dir", required=True)
    installer.add_argument("--source", type=Path, required=True)
    for name in ("pack", "random", "replay", "model", "oauth"):
        p = sub.add_parser(name)
        p.add_argument(
            "--run-dir", required=True, help="existing owned mode-0700 run directory"
        )
        p.add_argument(
            "--max-runtime", type=float, default=300, help="seconds, default 300"
        )
        p.add_argument("--poll", type=float, default=0.25, help="seconds, default .25")
        p.add_argument("--max-events", type=int, default=DEFAULT_EVENTS)
        p.add_argument("--max-bytes", type=int, default=DEFAULT_BYTES)
        p.add_argument("--max-submissions", type=int, default=12)
        if name == "pack":
            p.add_argument("name", choices=("ambient", "silence", "ward", "hunger"))
            p.add_argument("--id", type=int, default=1)
            p.add_argument("--at", type=int, default=1)
            p.add_argument(
                "--install-only",
                action="store_true",
                help="publish once; does NOT prove acceptance",
            )
        if name == "random":
            p.add_argument("--seed", type=int, default=0)
        if name == "oauth":
            p.add_argument("--ledger", type=Path, required=True)
        if name in ("random", "model", "oauth"):
            p.add_argument(
                "--ordinary-food",
                action="store_true",
                help="player affirms ordinary food metabolism; enables hunger proposals",
            )
        if name == "replay":
            p.add_argument("journal", type=Path)
            p.add_argument(
                "--accepted-events",
                type=Path,
                required=True,
                help="source-run accepted ACK evidence",
            )
        if name == "model":
            p.add_argument(
                "--endpoint",
                required=True,
                help="explicit full chat-completions HTTPS URL",
            )
            p.add_argument("--model", required=True)
            p.add_argument(
                "--api-key-env",
                required=True,
                help="environment variable NAME, not a key",
            )
            p.add_argument("--timeout", type=float, default=10)
            p.add_argument("--max-calls", type=int, default=4)
            p.add_argument("--max-context", type=int, default=8192)
            p.add_argument("--max-response", type=int, default=16384)
            p.add_argument(
                "--allow-local-http",
                action="store_true",
                help="explicit local fixture only",
            )
    args = parser.parse_args(argv)
    try:
        if args.command == "play":
            from .launcher import play

            return play(args)
        if args.command == "haunt":
            from .haunt import install

            print(json.dumps(install(args.source, args.run_dir)))
            return 0
        if args.command == "pack":
            raw = (Path(__file__).parent / "packs" / f"{args.name}.json").read_bytes()
            r = parse_request(raw)
            r.update(id=args.id, at=args.at)
            backend = ScheduleBackend([r])
        elif args.command == "random":
            backend = RandomBackend(args.seed, args.ordinary_food)
        elif args.command == "replay":
            backend = ScheduleBackend(load_replay(args.journal, args.accepted_events))
        elif args.command == "oauth":
            from .oauth import OAuthBackend

            backend = OAuthBackend(args.ledger, ordinary_food=args.ordinary_food)
        else:
            from .model import ModelBackend

            backend = ModelBackend(
                args.endpoint,
                args.model,
                args.api_key_env,
                timeout=args.timeout,
                max_calls=args.max_calls,
                max_context=args.max_context,
                max_response=args.max_response,
                allow_local_http=args.allow_local_http,
                ordinary_food=args.ordinary_food,
            )
        result = run(
            args.run_dir,
            backend,
            max_runtime=args.max_runtime,
            poll=args.poll,
            max_events=args.max_events,
            max_bytes=args.max_bytes,
            max_submissions=args.max_submissions,
            install_only=getattr(args, "install_only", False),
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as exc:
        # Static error class only: raw paths, model text, HTTP bodies may contain controls/secrets.
        print(
            "chaos: failed closed ("
            + type(exc).__name__
            + "); check private run state and documented limits",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    status = main()
    if status < 0:
        # Preserve the child's signal status, but only after supervisor cleanup.
        if -status != signal.SIGKILL:
            signal.signal(-status, signal.SIG_DFL)
        os.kill(os.getpid(), -status)
    sys.exit(status)
