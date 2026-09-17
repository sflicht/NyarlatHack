"""Synthetic source/ACK tests: no native process or provider."""

import importlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_history as fixtures
from test_director import ack, event
from test_episodes import action, wire
from chaos.history import HistoryState, candidate_requests
from chaos.director import ScheduleBackend


class HistoryDirectorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.events = self.path / "events.jsonl"
        self.rows = fixtures.HistoryTests().rows()
        self.save()

    def save(self):
        self.events.write_bytes(wire(*self.rows))
        self.events.chmod(0o600)

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("chaos.history_director"))
        return importlib.import_module("chaos.history_director")

    def run_case(self, choose=None, tick=None, **kwargs):
        api = self.api()

        class Backend:
            calls = 0

            def choose(inner, context, menu):
                inner.calls += 1
                self.assertNotIn("SECRET", json.dumps(context))
                self.assertNotIn("sha256", json.dumps(context))
                return choose(menu) if choose else menu[0]

        backend = Backend()
        clock = [0.0]

        def sleep(delay):
            clock[0] += delay
            if tick:
                tick()

        with (
            patch.object(api.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(api.time, "sleep", side_effect=sleep),
        ):
            result = api.run_history(
                self.path, backend, ordinary_food=True, max_runtime=1, **kwargs
            )
        return result, backend

    def test_install_receipt_not_acceptance(self):
        result, backend = self.run_case(install_only=True)
        self.assertEqual(result["reason"], "installed_pending_ack")
        self.assertEqual(
            (result["submitted"], result["accepted"], backend.calls), (1, 0, 1)
        )
        self.assertEqual(
            result["decision"]["selected"],
            json.loads((self.path / "whisper.json").read_bytes()),
        )

    def test_abstain(self):
        result, backend = self.run_case(choose=lambda menu: None)
        self.assertEqual(result["reason"], "abstained")
        self.assertEqual(backend.calls, 1)
        self.assertFalse((self.path / "whisper.json").exists())

    def test_invalid_member_and_mutated_menu(self):
        def bad(menu):
            menu[0]["duration"] = 11
            return menu[0]

        with self.assertRaises(ValueError):
            self.run_case(choose=bad)
        self.assertFalse((self.path / "whisper.json").exists())

    def test_stale_complete_and_partial_append(self):
        for suffix in (wire(event(6, sanity=70, budget=6)), b'{"v":'):
            self.save()

            def choose(menu):
                with self.events.open("ab") as f:
                    f.write(suffix)
                return menu[0]

            result, backend = self.run_case(choose=choose)
            self.assertEqual(result["reason"], "stale")
            self.assertEqual(backend.calls, 1)
            self.assertFalse((self.path / "whisper.json").exists())

    def test_rewrite_during_choice_fails(self):
        def choose(menu):
            self.events.write_bytes(
                self.events.read_bytes().replace(b"SECRET", b"PUBLIC")
            )
            return menu[0]

        with self.assertRaises(ValueError):
            self.run_case(choose=choose)

    def test_quiet_to_positive_same_safe(self):
        self.rows = fixtures.HistoryTests().rows("water_foul")
        self.save()

        def tick():
            action(self.rows, "fountain_drink", "water_refreshed")
            for row in self.rows:
                row.update(sanity=70, budget=6)
            self.save()

        result, backend = self.run_case(tick=tick, install_only=True)
        self.assertEqual(result["submitted"], 1)
        self.assertEqual(backend.calls, 1)

    def test_exact_ack_acceptance_and_rejection(self):
        for status in ("accepted", "rejected"):
            with tempfile.TemporaryDirectory() as directory:
                self.path = Path(directory)
                self.events = self.path / "events.jsonl"
                self.rows = fixtures.HistoryTests().rows()
                self.save()

                def tick():
                    request = json.loads((self.path / "whisper.json").read_bytes())
                    self.rows.append(
                        ack(
                            6,
                            request,
                            safe=2,
                            sanity=70,
                            cost=3,
                            spent=3 if status == "accepted" else 0,
                            reserved=3 if status == "accepted" else 0,
                            expires=20 if status == "accepted" else 0,
                            status=status,
                        )
                    )
                    self.save()

                result, _ = self.run_case(tick=tick)
                self.assertEqual(result["reason"], status)
                self.assertEqual(result["accepted"], int(status == "accepted"))

    def test_pending_timeout(self):
        result, _ = self.run_case()
        self.assertEqual(result["reason"], "runtime_cap")
        self.assertEqual(result["accepted"], 0)

    def test_exhausted_selector_distinct_from_abstention(self):
        from chaos.history_choice import RandomHistoryBackend

        backend = RandomHistoryBackend(0)
        backend.attempts = backend.max_attempts
        result = self.api().run_history(self.path, backend, ordinary_food=True)
        self.assertEqual(result["reason"], "exhausted")
        self.assertFalse((self.path / "whisper.json").exists())

    def test_append_during_final_snapshot_recheck(self):
        api = self.api()
        original = api.snapshot_history
        full = [0]

        def snapshot(*args, **kwargs):
            result = original(*args, **kwargs)
            if not kwargs.get("checkpoint"):
                full[0] += 1
                if full[0] == 2:
                    with self.events.open("ab") as f:
                        f.write(b"{")
            return result

        with patch.object(api, "snapshot_history", side_effect=snapshot):
            result, _ = self.run_case()
        self.assertEqual(result["reason"], "stale")
        self.assertFalse((self.path / "whisper.json").exists())

    def test_missing_startup_waits_but_disappearance_after_proof_fails(self):
        self.events.rename(self.path / "saved")
        result, backend = self.run_case()
        self.assertEqual((result["reason"], backend.calls), ("runtime_cap", 0))
        self.save()

        def tick():
            self.events.rename(self.path / "gone")

        with self.assertRaises(FileNotFoundError):
            self.run_case(tick=tick)

    def test_consumed_pending_without_ack_is_error(self):
        def tick():
            self.rows.append(event(6, safe=2, last_id=1, sanity=70, budget=6))
            self.save()

        with self.assertRaises(ValueError):
            self.run_case(tick=tick)

    def test_telegraph_wait_is_not_acceptance_at_deadline(self):
        def tick():
            if len(self.rows) == 5:
                self.rows.append(
                    event(
                        6,
                        safe=2,
                        last_id=1,
                        sanity=70,
                        budget=6,
                        event="telegraph",
                        detail="hunger_rate",
                    )
                )
                self.save()

        with self.assertRaises(ValueError):
            self.run_case(tick=tick)

    def test_checkpoint_rewrite_cannot_be_adopted_on_quiet_poll(self):
        self.rows = fixtures.HistoryTests().rows("water_foul")
        self.save()

        def tick():
            self.events.write_bytes(
                self.events.read_bytes().replace(b"SECRET", b"PUBLIC")
            )

        with self.assertRaises(ValueError):
            self.run_case(tick=tick)

    def test_final_deadline_rejects_replaced_pending_mailbox(self):
        ticks = [0]

        def tick():
            ticks[0] += 1
            if ticks[0] == 4:
                mailbox = self.path / "whisper.json"
                request = json.loads(mailbox.read_bytes())
                request["duration"] = 20
                mailbox.write_text(json.dumps(request))

        with self.assertRaises(ValueError):
            self.run_case(tick=tick)

    def test_poll_rewrite_between_old_check_and_full_read(self):
        api = self.api()
        original = api.snapshot_history
        self.rows = fixtures.HistoryTests().rows("water_foul")
        self.save()

        def snapshot(*args, **kwargs):
            result = original(*args, **kwargs)
            if kwargs.get("checkpoint"):
                self.events.write_bytes(
                    self.events.read_bytes().replace(b"SECRET", b"PUBLIC")
                )
            return result

        with patch.object(api, "snapshot_history", side_effect=snapshot):
            with self.assertRaises(ValueError):
                self.run_case()

    def test_caps_fail_before_choice(self):
        for kwargs in (dict(max_bytes=1), dict(max_events=1), dict(max_events=True)):
            with self.assertRaises(ValueError):
                self.run_case(**kwargs)

    def test_replay_requires_original_exact_acceptance(self):
        api = self.api()
        request = candidate_requests(HistoryState(wire(*self.rows)), True)[0]
        journal = self.path / "admissions.jsonl"
        journal.write_text(json.dumps(dict(request, status="admitted")) + "\n")
        journal.chmod(0o600)
        with self.assertRaises(ValueError):
            api.load_history_replay(journal, self.events)
        self.rows.append(
            ack(6, request, safe=2, sanity=70, cost=3, spent=3, reserved=3, expires=20)
        )
        self.save()
        self.assertEqual(api.load_history_replay(journal, self.events), [request])
        self.rows = fixtures.HistoryTests().rows("water_foul")
        self.save()
        result = api.run_history(
            self.path, ScheduleBackend([request]), install_only=True
        )
        self.assertEqual(result["submitted"], 1)
