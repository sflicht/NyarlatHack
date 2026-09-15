"""Curio startup with a real fake-game process, not a native engine build."""

from contextlib import redirect_stderr
import io

import os
from pathlib import Path
import signal
import unittest
from unittest.mock import patch

from chaos import curio_store as store
from chaos.__main__ import main
from chaos.director import Mailbox
from test_curio_cli import SOURCE, put, snapshot
import test_launcher as launcher_fixture


class CurioLauncherTests(unittest.TestCase):
    run_cli = launcher_fixture.LauncherTests.run_cli
    info = launcher_fixture.LauncherTests.info
    assert_reaped = launcher_fixture.LauncherTests.assert_reaped
    start_waiting = launcher_fixture.LauncherTests.start_waiting

    def setUp(self):
        launcher_fixture.LauncherTests.setUp(self)
        self.source = self.path / "source.lua"
        put(self.source, SOURCE)
        # Extend the existing controlled fake executable, not its assertions.
        self.game.write_text(
            launcher_fixture.GAME.replace(
                "pathlib.Path(os.environ['GAME_MARKER']).write_text(json.dumps(info))",
                "info['source'] = (run / 'curio.lua').read_bytes().hex()\n"
                "info['source_mode'] = (run / 'curio.lua').stat().st_mode & 0o777\n"
                "info['source_links'] = (run / 'curio.lua').stat().st_nlink\n"
                "info['receipt'] = json.loads((run / 'curio-install.json').read_text())\n"
                "pathlib.Path(os.environ['GAME_MARKER']).write_text(json.dumps(info))",
            )
        )

    def test_fresh_exact_source_visible_before_both_children_under_same_lock(self):
        run = self.path / "fresh"
        from chaos import launcher

        original = launcher._fork_director

        def checked(*args):
            self.assertEqual((run / "curio.lua").read_bytes(), SOURCE)
            self.assertEqual((run / "curio.lua").stat().st_nlink, 1)
            with self.assertRaises(ValueError):
                Mailbox(run)
            return original(*args)

        with (
            patch.dict(os.environ, self.env),
            redirect_stderr(io.StringIO()),
            patch("chaos.launcher._fork_director", side_effect=checked) as fork,
        ):
            status = main(
                [
                    "play",
                    "--game-root",
                    str(self.root),
                    "--run-dir",
                    str(run),
                    "--curio-source",
                    str(self.source),
                ]
            )
        self.assertEqual(status, 0)
        fork.assert_called_once()
        info = self.info()
        self.assertTrue(info["locked"])
        self.assertEqual(info["source"], SOURCE.hex())
        self.assertEqual(info["source_mode"], 0o600)
        self.assertEqual(info["source_links"], 1)
        self.assert_reaped(info)

    def test_real_cli_fresh_then_matching_restore_does_not_reinstall_or_retime(self):
        run = self.path / "fresh"
        p = self.run_cli("--run-dir", str(run), "--curio-source", str(self.source))
        self.assertEqual(p.returncode, 0, p.stderr)
        put(run / "curio-used.lua", SOURCE)
        evidence = {
            name: ((run / name).read_bytes(), (run / name).stat())
            for name in (
                "curio.lua",
                "curio-used.lua",
                "curio-install.json",
                "whisper.json",
            )
        }
        p = self.run_cli(
            "--reuse-run-dir", str(run), "--curio-source", str(self.source)
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        for name, (raw, st) in evidence.items():
            self.assertEqual((run / name).read_bytes(), raw)
            now = (run / name).stat()
            self.assertEqual(
                (now.st_ino, now.st_mtime_ns, now.st_ctime_ns),
                (st.st_ino, st.st_mtime_ns, st.st_ctime_ns),
            )
        self.assert_reaped(self.info())

    def test_restore_conflicts_never_fork_or_launch_or_repair(self):
        for kind in ("source", "used", "receipt", "missing", "missing-lock", "symlink"):
            with self.subTest(kind=kind):
                run = self.path / kind
                run.mkdir(mode=0o700)
                store.install_saved_source(run, source_file=self.source)
                if kind == "source":
                    put(run / "curio.lua", b"conflict")
                elif kind == "used":
                    put(run / "curio-used.lua", b"conflict")
                elif kind == "receipt":
                    put(run / "curio-install.json", b"{partial")
                elif kind == "missing":
                    (run / "curio-install.json").unlink()
                elif kind == "missing-lock":
                    (run / ".director.lock").unlink()
                else:
                    (run / "curio.lua").unlink()
                    (run / "curio.lua").symlink_to(self.source)
                before = snapshot(run)
                with (
                    patch("chaos.launcher._fork_director") as fork,
                    patch("chaos.launcher.subprocess.Popen") as game,
                    redirect_stderr(io.StringIO()),
                ):
                    status = main(
                        [
                            "play",
                            "--game-root",
                            str(self.root),
                            "--reuse-run-dir",
                            str(run),
                            "--curio-source",
                            str(self.source),
                        ]
                    )
                self.assertEqual(status, 2)
                fork.assert_not_called()
                game.assert_not_called()
                self.assertEqual(snapshot(run), before)

    def test_unsafe_source_rejects_before_new_run_directory(self):
        self.source.chmod(0o644)
        run = self.path / "absent"
        p = self.run_cli("--run-dir", str(run), "--curio-source", str(self.source))
        self.assertEqual(p.returncode, 2)
        self.assertFalse(run.exists())
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.source.stat().st_mode & 0o777, 0o644)

    def test_external_writer_blocks_restore_and_installer(self):
        run = self.path / "busy"
        run.mkdir(mode=0o700)
        store.install_saved_source(run, source_file=self.source)
        before = snapshot(run)
        with Mailbox(run):
            p = self.run_cli(
                "--reuse-run-dir", str(run), "--curio-source", str(self.source)
            )
        self.assertEqual(p.returncode, 2)
        self.assertFalse(self.marker.exists())
        self.assertEqual(snapshot(run), before)

    def test_curio_supervisor_signal_reaps_children_and_releases_lock(self):
        p = self.start_waiting("--curio-source", str(self.source))
        info = self.info()
        p.send_signal(signal.SIGTERM)
        p.communicate(timeout=8)
        self.assertEqual(p.returncode, -signal.SIGTERM)
        self.assertFalse(Path("/proc", str(info["pid"])).exists())
        self.assert_reaped(info)

    def test_default_play_real_process_never_imports_model_or_credentials(self):
        import subprocess
        import sys

        self.game.write_text(launcher_fixture.GAME)
        guard = """
import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('chaos.curio_generation', 'chaos.oauth', 'chaos.model', 'agent') or fullname.startswith('agent.'):
            raise AssertionError('FORBIDDEN_IMPORT')
sys.meta_path.insert(0, Guard())
from chaos.__main__ import main
sys.exit(main(sys.argv[1:]))
"""
        p = subprocess.run(
            [sys.executable, "-c", guard, "play", "--game-root", str(self.root)],
            cwd=launcher_fixture.ROOT,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("FORBIDDEN_IMPORT", p.stderr)
        self.assert_reaped(self.info())

    def test_locked_seam_restore_has_no_write_or_sync_and_replaced_lock_rejects(self):
        from chaos import launcher

        run = self.path / "locked"
        run.mkdir(mode=0o700)
        store.install_saved_source(run, source_file=self.source)
        prepared = store._source(self.source, None, None)
        with Mailbox(run) as box:
            with (
                patch.object(store, "_publish", side_effect=AssertionError("write")),
                patch.object(store.os, "fsync", side_effect=AssertionError("sync")),
            ):
                launcher._curio_install(run, box, prepared, restore=True)
            (run / ".director.lock").rename(run / "old-lock")
            put(run / ".director.lock", b"")
            before = snapshot(run)
            with self.assertRaises(ValueError):
                launcher._curio_install(run, box, prepared, restore=True)
            self.assertEqual(snapshot(run), before)


if __name__ == "__main__":
    unittest.main()
