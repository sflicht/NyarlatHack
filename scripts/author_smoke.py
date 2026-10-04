"""One explicit, ledgered model-authoring smoke call; never a game, never a retry.

Without --execute-live, stop before importing a transport. Provider and model
come from --author-provider / --author-model (or NYARLATHACK_AUTHOR_PROVIDER /
NYARLATHACK_AUTHOR_MODEL); only the xAI providers are supported here. The
receipt printed on success names provider, model, route and the ledger row; it
holds no credential. NGPL; see dat/license.

For xai-oauth, run under Hermes's own runtime: a launcher that imports
``hermes_bootstrap`` from the Hermes checkout first, then runs this file.
Importing Hermes may re-exec the interpreter, so the backend imports it when
built, before any ledger reservation.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

INSTRUCTIONS = (
    "You are a connectivity check for a game's authoring transport. "
    'Reply with exactly this JSON object and nothing else: {"ok":true}'
)
PROMPT = "Return the object."


def main(argv=None):
    from chaos.author_config import AuthorConfigError, add_arguments, resolve

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-live", action="store_true", required=True)
    parser.add_argument("--ledger", type=Path, help="default: the user xAI ledger")
    parser.add_argument("--timeout", type=float, default=120)
    add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        config = resolve(
            args.author_provider, args.author_model, args.api_key_env, os.environ
        )
        if config is None or config.provider not in ("xai-oauth", "xai"):
            raise AuthorConfigError(
                "this smoke needs --author-provider xai-oauth or xai, and --author-model"
            )
    except AuthorConfigError as exc:
        print("author smoke: " + str(exc), file=sys.stderr)
        return 2
    from chaos import xai

    ledger = xai.XaiLedger(args.ledger)
    run_id = "smoke-" + time.strftime("%Y%m%dt%H%M%S", time.gmtime())
    try:
        backend = xai.build(
            config, ledger, run_id=run_id, surface="smoke", timeout=args.timeout
        )
        content, receipt = backend.generate(INSTRUCTIONS, PROMPT, return_receipt=True)
    except Exception as exc:
        print(
            "author smoke: failed closed (" + type(exc).__name__ + "); no retry",
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            dict(receipt=receipt, reply=content, ledger=str(ledger.path)),
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
