"""Tiny FAKE filesystem assets only: never builds or invokes a native game."""

import ast
import errno
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from gameplay_support import Game


class GameAssetTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.source = self.root / "fake-production"
        self.source.mkdir()
        self.pool = self.root / "suite" / "assets"
        for name, mode in (("dnethack", 0o751), ("nhdat", 0o640), ("license", 0o644)):
            self.asset(
                self.source / name, b"FAKE filesystem fixture: " + name.encode(), mode
            )
        self.custom = self.root / "fake-custom-executable"
        self.asset(self.custom, b"FAKE custom filesystem fixture", 0o755)

    def asset(self, path, data, mode=0o555):
        path.write_bytes(data)
        path.chmod(mode)
        stamp = 1_700_000_000_123456789
        os.utime(path, ns=(stamp, stamp))
        return path

    def game(self, name, **kwargs):
        return Game(
            self.source,
            "unused-fake-preload",
            root=self.root / name,
            asset_pool=self.pool,
            **kwargs,
        )

    def cached(self, game, name="dnethack"):
        return next(
            p
            for p in self.pool.iterdir()
            if p.is_file() and p.samefile(game.game / name)
        )

    def test_shared_readonly_snapshot_not_mutable_source(self):
        a, b = self.game("a"), self.game("b")
        for name in ("dnethack", "nhdat"):
            original, one, two = self.source / name, a.game / name, b.game / name
            self.assertEqual(one.read_bytes(), original.read_bytes())
            self.assertTrue(one.samefile(two))
            self.assertFalse(one.samefile(original))
            self.assertEqual(one.stat().st_nlink, 3)
            self.assertEqual(original.stat().st_nlink, 1)
            self.assertEqual(one.stat().st_mtime_ns, original.stat().st_mtime_ns)
            self.assertEqual(
                stat.S_IMODE(one.stat().st_mode),
                stat.S_IMODE(original.stat().st_mode) & ~0o222,
            )
            self.assertTrue(self.cached(a, name).samefile(one))
        self.assertEqual(len(list(self.pool.iterdir())), 2)

    def test_only_one_copy_per_unique_asset(self):
        import gameplay_support

        with patch(
            "gameplay_support.shutil.copy2", wraps=gameplay_support.shutil.copy2
        ) as copy:
            self.game("a")
            self.game("b")
        for name in ("dnethack", "nhdat"):
            self.assertEqual(
                sum(
                    Path(call.args[0]) == self.source / name
                    for call in copy.call_args_list
                ),
                1,
            )

    def test_source_overwrite_retains_old_artifacts(self):
        a = self.game("a")
        old = (a.game / "dnethack").read_bytes()
        # Same path, same length and mtime: cache keys must use bytes, not stat alone.
        self.asset(self.source / "dnethack", b"X" * len(old), 0o751)
        b = self.game("b")
        self.assertEqual((a.game / "dnethack").read_bytes(), old)
        self.assertEqual((b.game / "dnethack").read_bytes(), b"X" * len(old))
        self.assertFalse((a.game / "dnethack").samefile(b.game / "dnethack"))
        self.assertEqual(len(list(self.pool.iterdir())), 3)

    def test_metadata_changes_have_distinct_snapshots(self):
        a = self.game("a")
        stamp = 1_800_000_000_987654321
        os.utime(self.source / "dnethack", ns=(stamp, stamp))
        (self.source / "dnethack").chmod(0o711)
        b = self.game("b")
        self.assertFalse((a.game / "dnethack").samefile(b.game / "dnethack"))
        self.assertEqual(stat.S_IMODE((b.game / "dnethack").stat().st_mode), 0o511)
        self.assertEqual(
            (b.game / "dnethack").stat().st_mtime_ns,
            (self.source / "dnethack").stat().st_mtime_ns,
        )

    def test_atomic_executable_replacement_isolates_other_cases(self):
        a, b = self.game("a"), self.game("b")
        cached = self.cached(a)
        old = cached.read_bytes()
        original_inode = cached.stat().st_ino
        a.install_executable(self.custom)
        self.assertEqual((a.game / "dnethack").read_bytes(), self.custom.read_bytes())
        self.assertEqual((b.game / "dnethack").read_bytes(), old)
        self.assertEqual(cached.read_bytes(), old)
        self.assertEqual(cached.stat().st_ino, original_inode)
        c = self.game("c", executable=self.custom)
        self.assertTrue((a.game / "dnethack").samefile(c.game / "dnethack"))

    def test_custom_constructor_never_copies_production_executable(self):
        (self.source / "dnethack").unlink()
        a = self.game("a", executable=self.custom)
        self.assertEqual((a.game / "dnethack").read_bytes(), self.custom.read_bytes())
        self.assertEqual(len(list(self.pool.iterdir())), 2)

    def test_mutable_files_and_directories_remain_private(self):
        a, b = self.game("a"), self.game("b")
        names = ("perm", "record", "logfile", "xlogfile", "livelog", "license")
        for name in names:
            before = (b.game / name).read_bytes()
            (a.game / name).write_bytes(b"private case evidence")
            self.assertEqual((b.game / name).read_bytes(), before)
            self.assertEqual((a.game / name).stat().st_nlink, 1)
        for first, second in (
            (a.run, b.run),
            (a.game / "save", b.game / "save"),
            (a.game / "dumplog", b.game / "dumplog"),
        ):
            (first / "private").write_bytes(b"private evidence")
            self.assertFalse((second / "private").exists())
        before = {
            p: (p.stat().st_ino, p.read_bytes())
            for base in (a.run, a.game)
            for p in base.rglob("*")
            if p.is_file() and p.name not in ("dnethack", "nhdat")
        }
        a.install_executable(self.custom)
        self.assertEqual(before, {p: (p.stat().st_ino, p.read_bytes()) for p in before})
        self.assertEqual(stat.S_IMODE(a.run.stat().st_mode), 0o700)

    def test_default_stays_private_and_writable(self):
        a = Game(self.source, "unused", root=self.root / "a")
        b = Game(self.source, "unused", root=self.root / "b")
        (a.game / "dnethack").write_bytes(b"legacy overwrite")
        self.assertEqual(
            (b.game / "dnethack").read_bytes(), (self.source / "dnethack").read_bytes()
        )
        self.assertEqual(stat.S_IMODE((b.game / "dnethack").stat().st_mode), 0o751)
        self.assertFalse(self.pool.exists())

    def test_corrupt_pool_entry_is_not_overwritten(self):
        a = self.game("a")
        cached = self.cached(a)
        cached.unlink()  # Do NOT corrupt through a shared inode, even in this test.
        self.asset(cached, b"CORRUPT fake snapshot")
        with self.assertRaises((ValueError, OSError)):
            self.game("b")
        self.assertEqual(cached.read_bytes(), b"CORRUPT fake snapshot")
        self.assertEqual(
            (a.game / "dnethack").read_bytes(), (self.source / "dnethack").read_bytes()
        )

    def test_symlink_and_special_pool_entries_rejected(self):
        a = self.game("a")
        cached = self.cached(a)
        for kind in ("symlink", "fifo", "directory"):
            with self.subTest(kind=kind):
                cached.unlink()
                if kind == "symlink":
                    cached.symlink_to(self.source / "dnethack")
                elif kind == "fifo":
                    os.mkfifo(cached)
                else:
                    cached.mkdir()
                with self.assertRaises((ValueError, OSError)):
                    self.game(kind)
                if kind == "directory":
                    cached.rmdir()
                    cached.touch()

    def test_symlink_pool_root_rejected(self):
        self.pool.parent.mkdir(parents=True)
        self.pool.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises((ValueError, OSError)):
            self.game("a")

    def test_publication_race_never_clobbers_winner(self):
        real_link = os.link
        winner = []

        def race(src, dst, **kwargs):
            dst = Path(dst)
            if dst.parent == self.pool:
                self.asset(dst, b"unexpected competing snapshot")
                winner.append(dst)
            return real_link(src, dst, **kwargs)

        with patch("gameplay_support.os.link", side_effect=race):
            with self.assertRaises((ValueError, OSError)):
                self.game("a")
        self.assertEqual(len(winner), 1)
        self.assertEqual(winner[0].read_bytes(), b"unexpected competing snapshot")
        self.assertEqual(list(self.pool.iterdir()), winner)

    def test_replace_failure_preserves_executable_and_snapshot(self):
        a = self.game("a")
        cached = self.cached(a)
        before = (cached.stat().st_ino, cached.read_bytes())
        with patch(
            "gameplay_support.os.replace", side_effect=OSError(errno.EIO, "injected")
        ):
            with self.assertRaises(OSError):
                a.install_executable(self.custom)
        self.assertTrue(cached.samefile(a.game / "dnethack"))
        self.assertEqual((cached.stat().st_ino, cached.read_bytes()), before)
        self.assertFalse(any(p.name.startswith(".asset-") for p in a.game.iterdir()))

    def test_hardlink_fallback_is_private_exact_and_readonly(self):
        for code in (errno.EXDEV, errno.EOPNOTSUPP, errno.EPERM):
            with self.subTest(errno=code):
                with patch(
                    "gameplay_support.os.link", side_effect=OSError(code, "injected")
                ):
                    a, b = self.game(f"a-{code}"), self.game(f"b-{code}")
                for name in ("dnethack", "nhdat"):
                    one, two, original = (
                        a.game / name,
                        b.game / name,
                        self.source / name,
                    )
                    self.assertEqual(one.read_bytes(), original.read_bytes())
                    self.assertEqual(
                        one.stat().st_mtime_ns, original.stat().st_mtime_ns
                    )
                    self.assertEqual(
                        stat.S_IMODE(one.stat().st_mode),
                        stat.S_IMODE(original.stat().st_mode) & ~0o222,
                    )
                    self.assertEqual(one.stat().st_nlink, 1)
                    self.assertFalse(one.samefile(two))
                    self.assertFalse(one.samefile(original))
                self.asset(
                    self.source / "dnethack", f"FAKE newer build {code}".encode(), 0o751
                )
                self.assertNotEqual(
                    (a.game / "dnethack").read_bytes(),
                    (self.source / "dnethack").read_bytes(),
                )

    def test_next_use_suite_selects_shared_assets_before_construction(self):
        # Static wiring guard only; do not import or execute the native suite.
        tree = ast.parse(
            Path(__file__).with_name("test_next_use_unix_save.py").read_text()
        )
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "Game"
        ]
        self.assertEqual(len(calls), 2)
        for node in calls:
            keywords = {kw.arg: ast.unparse(kw.value) for kw in node.keywords}
            self.assertEqual(keywords.get("asset_pool"), "self.asset_pool")
        custom = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "_two_family_order"
        )
        call = next(
            n for n in ast.walk(custom) if isinstance(n, ast.Call) and n in calls
        )
        self.assertEqual(
            {kw.arg: ast.unparse(kw.value) for kw in call.keywords}.get("executable"),
            "self.two_family_exe",
        )
        build = next(
            n
            for n in ast.walk(custom)
            if isinstance(n, ast.Call)
            and ast.unparse(n.func) == "self._build_two_family_game"
        )
        self.assertLess(build.lineno, call.lineno)
        self.assertNotIn("shutil.copy2(self.two_family_exe", ast.unparse(custom))

    def test_tiny_allocation_evidence(self):
        a, b = self.game("a"), self.game("b")
        paths = [
            self.source / "dnethack",
            self.cached(a),
            a.game / "dnethack",
            b.game / "dnethack",
        ]
        stats = [path.stat() for path in paths]
        records = [
            {
                "path": str(path.relative_to(self.root)),
                "size": info.st_size,
                "blocks_512": info.st_blocks,
                "allocated_bytes": info.st_blocks * 512,
                "nlink": info.st_nlink,
                "inode": info.st_ino,
            }
            for path, info in zip(paths, stats)
        ]
        unique = {(s.st_dev, s.st_ino): s.st_blocks * 512 for s in stats[1:]}
        self.assertEqual(len(unique), 1)
        self.assertEqual(sum(unique.values()), stats[1].st_blocks * 512)
        print("FAKE_ASSET_ALLOCATION=" + json.dumps(records), flush=True)

    def test_cross_device_case_fallback_keeps_single_pool_snapshot(self):
        a = self.game("a")
        real_link = os.link

        def cross_device(src, dst, **kwargs):
            if Path(dst).parent.parent == self.root / "b/game":
                raise OSError(errno.EXDEV, "injected case filesystem boundary")
            return real_link(src, dst, **kwargs)

        with patch("gameplay_support.os.link", side_effect=cross_device):
            b = self.game("b")
        for name in ("dnethack", "nhdat"):
            self.assertEqual((a.game / name).read_bytes(), (b.game / name).read_bytes())
            self.assertFalse((a.game / name).samefile(b.game / name))
            self.assertEqual((b.game / name).stat().st_nlink, 1)
            self.assertEqual((a.game / name).stat().st_nlink, 2)
        self.assertEqual(len(list(self.pool.iterdir())), 2)

    def test_valid_concurrent_publication_reuses_winner(self):
        import shutil

        real_link = os.link

        def race(src, dst, **kwargs):
            if Path(dst).parent == self.pool:
                shutil.copy2(src, dst)  # Simulated complete, separate winning snapshot.
            return real_link(src, dst, **kwargs)

        with patch("gameplay_support.os.link", side_effect=race):
            a = self.game("a")
        self.assertTrue(self.cached(a).samefile(a.game / "dnethack"))
        self.assertEqual((a.game / "dnethack").stat().st_nlink, 2)

    def test_writable_pool_entry_rejected_without_chmod(self):
        a = self.game("a")
        cached = self.cached(a)
        cached.unlink()
        self.asset(cached, (self.source / "dnethack").read_bytes(), 0o751)
        with self.assertRaisesRegex(ValueError, "writable pool asset"):
            self.game("b")
        self.assertEqual(stat.S_IMODE(cached.stat().st_mode), 0o751)

    def test_unexpected_link_error_fails_closed(self):
        with patch(
            "gameplay_support.os.link", side_effect=OSError(errno.EIO, "injected")
        ):
            with self.assertRaises(OSError):
                self.game("a")
        self.assertFalse((self.root / "a/game/dnethack").exists())
        self.assertEqual(list(self.pool.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
