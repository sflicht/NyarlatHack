"""Linked-native capture: actual dog_move publication and fountain remapping."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import test_next_use_dogmove as native
import test_next_use_fountain as fountain
from chaos.next_use_envelope import engine_run_hex, publish_envelope

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(
    os.environ.get("NYARLATHACK_GAME_TESTS") == "1", "real game opt-in"
)
class NextUseCaptureNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the established object/RNG setup, not a replacement game harness.
        native.NextUseDogMoveTests.setUpClass()
        base = native.NextUseDogMoveTests
        cls.exe = base.root / "capture-native"
        command = [
            "cc",
            "-g",
            "-DCHAOS",
            "-I" + str(ROOT / "include"),
            str(ROOT / "tests/chaos/next_use_capture_native.c"),
            *map(str, base.objects),
            "-lncursesw",
            "-ltinfo",
            "-lm",
            *subprocess.check_output(
                ["pkg-config", "--libs", "lua5.4"], text=True
            ).split(),
            "-o",
            str(cls.exe),
        ]
        subprocess.run(command, check=True, timeout=45)
        cls.fountain_exe = base.root / "capture-fountain-native"
        command[command.index(str(ROOT / "tests/chaos/next_use_capture_native.c"))] = (
            str(ROOT / "tests/chaos/next_use_capture_fountain_native.c")
        )
        command[-1] = str(cls.fountain_exe)
        subprocess.run(command, check=True, timeout=45)

    def test_actual_fountain_remap_captured_and_shadow_replayed(self):
        folder = Path(tempfile.mkdtemp(prefix="nyarl-capture-fountain-run-"))
        host = dict(fountain.HOST, run=engine_run_hex(folder))
        publish_envelope(folder, fountain.ROW, host)
        result = subprocess.run(
            [str(self.fountain_exe), str(folder)],
            env=dict(os.environ, TERM="xterm", COLUMNS="80", LINES="24"),
            cwd=folder,
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        captured = json.loads((folder / "capture.json").read_text())
        print(
            "CAPTURE_FOUNTAIN=" + str(folder) + " " + json.dumps(captured), flush=True
        )
        self.assertEqual(
            (captured["hunger_before"], captured["hunger_after"]), (1000, 1004)
        )
        self.assertEqual((captured["actions"], captured["results"]), (1, 1))
        self.assertEqual(captured["transitions"], 2)
        self.assertEqual(captured["cursor"], captured["transitions"])
        self.assertEqual(captured["outcome"], 6)  # CHAOS_FOUNTAIN_REMAPPED
        self.assertEqual(captured["consumed"], 1)
        self.assertEqual(captured["tamper_rejected"], 2)
        for identity in ("context_sha256", "intent_sha256"):
            self.assertRegex(captured[identity], r"^[0-9a-f]{64}$")

    def test_actual_publication_not_inferred_from_displacement_and_delivery(self):
        for blocked in (False, True):
            with self.subTest(blocked=blocked):
                folder = Path(tempfile.mkdtemp(prefix="nyarl-capture-native-run-"))
                host = dict(native.HOST, run=engine_run_hex(folder))
                publish_envelope(folder, native.ROW, host)
                env = dict(os.environ, TERM="xterm", COLUMNS="80", LINES="24")
                env.pop("NYARL_CAPTURE_BLOCK_PUBLICATION", None)
                if blocked:
                    env["NYARL_CAPTURE_BLOCK_PUBLICATION"] = "1"
                result = subprocess.run(
                    [str(self.exe), "admit", str(folder)],
                    env=env,
                    cwd=folder,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                row = json.loads((folder / "result.json").read_text())
                captured = json.loads((folder / "capture.json").read_text())
                print(
                    "CAPTURE_NATIVE=" + str(folder) + " " + json.dumps(captured),
                    flush=True,
                )
                self.assertEqual((row["delivered"], row["displaced"]), (1, 1))
                self.assertEqual((captured["delivered"], captured["displaced"]), (1, 1))
                self.assertEqual(captured["intents"], 1)
                self.assertEqual(captured["manifests"], 1)
                self.assertEqual(captured["published"], int(not blocked))
                self.assertEqual(captured["public"], int(not blocked))
                self.assertEqual(row["public"], captured["public"])
                self.assertEqual(captured["tamper_rejected"], 1)
