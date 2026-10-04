"""Curio replay backend: install the logged source, never regenerate (NGPL).

Proposal 3.5. A replay of a game with a model-authored curio reads that game's
run evidence (chaos.curio_author: prompt, raw response, source, receipt,
install record), verifies its hash chain, and publishes the exact logged
source at the logged safe point. It never builds a transport, never calls a
model and never regenerates: this module imports no backend.

Use: after each observed event, call due(latest_safe); when it is true,
install(run_directory) before the game reaches the next safe point. After play,
verify(run_directory) re-checks the installed bytes and the engine's own
curio-used.lua (curio_store.install_saved_source in verify mode).
"""

from pathlib import Path

from . import curio_author, curio_store as store


class ReplayDiverged(ValueError):
    """The replay passed the logged safe point without installing."""


class CurioReplayBackend:
    def __init__(self, evidence_dir):
        self.evidence = Path(evidence_dir).absolute()
        self.receipt = curio_author.read_evidence(self.evidence)
        self.record = curio_author.read_install(self.evidence)
        if self.record["source_sha256"] != self.receipt["lua_source_sha256"]:
            raise ValueError("install record does not match the evidence")
        self.safe = self.record["safe"]
        self.installed = None

    def __repr__(self):
        return f"<CurioReplayBackend safe={self.safe} source={self.record['source_sha256'][:12]}>"

    def due(self, latest_safe):
        if type(latest_safe) is not int or latest_safe < 0:
            raise ValueError("latest safe point must be a nonnegative integer")
        if self.installed is not None:
            return False
        if latest_safe > self.safe:
            raise ReplayDiverged("replay passed the logged curio safe point")
        return latest_safe == self.safe

    def install(self, run_directory):
        if self.installed is not None:
            raise ValueError("logged curio already installed")
        source = self.evidence / "source.lua"
        store.install_saved_source(run_directory, source_file=source)
        receipt = store.install_saved_source(
            run_directory, source_file=source, mode="verify"
        )
        if receipt["source_sha256"] != self.record["source_sha256"]:
            raise ValueError("replayed source differs from the logged source")
        self.installed = receipt
        return receipt

    def verify(self, run_directory):
        """Read-only: installed bytes and the engine's curio-used.lua match."""
        return store.install_saved_source(
            run_directory, source_file=self.evidence / "source.lua", mode="verify"
        )
