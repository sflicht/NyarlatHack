"""Current policy tests, independent of historical recordings and readers."""

import ctypes as C
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_protocol_contract import Request, state_type

ROOT = Path(__file__).resolve().parents[2]
State = state_type()
MAX = 2147483647


class IO(C.Structure):
    _fields_ = [(x, C.c_int) for x in "dir events journal busy failed".split()]


class Context(C.Structure):
    _fields_ = [("turn", C.c_long)] + [
        (x, C.c_int)
        for x in "sanity insight eligible hp hp_max power power_max".split()
    ]


SHOW = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_int, C.c_int)


class CosmeticCore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        lib = Path(cls.tmp.name) / "core.so"
        subprocess.run(
            [
                "cc",
                "-std=c99",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-shared",
                "-fPIC",
                "-I" + str(ROOT / "include"),
                str(ROOT / "src/chaos_protocol.c"),
                str(ROOT / "src/chaos_io.c"),
                str(ROOT / "tests/chaos/cosmetic_layout.c"),
                "-o",
                str(lib),
            ],
            check=True,
            timeout=25,
        )
        cls.c = C.CDLL(str(lib))
        cls.c.cosmetic_layout.restype = C.c_size_t
        cls.c.chaos_admit.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.c_long,
            C.c_int,
            C.c_int,
        ]
        cls.c.chaos_reason.restype = C.c_char_p
        # Never initialize an allocation smaller than the native struct.
        assert C.sizeof(State) >= cls.c.cosmetic_layout(0)
        if cls.c.cosmetic_layout(1):
            assert C.sizeof(State) == cls.c.cosmetic_layout(0)
            assert State.cosmetic_seen.offset == cls.c.cosmetic_layout(1)
            assert State.cosmetic_last_turn.offset == cls.c.cosmetic_layout(2)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def fresh(self):
        s = State()
        self.c.chaos_state_init(C.byref(s))
        s.safe = 1
        return s

    def admit(self, s, value=1, turn=0, kind=0, sanity=0):
        r = Request(
            1, s.last_id + 1, kind, value, 0 if kind == 0 else 5, kind + 1, int(s.safe)
        )
        return self.c.chaos_admit(C.byref(s), C.byref(r), turn, sanity, 1)

    def test_layout(self):
        self.assertEqual(self.c.cosmetic_layout(0), C.sizeof(State))
        for i, k in enumerate(("cosmetic_seen", "cosmetic_last_turn"), 1):
            self.assertEqual(self.c.cosmetic_layout(i), getattr(State, k).offset)

    def test_independent_spending(self):
        s = self.fresh()
        self.assertEqual(self.admit(s), 0)
        self.assertEqual(s.spent, 0)
        self.assertEqual((s.cosmetic_seen, s.cosmetic_last_turn), (1, 0))
        self.assertEqual(self.admit(s, 2, 50), 0)
        self.assertEqual(self.admit(s, 2, 51, 2, 90), 0)
        self.assertEqual((s.spent, s.reserved), (3, 3))
        s = self.fresh()
        s.spent = 12
        self.assertEqual(self.admit(s), 0)
        self.assertEqual(s.spent, 12)

    def test_spacing_repeats_depletion(self):
        s = self.fresh()
        self.assertEqual(self.admit(s), 0)
        for value, turn, reason in [
            (1, 50, 12),
            (2, 0, 11),
            (2, 49, 11),
            (2, 50, 0),
            (3, 49, 11),
            (3, 100, 0),
            (1, 150, 10),
        ]:
            self.assertEqual(self.admit(s, value, turn), reason)
        self.assertEqual((s.cosmetic_seen, s.cosmetic_last_turn), (7, 100))
        self.assertEqual(
            [self.c.chaos_reason(i).decode() for i in (10, 11, 12)],
            ["cosmetic_budget", "cosmetic_cooldown", "cosmetic_repeat"],
        )

    def test_invalid_state_atomic(self):
        for seen, last in [(-1, 0), (8, 0), (0, 1), (1, -1), (1, MAX + 1)]:
            s = self.fresh()
            s.cosmetic_seen = seen
            s.cosmetic_last_turn = last
            before = bytes(s)
            self.assertEqual(self.admit(s), 1)
            self.assertEqual(bytes(s), before)

    def test_masks_clocks_helpers(self):
        for mask in range(8):
            s = self.fresh()
            s.cosmetic_seen = mask
            self.assertEqual(self.c.chaos_state_valid(C.byref(s)), 1)
            before = bytes(s)
            self.assertEqual(self.c.chaos_spend_non_effect(C.byref(s), 0, 1), 0)
            s.spent -= 1
            self.assertEqual(bytes(s), before)
        for turn in (-1, MAX + 1):
            s = self.fresh()
            self.assertEqual(self.admit(s, turn=turn), 7)
        s = self.fresh()
        s.cosmetic_seen = 1
        s.cosmetic_last_turn = MAX
        self.assertEqual(self.admit(s, 2, MAX), 11)
        self.assertEqual(self.admit(s, 2, MAX - 1), 11)

    def test_null_and_schedule(self):
        # Old implementation is known to dereference null; gate only that unsafe probe.
        if self.c.cosmetic_layout(1):
            s = self.fresh()
            r = Request(1, 1, 0, 1, 0, 1, 1)
            self.assertEqual(self.c.chaos_admit(None, C.byref(r), 0, 0, 1), 1)
            self.assertEqual(self.c.chaos_admit(C.byref(s), None, 0, 0, 1), 1)
        s = self.fresh()
        r = Request(1, 1, 0, 1, 0, 1, 2)
        self.assertEqual(self.c.chaos_admit(C.byref(s), C.byref(r), 0, 0, 1), 9)
        self.assertEqual(s.last_id, 0)
        s.safe = 3
        self.assertEqual(self.c.chaos_admit(C.byref(s), C.byref(r), 0, 0, 1), 4)
        self.assertEqual(s.last_id, 1)

    def test_sequence_transaction_boundaries(self):
        for headroom in (1, 2):
            with (
                self.subTest(headroom=headroom),
                tempfile.TemporaryDirectory() as directory,
            ):
                s = self.fresh()
                s.safe = 0
                s.seq = MAX - headroom
                req = dict(
                    v=1,
                    id=1,
                    mutation="ambient",
                    value=1,
                    duration=0,
                    telegraph=1,
                    at=1,
                )
                Path(directory, "whisper.json").write_text(json.dumps(req))
                io = IO()
                self.assertEqual(
                    self.c.chaos_io_open(C.byref(io), directory.encode()), 1
                )
                calls = []

                @SHOW
                def show(arg, signal, value):
                    calls.append(
                        (s.spent, s.reserved, s.cosmetic_seen, s.cosmetic_last_turn)
                    )
                    return 1

                context = Context(10, 0, 0, 1, 0, 0, 0, 0)
                self.c.chaos_io_safe(
                    C.byref(io), C.byref(s), C.byref(context), b"pray", show, None
                )
                self.c.chaos_io_close(C.byref(io))
                rows = [
                    json.loads(x)
                    for x in Path(directory, "events.jsonl").read_text().splitlines()
                ]
                journal = json.loads(Path(directory, "whispers.jsonl").read_text())
                self.assertEqual(
                    journal,
                    dict(
                        req,
                        policy=2,
                        turn=10,
                        safe=1,
                        status="admitted",
                        cost=0,
                        cosmetic_cost=1,
                        expires=0,
                    ),
                )
                self.assertEqual((s.last_id, s.seq), (1, MAX))
                self.assertEqual(
                    [r["event"] for r in rows],
                    ["safe_point"] if headroom == 1 else ["safe_point", "telegraph"],
                )
                self.assertEqual(calls, [] if headroom == 1 else [(0, 0, 0, 0)])
                self.assertEqual((s.spent, s.reserved), (0, 0))
                self.assertEqual(
                    (s.cosmetic_seen, s.cosmetic_last_turn),
                    (0, 0) if headroom == 1 else (1, 10),
                )
                # Saturation fails emission without an OS write error.
                self.assertEqual(io.failed, 0)

    def test_transport_transactions(self):
        for mode in ("ok", "ui", "journal", "event", "ack", "safe", "seq", "deny"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                s = self.fresh()
                s.safe = 0
                if mode == "safe":
                    s.safe = MAX
                if mode == "seq":
                    s.seq = MAX
                if mode == "deny":
                    s.cosmetic_seen = 1
                req = dict(
                    v=1,
                    id=1,
                    mutation="ambient",
                    value=1,
                    duration=0,
                    telegraph=1,
                    at=1,
                )
                Path(directory, "whisper.json").write_text(json.dumps(req))
                io = IO()
                self.assertEqual(
                    self.c.chaos_io_open(C.byref(io), directory.encode()), 1
                )
                if mode in ("journal", "event"):
                    fd = os.open("/dev/full", os.O_WRONLY)
                    field = "journal" if mode == "journal" else "events"
                    os.close(getattr(io, field))
                    setattr(io, field, fd)
                calls = []

                @SHOW
                def show(arg, signal, value):
                    calls.append((s.spent, s.cosmetic_seen))
                    if mode == "ack":
                        os.close(io.events)
                        io.events = os.open("/dev/full", os.O_WRONLY)
                    return int(mode != "ui")

                context = Context(10, 0, 0, 1, 0, 0, 0, 0)
                self.c.chaos_io_safe(
                    C.byref(io), C.byref(s), C.byref(context), b"pray", show, None
                )
                self.c.chaos_io_close(C.byref(io))
                self.assertEqual(s.spent, 0)
                committed = mode in ("ok", "ack")
                self.assertEqual(
                    s.cosmetic_seen, 1 if committed or mode == "deny" else 0
                )
                self.assertEqual(calls, [(0, 0)] if mode in ("ok", "ui", "ack") else [])
                rows = [
                    json.loads(x)
                    for x in Path(directory, "events.jsonl").read_text().splitlines()
                ]
                for row in rows:
                    self.assertEqual(row["v"], 3)
                    self.assertIn("cosmetic", row)
                if mode == "ok":
                    self.assertEqual(
                        [r["cosmetic"] for r in rows],
                        [
                            dict(seen=0, last_turn=0),
                            dict(seen=0, last_turn=0),
                            dict(seen=1, last_turn=10),
                        ],
                    )
                    self.assertEqual([r["seq"] for r in rows], [1, 2, 3])
                    self.assertEqual(
                        (rows[-1]["cost"], rows[-1]["cosmetic_cost"]), (0, 1)
                    )
                    journal = json.loads(Path(directory, "whispers.jsonl").read_text())
                    self.assertEqual(
                        (
                            journal["v"],
                            journal["policy"],
                            journal["cost"],
                            journal["cosmetic_cost"],
                        ),
                        (1, 2, 0, 1),
                    )
                if mode in ("ui", "journal", "ack"):
                    self.assertEqual(s.last_id, 1)
