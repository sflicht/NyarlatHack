"""Origin schedule uses monstermoves, not the observation turn."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NextUseScheduleTests(unittest.TestCase):
    def note(self, directory):
        exe = directory / "note"
        subprocess.run(
            [
                "cc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I" + str(ROOT / "include"),
                str(ROOT / "src/chaos_next_use_schedule.c"),
                str(ROOT / "tests/chaos/next_use_schedule.c"),
                "-o",
                str(exe),
            ],
            check=True,
            timeout=20,
        )
        result = subprocess.run(
            [str(exe), str(directory)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_writer_records_monstermoves_not_turn(self):
        from chaos.next_use_schedule import host_from_schedule, parse_schedule_line

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = self.note(root)
            self.assertEqual(row["status"], 1)
            parsed = parse_schedule_line(
                (root / "next_use-schedule.jsonl").read_bytes()
            )
            self.assertEqual(parsed["move"], 40)
            host = host_from_schedule(parsed, "ab" * 32, 2, 1)
            self.assertEqual(host["move"], 40)
            self.assertNotEqual(host["move"], 1)

    def test_parser_rejects_a_turn_substituted_for_move(self):
        from chaos.next_use_schedule import parse_schedule_line

        raw = (
            b'{"next_use_schedule_v":1,"family":"W","move":1,'
            b'"level_dnum":0,"level_dlevel":1,"root":10,'
            b'"notice_seq":11,"end_seq":12}\n'
        )
        parsed = parse_schedule_line(raw)
        self.assertEqual(parsed["move"], 1)
        with self.assertRaises(ValueError):
            parse_schedule_line(raw.replace(b"\n", b""))
