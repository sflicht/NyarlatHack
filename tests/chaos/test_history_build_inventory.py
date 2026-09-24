"""Current build metadata regressions; no compilation or gameplay evidence."""

import copy
import json
from pathlib import Path
import re
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_history_gameplay as subject

ROOT = Path(__file__).resolve().parents[2]


class HashVerificationReached(Exception):
    """Stop after inventory validation, before linking or running a game."""


class HistoryBuildInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Evaluate only the actual object assignments, not the full makefile:
        # even make -n on it can regenerate included dependency files.
        text = (ROOT / "GNUmakefile").read_text().replace("\\\n", " ")
        assignments = "\n".join(
            line
            for line in text.splitlines()
            if re.match(
                r"^(?:SRCOBJ|SYSUNIXOBJ|SYSSHAREOBJ|WINTTYOBJ|WINCURSESOBJ|[A-Z_]+_O)\s*\+?=",
                line,
            )
        )
        # All SRCOBJ additions are CHAOS=1 additions; the hook inventory checks
        # their enclosing conditional separately. No recipes/includes copied.
        with tempfile.TemporaryDirectory(prefix="history-inventory-") as directory:
            makefile = Path(directory) / "inventory.mk"
            makefile.write_text(
                assignments
                + "\n.PHONY: inventory\ninventory:\n\t@printf '%s\\n' $(sort $(ALL_O))\n"
            )
            cls.objects = set(
                subprocess.check_output(
                    [
                        "/usr/bin/make",
                        "-rR",
                        "-s",
                        "-f",
                        str(makefile),
                        "CHAOS=1",
                        "inventory",
                    ],
                    cwd=directory,
                    text=True,
                    timeout=10,
                ).splitlines()
            )
        # Source-controlled headers plus the build-generated headers, independent
        # of any receipt and available without preparing a native build.
        cls.headers = set(
            subprocess.check_output(
                ["/usr/bin/git", "ls-files", "include/*.h"],
                cwd=ROOT,
                text=True,
                timeout=10,
            ).splitlines()
        ) | {
            "include/date.h",
            "include/dgn_comp.h",
            "include/gnames.h",
            "include/lev_comp.h",
            "include/onames.h",
            "include/pm.h",
            "include/verinfo.h",
        }

    def setUp(self):
        # Synthetic hashes, deliberately never accepted as compiled evidence.
        self.manifest: dict = dict(
            mode=1,
            revision="0" * 40,
            objects=dict.fromkeys(self.objects, "0" * 64),
            generated_headers=dict.fromkeys(self.headers, "0" * 64),
        )

    def preflight(self, manifest):
        with tempfile.TemporaryDirectory(prefix="history-receipt-unit-") as directory:
            parent = Path(directory)
            receipt = parent / "receipt.json"
            receipt.write_text(json.dumps(manifest))
            args = SimpleNamespace(
                root=str(ROOT),
                receipt=str(receipt),
                output=str(parent / "output"),
                revision=manifest["revision"],
            )
            # Exercise the real driver guards, stopping at the first protected
            # hash read. Never accept synthetic hashes or enter native linking.
            with (
                patch.object(subject, "digest", side_effect=HashVerificationReached),
                patch.object(subject.os, "umask"),
            ):
                subject.native(args)

    def test_current_make_inventory_reaches_hash_verification(self):
        self.assertIn("src/chaos_next_use_journal.o", self.objects)
        self.assertIn("include/chaos_next_use_journal.h", self.headers)
        with self.assertRaises(HashVerificationReached):
            self.preflight(self.manifest)

    def test_missing_or_extra_object_rejected(self):
        for missing in sorted(self.objects):
            manifest = copy.deepcopy(self.manifest)
            del manifest["objects"][missing]
            with (
                self.subTest(missing=missing),
                self.assertRaisesRegex(
                    ValueError, "complete original production object receipt"
                ),
            ):
                self.preflight(manifest)
        self.manifest["objects"]["src/unreviewed.o"] = "0" * 64
        with self.assertRaisesRegex(
            ValueError, "complete original production object receipt"
        ):
            self.preflight(self.manifest)

    def test_journal_object_cannot_be_replaced_at_same_count(self):
        objects = self.manifest["objects"]
        objects["src/unreviewed.o"] = objects.pop("src/chaos_next_use_journal.o")
        with self.assertRaisesRegex(
            ValueError, "complete original production object receipt"
        ):
            self.preflight(self.manifest)

    def test_missing_or_extra_header_rejected(self):
        for missing in sorted(self.headers):
            manifest = copy.deepcopy(self.manifest)
            del manifest["generated_headers"][missing]
            with (
                self.subTest(missing=missing),
                self.assertRaisesRegex(ValueError, "complete frozen header receipt"),
            ):
                self.preflight(manifest)
        self.manifest["generated_headers"]["include/unreviewed.h"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "complete frozen header receipt"):
            self.preflight(self.manifest)

    def test_journal_header_cannot_be_replaced_at_same_count(self):
        headers = self.manifest["generated_headers"]
        headers["include/unreviewed.h"] = headers.pop(
            "include/chaos_next_use_journal.h"
        )
        with self.assertRaisesRegex(ValueError, "complete frozen header receipt"):
            self.preflight(self.manifest)


if __name__ == "__main__":
    unittest.main()
