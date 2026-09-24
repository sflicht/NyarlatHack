"""Production runtime capture, with existing staged replay as subscriber."""

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NextUseCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="nyarl-capture-")
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = Path(cls.build.name) / "capture"
        flags = subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "lua5.4"], text=True
        ).split()
        command = [
            "cc",
            "-DCHAOS",
            "-DCHAOS_NEXT_USE_TEST_LEGACY_REPLAY",
            "-ffunction-sections",
            "-fdata-sections",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-Wno-misleading-indentation",
            "-isystem",
            str(ROOT / "include"),
            str(ROOT / "tests/chaos/next_use_capture.c"),
            *[
                str(ROOT / ("src/" + name + ".c"))
                for name in (
                    "chaos_next_use",
                    "chaos_next_use_admission",
                    "chaos_next_use_runtime",
                    "chaos_protocol",
                    "chaos_lua",
                )
            ],
            "-Wl,--gc-sections",
            *flags,
            "-lm",
            "-o",
            str(cls.binary),
        ]
        subprocess.run(command, check=True, timeout=45)

    def test_reject_record_controlled_downgrade(self):
        for mode in ("downgrade_post", "downgrade_result", "downgrade_version"):
            with self.subTest(mode=mode):
                self.run_validation(mode)

    def test_reject_noncanonical_booleans(self):
        for field in (
            "attention",
            "token_active",
            "token_consumed",
            "token_remap",
            "boundary_w",
            "boundary_f",
        ):
            for value in (2, -1):
                with self.subTest(field=field, value=value):
                    self.run_validation("bool_" + field, value)

    def run_validation(self, mode, value=2):
        result = subprocess.run(
            [str(self.binary), mode, str(value)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "capture ok")

    def test_capture(self):
        for mode in (
            "action",
            "rejected_token",
            "invalid_root_token",
            "nested",
            "failure",
            "missing",
            "fountain",
            "identity",
            "no_root",
            "ready_expiry",
            "manifest_unpublished",
            "manifest_published",
        ):
            with self.subTest(mode=mode):
                result = subprocess.run(
                    [str(self.binary), mode], capture_output=True, text=True, timeout=10
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip(), "capture ok")
