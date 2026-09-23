"""Static next-use author contract. Not a provider call."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "chaos/prompts/next-use-author.txt"


class NextUseAuthorContractTests(unittest.TestCase):
    def test_contract_teaches_fresh_calls_and_host_state(self):
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertIn("do not persist", text)
        self.assertIn("upvalues", text)
        self.assertIn("state, an integer 0..3", text)
        self.assertIn("own_witnessed", text)
        self.assertIn("not witnessed", text)
        self.assertNotIn("luaL_openlibs", text)
        self.assertIn("game RNG", text)
        self.assertIn("not a live-call authorization", text)

    def test_contract_is_not_loaded_by_the_live_history_prompt(self):
        history = (ROOT / "chaos/history_choice.py").read_text(encoding="utf-8")
        launcher = (ROOT / "chaos/launcher.py").read_text(encoding="utf-8")
        self.assertNotIn("next-use-author.txt", history)
        self.assertNotIn("next-use-author.txt", launcher)
