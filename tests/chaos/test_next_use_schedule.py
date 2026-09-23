"""Origin schedule uses monstermoves, not the observation turn."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from chaos.history import HistoryState
from chaos.launcher import add_parser
from chaos.next_use_history import next_use_menu
from chaos.next_use_schedule import (
    consider_next_use,
    host_from_schedule,
    parse_schedule_line,
    publish_scheduled,
)
from test_episodes import wire
from test_next_use_history import rows

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

    def test_parser_rejects_a_line_without_a_newline(self):
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

    def test_consider_publishes_quiet_from_matching_schedule_only(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command", required=True)
        add_parser(sub)
        args = parser.parse_args(["play"])
        self.assertFalse(args.next_use)
        help_text = sub.choices["play"].format_help()
        self.assertIn("host-built next-use selection", help_text)
        self.assertIn("no model call", help_text)

        raw = wire(*rows(("whistling", "sound_high")))
        history = HistoryState(raw)
        origin = next(
            row["origin"] for row in next_use_menu(history) if row["op"] == "quiet"
        )
        payload = {
            "next_use_schedule_v": 1,
            "family": "W",
            "move": 40,
            "level_dnum": 0,
            "level_dlevel": 1,
            "root": origin["root_seq"],
            "notice_seq": origin["notice_seq"],
            "end_seq": origin["end_seq"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            os.chmod(root, 0o700)
            (root / "events.jsonl").write_bytes(raw)
            self.assertIsNone(consider_next_use(root))
            (root / "next_use-schedule.jsonl").write_text(
                json.dumps(payload, separators=(",", ":")) + "\n"
            )
            result = consider_next_use(root)
            self.assertEqual(result["status"], "envelope_published_not_admitted")
            self.assertIsNone(consider_next_use(root))

    def test_whisper_reader_keeps_observation_rows_out_of_whisper_state(self):
        from chaos.director import EventReader, State

        raw = wire(*rows(("whistling", "sound_high")))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_bytes(raw)
            os.chmod(path, 0o600)
            state = State()
            for event in EventReader(path).read():
                state.ingest(event)
            self.assertNotEqual(state.latest["event"], "observation")
