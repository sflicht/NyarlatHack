"""ENGINE-UNIT: real intent/context hashes vs independent Python vectors."""

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
OPS = ("quiet", "delay", "whistle_attention", "fountain_refresh")
STATES = (0, 3)
SOURCE_SHA = "0" * 64


def independent_intent_bytes(op: str, state: int) -> bytes:
    payload = json.dumps(
        {"next_use_intent_v": 2, "op": op, "state": state},
        separators=(",", ":"),
    )
    return payload.encode("utf-8")


def independent_intent_digest(op: str, state: int) -> str:
    return hashlib.sha256(independent_intent_bytes(op, state)).hexdigest()


def independent_context_bytes(
    age=0,
    fountain_count=0,
    own="none",
    source_sha=SOURCE_SHA,
    state=0,
    trigger="W",
    variant=0,
    whistle_count=0,
) -> bytes:
    payload = json.dumps(
        {
            "age": age,
            "fountain_count": fountain_count,
            "next_use_context_v": 2,
            "own_witnessed": own,
            "source_sha256": source_sha,
            "state": state,
            "trigger": trigger,
            "variant": variant,
            "whistle_count": whistle_count,
        },
        separators=(",", ":"),
    )
    return payload.encode("utf-8")


class NextUseIntentHashTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="nyarl-intent-hash-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(cls.build.name) / "intent-hash"
        command = [
            "/usr/bin/gcc",
            "-DCHAOS",
            "-DCHAOS_NEXT_USE_HASH_FIXTURE",
            "-ffunction-sections",
            "-fdata-sections",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-misleading-indentation",
            "-isystem",
            str(ROOT / "include"),
            str(ROOT / "tests/chaos/next_use_intent_hash.c"),
            str(ROOT / "src/chaos_next_use.c"),
            str(ROOT / "src/chaos_next_use_admission.c"),
            str(ROOT / "src/chaos_next_use_runtime.c"),
            str(ROOT / "src/chaos_protocol.c"),
            "-Wl,--gc-sections",
            "-lm",
            "-o",
            str(cls.binary),
        ]
        result = subprocess.run(command, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    def run_json(self, args, stdin=None):
        result = subprocess.run(
            [str(self.binary), *args],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_literal_quiet_zero_has_no_escape_layer(self):
        declared = b'{"next_use_intent_v":2,"op":"quiet","state":0}'
        self.assertEqual(independent_intent_bytes("quiet", 0), declared)
        self.assertNotIn(b"\\", declared)
        self.assertFalse(declared.endswith(b"\n"))
        row = self.run_json(["hash-intent", "quiet", "0"])
        self.assertEqual(row["ok"], 1)
        self.assertEqual(row["digest"], hashlib.sha256(declared).hexdigest())

    def test_c_matches_independent_vectors_for_all_ops_and_bounds(self):
        seen = set()
        for op in OPS:
            for state in STATES:
                declared = independent_intent_bytes(op, state)
                digest = independent_intent_digest(op, state)
                row = self.run_json(["hash-intent", op, str(state)])
                self.assertEqual(row["ok"], 1, op)
                self.assertEqual(row["digest"], digest)
                self.assertNotIn(digest, seen)
                seen.add(digest)
                parsed = self.run_json(["parse-intent"], stdin=declared.decode())
                self.assertEqual(parsed["status"], 0)
                self.assertEqual(parsed["state"], state)

    def test_tampered_bytes_rejected_by_parser_and_hash(self):
        digest = independent_intent_digest("quiet", 0)
        tampered = b'{"next_use_intent_v":2,"op":"quiet","state":1}'
        self.assertNotEqual(hashlib.sha256(tampered).hexdigest(), digest)
        escaped = b'{"next_use_intent_v\\":2,\\"op\\":\\"quiet\\",\\"state\\":0}'
        parsed = self.run_json(["parse-intent"], stdin=escaped.decode())
        self.assertNotEqual(parsed["status"], 0)
        row = self.run_json(["hash-intent", "quiet", "0"])
        self.assertEqual(row["digest"], digest)
        self.assertNotEqual(row["digest"], hashlib.sha256(escaped).hexdigest())
        self.assertNotEqual(row["digest"], hashlib.sha256(tampered).hexdigest())

    def test_invalid_op_does_not_present_partial_hash(self):
        row = self.run_json(["fail-intent"])
        self.assertEqual(row["ok"], 0)
        self.assertEqual(row["digest"], "X" * 64)

    def test_insufficient_format_capacity_clears_output(self):
        row = self.run_json(["format-intent", "quiet", "0", "8"])
        self.assertEqual(row["ok"], 0)
        self.assertEqual(row["out"], "")

    def test_context_hash_matches_declared_literal(self):
        declared = independent_context_bytes()
        self.assertEqual(
            declared,
            (
                b'{"age":0,"fountain_count":0,"next_use_context_v":2,'
                b'"own_witnessed":"none","source_sha256":"'
                + SOURCE_SHA.encode()
                + b'","state":0,"trigger":"W","variant":0,"whistle_count":0}'
            ),
        )
        row = self.run_json(
            [
                "hash-context",
                "0",
                "0",
                "0",
                SOURCE_SHA,
                "0",
                "1",
                "0",
                "0",
            ]
        )
        self.assertEqual(row["ok"], 1)
        self.assertEqual(row["digest"], hashlib.sha256(declared).hexdigest())


if __name__ == "__main__":
    unittest.main()
