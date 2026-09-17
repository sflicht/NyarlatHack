"""Synthetic flow tests: no engine, compiler, or native evidence."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import test_history_gameplay as driver


class HistoryFlowTests(unittest.TestCase):
    def test_start_failure_cleans_and_rechecks_without_masking(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Mock(root=Path(directory))
            game.start.side_effect = ValueError("startup failed")
            game.save_artifacts.side_effect = RuntimeError("artifact failed")
            verify = Mock()
            before = dict(os.environ)
            with self.assertRaisesRegex(ValueError, "startup failed"):
                with driver.arm_session(game, {"PATH": "/usr/bin"}, verify):
                    self.fail("startup must fail")
            game.cleanup.assert_called_once()
            verify.assert_called_once()
            self.assertEqual(dict(os.environ), before)
            self.assertTrue((game.root / "hunger.jsonl").exists())

    def test_complete_validation_happens_after_quit(self):
        game = Mock()
        game.quit.return_value = 0
        game.events.return_value = []
        with tempfile.TemporaryDirectory() as directory:
            telemetry = Path(directory) / "hunger.jsonl"
            telemetry.write_text("")

            def validate(rows):
                game.quit.assert_called_once()
                return {"synthetic": True}

            from unittest.mock import patch

            with patch.object(driver, "check_control", side_effect=validate):
                game.raw = b""
                self.assertEqual(
                    driver.finish_arm(game, telemetry, None), {"synthetic": True}
                )

    def test_protected_recheck_failure_prevents_success(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Mock(root=Path(directory))
            with self.assertRaisesRegex(ValueError, "source changed"):
                with driver.arm_session(
                    game, {}, Mock(side_effect=ValueError("source changed"))
                ):
                    pass
            game.cleanup.assert_called_once()

    def test_start_failure_closes_telemetry_descriptor(self):
        with tempfile.TemporaryDirectory() as directory:
            game = Mock(root=Path(directory))
            descriptors = []

            def start():
                descriptors.append(int(os.environ["NYARLATHACK_HUNGER_FD"]))
                raise ValueError("startup failed")

            game.start.side_effect = start
            with self.assertRaisesRegex(ValueError, "startup failed"):
                with driver.arm_session(game, {}, Mock()):
                    pass
            with self.assertRaises(OSError):
                os.fstat(descriptors[0])

    def test_unjustified_paging_rejected(self):
        class SyntheticBase:
            def __init__(self):
                self.inputs = []

            def send(self, value, **kwargs):
                self.inputs.append(value)
                return b""

        game = driver.disciplined_game_type(SyntheticBase)()
        with self.assertRaisesRegex(ValueError, "unjustified"):
            game.send(" ")

    def test_dry_up_confirmation_is_explicit_nonturn_input(self):
        class SyntheticBase:
            def __init__(self):
                self.inputs = []

            def send(self, value, **kwargs):
                self.inputs.append(value.hex())
                return b"ready"

        game = driver.disciplined_game_type(SyntheticBase)()
        game.scripted = True
        game.last_text = b"Dry up fountain? [yn] (n) "
        self.assertEqual(game.send("n"), b"ready")
        self.assertEqual(game.command_index, 0)
        self.assertEqual(game.prompt_inputs[0]["kind"], "dry_up_decline")
        game.last_text = b"ready"
        with self.assertRaisesRegex(ValueError, "frozen"):
            game.send("n")

    def test_wrong_gameplay_byte_rejected(self):
        class SyntheticBase:
            def __init__(self):
                self.inputs = []

            def send(self, value, **kwargs):
                return b""

        game = driver.disciplined_game_type(SyntheticBase)()
        game.scripted = True
        with self.assertRaisesRegex(ValueError, "frozen"):
            game.send("q")
