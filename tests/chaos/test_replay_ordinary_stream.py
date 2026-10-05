"""Replay regressions from the real slice-3b ordinary event stream."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from chaos.director import ScheduleBackend, load_replay, run

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "docs/evidence/curio-live-capture/attempt-001/run"
REQUEST = dict(v=1, id=1, mutation="ambient", value=1, duration=0, telegraph=1, at=1)
JOURNAL = {
    "v": 1,
    "policy": 2,
    "turn": 1,
    "safe": 1,
    "id": 1,
    "status": "admitted",
    "mutation": "ambient",
    "value": 1,
    "duration": 0,
    "telegraph": 1,
    "at": 1,
    "cost": 0,
    "cosmetic_cost": 1,
    "expires": 0,
}


class OrdinaryReplayStreamTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="nyarl-replay-mixed-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.events = self.root / "events.jsonl"
        self.events.write_bytes((CAPTURE / "events.jsonl").read_bytes())
        self.journal = self.root / "whispers.jsonl"
        self.journal.write_text(json.dumps(JOURNAL) + "\n")
        self.events.chmod(0o600)
        self.journal.chmod(0o600)

    def test_load_real_ordinary_stream_without_dropping_observations(self):
        self.assertEqual(load_replay(self.journal, self.events), [REQUEST])

    def test_replay_loop_reads_real_ordinary_stream(self):
        result = run(self.root, ScheduleBackend([]), max_runtime=1)
        self.assertEqual(result["reason"], "death")
        self.assertEqual(result["submitted"], 0)
        self.assertEqual(result["events"], 265)

    def test_cli_curio_replay_stages_exact_source_and_engine_index(self):
        from chaos.__main__ import main

        evidence = self.root / "evidence"
        evidence.mkdir(mode=0o700)
        for source in (CAPTURE / "curio-evidence").iterdir():
            target = evidence / source.name
            target.write_bytes(source.read_bytes())
            target.chmod(0o600)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(
                [
                    "replay",
                    str(self.journal),
                    "--run-dir",
                    str(self.root),
                    "--accepted-events",
                    str(self.events),
                    "--curio-evidence",
                    str(evidence),
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["reason"], "death")
        self.assertEqual((self.root / "curio-safe").read_bytes(), b"2\n")
        self.assertEqual(
            (self.root / "curio.lua").read_bytes(),
            (evidence / "source.lua").read_bytes(),
        )

    def test_malformed_observation_is_rejected_not_filtered(self):
        rows = [json.loads(line) for line in self.events.read_text().splitlines()]
        row = next(r for r in rows if r["event"] == "observation")
        row["observation"]["stage"] = "not-a-stage"
        self.events.write_text("".join(json.dumps(r) + "\n" for r in rows))
        with self.assertRaises(ValueError):
            load_replay(self.journal, self.events)
        with self.assertRaises(ValueError):
            run(self.root, ScheduleBackend([]), max_runtime=1)

    def test_observation_sequence_rollback_is_rejected(self):
        rows = [json.loads(line) for line in self.events.read_text().splitlines()]
        row = next(r for r in rows if r["event"] == "observation" and r["seq"] > 1)
        row["seq"] = 1
        self.events.write_text("".join(json.dumps(r) + "\n" for r in rows))
        with self.assertRaises(ValueError):
            load_replay(self.journal, self.events)

    def test_partial_observation_tail_is_rejected(self):
        with self.events.open("ab") as stream:
            stream.write(b'{"v":4,"event":"observation"')
        with self.assertRaisesRegex(ValueError, "incomplete"):
            load_replay(self.journal, self.events)


if __name__ == "__main__":
    unittest.main()
