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

    def test_publish_uses_schedule_move_and_refuses_when_absent(self):
        import os

        from chaos.next_use_schedule import publish_scheduled

        selected = {
            "family": "W",
            "op": "quiet",
            "origin": {
                "root_seq": 10,
                "notice_seq": 11,
                "end_seq": 12,
                "fact": "sound_high",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.chmod(root, 0o700)
            with self.assertRaises(ValueError):
                publish_scheduled(root, selected, "ab" * 32, 2, 1)
            self.note(root)
            result = publish_scheduled(root, selected, "ab" * 32, 2, 1)
            self.assertEqual(result["status"], "envelope_published_not_admitted")
            envelope = json.loads((root / "next_use-envelope.json").read_text())
            self.assertEqual(envelope["origin_refs"][0]["move"], 40)
