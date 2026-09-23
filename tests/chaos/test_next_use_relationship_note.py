"""The recurrence note must not raise caps."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
NOTE = ROOT / "docs/next-use-relationship.md"


class NextUseRelationshipNoteTests(unittest.TestCase):
    def test_note_keeps_existing_limits(self):
        text = NOTE.read_text(encoding="utf-8")
        self.assertIn("Do not reset a consumed slot", text)
        self.assertIn("Do not raise the use cap", text)
        self.assertIn("ordinary acceptance is still open", text)
        self.assertNotIn("increase the use cap to", text)
