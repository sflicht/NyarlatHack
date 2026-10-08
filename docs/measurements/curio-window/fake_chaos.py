"""`python3 -m chaos` with a fake curio author (no model, no transport).

usage (as the game's launcher interpreter): fake_chaos.py -m chaos play ...

The game harness starts the launcher as `<sys.executable> -m chaos play ...`;
measure.py points sys.executable at a two-line shell wrapper that runs this file
instead. It replaces chaos.curio_author.build_backend with FakeBackend and then
runs chaos/__main__.py exactly as `-m chaos` would. Everything else is the tree's
own code: the curio lane, its deadline, the envelope parse, the native
validator, the truth check, publication and the engine's admission.

FakeBackend.generate sleeps CURIO_WINDOW_DELAY_S wall-clock seconds, then
returns the bytes of CURIO_WINDOW_RAW (the committed #247 raw response). It
imports no transport and writes no ledger row.
"""

import os
from pathlib import Path
import runpy
import sys
import time
from types import SimpleNamespace

if sys.argv[1:3] != ["-m", "chaos"]:
    sys.exit("fake_chaos.py: expected '-m chaos ...'")
if any(k.startswith("NYARLATHACK_AUTHOR") for k in os.environ):
    sys.exit("fake_chaos.py: refusing, an author setting is present in the environment")
sys.argv = [sys.argv[0]] + sys.argv[3:]
DELAY = float(os.environ["CURIO_WINDOW_DELAY_S"])
RAW = Path(os.environ["CURIO_WINDOW_RAW"]).read_text(encoding="utf-8")
if not 0 < DELAY < 480:
    sys.exit("fake_chaos.py: delay outside the lane deadline")

from chaos import curio_author  # noqa: E402  (PYTHONPATH is the tree under test)


class FakeBackend:
    """The lane's backend interface: generate(), deadline, retry_delay."""

    config = SimpleNamespace(provider="fake", model="fake-locket-247")
    model = "fake-locket-247"

    def __init__(self):
        self.deadline = None
        self.retry_delay = None
        self.calls = 0

    def generate(self, instructions, prompt, return_receipt=False):
        self.calls += 1
        started = time.monotonic()
        time.sleep(DELAY)
        transport = dict(
            fake=True,
            delay_s=DELAY,
            slept_s=round(time.monotonic() - started, 3),
            call=self.calls,
        )
        return (RAW, transport) if return_receipt else RAW


def build_backend(config, **_):
    if config is None:
        return None
    return FakeBackend()


curio_author.build_backend = build_backend
runpy.run_module("chaos", run_name="__main__", alter_sys=True)
