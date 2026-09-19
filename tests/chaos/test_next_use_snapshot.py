"""ENGINE-UNIT: bounded next-use snapshot. Not save/restore."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NextUseSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="nyarl-next-use-snapshot-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(cls.build.name) / "next-use-snapshot"
        flags = subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "lua5.4"], text=True
        ).split()
        command = [
            "/usr/bin/gcc",
            "-DCHAOS",
            "-ffunction-sections",
            "-fdata-sections",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-misleading-indentation",
            "-isystem",
            str(ROOT / "include"),
            str(ROOT / "tests/chaos/next_use_snapshot.c"),
            str(ROOT / "src/chaos_next_use.c"),
            str(ROOT / "src/chaos_next_use_admission.c"),
            str(ROOT / "src/chaos_next_use_runtime.c"),
            str(ROOT / "src/chaos_protocol.c"),
            str(ROOT / "src/chaos_lua.c"),
            "-Wl,--gc-sections",
            *flags,
            "-lm",
            "-o",
            str(cls.binary),
        ]
        result = subprocess.run(command, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    def run_mode(self, mode):
        result = subprocess.run(
            [str(self.binary), mode], capture_output=True, text=True, timeout=5
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return [json.loads(line) for line in result.stdout.splitlines() if line]

    def test_roundtrip_pending_does_not_readmit(self):
        rows = self.run_mode("roundtrip")
        self.assertEqual(rows[0]["ok"], 1)
        self.assertEqual(rows[0]["slot_w"], 1)
        self.assertEqual(rows[1]["ok"], 0)
        self.assertEqual(rows[2]["ok"], 1)
        self.assertEqual(rows[2]["program_id"], rows[0]["program_id"])
        self.assertEqual(rows[2]["slot_w"], rows[0]["slot_w"])
        self.assertEqual(rows[2]["sha"], rows[0]["sha"])
        self.assertEqual(rows[2]["source_len"], rows[0]["source_len"])

    def test_bad_version_does_not_overwrite_live(self):
        rows = self.run_mode("bad_version")
        self.assertEqual(rows[-1]["validated"], 0)
        self.assertEqual(rows[-1]["imported"], 0)
        self.assertEqual(rows[-1]["live_program"], 1)

    def test_digest_mismatch_does_not_overwrite_live(self):
        rows = self.run_mode("digest_mismatch")
        self.assertEqual(rows[-1]["validated"], 0)
        self.assertEqual(rows[-1]["imported"], 0)
        self.assertEqual(rows[-1]["live_program"], 1)

    def test_consumed_invalid_roundtrip_cannot_revive(self):
        rows = self.run_mode("consumed_invalid")
        after = next(row for row in rows if row["tag"] == "after_invalid")
        imported = next(row for row in rows if row["tag"] == "imported_invalid")
        resurrect = next(row for row in rows if row["tag"] == "resurrect")
        self.assertEqual(after["slot_w"], 5)
        self.assertEqual(imported["slot_w"], 5)
        self.assertEqual(imported["sha"], after["sha"])
        self.assertEqual(resurrect["validated"], 0)

    def test_roundtrip_pending_f(self):
        rows = self.run_mode("roundtrip_f")
        after = next(row for row in rows if row["tag"] == "after_install_f")
        imported = next(row for row in rows if row["tag"] == "after_import_f")
        self.assertEqual(after["slot_w"], 0)
        self.assertEqual(after["slot_f"], 1)
        self.assertEqual(imported["slot_f"], 1)
        self.assertEqual(imported["slot_w"], 0)
        self.assertEqual(imported["sha"], after["sha"])

    def test_file_bytes_roundtrip(self):
        rows = self.run_mode("file")
        after = next(row for row in rows if row["tag"] == "after_file")
        self.assertEqual(after["ok"], 1)
        self.assertEqual(after["slot_w"], 1)


if __name__ == "__main__":
    unittest.main()
