"""Explicit pre-game authoring interface; no implicit allowance, install or retry.

Without --execute-live, stop before importing the service or touching resources.
--inspect is separately read-only. A successful receipt is evidence binding, not
native admission or live-authorship proof (the service also supports fake clients).
NGPL; see dat/license.
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(
            2, "curio generation: failed closed (ValueError); use --help for syntax\n"
        )


def main(argv=None):
    parser = _Parser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--execute-live",
        action="store_true",
        help="explicit future live opt-in; one attempt, never a fallback or retry",
    )
    mode.add_argument(
        "--inspect",
        action="store_true",
        help="verify complete existing generation read-only",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="generation: must not exist; inspect: existing complete evidence",
    )
    parser.add_argument(
        "--event-file", type=Path, help="complete stable offline native event history"
    )
    parser.add_argument("--bundle-root", type=Path, help="existing private bundle root")
    parser.add_argument(
        "--journal-root",
        type=Path,
        help="existing explicitly initialized private journal",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        help="REQUIRED retained SAME shared authorization ledger; no creation/reset/migration. "
        "Fixed curio limit 2 inside global 20/$1; pinned gpt-5.6-luna/openai-codex",
    )
    parser.add_argument(
        "--literary-layer",
        choices=(
            "poe",
            "wilde",
            "carroll",
            "mackay",
            "abbott",
            "chambers",
            "gilman",
            "hodgson",
        ),
    )
    parser.add_argument(
        "--role", help="optional host assertion, not inferred from event extras"
    )
    parser.add_argument(
        "--race", help="optional host assertion, not inferred from event extras"
    )
    args = parser.parse_args(argv)
    generation_args = (
        args.event_file,
        args.bundle_root,
        args.journal_root,
        args.ledger,
    )
    if args.inspect:
        if any(
            v is not None
            for v in (*generation_args, args.literary_layer, args.role, args.race)
        ):
            parser.error("inspect takes only output-directory")
    elif any(v is None for v in generation_args):
        parser.error("generation requires all resource paths including retained ledger")
    try:
        # Only this opt-in/inspect branch may import the reviewed service. Its
        # preflight validates all resources and retained ledger before factory.
        from chaos.curio_generation import generate_curio, read_generation

        if args.inspect:
            receipt = read_generation(args.output_directory)
        else:
            receipt = generate_curio(
                event_file=args.event_file,
                output_directory=args.output_directory,
                bundle_root=args.bundle_root,
                journal_root=args.journal_root,
                ledger=args.ledger,
                literary_layer=args.literary_layer or "poe",
                role=args.role,
                race=args.race,
            )
        print(json.dumps(receipt, sort_keys=True, ensure_ascii=True))
        return 0
    except Exception as exc:
        print(
            "curio generation: failed closed ("
            + type(exc).__name__
            + "); no fallback or automatic retry",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
