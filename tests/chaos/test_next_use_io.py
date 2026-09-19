"""Load-only next_use.lua tick: marker is not admission. Synthetic I/O faults."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    b"return {\n"
    b"  on_action = function(context)\n"
    b'    return {next_use_intent_v=2, op="quiet", state=0}\n'
    b"  end\n"
    b"}\n"
)


class NextUseIoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="nyarl-next-use-io-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.exe = Path(cls.tmp.name) / "next-use-io"
        flags = subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "lua5.4"], text=True
        ).split()
        command = [
            "cc",
            "-DCHAOS",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-std=c99",
            "-I" + str(ROOT / "include"),
            str(ROOT / "src/chaos_next_use_io.c"),
            str(ROOT / "src/chaos_lua.c"),
            str(ROOT / "tests/chaos/next_use_io_harness.c"),
            "-Wl,--wrap=read",
            "-Wl,--wrap=write",
            "-Wl,--wrap=fsync",
            *flags,
            "-o",
            str(cls.exe),
        ]
        result = subprocess.run(command, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr.decode())

    def run_dir(self, mode, source: bytes | None = SOURCE, extra=None):
        folder = Path(tempfile.mkdtemp(prefix="nyarl-next-use-io-run-"))
        if source is not None:
            target = folder / "next_use.lua"
            target.write_bytes(source)
            target.chmod(0o600)
        if extra:
            extra(folder)
        p = subprocess.run(
            [str(self.exe), str(folder), mode],
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        row = json.loads(p.stdout)
        row["dir"] = folder
        return row

    def test_valid_load_writes_exact_marker_once(self):
        row = self.run_dir("ok")
        self.assertEqual(row["used"], 1)
        self.assertEqual((row["dir"] / "next_use-used.lua").read_bytes(), SOURCE)
        self.assertGreaterEqual(row["writes"], 1)

    def test_eintr_and_short_read_still_publish(self):
        for mode in ("eintr-read", "short-read", "short-write"):
            with self.subTest(mode=mode):
                row = self.run_dir(mode)
                self.assertEqual(row["used"], 1)
                self.assertEqual(
                    (row["dir"] / "next_use-used.lua").read_bytes(), SOURCE
                )

    def test_write_or_fsync_failure_leaves_no_marker(self):
        for mode in ("write-fail", "fsync-fail"):
            with self.subTest(mode=mode):
                row = self.run_dir(mode)
                self.assertEqual(row["used"], 0)
                self.assertFalse((row["dir"] / "next_use-used.lua").exists())

    def test_absent_and_nul_and_oversize_leave_no_marker(self):
        absent = self.run_dir("ok", source=None)
        self.assertEqual(absent["used"], 0)
        nul = self.run_dir("ok", source=b"return {on_action=function() end}\0x")
        self.assertEqual(nul["used"], 0)
        huge = self.run_dir("ok", source=b"x" * 4097)
        self.assertEqual(huge["used"], 0)

    def test_existing_marker_is_not_replaced(self):
        def seed(folder: Path):
            marker = folder / "next_use-used.lua"
            marker.write_bytes(b"keep")
            marker.chmod(0o600)

        row = self.run_dir("ok", extra=seed)
        self.assertEqual((row["dir"] / "next_use-used.lua").read_bytes(), b"keep")
