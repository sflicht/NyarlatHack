"""Current-source transport receipts, with explicitly synthetic native context."""

import ctypes
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

from chaos.episodes import parse_episode_event
from chaos.protocol import parse_event

ROOT = Path(__file__).resolve().parents[2]


class EpisodeIOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="episode-io-build-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.exe = Path(cls.tmp.name) / "episode-io"
        cls.logs = Path(cls.tmp.name) / "logs"
        cls.logs.mkdir()
        command = [
            "/usr/bin/gcc",
            "-std=c99",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I" + str(ROOT / "include"),
            str(ROOT / "src/chaos_protocol.c"),
            str(ROOT / "src/chaos_io.c"),
            str(ROOT / "tests/chaos/episode_io.c"),
            "-Wl,--wrap=write",
            "-Wl,--wrap=fsync",
            "-o",
            str(cls.exe),
        ]
        cls.logged(command, "compile", timeout=30)

    @classmethod
    def logged(cls, command, name, **kwargs):
        result = subprocess.run(command, capture_output=True, **kwargs)
        (cls.logs / (name + ".log")).write_text(
            shlex.join(command)
            + "\nexit="
            + str(result.returncode)
            + "\n"
            + result.stdout.decode()
            + result.stderr.decode()
        )
        if result.returncode:
            raise AssertionError(result.stderr.decode())
        return result.stdout

    def run_rows(self, rows=(), *, mode="rows", fault=0, request=None):
        with tempfile.TemporaryDirectory(prefix="episode-io-run-") as directory:
            path = Path(directory)
            if request:
                (path / "whisper.json").write_text(json.dumps(request))
            data = "".join(" ".join(map(str, row)) + "\n" for row in rows).encode()
            name = self.id().split(".")[-1] + "-" + str(len(list(self.logs.iterdir())))
            (self.logs / (name + ".input")).write_bytes(data)
            out = self.logged(
                [str(self.exe), directory, mode, str(fault)],
                name,
                input=data,
                timeout=5,
            )
            raw = (path / "events.jsonl").read_bytes()
            (self.logs / (name + ".events.jsonl")).write_bytes(raw)
            self.assertEqual(os.stat(path / "events.jsonl").st_mode & 0o777, 0o600)
            return [tuple(map(int, row.split())) for row in out.splitlines()], raw

    def test_logs_are_inside_private_temporary_directory(self):
        temporary = Path(self.tmp.name).resolve()
        self.assertTrue(self.logs.resolve().is_relative_to(temporary))
        self.assertEqual(temporary.stat().st_mode & 0o777, 0o700)

    def test_class_cleanup_removes_logs(self):
        class IsolatedSetup(EpisodeIOTests):
            pass

        try:
            IsolatedSetup.setUpClass()  # Real, bounded standalone compilation.
            logs = IsolatedSetup.logs
            self.assertTrue((logs / "compile.log").is_file())
        finally:
            IsolatedSetup.doClassCleanups()
        self.assertFalse(logs.exists())

    def test_negative_sequences_are_noops(self):
        long_min = -(1 << (ctypes.sizeof(ctypes.c_long) * 8 - 1))
        for seq in (-1, -2, long_min):
            with self.subTest(seq=seq):
                # Otherwise-valid enabled observation, never the legacy -99 op.
                states, raw = self.run_rows(
                    [(seq, 0, 0, 0, 0)], mode="literal-sequence"
                )
                self.assertEqual(states, [(0, seq, 0, 0, 0)])
                self.assertEqual(raw, b"")

    def test_enabled_and_all_positive_rows(self):
        rows = [(-1, 0, 0, 0, 0), (-1, 1, 1, 0, 0), (-1, -99, 0, 0, 0)]
        rows += [(-1, 1, 2, 2, fact) for fact in range(1, 6)]
        rows += [(-1, 1, 3, 2, 0), (-1, 2, 1, 0, 0)]
        rows += [(-1, 2, 2, 10, fact) for fact in range(6, 10)]
        rows += [(-1, 2, 3, 10, 0), (-1, 2, 4, 10, 0)]
        states, raw = self.run_rows(rows)
        self.assertTrue(all(state[0] == 1 for state in states), states)
        lines = raw.splitlines(keepends=True)
        self.assertEqual(len(lines), len(rows))
        for seq, (line, state) in enumerate(zip(lines, states), 1):
            self.assertLess(len(line), 3072)
            record = parse_episode_event(line)
            self.assertEqual(record["seq"], seq)
            self.assertEqual(state, (1, seq, 0, seq, seq))
            if record["v"] == 2:
                _, op, stage, root, fact = rows[seq - 1]
                self.assertEqual(
                    record["observation"],
                    dict(
                        operation=("none", "whistling", "fountain_drink")[op],
                        stage=("enabled", "started", "notice", "completed", "blocked")[
                            stage
                        ],
                        root_seq=root,
                        fact=(
                            "none",
                            "sound_high",
                            "sound_shrill",
                            "sound_normal",
                            "sound_strange",
                            "sound_humming",
                            "water_refreshed",
                            "water_foul",
                            "cannot_reach",
                            "detection_presented",
                        )[fact],
                    ),
                )
                self.assertEqual(
                    record["vitals"], dict(hp=7, hp_max=20, power=-2, power_max=10)
                )
                with self.assertRaises(ValueError):
                    parse_event(line)
            else:
                parse_event(line)
        self.assertEqual(
            [parse_episode_event(line)["observation"]["fact"] for line in lines[3:8]],
            [
                "sound_high",
                "sound_shrill",
                "sound_normal",
                "sound_strange",
                "sound_humming",
            ],
        )

    def test_invalid_combinations_are_noops(self):
        rows = []
        for op in range(3):
            for stage in range(5):
                for root in (-1, 0, 1, 10, 11, 2147483647, 2147483648):
                    for fact in range(10):
                        legal = (
                            (stage == 0 and op == 0 and root == 0 and fact == 0)
                            or (stage == 1 and op in (1, 2) and root == 0 and fact == 0)
                            or (
                                stage == 2
                                and 0 < root < 11
                                and (
                                    (op == 1 and 1 <= fact <= 5)
                                    or (op == 2 and 6 <= fact <= 9)
                                )
                            )
                            or (
                                stage == 3
                                and op in (1, 2)
                                and 0 < root < 11
                                and fact == 0
                            )
                            or (stage == 4 and op == 2 and 0 < root < 11 and fact == 0)
                        )
                        if not legal:
                            rows.append((10, op, stage, root, fact))
        states, raw = self.run_rows(rows)
        self.assertEqual(raw, b"")
        self.assertEqual(states, [(0, 10, 0, 0, 0)] * len(rows))
        # Rejection must not poison later valid appends or predict a new sequence.
        states, raw = self.run_rows([(0, 1, 3, 1, 0), (-1, 0, 0, 0, 0)])
        self.assertEqual(states, [(0, 0, 0, 0, 0), (1, 1, 0, 1, 1)])
        self.assertEqual(parse_episode_event(raw)["seq"], 1)

    def test_invalid_enums_are_noops(self):
        rows = []
        for index, first_invalid in ((1, 3), (2, 5), (4, 10)):
            for value in (-2147483648, -1, first_invalid, 2147483647):
                row = [0, 0, 0, 0, 0]
                row[index] = value
                rows.append(row)
        states, raw = self.run_rows(rows)
        self.assertEqual(raw, b"")
        self.assertEqual(states, [(0, 0, 0, 0, 0)] * len(rows))

    def test_counter_boundary(self):
        states, raw = self.run_rows(
            [
                (2147483646, 2, 2, 2147483647, 9),
                (2147483646, 2, 2, 2147483646, 9),
                (-1, 2, 3, 2147483646, 0),
                (9223372036854775807, 0, 0, 0, 0),
            ]
        )
        self.assertEqual(
            states,
            [
                (0, 2147483646, 0, 0, 0),
                (1, 2147483647, 0, 1, 1),
                (0, 2147483647, 0, 1, 1),
                (0, 9223372036854775807, 0, 1, 1),
            ],
        )
        self.assertEqual(parse_episode_event(raw)["seq"], 2147483647)
        self.assertLess(len(raw), 3072)

    def test_partial_write_and_eintr_eventually_durable(self):
        states, raw = self.run_rows([(0, 0, 0, 0, 0)], fault=1)
        self.assertEqual(states, [(1, 1, 0, 3, 1)])
        self.assertEqual(len(raw.splitlines()), 1)
        self.assertEqual(parse_episode_event(raw)["seq"], 1)

    def test_write_and_fsync_fail_closed_without_sequence_advance(self):
        _, expected = self.run_rows([(0, 0, 0, 0, 0)])
        for fault, prefix, writes, syncs in (
            (2, expected[:7], 2, 0),
            (3, expected, 1, 1),
        ):
            with self.subTest(fault=fault):
                states, raw = self.run_rows(
                    [
                        (0, 0, 0, 0, 0),
                        (-1, 1, 1, 0, 0),
                        (-1, -99, 0, 0, 0),
                    ],
                    fault=fault,
                )
                self.assertEqual(states, [(0, 0, 1, writes, syncs)] * 3)
                self.assertEqual(raw, prefix)

    def test_checked_bounded_format_defense(self):
        # Closed fields cannot exhaust these buffers; check defense, not a
        # fabricated runtime overflow case requiring arbitrary payload strings.
        source = (ROOT / "src/chaos_io.c").read_text()
        self.assertIn("line[3072]", source)
        writer = source.split("int chaos_io_observation(", 1)[1].split(
            "static void fields", 1
        )[0]
        self.assertIn("extra[512]", writer)
        self.assertIn("n < 0 || (size_t)n >= sizeof extra", writer)
        self.assertIn("n < 0 || (size_t)n >= sizeof line", source)

    def test_legacy_independent_byte_golden(self):
        _, raw = self.run_rows(
            mode="legacy",
            request=dict(
                v=1,
                id=1,
                mutation="ward_efficacy",
                value=50,
                duration=1,
                telegraph=2,
                at=1,
            ),
        )
        # Frozen historical layout/values, not another current writer path.
        envelope = (
            '{{"v":1,"seq":{seq},"turn":{turn},"safe":{safe},"event":"{event}",'
            '"phase":"{phase}","detail":{detail},"sanity":0,"insight":0,'
            '"budget":{budget},"spent":{spent},"reserved":{reserved},"last_id":{last_id},'
            '"vitals":{{"hp":7,"hp_max":20,"power":-2,"power_max":10}}{extra}}}\n'
        )
        records = [
            (1, 10, 0, "apply", "attempt", '"quote\\"\\\\\\u000a"', 12, 0, 0, 0, ""),
            (2, 10, 1, "safe_point", "result", '"level_enter"', 12, 0, 0, 0, ""),
            (3, 10, 1, "telegraph", "result", '"ward_efficacy"', 12, 0, 0, 1, ""),
            (
                4,
                10,
                1,
                "ack",
                "result",
                '"ok"',
                8,
                4,
                4,
                1,
                ',"id":1,"status":"accepted","mutation":"ward_efficacy","value":50,'
                '"duration":1,"telegraph":2,"at":1,"cost":4,"expires":11',
            ),
            (5, 11, 1, "expiry", "result", '"ward_efficacy"', 8, 4, 0, 1, ""),
        ]
        keys = "seq turn safe event phase detail budget spent reserved last_id extra".split()
        expected = "".join(envelope.format(**dict(zip(keys, row))) for row in records)
        self.assertEqual(raw, expected.encode())


if __name__ == "__main__":
    unittest.main()
