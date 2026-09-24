"""Static next-use author contract. Not a provider call."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "chaos/prompts/next-use-author.txt"

# Exact handwritten teaching fixtures, not model output or gameplay recurrence.
RESET_COUNTER = """local n = 0
return {on_action = function(context)
  n = n + 1
  return {next_use_intent_v=2, op="quiet", state=n}
end}
"""
EXPLICIT_STATE = """return {on_action = function(context)
  local next_state = context.state
  if next_state < 3 then next_state = next_state + 1 end
  return {next_use_intent_v=2, op="quiet", state=next_state}
end}
"""
HANDWRITTEN_EXAMPLES = (
    ("Handwritten fixture: reset counter", RESET_COUNTER),
    ("Handwritten fixture: explicit state", EXPLICIT_STATE),
)


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

    def test_exact_handwritten_memory_examples_and_limits(self):
        text = CONTRACT.read_text(encoding="utf-8")
        self.assertEqual(text.count("```lua\n"), 2)
        for label, source in HANDWRITTEN_EXAMPLES:
            self.assertIn(f"{label}\n```lua\n{source}```", text)
        for limit in (
            "quiet consumes the triggering slot",
            "not recurrence",
            "0->1, 1->2, 2->3, 3->3",
            "not observed history or witness facts",
            "wired to offline authoring",
            "live evaluation stay gated",
        ):
            self.assertIn(limit, text)

    def test_contract_is_not_loaded_by_the_live_history_prompt(self):
        history = (ROOT / "chaos/history_choice.py").read_text(encoding="utf-8")
        launcher = (ROOT / "chaos/launcher.py").read_text(encoding="utf-8")
        self.assertNotIn("next-use-author.txt", history)
        self.assertNotIn("next-use-author.txt", launcher)
