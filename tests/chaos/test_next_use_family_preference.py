"""Arc 1 director family preference: public felt receipts only.

The scheduler may narrow its choice to the family the player most recently
felt, among origins already ready at this exact safe point. It never waits for
that family, never retimes, never reads private journals, and keeps the M2
rules (terminal receipt first, fresh origin, cap 3, no republication).
"""

import json
from pathlib import Path
import tempfile
import unittest

from chaos.next_use_schedule import (
    NextUseScheduler,
    parse_felt,
    preferred_family,
)
from test_episodes import wire
from test_next_use_history import rows
from test_next_use_schedule_robustness import record, encoded

W, F = ("whistling", "sound_high"), ("fountain_drink", "water_refreshed")


def felt(ordinal, family, root, program_id=2):
    return dict(
        next_use_felt_v=1,
        program_ordinal=ordinal,
        program_id=program_id,
        family=family,
        root_seq=root,
    )


class FamilyPreferenceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def put(self, name, raw):
        path = self.root / name
        path.write_bytes(raw)
        path.chmod(0o600)

    def actions(self, *ops):
        """Public history: each action is started/notice/completed rows."""
        self.put("events.jsonl", wire(*rows(*ops)[:-1]))
        self.put(
            "next_use-schedule.jsonl",
            b"".join(
                encoded(record(3 + 3 * i, "W" if op is W else "F"))
                for i, op in enumerate(ops)
            ),
        )

    def close(self, ordinal, seq):
        name = (
            "next_use-envelope.json"
            if ordinal == 1
            else f"next_use-envelope.{ordinal}.json"
        )
        envelope = json.loads((self.root / name).read_text())
        with (self.root / "next_use-lifecycle.jsonl").open("ab") as stream:
            stream.write(
                encoded(
                    dict(
                        next_use_lifecycle_v=1,
                        program_ordinal=ordinal,
                        program_id=envelope["id"],
                        terminal_seq=seq,
                        reason="completed",
                        journal_closed=True,
                    )
                )
            )
        (self.root / "next_use-lifecycle.jsonl").chmod(0o600)

    def felt_rows(self, *rows_):
        self.put("next_use-felt.jsonl", b"".join(encoded(r) for r in rows_))

    def family_of(self, ordinal):
        name = (
            "next_use-envelope.json"
            if ordinal == 1
            else f"next_use-envelope.{ordinal}.json"
        )
        envelope = json.loads((self.root / name).read_text())
        refs = envelope["origin_refs"]
        self.assertEqual(len(refs), 1)
        return refs[0]["family"]

    def second_program(self, *felt_):
        """Program 1 (W) closes; then W and F origins are both ready at once."""
        scheduler = NextUseScheduler(self.root, seed=0, programs=3)
        self.actions(W)
        self.assertEqual(scheduler.poll()["program"], 1)
        self.close(1, 5)
        if felt_:
            self.felt_rows(*felt_)
        self.actions(W, W, F)
        result = scheduler.poll()
        self.assertEqual(result["status"], "envelope_published_not_admitted")
        self.assertEqual(result["program"], 2)
        return self.family_of(2)

    def test_without_felt_history_the_earliest_ready_origin_is_kept(self):
        # Unchanged M2 order: the earliest ready completion (W at root 6).
        self.assertEqual(self.second_program(), "W")

    def test_felt_fountain_prefers_a_ready_fountain_origin(self):
        self.assertEqual(self.second_program(felt(1, 2, 3)), "F")

    def test_most_recent_felt_family_wins(self):
        self.assertEqual(
            self.second_program(felt(1, 2, 3), felt(1, 1, 3)),
            "W",
        )

    def test_preference_never_waits_for_an_absent_family(self):
        scheduler = NextUseScheduler(self.root, seed=0, programs=3)
        self.actions(W)
        scheduler.poll()
        self.close(1, 5)
        self.felt_rows(felt(1, 2, 3))  # F felt, but only W is ready now
        self.actions(W, W)
        result = scheduler.poll()
        self.assertEqual(result["status"], "envelope_published_not_admitted")
        self.assertEqual(self.family_of(2), "W")

    def test_first_program_ignores_felt_receipts(self):
        self.felt_rows(felt(1, 2, 3))
        self.actions(W, F)
        scheduler = NextUseScheduler(self.root, seed=0, programs=3)
        self.assertEqual(scheduler.poll()["program"], 1)
        self.assertEqual(self.family_of(1), "W")

    def test_legacy_single_program_never_reads_felt(self):
        self.put("next_use-felt.jsonl", b"not json\n")
        self.actions(W)
        result = NextUseScheduler(self.root, seed=0).poll()
        self.assertEqual(result["status"], "envelope_published_not_admitted")

    def test_preference_keeps_terminal_receipt_and_fresh_origin_rules(self):
        scheduler = NextUseScheduler(self.root, seed=0, programs=3)
        self.actions(W)
        scheduler.poll()
        self.felt_rows(felt(1, 2, 3))
        self.actions(W, W, F)
        # No terminal receipt yet: nothing new, felt history or not.
        self.assertEqual(scheduler.poll()["status"], "already_published")
        self.assertFalse((self.root / "next_use-envelope.2.json").exists())
        # Terminal at 14 is after every ready origin: none is fresh.
        self.close(1, 14)
        self.assertNotEqual(
            scheduler.poll()["status"], "envelope_published_not_admitted"
        )
        self.assertFalse((self.root / "next_use-envelope.2.json").exists())

    def test_published_program_is_never_republished_toward_the_preference(self):
        family = self.second_program()
        self.assertEqual(family, "W")
        first = (self.root / "next_use-envelope.2.json").read_bytes()
        self.felt_rows(felt(1, 2, 3))
        scheduler = NextUseScheduler(self.root, seed=0, programs=3)
        self.assertEqual(scheduler.poll()["status"], "already_published")
        self.assertEqual((self.root / "next_use-envelope.2.json").read_bytes(), first)

    def test_malformed_felt_receipt_fails_closed(self):
        scheduler = NextUseScheduler(self.root, seed=0, programs=3)
        self.actions(W)
        scheduler.poll()
        self.close(1, 5)
        self.put("next_use-felt.jsonl", encoded(dict(felt(1, 2, 3), extra=1)))
        self.actions(W, W)
        with self.assertRaisesRegex(ValueError, "felt receipt schema"):
            scheduler.poll()

    def test_felt_parser_and_preference_are_public_schema_only(self):
        good = felt(2, 1, 9)
        self.assertEqual(parse_felt(encoded(good)[:-1]), good)
        for bad in (
            dict(good, family=3),
            dict(good, program_ordinal=4),
            dict(good, root_seq=0),
            dict(good, family=True),
            dict(good, next_use_felt_v=2),
            {k: v for k, v in good.items() if k != "root_seq"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_felt(encoded(bad)[:-1])
        self.assertIsNone(preferred_family([]))
        self.assertEqual(preferred_family([felt(1, 1, 3), felt(2, 2, 6)]), "F")


if __name__ == "__main__":
    unittest.main()
