"""Bounded schedule regressions; ENGINE-UNIT, no provider or game runs."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from chaos import next_use_schedule as schedule
from chaos.director import Mailbox
from chaos.history import HistoryState
from chaos.next_use_history import next_use_menu
from test_episodes import wire
from test_next_use_history import rows

ROOT = Path(__file__).resolve().parents[2]


def record(root=3, family="W", **changes):
    return dict(
        next_use_schedule_v=1,
        family=family,
        move=40,
        level_dnum=0,
        level_dlevel=1,
        root=root,
        notice_seq=root + 1,
        end_seq=root + 2,
        **changes,
    )


def encoded(row):
    return (json.dumps(row, separators=(",", ":")) + "\n").encode()


class ScheduleRobustnessTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.events = self.root / "events.jsonl"
        self.path = self.root / "next_use-schedule.jsonl"
        self.put(self.events, wire(*rows(("whistling", "sound_high"))))

    def put(self, path, raw):
        path.write_bytes(raw)
        path.chmod(0o600)

    def consumer(self, seed=0):
        self.assertTrue(
            hasattr(schedule, "NextUseScheduler"), "stateful scheduler required"
        )
        return schedule.NextUseScheduler(self.root, seed=seed)

    def test_latest_same_family_is_the_engine_owned_origin(self):
        history = HistoryState(
            wire(*rows(("whistling", "sound_high"), ("whistling", "sound_normal")))
        )
        self.assertEqual({r["origin"]["root_seq"] for r in next_use_menu(history)}, {6})

    def test_complete_line_and_duplicate_keys_are_bounded(self):
        raw = encoded(record())
        for bad in (
            b" " * 257 + raw,
            raw.replace(b'"move":40', b'"move":39,"move":40'),
            raw.replace(b'"next_use_schedule_v":1', b'"next_use_schedule_v":true'),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                schedule.parse_schedule_line(bad)

    def test_pending_tail_completes_once_without_reroll(self):
        raw = encoded(record())
        self.put(self.path, raw[:-2])
        consumer = self.consumer()
        self.assertEqual(consumer.poll()["status"], "pending")
        with self.path.open("ab") as stream:
            stream.write(raw[-2:])
        self.assertEqual(consumer.poll()["status"], "envelope_published_not_admitted")
        before = (self.root / "next_use-envelope.json").read_bytes()
        self.assertEqual(consumer.poll()["status"], "already_published")
        self.assertEqual((self.root / "next_use-envelope.json").read_bytes(), before)
        self.assertEqual(consumer.selector.attempts, 1)

    def test_history_tail_is_pending_and_never_read_bytes(self):
        raw = self.events.read_bytes()
        self.put(self.events, raw[:-2])
        self.put(self.path, encoded(record()))
        consumer = self.consumer()
        with patch.object(
            Path, "read_bytes", side_effect=AssertionError("unbounded read")
        ):
            self.assertEqual(consumer.poll()["status"], "pending")
            with self.events.open("ab") as stream:
                stream.write(raw[-2:])
            self.assertEqual(
                consumer.poll()["status"], "envelope_published_not_admitted"
            )

    def test_replacement_truncation_and_rewrite_are_failures(self):
        for name in ("events.jsonl", "next_use-schedule.jsonl"):
            for change, message in (
                ("replace", "replaced"),
                ("truncate", "truncated"),
                ("rewrite", "rewritten"),
                ("remove", "disappeared"),
            ):
                with self.subTest(name=name, change=change):
                    self.put(self.events, wire(*rows(("whistling", "sound_high"))))
                    self.put(self.path, encoded(record(50)))
                    consumer = self.consumer()
                    self.assertEqual(consumer.poll()["status"], "no_eligible_origin")
                    path = self.root / name
                    raw = path.read_bytes()
                    if change == "replace":
                        new = self.root / "replacement"
                        self.put(new, raw)
                        new.replace(path)
                    elif change == "truncate":
                        self.put(path, raw[:-2])
                    elif change == "remove":
                        path.unlink()
                    else:
                        self.put(path, b" " + raw[1:])
                    with self.assertRaisesRegex(ValueError, message):
                        consumer.poll()
                    self.assertEqual(consumer.poll()["status"], "failed")
                    self.assertFalse((self.root / "next_use-envelope.json").exists())

    def test_duplicate_root_conflict_is_not_another_candidate(self):
        for extra in (
            record(),
            dict(record(), move=41),
            dict(record(), notice_seq=5, end_seq=6),
            dict(record(), family="F"),
        ):
            with self.subTest(extra=extra):
                self.put(self.path, encoded(record()) + encoded(extra))
                with self.assertRaisesRegex(ValueError, "duplicate|conflict"):
                    self.consumer().poll()

    def test_caps_and_malformed_rows_fail_explicitly(self):
        cases = [
            (b"x" * 16385, "byte cap"),
            (b"x" * 257, "byte cap"),
            (b"x" * 257 + b"\n", "byte cap"),
            (b"{}\n", "schema"),
            (b"".join(encoded(record(3 * n + 3)) for n in range(33)), "count cap"),
        ]
        for raw, message in cases:
            with self.subTest(message=message):
                self.put(self.path, raw)
                with self.assertRaisesRegex(ValueError, message):
                    self.consumer().poll()
        self.put(self.path, encoded(record()))
        with self.events.open("r+b") as stream:
            stream.truncate(16 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, "byte cap"):
            self.consumer().poll()

    def test_unsafe_inputs_fail_instead_of_being_absent(self):
        for kind in ("symlink", "hardlink", "fifo", "directory", "public"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    self.path.symlink_to(self.events)
                elif kind == "hardlink":
                    os.link(self.events, self.path)
                elif kind == "fifo":
                    os.mkfifo(self.path, 0o600)
                elif kind == "directory":
                    self.path.mkdir()
                else:
                    self.put(self.path, encoded(record()))
                    self.path.chmod(0o644)
                with self.assertRaises((ValueError, OSError)):
                    self.consumer().poll()
                if kind == "directory":
                    self.path.rmdir()
                else:
                    self.path.unlink()

    def test_unrelated_and_evicted_records_are_not_candidates(self):
        for actions, origin in (
            ((("whistling", "sound_high"),), record(50)),
            (
                (("whistling", "sound_high"),)
                + (("fountain_drink", "water_foul"),) * 32,
                record(),
            ),
        ):
            with self.subTest(origin=origin):
                self.put(self.events, wire(*rows(*actions)))
                self.put(self.path, encoded(origin))
                consumer = self.consumer()
                self.assertEqual(consumer.poll()["status"], "no_eligible_origin")
                self.assertEqual(consumer.selector.attempts, 0)
                self.assertFalse((self.root / "next_use-envelope.json").exists())

    def test_missed_safe_point_does_not_retime_origin(self):
        data = rows(("whistling", "sound_high"))
        data[-1].update(
            safe=data[-2]["safe"] + 1,
            event="safe_point",
            phase="result",
            detail="prayer",
        )
        self.put(self.events, wire(*data))
        self.put(self.path, encoded(record()))
        consumer = self.consumer()
        self.assertEqual(consumer.poll()["status"], "no_eligible_origin")
        self.assertEqual(consumer.selector.attempts, 0)
        self.assertFalse((self.root / "next_use-envelope.json").exists())

    def test_selector_seed_quiet_and_abstention_are_stable(self):
        self.put(self.path, encoded(record()))
        consumer = self.consumer(seed=1)
        self.assertEqual(consumer.poll()["status"], "envelope_published_not_admitted")
        payload = json.loads((self.root / "next_use-envelope.json").read_text())
        self.assertIn('op="quiet"', payload["source"])
        (self.root / "next_use-envelope.json").unlink()
        self.assertEqual(consumer.poll()["status"], "already_published")
        consumer = self.consumer()
        with patch.object(
            consumer.selector, "choose_next_use", return_value=None
        ) as choose:
            self.assertEqual(consumer.poll()["status"], "abstained")
            self.assertEqual(consumer.poll()["status"], "abstained")
            choose.assert_called_once()

    def test_lock_reuse_competition_and_existing_envelope(self):
        self.put(self.path, encoded(record()))
        with Mailbox(self.root) as box:
            with self.assertRaisesRegex(ValueError, "another director"):
                self.consumer().poll()
            result = self.consumer().poll(box)
            self.assertEqual(result["status"], "envelope_published_not_admitted")
        before = (self.root / "next_use-envelope.json").read_bytes()
        self.assertEqual(self.consumer().poll()["status"], "already_published")
        self.assertEqual((self.root / "next_use-envelope.json").read_bytes(), before)

    def test_launcher_uses_one_declared_seed_and_reports_status(self):
        from contextlib import redirect_stderr
        import io
        from types import SimpleNamespace
        from chaos.director import EventReader, ScheduleBackend, State
        from chaos.launcher import _offline_loop

        self.put(self.path, encoded(record()))
        args = SimpleNamespace(
            next_use=True, seed=1, max_runtime=0.01, poll=0.001, max_submissions=1
        )
        read_fd, write_fd = os.pipe()
        output = io.StringIO()
        try:
            with Mailbox(self.root) as box, redirect_stderr(output):
                _offline_loop(
                    box,
                    ScheduleBackend([]),
                    EventReader(self.events),
                    State(),
                    args,
                    write_fd,
                )
            self.assertEqual(os.read(read_fd, 1), b"R")
        finally:
            os.close(read_fd)
        envelope = json.loads((self.root / "next_use-envelope.json").read_text())
        self.assertIn('op="quiet"', envelope["source"])
        self.assertIn("next-use: envelope_published_not_admitted", output.getvalue())
        self.assertEqual(output.getvalue().count("next-use: already_published"), 1)

    def test_publication_failure_is_not_retried(self):
        self.put(self.path, encoded(record()))
        consumer = self.consumer()
        with patch(
            "chaos.next_use_envelope.publish_envelope",
            side_effect=OSError("sync failed"),
        ) as publish:
            with self.assertRaisesRegex(OSError, "sync failed"):
                consumer.poll()
            self.assertEqual(consumer.poll()["status"], "failed")
            publish.assert_called_once()


class ScheduleProductionFlowTests(unittest.TestCase):
    """Real engine output -> unchanged consumer -> production admission wrapper.

    The existing C helpers stub the game host and telegraph callback. This is
    schedule/transport evidence, not native gameplay or consequence delivery.
    """

    @classmethod
    def setUpClass(cls):
        import test_episode_scopes
        import test_next_use_safe

        test_episode_scopes.EpisodeScopesTests.setUpClass.__func__(cls)
        cls.producer = cls.binary
        test_next_use_safe.NextUseSafeAdmitTests.setUpClass.__func__(cls)

    def produce(self, root, pair="ww", suffix=""):
        second = "begin 1 arm 1 3" if pair == "ww" else "begin 2 arm 2 6"
        env = {k: v for k, v in os.environ.items() if not k.startswith("NYARLATHACK_")}
        env.update(
            NYARLATHACK_RUN_DIR=str(root),
            NYARLATHACK_OBSERVATIONS="1",
            NYARLATHACK_NEXT_USE_ADMIT="1",
        )
        result = subprocess.run(
            [str(self.producer)],
            input="schedule start begin 1 arm 1 1 take deliver end "
            + second
            + " take deliver end "
            + suffix,
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def admit(self, root, pair, **changes):
        import test_next_use_safe
        from chaos.next_use_envelope import engine_run_hex

        options = dict(
            at_safe=2,
            at_move=40,
            run=engine_run_hex(root),
            wrapper="on_safe",
            evidence="schedule_" + pair,
        )
        options.update(changes)
        return test_next_use_safe.NextUseSafeAdmitTests.run_case(
            self, str(root), **options
        )

    def paused_producer(self, root, commands, lines):
        env = {k: v for k, v in os.environ.items() if not k.startswith("NYARLATHACK_")}
        env.update(
            NYARLATHACK_RUN_DIR=str(root),
            NYARLATHACK_OBSERVATIONS="1",
            NYARLATHACK_NEXT_USE_ADMIT="1",
        )
        proc = subprocess.Popen(
            [str(self.producer)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        def cleanup():
            if proc.poll() is None:
                proc.kill()
            proc.communicate(timeout=5)

        self.addCleanup(cleanup)
        proc.stdin.write("schedule start " + commands + "\n")
        proc.stdin.flush()
        path = root / "events.jsonl"
        deadline = time.monotonic() + 5
        while not path.exists() or path.read_bytes().count(b"\n") != lines:
            if proc.poll() is not None or time.monotonic() >= deadline:
                self.fail("real producer did not reach the expected prefix")
            time.sleep(0.005)
        return proc

    def test_latest_qualifying_fountain_is_not_a_sampled_summary(self):
        from chaos.next_use_compose import compose

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            commands = "begin 2 arm 2 6 take deliver end " * 3
            commands += "begin 2 arm 2 7 take deliver end"
            proc = self.paused_producer(root, commands, 16)
            consumer = schedule.NextUseScheduler(root, seed=0)
            self.assertEqual(
                consumer.poll()["status"], "envelope_published_not_admitted"
            )
            payload = json.loads((root / "next_use-envelope.json").read_bytes())
            ref = payload["origin_refs"][0]
            self.assertEqual(
                (ref["family"], ref["root"], ref["notice_seq"], ref["end_seq"]),
                ("F", 11, 12, 13),
            )
            selected = next(
                r
                for r in next_use_menu(consumer.history)
                if r["op"] == "fountain_refresh"
            )
            self.assertEqual(payload["source"], compose(selected)["source"])
            # Native ownership is inspected independently, after publication.
            out, err = proc.communicate("safe\n", timeout=5)
            self.assertEqual((proc.returncode, err), (0, ""))
            self.assertIn("owned 11 12 13 1", out)
            result = self.admit(root, "fff")
            self.assertEqual(
                (result["admitted"], result["telegraph"], result["caller_spent"]),
                (1, 1, 1),
            )
            self.assertEqual(
                (
                    result["second_admitted"],
                    result["second_telegraph"],
                    result["second_caller_spent"],
                ),
                (0, 0, 1),
            )

    def test_new_qualifying_notice_waits_for_its_own_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            proc = self.paused_producer(
                root, "begin 1 arm 1 1 take deliver end begin 1 arm 1 3 take deliver", 9
            )
            consumer = schedule.NextUseScheduler(root, seed=0)
            self.assertEqual(consumer.poll()["status"], "pending")
            self.assertFalse((root / "next_use-envelope.json").exists())
            self.assertEqual(consumer.selector.attempts, 0)
            proc.stdin.write("end\n")
            proc.stdin.flush()
            path = root / "events.jsonl"
            deadline = time.monotonic() + 5
            while (
                path.read_bytes().count(b"\n") != 10
                or (root / "next_use-schedule.jsonl").read_bytes().count(b"\n") != 2
            ):
                if time.monotonic() >= deadline:
                    self.fail("real producer did not finish the pending origin")
                time.sleep(0.005)
            self.assertEqual(
                consumer.poll()["status"], "envelope_published_not_admitted"
            )
            payload = json.loads((root / "next_use-envelope.json").read_bytes())
            self.assertEqual(payload["origin_refs"][0]["root"], 8)
            out, err = proc.communicate("safe\n", timeout=5)
            self.assertEqual((proc.returncode, err), (0, ""))
            self.assertIn("owned 8 9 10 1", out)
            result = self.admit(root, "ww")
            self.assertEqual(
                (result["admitted"], result["telegraph"], result["caller_spent"]),
                (1, 1, 1),
            )
            self.assertEqual(consumer.selector.attempts, 1)
            self.assertEqual(consumer.poll()["status"], "already_published")

    def test_real_engine_multiple_origins_publish_and_admit_exactly_once(self):
        from chaos.next_use_compose import compose

        for pair, expected in (("ww", 8), ("wf", 5)):
            with self.subTest(pair=pair), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.produce(root, pair)
                emitted = schedule.read_schedule_rows(root / "next_use-schedule.jsonl")
                self.assertEqual([r["root"] for r in emitted], [5, 8])
                consumer = schedule.NextUseScheduler(root, seed=0)
                self.assertEqual(
                    consumer.poll()["status"], "envelope_published_not_admitted"
                )
                path = root / "next_use-envelope.json"
                before = path.read_bytes()
                envelope = json.loads(before)
                selected = next(
                    r
                    for r in next_use_menu(consumer.history)
                    if r["origin"]["root_seq"] == expected
                    and r["op"] == "whistle_attention"
                )
                source = compose(selected)
                self.assertEqual(envelope["source"], source["source"])
                self.assertEqual(envelope["source_sha256"], source["source_sha256"])
                ref = envelope["origin_refs"][0]
                self.assertEqual(
                    (ref["family"], ref["root"], ref["notice_seq"], ref["end_seq"]),
                    ("W", expected, expected + 1, expected + 2),
                )
                self.assertEqual(consumer.poll()["status"], "already_published")
                self.assertEqual(path.read_bytes(), before)
                admitted = self.admit(root, pair)
                self.assertEqual(
                    (
                        admitted["admitted"],
                        admitted["telegraph"],
                        admitted["caller_spent"],
                    ),
                    (1, 1, 1),
                )
                self.assertEqual(
                    (
                        admitted["second_admitted"],
                        admitted["second_telegraph"],
                        admitted["second_caller_spent"],
                    ),
                    (0, 0, 1),
                )

    def test_production_revalidates_selected_origin_not_schedule_authority(self):
        cases = (
            {"run": "cd" * 32},
            {"dlevel": 2},
            {"at_move": 141},
            {"at_safe": 3},
            {"evidence": "missing"},
            {"evidence": "schedule_ww"},
        )
        for changes in cases:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.produce(root, "wf")
                consumer = schedule.NextUseScheduler(root, seed=0)
                self.assertEqual(
                    consumer.poll()["status"], "envelope_published_not_admitted"
                )
                result = self.admit(root, "wf", **changes)
                self.assertEqual(
                    (
                        result["rejected"],
                        result["admitted"],
                        result["telegraph"],
                        result["caller_spent"],
                    ),
                    (1, 0, 0, 0),
                )
                self.assertEqual(consumer.poll()["status"], "already_published")
                self.assertEqual(consumer.selector.attempts, 1)

    def test_partial_real_schedule_completes_before_one_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.produce(root)
            path = root / "next_use-schedule.jsonl"
            raw = path.read_bytes()
            path.write_bytes(raw[:-2])
            consumer = schedule.NextUseScheduler(root, seed=0)
            self.assertEqual(consumer.poll()["status"], "pending")
            self.assertFalse((root / "next_use-envelope.json").exists())
            with path.open("ab") as stream:
                stream.write(raw[-2:])
            self.assertEqual(
                consumer.poll()["status"], "envelope_published_not_admitted"
            )
            result = self.admit(root, "ww")
            self.assertEqual(
                (
                    result["admitted"],
                    result["telegraph"],
                    result["caller_spent"],
                    result["second_admitted"],
                    result["second_telegraph"],
                    result["second_caller_spent"],
                ),
                (1, 1, 1, 0, 0, 1),
            )
            self.assertEqual(consumer.poll()["status"], "already_published")
            self.assertEqual(consumer.selector.attempts, 1)

    def test_schedule_metadata_cannot_override_engine_owned_origin(self):
        for changes in ({"move": 41}, {"level_dlevel": 2}):
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.produce(root)
                path = root / "next_use-schedule.jsonl"
                emitted = schedule.read_schedule_rows(path)
                emitted[-1].update(changes)
                path.write_bytes(b"".join(encoded(row) for row in emitted))
                consumer = schedule.NextUseScheduler(root, seed=0)
                self.assertEqual(
                    consumer.poll()["status"], "envelope_published_not_admitted"
                )
                result = self.admit(root, "ww")
                self.assertEqual(
                    (
                        result["rejected"],
                        result["admitted"],
                        result["telegraph"],
                        result["caller_spent"],
                    ),
                    (1, 0, 0, 0),
                )

    def test_failed_schedule_write_never_binds_a_ready_origin(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                if fail:
                    os.mkfifo(root / "next_use-schedule.jsonl", 0o600)
                output = self.produce(root, suffix="safe")
                # Independent engine-owned lookup must not authorize failed I/O.
                self.assertEqual("owned 8 9 10 1" in output, not fail)
                history = HistoryState((root / "events.jsonl").read_bytes())
                self.assertEqual(history.latest["seq"], 11)
                self.assertEqual(history.safe, 2)


class ScheduleWriterRobustnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.exe = Path(tmp.name) / "note"
        subprocess.run(
            [
                "cc",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I" + str(ROOT / "include"),
                str(ROOT / "tests/chaos/next_use_schedule.c"),
                "-o",
                str(cls.exe),
            ],
            check=True,
            timeout=20,
        )

    def test_interrupted_short_io_failure_rollback_and_nonblocking_lock(self):
        for fault, success in (
            ("eintr", 1),
            ("short", 1),
            ("read_eintr", 1),
            ("read_short", 1),
            ("partial_fail", 0),
            ("sync_fail", 0),
            ("owner", 0),
            ("held_lock", 0),
        ):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "next_use-schedule.jsonl"
                before = encoded(record())
                path.write_bytes(before)
                path.chmod(0o600)
                result = subprocess.run(
                    [str(self.exe), tmp, fault],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], success)
                self.assertEqual(
                    path.read_bytes(),
                    before + (encoded(record(10)) if success else b""),
                )

    def test_real_producer_multiple_origins_selects_exact_latest_slot(self):
        for actions, families, expected in (
            (
                (("whistling", "sound_high"), ("whistling", "sound_normal")),
                ("W", "W"),
                6,
            ),
            (
                (("whistling", "sound_high"), ("fountain_drink", "water_refreshed")),
                ("W", "F"),
                3,
            ),
        ):
            with self.subTest(families=families), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                events = root / "events.jsonl"
                events.write_bytes(wire(*rows(*actions)))
                events.chmod(0o600)
                for start, family in zip((3, 6), families):
                    result = subprocess.run(
                        [
                            str(self.exe),
                            tmp,
                            family,
                            str(start),
                            str(start + 1),
                            str(start + 2),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    self.assertEqual(
                        json.loads(result.stdout)["status"], 1, result.stderr
                    )
                self.assertTrue(hasattr(schedule, "NextUseScheduler"))
                consumer = schedule.NextUseScheduler(root, seed=0)
                self.assertEqual(
                    consumer.poll()["status"], "envelope_published_not_admitted"
                )
                envelope = json.loads((root / "next_use-envelope.json").read_text())
                self.assertEqual(envelope["origin_refs"][0]["root"], expected)
                self.assertEqual(consumer.poll()["status"], "already_published")

    def test_writer_refuses_public_partial_and_full_files_preserving_bytes(self):
        for raw, mode in (
            (b"", 0o644),
            (b"partial", 0o600),
            (b"x" * 16380, 0o600),
            (encoded(record()) * 32, 0o600),
        ):
            with (
                self.subTest(size=len(raw), mode=mode),
                tempfile.TemporaryDirectory() as tmp,
            ):
                path = Path(tmp) / "next_use-schedule.jsonl"
                path.write_bytes(raw)
                path.chmod(mode)
                result = subprocess.run(
                    [str(self.exe), tmp], capture_output=True, text=True, timeout=5
                )
                self.assertEqual(json.loads(result.stdout)["status"], 0)
                self.assertEqual(path.read_bytes(), raw)
