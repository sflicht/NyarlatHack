"""Unit tests for scripts/clean_workspace.py, using temp fixtures only."""

import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location(
        "clean_workspace_unit", ROOT / "scripts/clean_workspace.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cw = load()
OLD = 30 * cw.DAY


class CleanWorkspaceTests(unittest.TestCase):
    def setUp(self):
        base = tempfile.TemporaryDirectory(prefix="clean-workspace-unit-")
        self.addCleanup(base.cleanup)
        self.base = Path(os.path.realpath(base.name))
        self.work = self.base / "nyarlathack-work"
        self.named = self.base / "tmp"
        self.outside = self.base / "elsewhere"
        for d in (self.work, self.named, self.outside):
            d.mkdir()
        self.roots = cw.Roots(self.work, [self.named])

    def make(self, path, age_days=30.0, size=4096):
        path.mkdir(parents=True)
        (path / "events.jsonl").write_bytes(b"x" * size)
        when = time.time() - age_days * cw.DAY
        for p in (path / "events.jsonl", path):
            os.utime(p, (when, when), follow_symlinks=False)
        return path

    def clean(self, paths=(), **kw):
        out = io.StringIO()
        status, total = cw.run(list(paths), roots=self.roots, out=out, **kw)
        return status, total, out.getvalue()

    def test_dry_run_deletes_nothing_and_reports_bytes(self):
        a = self.make(self.work / "run-1")
        b = self.make(self.named / "nyarl-sweep-abc")
        status, total, text = self.clean()
        self.assertEqual(status, 0)
        self.assertTrue(a.exists() and b.exists())
        self.assertGreater(total, 0)
        self.assertIn("would delete", text)
        self.assertIn(f"would free {total} bytes", text)

    def test_apply_deletes_old_candidates_and_reports_freed(self):
        a = self.make(self.work / "run-1")
        b = self.make(self.named / "nyarlathack-abc")
        status, total, text = self.clean(apply=True)
        self.assertEqual(status, 0)
        self.assertFalse(a.exists() or b.exists())
        self.assertIn(f"freed {total} bytes", text)

    def test_unrelated_names_in_named_roots_are_not_candidates(self):
        other = self.make(self.named / "seti-meta-run")
        self.clean(apply=True)
        self.assertTrue(other.exists())

    def test_refuses_paths_outside_allowed_roots(self):
        victims = [
            self.make(self.outside / "nyarl-x"),
            self.make(self.named / "bridge-run"),
            self.make(self.work / "run-1" / "nested"),
        ]
        status, total, text = self.clean([str(v) for v in victims], apply=True)
        self.assertEqual(status, 2)
        self.assertEqual(total, 0)
        self.assertTrue(all(v.exists() for v in victims))
        self.assertEqual(text.count("refuse "), 3)
        for root in (self.work, self.named):
            self.assertIsNotNone(cw.refusal(root, self.roots))

    def test_does_not_follow_symlinks(self):
        target = self.make(self.outside / "precious")
        link = self.work / "run-link"
        link.symlink_to(target, target_is_directory=True)
        inner = self.make(self.work / "run-2")
        (inner / "escape").symlink_to(target, target_is_directory=True)
        old = time.time() - OLD
        for p in (inner / "escape", inner):
            os.utime(p, (old, old), follow_symlinks=False)
        via = self.base / "via"
        via.symlink_to(self.work, target_is_directory=True)
        status, _, text = self.clean([str(link), str(via / "run-2")], apply=True)
        self.assertEqual(status, 2)
        self.assertTrue(link.is_symlink() and inner.exists())
        self.clean(apply=True)  # scan mode: link skipped, run-2 removed
        self.assertTrue(link.is_symlink())
        self.assertFalse(inner.exists())
        self.assertTrue((target / "events.jsonl").exists())

    def test_keep_marker_is_honoured(self):
        kept = self.make(self.work / "run-kept")
        (kept / "KEEP").touch()
        status, total, text = self.clean([str(kept)], apply=True)
        self.assertTrue(kept.exists())
        self.assertIn("KEEP marker", text)
        self.assertEqual(total, 0)

    def test_in_use_items_are_skipped(self):
        busy = self.make(self.work / "run-busy")
        proc = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"], cwd=busy
        )
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        deadline = time.monotonic() + 10
        while str(busy) not in cw.held_paths() and time.monotonic() < deadline:
            time.sleep(0.05)
        _, total, text = self.clean(apply=True)
        self.assertTrue(busy.exists())
        self.assertIn("in use", text)
        self.assertEqual(total, 0)

    def test_age_filter_applies_to_scans_not_explicit_paths(self):
        young = self.make(self.work / "run-young", age_days=1)
        old = self.make(self.work / "run-old", age_days=8)
        self.clean(apply=True)  # default --max-age 7
        self.assertTrue(young.exists())
        self.assertFalse(old.exists())
        self.clean(apply=True, max_age=0.5)
        self.assertFalse(young.exists())
        fresh = self.make(self.work / "run-own", age_days=0)
        self.clean([str(fresh)], apply=True)  # end-of-run: any age
        self.assertFalse(fresh.exists())

    def test_cli_defaults_to_dry_run(self):
        with tempfile.TemporaryDirectory(prefix="nyarl-cli-unit-", dir="/tmp") as d:
            probe = Path(d) / "events.jsonl"
            probe.write_text("{}")
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/clean_workspace.py"), d],
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(probe.exists())
            self.assertIn("would free", result.stdout)
        with mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(cw.main(["--max-age", "7", "/etc"]), 2)


if __name__ == "__main__":
    unittest.main()
