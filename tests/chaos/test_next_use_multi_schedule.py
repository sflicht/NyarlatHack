"""M2 director tests: public lifecycle receipts, never private replay inputs."""

import json
from pathlib import Path
import tempfile
import unittest

from chaos.next_use_schedule import NextUseScheduler
from test_episodes import wire
from test_next_use_history import rows
from test_next_use_schedule_robustness import record, encoded


class MultiScheduleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data = rows(("whistling", "sound_high"))[:-1]
        self.put("events.jsonl", wire(*self.data))
        self.put("next_use-schedule.jsonl", encoded(record()))

    def put(self, name, raw):
        path = self.root / name
        path.write_bytes(raw)
        path.chmod(0o600)

    def test_second_publication_waits_for_terminal_and_fresh_completion(self):
        scheduler = NextUseScheduler(self.root, seed=0, programs=3)
        self.assertEqual(scheduler.poll()["status"], "envelope_published_not_admitted")
        first = (self.root / "next_use-envelope.json").read_bytes()
        envelope = json.loads(first)
        self.put(
            "next_use-lifecycle.jsonl",
            encoded(
                dict(
                    next_use_lifecycle_v=1,
                    program_ordinal=1,
                    program_id=envelope["id"],
                    terminal_seq=5,
                    reason="completed",
                    journal_closed=True,
                )
            ),
        )
        self.assertNotEqual(
            scheduler.poll()["status"], "envelope_published_not_admitted"
        )
        # Append, don't rewrite, the independently valid second public episode.
        more = rows(("whistling", "sound_high"), ("whistling", "sound_normal"))[:-1]
        self.put("events.jsonl", wire(*more))
        self.put("next_use-schedule.jsonl", encoded(record()) + encoded(record(6)))
        self.assertEqual(scheduler.poll()["status"], "envelope_published_not_admitted")
        self.assertTrue((self.root / "next_use-envelope.2.json").exists())
        self.assertEqual((self.root / "next_use-envelope.json").read_bytes(), first)

    def append_action(self, count):
        self.put(
            "events.jsonl", wire(*rows(*(("whistling", "sound_high"),) * count)[:-1])
        )
        self.put(
            "next_use-schedule.jsonl",
            b"".join(encoded(record(3 + 3 * i)) for i in range(count)),
        )

    def close_program(self, ordinal, seq, reason="completed"):
        name = (
            "next_use-envelope.json"
            if ordinal == 1
            else f"next_use-envelope.{ordinal}.json"
        )
        envelope = json.loads((self.root / name).read_text())
        path = self.root / "next_use-lifecycle.jsonl"
        with path.open("ab") as stream:
            stream.write(
                encoded(
                    dict(
                        next_use_lifecycle_v=1,
                        program_ordinal=ordinal,
                        program_id=envelope["id"],
                        terminal_seq=seq,
                        reason=reason,
                        journal_closed=reason != "rejected",
                    )
                )
            )
        path.chmod(0o600)

    def test_no_receipt_no_advance_even_with_fresh_actions(self):
        scheduler = NextUseScheduler(self.root, seed=0, programs=3)
        scheduler.poll()
        self.append_action(2)
        self.assertEqual(scheduler.poll()["status"], "already_published")
        self.assertFalse((self.root / "next_use-envelope.2.json").exists())

    def test_rejected_and_expired_are_not_republished_and_cap_survives_restart(self):
        scheduler = NextUseScheduler(self.root, seed=0, programs=3)
        for ordinal, reason in enumerate(
            ("rejected", "program_expired", "completed"), 1
        ):
            self.append_action(ordinal)
            result = scheduler.poll()
            self.assertEqual(result["status"], "envelope_published_not_admitted")
            self.assertEqual(result["program"], ordinal)
            self.close_program(ordinal, 2 + 3 * ordinal, reason)
            scheduler = NextUseScheduler(self.root, seed=0, programs=3)
        self.append_action(4)
        self.assertEqual(scheduler.poll()["status"], "cap_reached")
        self.assertEqual(len(list(self.root.glob("next_use-envelope*.json"))), 3)

    def test_completion_at_terminal_boundary_cannot_fund_next_program(self):
        scheduler = NextUseScheduler(self.root, seed=0, programs=3)
        scheduler.poll()
        self.append_action(2)
        self.close_program(1, 8)
        scheduler.poll()
        self.assertFalse((self.root / "next_use-envelope.2.json").exists())
        self.append_action(3)
        self.assertEqual(scheduler.poll()["status"], "envelope_published_not_admitted")

    def series(self, repair):
        from chaos.next_use_compose import lua_source

        scheduler = NextUseScheduler(self.root, seed=0, programs=3, repair=repair)
        found = []
        for ordinal in (1, 2, 3):
            self.append_action(ordinal)
            self.assertEqual(scheduler.poll()["program"], ordinal)
            name = (
                "next_use-envelope.json"
                if ordinal == 1
                else f"next_use-envelope.{ordinal}.json"
            )
            envelope = json.loads((self.root / name).read_text())
            op = next(
                op
                for op in ("quiet", "whistle_attention")
                if envelope["source"] == lua_source(op)
            )
            found.append((op, envelope["ttl"]))
            self.close_program(ordinal, 2 + 3 * ordinal, "completed")
        return found

    def test_recurrence_repair_later_programs_author_the_effect(self):
        # Program 1 keeps its seeded choice (seed 0 picks the effect); programs
        # 2-3 never draw quiet and live 300 moves.
        self.assertEqual(
            self.series(repair=True),
            [("whistle_attention", 100), ("whistle_attention", 300)] * 1
            + [("whistle_attention", 300)],
        )

    def test_without_repair_later_programs_keep_the_seeded_quiet(self):
        # The pre-repair rules (a v3 ordinary-choice record): seeds 1 and 2
        # pick quiet from the two-row menu, and every program lives 100 moves.
        self.assertEqual(
            self.series(repair=False),
            [("whistle_attention", 100), ("quiet", 100), ("quiet", 100)],
        )

    def test_repair_requires_the_m2_cap(self):
        with self.assertRaises(ValueError):
            NextUseScheduler(self.root, seed=0, programs=1, repair=True)
        with self.assertRaises(ValueError):
            NextUseScheduler(self.root, seed=0, programs=3, repair=1)

    def test_legacy_single_program_ignores_lifecycle_and_new_origins(self):
        scheduler = NextUseScheduler(self.root, seed=0, programs=1)
        scheduler.poll()
        self.close_program(1, 5)
        self.append_action(2)
        self.assertEqual(scheduler.poll()["status"], "already_published")
        self.assertEqual(
            NextUseScheduler(self.root, seed=0).poll()["status"], "already_published"
        )

    def test_lifecycle_partial_row_waits_and_wrong_identity_fails_closed(self):
        scheduler = NextUseScheduler(self.root, seed=0, programs=3)
        scheduler.poll()
        self.close_program(1, 5)
        path = self.root / "next_use-lifecycle.jsonl"
        raw = path.read_bytes()
        self.put(path.name, raw[:-1])
        self.append_action(2)
        scheduler.poll()
        self.assertFalse((self.root / "next_use-envelope.2.json").exists())
        self.put(path.name, raw)
        self.assertEqual(scheduler.poll()["status"], "envelope_published_not_admitted")
        row = json.loads(raw)
        row["program_id"] += 999
        self.put(path.name, encoded(row))
        with self.assertRaisesRegex(ValueError, "identity"):
            NextUseScheduler(self.root, seed=0, programs=3).poll()
