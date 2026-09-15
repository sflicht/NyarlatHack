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


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's normal message echoes untrusted tokens/paths and controls.
        self.exit(2, "chaos: failed closed (ValueError); use --help for syntax\n")


def _curio_parser(sub):
    p = sub.add_parser(
        "curio",
        help="offline saved-curio evidence; never inference or native admission",
    )
    commands = p.add_subparsers(dest="curio_command", required=True)
    for op in ("install", "verify"):
        p = commands.add_parser(
            op,
            help="exclusive pre-game installation"
            if op == "install"
            else "read-only exact installation verification; no repair",
        )
        p.add_argument("--run-dir", type=Path, required=True)
        source = p.add_mutually_exclusive_group(required=True)
        source.add_argument(
            "--source", type=Path, help="saved 0600 file in owned 0700 parent"
        )
        source.add_argument(
            "--bundle-root",
            type=Path,
            help="private stored bundles; requires --candidate-id",
        )
        p.add_argument(
            "--candidate-id", help="exact lowercase source SHA-256; bundle mode only"
        )
    p = commands.add_parser(
        "continuity", help="explicit offline journal operations; no automatic repair"
    )
    operations = p.add_subparsers(dest="continuity_command", required=True)
    for op in ("init", "register", "bind", "observe", "notes"):
        p = operations.add_parser(
            op,
            help={
                "init": "initialize an EXISTING EMPTY owned 0700 journal root",
                "register": "register a verified bundle, not a live authorship claim",
                "bind": "bind a registered bundle to an exact installation",
                "observe": "checkpoint stable offline native evidence; never infer admission from installation",
                "notes": "read-only validated editorial notes; quoted fallible context",
            }[op],
        )
        p.add_argument("--journal-root", type=Path, required=True)
        if op in ("register", "bind", "observe"):
            p.add_argument("--candidate-id", required=True)
        if op == "register":
            p.add_argument("--bundle-root", type=Path, required=True)
        if op == "bind":
            p.add_argument("--run-dir", type=Path, required=True)
        if op == "notes":
            p.add_argument("--limit", type=int, choices=range(7), default=6)


def _curio_command(args):
    if args.curio_command in ("install", "verify"):
        from .curio_store import install_saved_source

        return install_saved_source(
            args.run_dir,
            source_file=args.source,
            bundle_root=args.bundle_root,
            candidate_id=args.candidate_id,
            mode="fresh" if args.curio_command == "install" else "verify",
        )
    from . import curio_continuity as continuity

    op = args.continuity_command
    if op == "notes":
        return continuity.prior_notes(args.journal_root, limit=args.limit)
    if op == "init":
        continuity.create_journal(args.journal_root)
    elif op == "register":
        continuity.register(args.journal_root, args.bundle_root, args.candidate_id)
    elif op == "bind":
        continuity.bind_run(args.journal_root, args.candidate_id, args.run_dir)
    else:
        continuity.observe(args.journal_root, args.candidate_id)
    # Operation acknowledgement only, not an invented lifecycle status.
    return {"operation": op, "verified": True}


def main(argv=None):
    parser = _Parser(
        description="The Crawling Chaos — bounded engine-protocol v1 director"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    from .launcher import add_parser

    add_parser(sub)
    _curio_parser(sub)
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
        if args.command == "curio":
            print(json.dumps(_curio_command(args), sort_keys=True, ensure_ascii=True))
            return 0
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
