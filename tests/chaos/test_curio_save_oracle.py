"""Synthetic decoder controls; not native saves or gameplay witnesses."""

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_curio_launcher_gameplay import decode_save


def fixture(policy):
    schema: dict = dict(
        byteorder="little",
        external_compression=False,
        internal_compression=False,
        save_header_size=4,
        save_header={"tag": dict(offset=0, size=4)},
        save_header_values={"tag": 123},
        version=1,
        placed=2,
        record_size=80,
        you_size=192,
        spent_offset=4,
        spent_size=4,
        you={
            "curio": dict(offset=112, size=80),
            "chaos": dict(offset=8, size=96 if policy == "current" else 80),
            "usanity": dict(offset=0, size=4),
        },
        record={},
    )
    for i, name in enumerate(
        ("version", "phase", "source_len", "owner", "charges", "state", "disabled")
    ):
        schema["record"][name] = dict(offset=i * 4, size=4)
    schema["record"].update(
        name=dict(offset=28, size=24), source=dict(offset=52, size=28)
    )
    data = bytearray(196)

    def put(offset, value, size=4):
        data[offset : offset + size] = value.to_bytes(size, "little", signed=True)

    put(0, 123)
    put(4, 98)
    put(16, 1 if policy == "current" else 2)
    source = b"synthetic source"
    for name, value in dict(
        version=1,
        phase=2,
        source_len=len(source),
        owner=4,
        charges=2,
        state=1,
        disabled=0,
    ).items():
        put(116 + schema["record"][name]["offset"], value)
    data[144:168] = b"Offline counter".ljust(24, b"\0")
    data[168:196] = source.ljust(28, b"\0")
    if policy == "current":
        schema.update(
            chaos_state_version=2,
            chaos_size=96,
            chaos_fields={
                "version": dict(offset=0, size=4),
                "cosmetic_seen": dict(offset=80, size=4),
                "cosmetic_last_turn": dict(offset=88, size=8),
            },
        )
        put(12, 2)
        put(92, 1)
        put(100, 1, 8)
    return bytes(data), schema, source


class CurioSaveOracleTests(unittest.TestCase):
    def test_current_compiled_layout_reporter(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix="curio-layout-") as tmp:
            exe = Path(tmp) / "layout"
            subprocess.run(
                [
                    "/usr/bin/cc",
                    "-std=gnu17",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-DCHAOS",
                    "-DDLB",
                    "-isystem" + str(root / "include"),
                    str(root / "tests/chaos/curio_save_layout.c"),
                    "-o",
                    str(exe),
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
            schema = json.loads(subprocess.check_output([str(exe)], timeout=5))
        self.assertEqual(schema["chaos_state_version"], 2)
        self.assertEqual(schema["chaos_size"], schema["you"]["chaos"]["size"])
        previous = 0
        for name in ("version", "cosmetic_seen", "cosmetic_last_turn"):
            field = schema["chaos_fields"][name]
            self.assertGreaterEqual(field["offset"], previous)
            previous = field["offset"] + field["size"]
            self.assertLessEqual(previous, schema["chaos_size"])
        self.assertLessEqual(
            schema["you"]["chaos"]["offset"] + schema["chaos_size"], schema["you_size"]
        )
        # date.h is NOT evidence of a fresh matching binary/save fingerprint.

    def decode(self, data, schema, source, policy):
        return decode_save(
            self,
            data,
            schema,
            source,
            2,
            1,
            98,
            policy=policy,
            cosmetic={"seen": 1, "last_turn": 1} if policy == "current" else None,
        )

    def test_historical_spent_two_remains_historical(self):
        data, schema, source = fixture("historical")
        self.assertEqual(self.decode(data, schema, source, "historical")[1]["spent"], 2)
        with self.assertRaises((AssertionError, KeyError)):
            self.decode(data, schema, source, "current")

    def test_current_spent_one_and_exact_cosmetics(self):
        data, schema, source = fixture("current")
        fields = self.decode(data, schema, source, "current")[1]
        self.assertEqual(fields["spent"], 1)
        self.assertEqual(fields["cosmetic"], {"seen": 1, "last_turn": 1})
        for offset in (12, 16, 92, 100):
            changed = bytearray(data)
            changed[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(AssertionError):
                self.decode(bytes(changed), schema, source, "current")
        with self.assertRaises(AssertionError):
            self.decode(data, schema, source, "historical")

    def test_current_layout_and_truncation_fail_closed(self):
        data, schema, source = fixture("current")
        for field in ("version", "cosmetic_seen", "cosmetic_last_turn"):
            bad = copy.deepcopy(schema)
            bad["chaos_fields"][field]["offset"] = 96
            with self.subTest(field=field), self.assertRaises(AssertionError):
                self.decode(data, bad, source, "current")
        with self.assertRaises(AssertionError):
            self.decode(data[:-1], schema, source, "current")
        bad = copy.deepcopy(schema)
        bad["chaos_size"] = 80
        with self.assertRaises(AssertionError):
            self.decode(data, bad, source, "current")
        with self.assertRaises(ValueError):
            self.decode(data, schema, source, "guess")
