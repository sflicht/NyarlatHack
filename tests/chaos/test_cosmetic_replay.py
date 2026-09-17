"""Synthetic current-policy receipt tests; archived recordings stay unchanged."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from chaos.director import load_replay
from chaos.history_director import load_history_replay
from test_director import event, ack, REQ
from test_episodes import session, enabled, wire
from test_cosmetic_readers import current, accepted


class CosmeticReplay(unittest.TestCase):
    def fixture(self, name="ambient", legacy=False, mixed=False):
        req = dict(REQ)
        if name == "hunger_rate":
            req.update(mutation=name, value=2, duration=10, telegraph=3)
        rows = [session(), event(2)]
        if name == "ambient":
            receipt = accepted(3)
        else:
            receipt = current(
                ack(
                    3, req, sanity=70, budget=2, spent=3, reserved=3, cost=3, expires=20
                ),
                cosmetic_cost=0,
            )
        rows = [current(r) for r in rows] + [receipt]
        if legacy:
            for r in rows:
                r["v"] = 1
                del r["cosmetic"]
            rows[-1].pop("cosmetic_cost")
            if name == "ambient":
                rows[-1].update(cost=1, spent=1, budget=1)
        if mixed:
            rows = [current(enabled())] + [dict(r, seq=r["seq"] + 1) for r in rows]
        journal = dict(
            req,
            policy=2,
            turn=10,
            safe=1,
            status="admitted",
            cost=0 if name == "ambient" else 3,
            cosmetic_cost=1 if name == "ambient" else 0,
            expires=0 if name == "ambient" else 20,
        )
        return req, rows, journal

    def load(self, loader, rows, journals, partial=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = root / "events.jsonl"
            journal = root / "whispers.jsonl"
            events.write_bytes(wire(*rows) + (b'{"v":' if partial else b""))
            journal.write_bytes(wire(*journals))
            events.chmod(0o600)
            journal.chmod(0o600)
            result = loader(journal, events)
            self.assertFalse((root / "whisper.json").exists())
            return result

    def test_current_accepted_ambient_and_hunger(self):
        for loader in (load_replay, load_history_replay):
            for name in ("ambient", "hunger_rate"):
                req, rows, journal = self.fixture(name)
                with self.subTest(loader=loader.__name__, name=name):
                    self.assertEqual(self.load(loader, rows, [journal]), [req])
        req, rows, journal = self.fixture(mixed=True)
        self.assertEqual(self.load(load_history_replay, rows, [journal]), [req])

    def test_policy_cross_product_including_empty_and_mechanical(self):
        for loader in (load_replay, load_history_replay):
            for name in ("ambient", "hunger_rate"):
                for old_evidence in (False, True):
                    for old_journal in (False, True):
                        if not old_evidence and not old_journal:
                            continue
                        _, rows, journal = self.fixture(name, legacy=old_evidence)
                        if old_journal:
                            journal.pop("policy")
                            journal.pop("cosmetic_cost")
                        with (
                            self.subTest(
                                loader=loader.__name__,
                                name=name,
                                old_evidence=old_evidence,
                                old_journal=old_journal,
                            ),
                            self.assertRaises(ValueError),
                        ):
                            self.load(loader, rows, [journal])
            for rows in ([], [session()], [current(session()), event(2)]):
                with (
                    self.subTest(loader=loader.__name__, rows=rows),
                    self.assertRaises(ValueError),
                ):
                    self.load(loader, rows, [])
            self.assertEqual(self.load(loader, [current(session())], []), [])

    def test_every_journal_field_is_exact_and_typed(self):
        for loader in (load_replay, load_history_replay):
            for name in ("ambient", "hunger_rate"):
                _, rows, journal = self.fixture(name)
                for key in journal:
                    changes = [None]
                    if type(journal[key]) is int:
                        changes += [True, journal[key] + 1, float(journal[key])]
                    else:
                        changes += ["accepted", "rejected"]
                    for value in changes:
                        changed = dict(journal, **{key: value})
                        if changed == journal and type(value) is type(journal[key]):
                            continue
                        with (
                            self.subTest(loader=loader.__name__, key=key, value=value),
                            self.assertRaises(ValueError),
                        ):
                            self.load(loader, rows, [changed])
                    changed = dict(journal)
                    del changed[key]
                    with self.subTest(missing=key), self.assertRaises(ValueError):
                        self.load(loader, rows, [changed])
                with self.assertRaises(ValueError):
                    self.load(loader, rows, [dict(journal, extra=0)])

    def test_missing_ack_failed_ui_restore_and_partial(self):
        for loader in (load_replay, load_history_replay):
            _, rows, journal = self.fixture()
            variants = [
                rows[:-1],
                rows[:-1]
                + [
                    current(
                        ack(3),
                        status="rejected",
                        detail="log_failure",
                        cost=0,
                        cosmetic_cost=1,
                        expires=0,
                    )
                ],
                rows[:-1] + [current(session(3, "restore", safe=1, last_id=1), 1, 10)],
            ]
            for variant in variants:
                with (
                    self.subTest(loader=loader.__name__, variant=variant),
                    self.assertRaises(ValueError),
                ):
                    self.load(loader, variant, [journal])
            with self.assertRaises(ValueError):
                self.load(loader, rows, [journal], partial=True)

    def test_receipt_tampering_and_malformed_sentinel(self):
        for loader in (load_replay, load_history_replay):
            _, rows, journal = self.fixture("hunger_rate")
            for key, value in (
                ("cost", 0),
                ("cosmetic_cost", 1),
                ("turn", 11),
                ("safe", 2),
                ("expires", 21),
                ("status", "admitted"),
                ("phase", "attempt"),
                ("cost", True),
            ):
                altered = copy.deepcopy(rows)
                altered[-1][key] = value
                with (
                    self.subTest(loader=loader.__name__, key=key),
                    self.assertRaises(ValueError),
                ):
                    self.load(loader, altered, [journal])
            sentinel = current(
                ack(3),
                status="rejected",
                detail="schema",
                id=0,
                mutation="",
                value=0,
                duration=0,
                telegraph=0,
                at=0,
                expires=0,
                cost=0,
                cosmetic_cost=1,
            )
            with self.assertRaises(ValueError):
                self.load(loader, rows[:2] + [sentinel], [])

    def test_schedule_order_and_journal_caps_retained(self):
        for loader in (load_replay, load_history_replay):
            req, rows, journal = self.fixture("hunger_rate")
            ambient = dict(REQ, id=3, at=2)
            rows += [
                current(
                    event(4, safe=2, turn=11, sanity=70, last_id=1, spent=3, reserved=3)
                ),
                accepted(5, turn=11, id=3, at=2, safe=2, last_id=3),
            ]
            rows[-1].update(spent=3, reserved=3, sanity=70)
            second = dict(
                ambient,
                policy=2,
                turn=11,
                safe=2,
                status="admitted",
                cost=0,
                cosmetic_cost=1,
                expires=0,
            )
            self.assertEqual(self.load(loader, rows, [journal, second]), [req, ambient])
            for journals in ([second, journal], [journal, journal]):
                with self.assertRaises(ValueError):
                    self.load(loader, rows, journals)
            module = (
                "chaos.director" if loader == load_replay else "chaos.history_director"
            )
            with patch(module + ".DEFAULT_EVENTS", 1), self.assertRaises(ValueError):
                self.load(loader, rows, [journal, second])
            with patch(module + ".DEFAULT_BYTES", 1), self.assertRaises(ValueError):
                self.load(loader, rows, [journal])

    def test_history_actual_source_change_rejected(self):
        from chaos.director import secure_open

        _, rows, journal = self.fixture(mixed=True)

        def change_source(path):
            source = Path(path).parent / "events.jsonl"
            source.write_bytes(source.read_bytes().replace(b'"pray"', b'"changed"'))
            return secure_open(path)

        with patch("chaos.history_director.secure_open", side_effect=change_source):
            with self.assertRaisesRegex(ValueError, "evidence changed"):
                self.load(load_history_replay, rows, [journal])

    def test_history_exact_readback_retained(self):
        _, rows, journal = self.fixture(mixed=True)
        with patch(
            "chaos.history_director._exact_source", return_value=False
        ) as reread:
            with self.assertRaisesRegex(ValueError, "evidence changed"):
                self.load(load_history_replay, rows, [journal])
            reread.assert_called_once()
