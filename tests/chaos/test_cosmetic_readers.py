"""Synthetic version/pacing fixtures, never native delivery evidence."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chaos import protocol as p
from chaos.director import State, Mailbox, RandomBackend, eligible
from chaos.episodes import parse_episode_event, project_episodes
from chaos.history import HistoryState
from chaos.model import ModelBackend
from test_director import event, ack, REQ
from test_episodes import enabled, session, action, wire


def current(row=None, seen=0, last=0, **kw):
    row = dict(event() if row is None else row)
    row.update(v=4 if row["v"] == 2 else 3, cosmetic=dict(seen=seen, last_turn=last))
    row.update(kw)
    return row


def accepted(seq=2, value=1, seen=1, turn=10, **kw):
    return current(
        ack(seq),
        seen,
        turn,
        turn=turn,
        value=value,
        cost=0,
        cosmetic_cost=1,
        expires=0,
        spent=0,
        budget=2,
        **kw,
    )


class CosmeticReaders(unittest.TestCase):
    def parse(self, row):
        return p.parse_event(json.dumps(row, ensure_ascii=False))

    def test_legacy_bounds_loose_ack_extras_and_reasons(self):
        row = ack(status="rejected", detail="ok", cost=999, expires=99, hidden="kept")
        self.assertEqual(self.parse(row), row)
        self.assertEqual(self.parse(event()), event())
        for bad in (ack(detail="cosmetic_repeat"), event(v=True), event(spent=13)):
            with self.assertRaises(ValueError):
                self.parse(bad)
        # Historical raw character cap is deliberately not UTF-8 byte length.
        row = event(extra="é" * 2000)
        self.assertEqual(self.parse(row), row)

    def test_current_shape_and_explicit_request_projection(self):
        row = accepted()
        self.assertEqual(self.parse(row), row)
        for cosmetic in (
            None,
            {},
            {"seen": True, "last_turn": 0},
            {"seen": 8, "last_turn": 0},
            {"seen": 0, "last_turn": 1},
            {"seen": 1, "last_turn": 11},
            {"seen": 1, "last_turn": 0, "extra": 0},
        ):
            with self.subTest(cosmetic=cosmetic), self.assertRaises(ValueError):
                self.parse(dict(row, cosmetic=cosmetic))
        bad = dict(row)
        del bad["cosmetic"]
        with self.assertRaises(ValueError):
            self.parse(bad)
        for key in ("cost", "cosmetic_cost", "policy", "cosmetic"):
            with self.assertRaises(ValueError):
                p.encode_request(dict(REQ, **{key: 0}))

    def test_current_tariffs_rejected_and_sentinel(self):
        for name, value, duration, telegraph, cost, cosmetic_cost in (
            ("ambient", 1, 0, 1, 0, 1),
            ("ward_efficacy", 50, 1, 2, 4, 0),
            ("hunger_rate", 2, 1, 3, 3, 0),
        ):
            row = current(
                ack(),
                status="rejected",
                detail="budget",
                mutation=name,
                value=value,
                duration=duration,
                telegraph=telegraph,
                cost=cost,
                cosmetic_cost=cosmetic_cost,
                expires=0,
            )
            self.assertEqual(self.parse(row), row)
            for key in ("cost", "cosmetic_cost"):
                with self.assertRaises(ValueError):
                    self.parse(dict(row, **{key: row[key] + 1}))
        sentinel = current(
            ack(),
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
            cosmetic_cost=0,
        )
        self.assertEqual(self.parse(sentinel), sentinel)
        with self.assertRaises(ValueError):
            self.parse(dict(sentinel, cosmetic_cost=1))

    def test_state_precommit_ack_receipt_and_no_reconstruction(self):
        state = State()
        state.ingest(current())
        state.ingest(current(event(2, event="telegraph", detail="ambient", last_id=1)))
        state.ingest(accepted(3))
        self.assertEqual(state.accepted[1], REQ)
        self.assertEqual(state.accepted_receipts[1], accepted(3))
        state.ingest(current(session(4, "restore", safe=1, last_id=2), 3, 60, turn=60))
        self.assertEqual(set(state.accepted), {1})
        # General reader can start on a restored nonzero authoritative snapshot.
        other = State()
        other.ingest(current(session(detail="restore"), 3, 10))
        self.assertEqual(other.latest["cosmetic"]["seen"], 3)

    def test_state_rejects_unexplained_changes_and_policy_mix(self):
        pairs = [
            (current(), current(event(2), 1, 10)),
            (current(seen=1, last=10), current(event(2), 2, 10)),
            (current(seen=1, last=10), current(event(2), 1, 11, turn=11)),
            (current(), accepted(2, seen=3)),
            (current(seen=1, last=10), accepted(2, value=2, seen=3, turn=59)),
            (
                current(),
                current(
                    ack(),
                    1,
                    10,
                    status="rejected",
                    detail="log_failure",
                    cost=0,
                    cosmetic_cost=1,
                    expires=0,
                ),
            ),
            (current(), event(2)),
            (event(), current(event(2))),
            (current(seen=1, last=10), current(session(2), 1, 10, safe=1)),
        ]
        for first, second in pairs:
            with self.subTest(second=second):
                state = State()
                state.ingest(first)
                with self.assertRaises(ValueError):
                    state.ingest(second)
                self.assertEqual(state.latest, first)

    def test_history_current_projection_and_legacy_price(self):
        rows = [enabled(), session(2)]
        action(rows, "fountain_drink", "water_refreshed")
        old = HistoryState(wire(*rows))
        new = HistoryState(wire(*(current(row) for row in rows)))
        self.assertEqual(new.episodes, old.episodes)
        with self.assertRaises(ValueError):
            State().ingest(current(enabled()))
        for v in (2, 4):
            row = enabled()
            if v == 4:
                row = current(row)
            self.assertEqual(parse_episode_event(wire(row).strip()), row)
            with self.assertRaises(ValueError):
                parse_episode_event(wire(dict(row, extra=0)).strip())
        rows = [session(), ack(2, expires=0)]
        self.assertIn(1, HistoryState(wire(*rows)).accepted)

    def test_full_history_restore_marker_pair(self):
        rows = [current(enabled()), current(session(2)), current(event(3))]
        marker = current(enabled(4), 1, 10, safe=1, last_id=1)
        restore = current(session(5, "restore", safe=1, last_id=1), 1, 10)
        state = HistoryState(wire(*rows, marker, restore))
        self.assertEqual(state.accepted, {})
        for suffix in (
            (marker,),
            (marker, dict(restore, cosmetic=dict(seen=3, last_turn=10))),
            (current(enabled(4), 1, 10, safe=1), current(event(5), 1, 10)),
        ):
            with self.assertRaises(ValueError):
                HistoryState(wire(*rows, *suffix))
        for bad in (
            wire(current(session(), 1, 10)),
            wire(current(enabled(), 1, 10), current(session(2), 1, 10)),
            wire(current(session()), event(2)),
        ):
            with self.assertRaises(ValueError):
                project_episodes(bad)

    def test_random_native_eligibility_and_preferred_unused_values(self):
        state = State()
        state.ingest(current(seen=3, last=10, turn=60, budget=0, spent=12))
        self.assertEqual(eligible(state), ["ambient"])
        for seed in range(12):
            self.assertEqual(RandomBackend(seed).choose(state, 1, 2)["value"], 3)
        for seen, turn in ((3, 59), (7, 60)):
            state = State()
            state.ingest(current(seen=seen, last=10, turn=turn, budget=0, spent=12))
            self.assertEqual(eligible(state), [])
        state = State()
        state.ingest(current(sanity=0, budget=12))
        self.assertIn("ambient", eligible(state, True))
        for seed in range(12):
            self.assertIn(
                RandomBackend(seed, True).choose(state, 1, 2)["mutation"],
                ("ward_efficacy", "hunger_rate"),
            )

    def test_model_local_fake_transport_value_menu(self):
        # No HTTP/network/provider call: exercise real request/response logic.
        class Response:
            status = 200
            fp = None

            def __init__(self, value):
                self.raw = json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(dict(REQ, value=value, at=2))
                                }
                            }
                        ]
                    }
                ).encode()

            def read1(self, _):
                raw, self.raw = self.raw, b""
                return raw

        captured = []

        class Connection:
            value = 3

            def __init__(self, *a, **kw):
                pass

            def request(self, *a, **kw):
                captured.append(json.loads(kw["body"]))

            def getresponse(self):
                return Response(self.value)

            def close(self):
                pass

        state = State()
        state.ingest(current(seen=3, last=10, turn=60, budget=0, spent=12))
        with (
            patch.dict("os.environ", {"COSMETIC_FAKE_KEY": "local-test"}),
            patch("chaos.model.http.client.HTTPConnection", Connection),
        ):
            backend = ModelBackend(
                "http://127.0.0.1/fake",
                "fake",
                "COSMETIC_FAKE_KEY",
                allow_local_http=True,
            )
            self.assertEqual(backend.choose(state, 1, 2)["value"], 3)
            prompt = json.loads(captured[-1]["messages"][1]["content"])
            self.assertEqual(prompt["allowed_values"], {"ambient": [3]})
            Connection.value = 1
            with self.assertRaises(ValueError):
                backend.choose(state, 1, 2)
            state = State()
            state.ingest(current(sanity=0, budget=12))
            with self.assertRaises(ValueError):
                backend.choose(state, 1, 2)
            prompt = json.loads(captured[-1]["messages"][1]["content"])
            self.assertEqual(prompt["eligible"], ["ward_efficacy"])

    def test_historical_state_cannot_publish_current_mailbox(self):
        state = State()
        state.ingest(event())
        with tempfile.TemporaryDirectory() as tmp, Mailbox(tmp) as box:
            with self.assertRaises(ValueError):
                box.submit(dict(REQ, at=2), state)
            self.assertFalse((Path(tmp) / "whisper.json").exists())

    def test_failed_ui_and_restore_never_discharge_pending_mailbox(self):
        state = State()
        state.ingest(current())
        with tempfile.TemporaryDirectory() as tmp, Mailbox(tmp) as box:
            request = dict(REQ, at=2)
            box.submit(request, state)
            state.ingest(
                current(
                    event(2, event="telegraph", detail="ambient", safe=2, last_id=1)
                )
            )
            self.assertEqual(box.pending(state, known=request), request)
            state.ingest(current(session(3, "restore", safe=2, last_id=1), 1, 10))
            with self.assertRaisesRegex(ValueError, "exact ACK"):
                box.pending(state)
            self.assertEqual(state.accepted_receipts, {})
        state = State()
        state.ingest(current())
        rejection = current(
            ack(),
            cost=0,
            cosmetic_cost=1,
            expires=0,
            status="rejected",
            detail="log_failure",
            spent=0,
            budget=2,
        )
        state.ingest(rejection)
        self.assertEqual(state.accepted, {})
        self.assertEqual(state.latest["cosmetic"], dict(seen=0, last_turn=0))

    def test_pending_marker_cannot_publish_history(self):
        from chaos.director import ScheduleBackend
        from chaos.history_director import run_history

        rows = [
            current(enabled()),
            current(session(2)),
            current(event(3)),
            current(enabled(4), 1, 10, safe=1, last_id=1),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_bytes(wire(*rows))
            path.chmod(0o600)
            with self.assertRaises(ValueError):
                run_history(
                    tmp,
                    ScheduleBackend([dict(REQ, id=2, at=2)]),
                    max_runtime=0.05,
                    poll=0.01,
                    install_only=True,
                )
            self.assertFalse((Path(tmp) / "whisper.json").exists())

    def test_model_prompt_current_tariff_and_value_constraint(self):
        text = (
            Path(__file__).resolve().parents[2] / "chaos/prompts/director.txt"
        ).read_text()
        self.assertIn("allowed_values", text)
        self.assertIn("mechanical cost 0; cosmetic cost 1", text)
