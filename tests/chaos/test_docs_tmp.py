"""#176: docs must not cite /tmp/ beyond the frozen historical allowlist."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_docs_tmp  # noqa: E402


class DocsTmpTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "docs").mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def add(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        subprocess.run(["git", "add", name], cwd=self.root, check=True)

    def check(self, files):
        return check_docs_tmp.violations(self.root, {"files": files})

    def test_repository_is_clean_against_its_allowlist(self):
        self.assertEqual(check_docs_tmp.main([]), 0)

    def test_new_file_with_tmp_citation_fails(self):
        self.add("docs/new.md", "See /tmp/nyarl-run-1/result.json for details\n")
        self.assertEqual(
            self.check({}), ["docs/new.md: /tmp/nyarl-run-1/result.json (1 new)"]
        )

    def test_allowlisted_citation_passes_and_extra_copy_fails(self):
        self.add("docs/old.md", "`/tmp/a.log` and `/tmp/a.log`\n")
        self.assertEqual(self.check({"docs/old.md": {"/tmp/a.log": 2}}), [])
        self.assertEqual(
            self.check({"docs/old.md": {"/tmp/a.log": 1}}),
            ["docs/old.md: /tmp/a.log (1 new)"],
        )

    def test_changed_file_adding_a_different_citation_fails(self):
        self.add("docs/old.md", "/tmp/a.log\n/tmp/b.log\n")
        self.assertEqual(
            self.check({"docs/old.md": {"/tmp/a.log": 1}}),
            ["docs/old.md: /tmp/b.log (1 new)"],
        )

    def test_durable_paths_and_untracked_files_pass(self):
        self.add("docs/ok.md", "~/nyarlathack-evidence/tmp-2026-09/x and $TMPDIR/y\n")
        (self.root / "docs" / "untracked.md").write_text("/tmp/z\n")
        self.assertEqual(self.check({}), [])

    def test_allowlist_points_at_the_mapping(self):
        data = json.loads(check_docs_tmp.ALLOWLIST.read_text())
        self.assertEqual(
            data["mapping"], "~/nyarlathack-evidence/tmp-2026-09/MAPPING.json"
        )


if __name__ == "__main__":
    unittest.main()
