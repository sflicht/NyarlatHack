"""Preflight must reject an unusable output before consuming an inference attempt."""

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_director import event, append

ROOT = Path(__file__).resolve().parents[2]


class GenerationPreflightTests(unittest.TestCase):
    def test_existing_output_stops_before_model_call(self):
        spec = importlib.util.spec_from_file_location(
            "haunting_generation_script", ROOT / "scripts/generate_haunting.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            events = Path(tmp) / "events.jsonl"
            append(events, event(event="backtrack"))
            output = Path(tmp) / "existing"
            output.mkdir()
            argv = [
                "generate_haunting.py",
                "--events",
                str(events),
                "--output",
                str(output),
                "--execute-live",
            ]
            with (
                patch.object(sys, "argv", argv),
                patch(
                    "chaos.oauth.OAuthBackend.generate",
                    side_effect=AssertionError("unexpected inference"),
                ) as generate,
            ):
                with self.assertRaises(FileExistsError):
                    module.main()
                generate.assert_not_called()
