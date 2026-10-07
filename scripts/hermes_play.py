"""Run ``python3 -m chaos ...`` under Hermes's runtime (NGPL; see dat/license).

The xai-oauth provider uses the xAI OAuth login Hermes holds, through
Hermes's own client builder, so the launcher must run inside Hermes's
Python environment. This wrapper imports ``hermes_bootstrap`` from the Hermes
checkout first (it may re-exec the interpreter into Hermes's environment),
then runs the chaos command line unchanged:

  python3 scripts/hermes_play.py play --ordinary \\
      --author-provider xai-oauth --author-model grok-4.7

The checkout is $HERMES_AGENT_DIR, default ~/.hermes/hermes-agent. Nothing
here reads, copies or prints a credential.
"""

import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    hermes = Path(
        os.environ.get("HERMES_AGENT_DIR") or Path.home() / ".hermes" / "hermes-agent"
    )
    if not (hermes / "hermes_bootstrap.py").is_file():
        print(
            "hermes_play: no Hermes checkout at "
            + str(hermes)
            + " (set HERMES_AGENT_DIR); without it xai-oauth has no model",
            file=sys.stderr,
        )
        return 2
    sys.path.insert(0, str(hermes))
    import hermes_bootstrap  # noqa: F401  (may re-exec into Hermes's environment)

    sys.path.insert(0, str(ROOT))
    sys.argv = ["chaos"] + sys.argv[1:]
    runpy.run_module("chaos", run_name="__main__", alter_sys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
