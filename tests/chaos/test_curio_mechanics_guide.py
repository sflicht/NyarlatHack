"""Sanity/Insight guide reaches compose_prompt. Not a play-distribution study."""

import hashlib
from pathlib import Path
import unittest

from chaos.curio import compose_prompt, MAX_PROMPT_BYTES

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "chaos/prompts/curio/mechanics-sanity-insight.txt"
EVIDENCE = ROOT / "docs/evidence/milestone2-summary.json"
PUBLIC = dict(sanity=100, insight=0)


class SanityInsightGuideTests(unittest.TestCase):
    def test_guide_is_in_authoring_instructions(self):
        text = GUIDE.read_text(encoding="utf-8")
        composed = compose_prompt(PUBLIC).instructions
        self.assertIn(text, composed)
        self.assertTrue(composed.startswith("Curio authoring contract"))

    def test_legal_bound_is_not_called_typical(self):
        text = GUIDE.read_text(encoding="utf-8")
        self.assertIn("0..1000000", text)
        self.assertIn("LEGAL", text)
        self.assertIn("UNKNOWN", text)
        self.assertIn("not typical", text.lower())
        self.assertNotRegex(text, r"typical Insight is \d+")
        self.assertNotRegex(text, r"usually \d+")

    def test_source_and_revision_binding(self):
        text = GUIDE.read_text(encoding="utf-8")
        self.assertIn("082f94611", text)
        self.assertIn("src/attrib.c", text)
        self.assertIn("change_usanity", text)
        self.assertIn("change_uinsight", text)
        self.assertIn("src/u_init.c", text)

    def test_hidden_state_is_not_in_user_payload(self):
        payload = compose_prompt(PUBLIC).prompt
        self.assertNotIn("veil", payload)
        self.assertNotIn("u.uz", payload)
        self.assertNotIn("dungeon", payload)
        self.assertIn('"sanity":100', payload)

    def test_combined_prompt_stays_in_byte_cap(self):
        result = compose_prompt(PUBLIC)
        n = len((result.instructions + result.prompt).encode())
        self.assertLessEqual(n, MAX_PROMPT_BYTES)
        self.assertGreater(n, 5000)

    def test_historical_thimble_evidence_bytes_unchanged(self):
        digest = hashlib.sha256(EVIDENCE.read_bytes()).hexdigest()
        self.assertEqual(
            digest,
            "ae031d481f3c28235978a7177f2a2e6793fd52150434931a07adcfd0493d6b52",
        )


if __name__ == "__main__":
    unittest.main()
