"""Independent v1 preservation oracle and generated/real-consumer drift tests."""

import ctypes as C
import itertools
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from chaos import protocol
from chaos.director import RandomBackend, State, eligible

ROOT = Path(__file__).resolve().parents[2]
# Deliberately independent of the production contract and generator.
ROWS = (
    ("ambient", 1, 3, 0, 0, 1, 1, 100),
    ("ward_efficacy", 50, 50, 1, 50, 2, 4, 80),
    ("hunger_rate", 2, 2, 1, 50, 3, 3, 90),
)
EVENTS = "eat read zap apply pray kill level_enter level_leave sanity insight death sleep session safe_point ack telegraph expiry haunting haunt_step backtrack curio".split()
REASONS = (
    "ok schema oversize duplicate schedule budget active ineligible log_failure".split()
)
FIELDS = "v id mutation value duration telegraph at".split()


class Request(C.Structure):
    _fields_ = [(k, C.c_int) for k in "v id kind value duration telegraph at".split()]


class Effect(C.Structure):
    _fields_ = [("value", C.c_int), ("cost", C.c_int), ("expires", C.c_long)]


def state_type(count=3):
    class NativeState(C.Structure):
        _fields_ = [(k, C.c_int) for k in "version spent reserved last_id".split()] + [
            ("seq", C.c_long),
            ("safe", C.c_long),
            ("effects", Effect * count),
        ]

    return NativeState


def compile_core(root, target):
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
            "-I" + str(root / "include"),
            str(root / "src/chaos_protocol.c"),
            "-o",
            str(target),
        ],
        check=True,
    )
    lib = C.CDLL(str(target))
    lib.chaos_parse.argtypes = [C.c_char_p, C.c_size_t, C.POINTER(Request)]
    lib.chaos_admit.argtypes = [
        C.c_void_p,
        C.POINTER(Request),
        C.c_long,
        C.c_int,
        C.c_int,
    ]
    lib.chaos_rule.argtypes = [C.c_void_p, C.c_int, C.c_long, C.c_int]
    lib.chaos_name.restype = C.c_char_p
    lib.chaos_reason.restype = C.c_char_p
    return lib


def request(name="ambient", value=1, duration=0, telegraph=1):
    return dict(
        v=1,
        id=1,
        mutation=name,
        value=value,
        duration=duration,
        telegraph=telegraph,
        at=1,
    )


def raw(obj):
    return json.dumps(obj, separators=(",", ":")).encode()


def corpus():
    base = request()
    good = raw(base)
    yield good, True
    for name, lo, hi, dlo, dhi, signal, _, _ in ROWS:
        for value, duration, telegraph in itertools.product(
            {lo - 1, lo, hi, hi + 1},
            {dlo - 1, dlo, dhi, dhi + 1},
            {0, signal, signal + 1},
        ):
            yield (
                raw(request(name, value, duration, telegraph)),
                lo <= value <= hi and dlo <= duration <= dhi and telegraph == signal,
            )
    for key in FIELDS:
        obj = dict(base)
        del obj[key]
        yield raw(obj), False
        yield good[:-1] + b"," + raw({key: base[key]})[1:], False
    for a, b in itertools.combinations(range(7), 2):
        keys = list(FIELDS)
        keys[a], keys[b] = keys[b], keys[a]
        yield raw({k: base[k] for k in keys}), True
    for key in set(FIELDS) - {"mutation"}:
        for token in [
            b"true",
            b"false",
            b"1.0",
            b"1e0",
            b'"1"',
            b"null",
            b"[]",
            b"{}",
            b"-1",
            b"-0",
            b"+1",
            b"01",
            b"2147483648",
            b"9" * 100,
        ]:
            yield (
                good.replace(raw(key) + b":" + raw(base[key]), raw(key) + b":" + token),
                False,
            )
    for key in ("id", "at", "v"):
        for n in (0, 1, 2, 2147483647, 2147483648):
            yield (
                raw(dict(base, **{key: n})),
                n == 1 if key == "v" else 1 <= n <= 2147483647,
            )
    for byte in (b" ", b"\r", b"\n", b"\t"):
        yield byte + good + byte, True
    for bad in (
        b"",
        b"[]",
        b"{}",
        good + b"{}",
        good + b"\x00",
        good[:-1],
        good[:-1] + b",}",
        b"\v" + good,
        b"\f" + good,
        good.replace(b"ambient", b"ambi\\u0065nt"),
        good.replace(b"ambient", b"Ambient"),
        good.replace(b"ambient", b"ambient\xff"),
        good.replace(b"ambient", b"ambient\x7f"),
        raw(dict(base, cost=1)),
    ):
        yield bad, False
    yield good + b" " * (512 - len(good)), True
    yield good + b" " * (513 - len(good)), False


class CompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="issue29-core-")
        cls.lib = compile_core(ROOT, Path(cls.tmp.name) / "core.so")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_differential_corpus(self):
        for payload, accepted in corpus():
            with self.subTest(payload=payload):
                r = Request()
                code = self.lib.chaos_parse(payload, len(payload), C.byref(r))
                self.assertEqual(
                    code, 0 if accepted else 2 if len(payload) > 512 else 1
                )
                if accepted:
                    obj = protocol.parse_request(payload)
                    self.assertEqual(
                        tuple(getattr(r, k) for k, _ in Request._fields_),
                        (
                            obj["v"],
                            obj["id"],
                            [x[0] for x in ROWS].index(obj["mutation"]),
                            obj["value"],
                            obj["duration"],
                            obj["telegraph"],
                            obj["at"],
                        ),
                    )
                    encoded = protocol.encode_request(obj)
                    self.assertEqual(
                        self.lib.chaos_parse(encoded, len(encoded), C.byref(r)), 0
                    )
                else:
                    with self.assertRaises(ValueError):
                        protocol.parse_request(payload)

    def test_frozen_registry_and_admission(self):
        self.assertEqual(protocol.REGISTRY, {r[0]: (r[6], r[7], r[5]) for r in ROWS})
        self.assertEqual(protocol.EVENTS, frozenset(EVENTS))
        self.assertEqual(protocol.REASONS, frozenset(REASONS))
        self.assertEqual(protocol.FIELDS, tuple(FIELDS))
        self.assertEqual(protocol.MAX_INT, 2147483647)
        self.assertEqual(C.sizeof(C.c_int), 4)
        for i, row in enumerate(ROWS):
            name, lo, _, dlo, _, signal, cost, limit = row
            self.assertEqual(self.lib.chaos_name(i), name.encode())
            self.assertEqual(self.lib.chaos_cost(i), cost)
            for sanity, food in itertools.product(
                (0, limit, limit + 1, 101), (-1, 0, 1, 2, 3)
            ):
                s = state_type()()
                self.lib.chaos_state_init(C.byref(s))
                s.safe = 1
                r = Request(1, 1, i, lo, dlo, signal, 1)
                expected = (
                    7
                    if not food or (i and sanity > limit) or (i == 2 and food != 1)
                    else 5
                    if cost > 2 + (100 - min(100, max(0, sanity))) // 10
                    else 0
                )
                self.assertEqual(
                    self.lib.chaos_admit(C.byref(s), C.byref(r), 10, sanity, food),
                    expected,
                )
                self.assertEqual(s.spent, cost if expected == 0 else 0)
                self.assertEqual(s.reserved, cost if expected == 0 and i else 0)
                self.assertTrue(self.lib.chaos_state_valid(C.byref(s)))
                if expected == 0 and i:
                    self.assertEqual(s.effects[i].expires, 10 + dlo)
                    self.assertEqual(
                        self.lib.chaos_rule(C.byref(s), i, 10, 3), 1 if i == 1 else 6
                    )
        for i, reason in enumerate(REASONS + ["future"]):
            self.assertEqual(self.lib.chaos_reason(i), reason.encode())
        self.assertEqual(self.lib.chaos_name(3), b"")
        self.assertEqual(self.lib.chaos_cost(3), 0)
        self.assertEqual(self.lib.chaos_reason(10), b"schema")

    def test_legacy_bytes_and_random(self):
        self.assertEqual(
            protocol.encode_request(request()),
            b'{"v":1,"id":1,"mutation":"ambient","value":1,"duration":0,"telegraph":1,"at":1}',
        )
        expected = json.loads(
            (ROOT / "tests/chaos/protocol_legacy_baseline.json").read_text()
        )
        s = State()
        s.latest = dict(sanity=0, budget=12)
        backend = RandomBackend(7, ordinary_food=True)
        self.assertEqual(
            [
                protocol.encode_request(backend.choose(s, i, i)).decode()
                for i in range(1, 13)
            ],
            expected["random"],
        )
        self.assertEqual(eligible(s), ["ambient", "ward_efficacy"])

    def test_legacy_event_openness(self):
        e = dict(
            v=1,
            seq=1,
            turn=0,
            safe=0,
            sanity=100,
            insight=0,
            budget=2,
            spent=0,
            reserved=0,
            last_id=0,
            event="eat",
            phase="attempt",
            detail="",
            extra={"unicode": "雪"},
        )
        self.assertEqual(protocol.parse_event(raw(e)), e)
        for name in EVENTS:
            if name != "ack":
                self.assertEqual(
                    protocol.parse_event(raw(dict(e, event=name)))["event"], name
                )
        ack = dict(
            e,
            event="ack",
            status="rejected",
            detail="ok",
            id=0,
            mutation="ambient",
            value=3,
            duration=50,
            telegraph=3,
            at=0,
            cost=12,
            expires=999,
        )
        self.assertEqual(protocol.parse_event(raw(ack)), ack)
        for reason in REASONS:
            self.assertEqual(
                protocol.parse_event(raw(dict(ack, detail=reason)))["detail"], reason
            )
        for change in ({"detail": "future"}, {"status": "accepted"}):
            with self.assertRaises(ValueError):
                protocol.parse_event(raw(dict(ack, **change)))
        for change in (
            {"detail": "x" * 257},
            {"sanity": 101},
            {"v": 2},
            {"event": "observation"},
            {"vitals": {"hp": 1}},
        ):
            with self.assertRaises(ValueError):
                protocol.parse_event(raw(dict(e, **change)))


class GenerationTests(unittest.TestCase):
    def run_generator(self, root, *args):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/generate_protocol_contract.py"),
                "--root",
                str(root),
                *args,
            ],
            capture_output=True,
        )

    def copy_root(self, root):
        for path in (
            "include/chaos_protocol.h",
            "src/chaos_protocol.c",
            "chaos/protocol.py",
            "chaos/protocol_contract.json",
            "chaos/_protocol_contract.py",
        ):
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, target)

    def test_invalid_sources_fail_without_writes(self):
        with tempfile.TemporaryDirectory(prefix="issue29-invalid-") as tmp:
            root = Path(tmp)
            self.copy_root(root)
            source = root / "chaos/protocol_contract.json"
            original = source.read_text()
            changes = [
                (("format",), True),
                (("versions", "extra"), 1),
                (("limits", "extra"), 1),
                (("budget", "extra"), 1),
                (("mutations", 0, "cost"), True),
                (("mutations", 0, "value"), [3, 1]),
                (("mutations", 0, "telegraph"), 99),
                (("mutations", 1, "id"), 0),
                (("mutations", 1, "name"), "ambient"),
                (("mutations", 1, "rule"), "unknown"),
                (("mutations", 1, "duration"), [1, 51]),
                (("request_fields", 0, "type"), "float"),
                (("ack_number_bounds",), [-1, 2147483647]),
                (("wire_order", "event"), ["seq", "v"]),
                (("vitals", 0, "wire"), "unknown"),
                (("reader_policy", "vitals_optional"), 1),
            ]
            outputs = [
                root / p
                for p in ("include/chaos_protocol.h", "chaos/_protocol_contract.py")
            ]
            before = [p.read_bytes() for p in outputs]
            for keys, value in changes:
                with self.subTest(keys=keys):
                    data = json.loads(original)
                    obj = data
                    for key in keys[:-1]:
                        obj = obj[key]
                    obj[keys[-1]] = value
                    source.write_text(json.dumps(data))
                    result = self.run_generator(root)
                    self.assertNotEqual(result.returncode, 0, result.stderr.decode())
                    self.assertEqual([p.read_bytes() for p in outputs], before)
            for text in ('{"format":1,"format":1}', "{", "[]", "null"):
                source.write_text(text)
                self.assertNotEqual(self.run_generator(root).returncode, 0)
            source.unlink()
            self.assertNotEqual(self.run_generator(root, "--check").returncode, 0)

    def test_missing_outputs_and_bad_markers_are_read_only(self):
        with tempfile.TemporaryDirectory(prefix="issue29-markers-") as tmp:
            root = Path(tmp)
            self.copy_root(root)
            header = root / "include/chaos_protocol.h"
            python = root / "chaos/_protocol_contract.py"
            original = header.read_text()
            begin = "/* BEGIN GENERATED PROTOCOL CONTRACT */"
            end = "/* END GENERATED PROTOCOL CONTRACT */"
            for broken in (
                original.replace(begin, ""),
                original + begin,
                original + end,
                original.replace(begin, "TEMP")
                .replace(end, begin)
                .replace("TEMP", end),
            ):
                header.write_text(broken)
                self.assertNotEqual(self.run_generator(root, "--check").returncode, 0)
                self.assertEqual(header.read_text(), broken)
            header.write_text("/* outside */\n" + original + "\n/* outside end */\n")
            before = header.read_bytes()
            python.unlink()
            self.assertNotEqual(self.run_generator(root, "--check").returncode, 0)
            self.assertFalse(python.exists())
            self.assertEqual(self.run_generator(root).returncode, 0)
            self.assertEqual(header.read_bytes(), before)
            header.unlink()
            self.assertNotEqual(self.run_generator(root, "--check").returncode, 0)
            self.assertFalse(header.exists())

    def test_fresh_generated_files_do_not_mask_consumer_bypass(self):
        mutations = [
            ("mutations[k].name :", '"bypass" :', "test_frozen_registry_and_admission"),
            ("mutations[k].cost :", "0 :", "test_frozen_registry_and_admission"),
            (
                "r->value <= m->high",
                "r->value <= m->high + 1",
                "test_differential_corpus",
            ),
            (
                "r->duration <= m->duration_high",
                "r->duration <= m->duration_high + 1",
                "test_differential_corpus",
            ),
            (
                "sanity > mutations[r->kind].sanity_max",
                "sanity >= mutations[r->kind].sanity_max",
                "test_frozen_registry_and_admission",
            ),
            ("eligible != 1", "eligible == 0", "test_frozen_registry_and_admission"),
            (
                "r->telegraph == m->telegraph",
                "r->telegraph == m->telegraph + 1",
                "test_differential_corpus",
            ),
        ]
        with tempfile.TemporaryDirectory(prefix="issue29-bypass-") as tmp:
            root = Path(tmp)
            self.copy_root(root)
            source = root / "src/chaos_protocol.c"
            original = source.read_text()
            for index, (old, new, probe) in enumerate(mutations):
                with self.subTest(bypass=old):
                    self.assertEqual(original.count(old), 1)
                    source.write_text(original.replace(old, new))
                    self.assertEqual(self.run_generator(root, "--check").returncode, 0)
                    case = CompatibilityTests(probe)
                    case.lib = compile_core(root, root / f"bypass-{index}.so")
                    result = unittest.TestResult()
                    case.run(result)
                    self.assertTrue(result.failures, result.errors)
                    self.assertFalse(result.errors)
            source.write_text(original)
            p = root / "chaos/protocol.py"
            p.write_text(p.read_text() + "\nEVENTS = frozenset()\n")
            (root / "chaos/__init__.py").write_text("")
            self.assertEqual(self.run_generator(root, "--check").returncode, 0)
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    'from chaos.protocol import EVENTS; assert "eat" in EVENTS',
                ],
                cwd=root,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"AssertionError", result.stderr)

    def test_check_exists_and_clean(self):
        result = self.run_generator(ROOT, "--check")
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def test_drift_and_fourth_row(self):
        with tempfile.TemporaryDirectory(prefix="issue29-fourth-") as tmp:
            root = Path(tmp)
            self.copy_root(root)
            self.assertEqual(self.run_generator(root, "--check").returncode, 0)
            for path in ("include/chaos_protocol.h", "chaos/_protocol_contract.py"):
                p = root / path
                original = p.read_bytes()
                p.write_bytes(original.replace(b"ambient", b"changed", 1))
                self.assertNotEqual(self.run_generator(root, "--check").returncode, 0)
                self.assertEqual(
                    p.read_bytes(), original.replace(b"ambient", b"changed", 1)
                )
                p.write_bytes(original)
            source = root / "chaos/protocol_contract.json"
            data = json.loads(source.read_text())
            fourth = dict(
                data["mutations"][0],
                symbol="CHAOS_TEST_ONLY",
                id=3,
                name="test_only",
                value=[1, 1],
            )
            data["mutations"].append(fourth)
            source.write_text(json.dumps(data))
            self.assertNotEqual(self.run_generator(root, "--check").returncode, 0)
            result = self.run_generator(root)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(self.run_generator(root, "--check").returncode, 0)
            before = (root / "include/chaos_protocol.h").read_bytes()
            self.assertEqual(self.run_generator(root).returncode, 0)
            self.assertEqual((root / "include/chaos_protocol.h").read_bytes(), before)
            lib = compile_core(root, root / "fourth.so")
            payload = raw(request("test_only"))
            r = Request()
            self.assertEqual(lib.chaos_parse(payload, len(payload), C.byref(r)), 0)
            self.assertEqual(r.kind, 3)
            s = state_type(4)()
            lib.chaos_state_init(C.byref(s))
            s.safe = 1
            self.assertEqual(lib.chaos_admit(C.byref(s), C.byref(r), 10, 101, 2), 0)
            self.assertEqual((s.spent, s.reserved), (1, 0))
            self.assertTrue(lib.chaos_state_valid(C.byref(s)))
            (root / "chaos/__init__.py").write_text("")
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    'from chaos.protocol import parse_request; import sys; assert parse_request(sys.stdin.buffer.read())["mutation"] == "test_only"',
                ],
                input=payload,
                cwd=root,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
