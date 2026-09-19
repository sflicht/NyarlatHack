"""Publish one immutable envelope; C reads it without admission."""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import unittest

from chaos.next_use_compose import compose
from chaos.next_use_envelope import (
    engine_run_hex,
    envelope_from_selection,
    publish_envelope,
)

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / "tests" / "chaos" / "next_use_envelope.c"
SOURCES = [
    ROOT / "src" / "chaos_next_use.c",
    ROOT / "src" / "chaos_next_use_io.c",
    ROOT / "src" / "chaos_lua.c",
]
ROW = {
    "family": "W",
    "op": "whistle_attention",
    "origin": {
        "root_seq": 10,
        "notice_seq": 11,
        "end_seq": 12,
        "fact": "sound_high",
    },
}
HOST = {
    "at": 7,
    "id": 1,
    "level_dlevel": 1,
    "level_dnum": 0,
    "move": 40,
    "run": "ab" * 32,
    "variant": 0,
}


def _compile(binary):
    flags = subprocess.check_output(
        ["pkg-config", "--cflags", "--libs", "lua5.4"], text=True
    ).split()
    cmd = [
        "/usr/bin/gcc",
        "-DCHAOS",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-Wno-misleading-indentation",
        "-std=c99",
        "-I" + str(ROOT / "include"),
        str(HARNESS),
        *[str(p) for p in SOURCES],
        *flags,
        "-lm",
        "-o",
        str(binary),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.decode())


class EnvelopePublishTests(unittest.TestCase):
    def test_python_maps_engine_fact_and_hashes_source(self):
        envelope, encoded = envelope_from_selection(ROW, HOST)
        composed = compose(ROW)
        self.assertEqual(envelope["source_sha256"], composed["source_sha256"])
        self.assertEqual(envelope["origin_refs"][0]["fact"], "ordinary_whistle")
        self.assertEqual(envelope["origin_refs"][0]["root"], 10)
        self.assertEqual(envelope["ttl"], 100)
        self.assertEqual(envelope["cost"], 1)
        self.assertNotIn("spent", json.loads(encoded))

    def test_missing_host_field_is_closed(self):
        host = dict(HOST)
        del host["run"]
        with self.assertRaises(ValueError):
            envelope_from_selection(ROW, host)

    def test_publish_is_once_and_c_reads_without_admit(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o700)
            published = publish_envelope(tmp, ROW, HOST)
            self.assertEqual(published["status"], "envelope_published_not_admitted")
            path = Path(tmp) / "next_use-envelope.json"
            self.assertTrue(path.is_file())
            self.assertFalse((Path(tmp) / "next_use.lua").exists())
            with self.assertRaises(ValueError):
                publish_envelope(tmp, ROW, HOST)
            binary = Path(tmp) / "next_use_envelope"
            _compile(binary)
            out = subprocess.check_output([str(binary), tmp], text=True)
            self.assertIn("load=0", out)
            self.assertIn(f"sha={published['source_sha256']}", out)
            self.assertIn("cost=1", out)
            self.assertNotIn("spent", out)

    def test_tampered_source_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o700)
            publish_envelope(tmp, ROW, HOST)
            path = Path(tmp) / "next_use-envelope.json"
            payload = json.loads(path.read_text())
            payload["source_sha256"] = "0" * 64
            path.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True))
            os.chmod(path, 0o600)
            binary = Path(tmp) / "next_use_envelope"
            _compile(binary)
            proc = subprocess.run([str(binary), tmp], capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("load=", proc.stdout)
            self.assertNotIn("load=0", proc.stdout)

    def test_engine_run_hex_matches_owned_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.chmod(tmp, 0o700)
            binary = Path(tmp) / "next_use_envelope"
            _compile(binary)
            owned = subprocess.check_output(
                [str(binary), tmp, "runhex"], text=True
            ).strip()
            self.assertEqual(engine_run_hex(tmp), owned)
            self.assertEqual(len(owned), 64)

    def test_engine_run_hex_differs_across_directories(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.assertNotEqual(engine_run_hex(a), engine_run_hex(b))


if __name__ == "__main__":
    unittest.main()
