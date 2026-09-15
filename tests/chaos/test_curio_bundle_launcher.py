"""Proposed explicit bundle launcher contract; fake processes, not native proof.

Prepared test-first without execution. The byte-preservation fixture is honestly
handwritten transport input, NOT valid native hooks or model-authorship evidence.
"""

from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from chaos import curio_store as store, launcher
from chaos.__main__ import main
from chaos.director import Mailbox
from test_curio_cli import SOURCE, put, snapshot
import test_launcher as launcher_fixture


@unittest.skipUnless(sys.platform.startswith("linux"), "POSIX/Linux process fixtures")
class CurioBundleLauncherTests(unittest.TestCase):
    run_cli = launcher_fixture.LauncherTests.run_cli
    info = launcher_fixture.LauncherTests.info
    assert_reaped = launcher_fixture.LauncherTests.assert_reaped

    def setUp(self):
        launcher_fixture.LauncherTests.setUp(self)
        self.bundles = self.path / "bundles"
        self.bundles.mkdir(mode=0o700)
        self.candidate = store.store_candidate(
            self.bundles,
            json.dumps(
                dict(lua_source=SOURCE.decode(), continuity_note="Handwritten fixture")
            ),
        )
        self.bundle = self.bundles / self.candidate.candidate_id
        self.source = self.bundle / "source.lua"
        self.selection = [
            "--curio-bundle-root",
            str(self.bundles),
            "--curio-candidate-id",
            self.candidate.candidate_id,
        ]
        self.receipt = {
            "version": 1,
            "status": "candidate_installed_not_admitted",
            "source_sha256": self.candidate.candidate_id,
            "provenance": "supplied_raw_envelope",
        }
        # Reuse the real process fixture's marker, lock probe and PID collection.
        marker_line = (
            "pathlib.Path(os.environ['GAME_MARKER']).write_text(json.dumps(info))"
        )
        self.assertEqual(launcher_fixture.GAME.count(marker_line), 1)
        self.game.write_text(
            launcher_fixture.GAME.replace(
                marker_line,
                "info['source'] = (run / 'curio.lua').read_bytes().hex()\n"
                "info['source_mode'] = (run / 'curio.lua').stat().st_mode & 0o777\n"
                "info['source_links'] = (run / 'curio.lua').stat().st_nlink\n"
                "info['receipt'] = json.loads((run / 'curio-install.json').read_text())\n"
                + marker_line,
            )
        )

    def invoke(self, *options):
        """Exercise real parsing; normalize argparse's SystemExit, not errors."""
        err = io.StringIO()
        with patch.dict(os.environ, self.env), redirect_stderr(err):
            try:
                status = main(["play", "--game-root", str(self.root), *options])
            except SystemExit as exc:
                status = exc.code
        return status, err.getvalue()

    def preinstall(self, name, *, plain=False):
        run = self.path / name
        run.mkdir(mode=0o700)
        if plain:
            store.install_saved_source(run, source_file=self.source)
        else:
            store.install_saved_source(
                run,
                bundle_root=self.bundles,
                candidate_id=self.candidate.candidate_id,
            )
        return run

    def assert_installed(self, run):
        self.assertEqual((run / "curio.lua").read_bytes(), SOURCE)
        for name in ("curio.lua", "curio-install.json"):
            st = (run / name).stat()
            self.assertEqual(st.st_mode & 0o777, 0o600)
            self.assertEqual(st.st_uid, os.getuid())
            self.assertEqual(st.st_nlink, 1)
        self.assertEqual(
            json.loads((run / "curio-install.json").read_bytes()), self.receipt
        )

    def assert_game_evidence(self):
        info = self.info()
        self.assertTrue(info["locked"])
        self.assertEqual(info["source"], SOURCE.hex())
        self.assertEqual(info["source_mode"], 0o600)
        self.assertEqual(info["source_links"], 1)
        self.assertEqual(info["receipt"], self.receipt)
        self.assertFalse(Path("/proc", str(info["pid"])).exists())
        self.assert_reaped(info)

    def assert_rejected_without_children(self, *options):
        with (
            patch("chaos.launcher._fork_director") as fork,
            patch("chaos.launcher.subprocess.Popen") as game,
        ):
            status, err = self.invoke(*options)
        self.assertEqual(status, 2, err)
        fork.assert_not_called()
        game.assert_not_called()
        self.assertFalse(self.marker.exists())
        self.assertNotIn("SECRET", err)
        self.assertNotIn("\x1b", err)

    def test_real_cli_fresh_bundle_then_restore_preserves_evidence(self):
        # First future RED target: current real CLI lacks these valid options.
        run = self.path / "fresh"
        bundle_before = snapshot(self.bundles)
        p = self.run_cli("--run-dir", str(run), *self.selection)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assert_installed(run)
        self.assert_game_evidence()
        put(run / "curio-used.lua", SOURCE)
        names = ("curio.lua", "curio-used.lua", "curio-install.json", "whisper.json")
        before = {name: value for name, value in snapshot(run).items() if name in names}
        self.marker.unlink()
        p = self.run_cli("--reuse-run-dir", str(run), *self.selection)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(
            {name: value for name, value in snapshot(run).items() if name in names},
            before,
        )
        self.assertEqual(snapshot(self.bundles), bundle_before)
        self.assert_installed(run)
        self.assert_game_evidence()

    def test_fresh_bundle_verified_before_both_children_with_same_held_lock(self):
        run = self.path / "ordered"
        original_install, original_fork = (
            launcher._curio_install,
            launcher._fork_director,
        )
        held = {}

        def checked_install(directory, box, prepared, *, restore):
            held["fd"] = box.lock
            held["inode"] = os.fstat(box.lock).st_ino
            self.assertEqual(prepared, (SOURCE, "supplied_raw_envelope"))
            self.assertFalse(restore)
            with self.assertRaises(ValueError):
                Mailbox(run)
            result = original_install(directory, box, prepared, restore=restore)
            self.assert_installed(run)
            return result

        def checked_fork(box, *args):
            self.assertEqual(box.lock, held["fd"])
            self.assertEqual(os.fstat(box.lock).st_ino, held["inode"])
            self.assertEqual((run / ".director.lock").stat().st_ino, held["inode"])
            self.assert_installed(run)
            with self.assertRaises(ValueError):
                Mailbox(run)
            return original_fork(box, *args)

        with (
            patch.object(
                launcher, "_curio_install", side_effect=checked_install
            ) as install,
            patch.object(launcher, "_fork_director", side_effect=checked_fork) as fork,
        ):
            status, err = self.invoke("--run-dir", str(run), *self.selection)
        self.assertEqual(status, 0, err)
        install.assert_called_once()
        fork.assert_called_once()
        self.assert_game_evidence()

    def test_preinstalled_bundle_reuse_optional_used_source_is_verify_only(self):
        original = launcher._curio_install

        def readonly_install(*args, **kwargs):
            self.assertTrue(kwargs["restore"])
            # Only the installation seam is read-only, not the resumed director.
            with (
                patch.object(store, "_publish", side_effect=AssertionError("write")),
                patch.object(store.os, "fsync", side_effect=AssertionError("sync")),
            ):
                return original(*args, **kwargs)

        for used in (False, True):
            with self.subTest(used=used):
                self.marker.unlink(missing_ok=True)
                run = self.preinstall("preinstalled-" + str(used))
                if used:
                    put(run / "curio-used.lua", SOURCE)
                before, bundle_before = snapshot(run), snapshot(self.bundles)
                with patch.object(
                    launcher, "_curio_install", side_effect=readonly_install
                ) as install:
                    status, err = self.invoke(
                        "--reuse-run-dir", str(run), *self.selection
                    )
                self.assertEqual(status, 0, err)
                install.assert_called_once()
                now = snapshot(run)
                self.assertEqual({name: now[name] for name in before}, before)
                self.assertEqual((run / "curio-used.lua").exists(), used)
                self.assertEqual(snapshot(self.bundles), bundle_before)
                self.assert_game_evidence()

    def test_incomplete_or_mixed_selectors_reject_before_run_creation(self):
        cases = (
            ["--curio-bundle-root", str(self.bundles)],
            ["--curio-candidate-id", self.candidate.candidate_id],
            [
                "--curio-source",
                str(self.source),
                "--curio-candidate-id",
                self.candidate.candidate_id,
            ],
            [
                "--curio-source",
                str(self.source),
                "--curio-bundle-root",
                str(self.bundles),
            ],
            ["--curio-source", str(self.source), *self.selection],
        )
        before = snapshot(self.bundles)
        for index, options in enumerate(cases):
            with self.subTest(index=index):
                run = self.path / f"bad-selectors-{index}"
                self.assert_rejected_without_children("--run-dir", str(run), *options)
                self.assertFalse(run.exists())
                self.assertEqual(snapshot(self.bundles), before)

    def test_malformed_candidate_id_rejects_literal_before_bundle_lookup(self):
        ident = self.candidate.candidate_id
        cases = (
            ident.upper(),
            " " + ident,
            ident + "\n",
            ident[:-1],
            ident + "0",
            "g" * 64,
            "../" + ident,
            "\x1bSECRET",
        )
        before = snapshot(self.bundles)
        for index, token in enumerate(cases):
            with self.subTest(index=index):
                run = self.path / f"bad-id-{index}"
                # Real read_candidate validates identity BEFORE this filesystem seam.
                with patch.object(
                    store, "_directory", side_effect=AssertionError("lookup")
                ) as lookup:
                    self.assert_rejected_without_children(
                        "--run-dir",
                        str(run),
                        "--curio-bundle-root",
                        str(self.bundles),
                        "--curio-candidate-id",
                        token,
                    )
                lookup.assert_not_called()
                self.assertFalse(run.exists())
                self.assertEqual(snapshot(self.bundles), before)

    def test_tampered_bundle_rejects_before_run_creation_without_repair(self):
        put(self.source, SOURCE + b"-- SECRET\n")
        before = snapshot(self.bundles)
        run = self.path / "tampered"
        self.assert_rejected_without_children("--run-dir", str(run), *self.selection)
        self.assertFalse(run.exists())
        self.assertEqual(snapshot(self.bundles), before)

    def test_same_lua_opposite_receipt_provenance_rejects_both_directions(self):
        for plain in (False, True):
            with self.subTest(installed_plain=plain):
                run = self.preinstall("provenance-" + str(plain), plain=plain)
                selection = (
                    self.selection if plain else ["--curio-source", str(self.source)]
                )
                before, bundle_before = snapshot(run), snapshot(self.bundles)
                self.assert_rejected_without_children(
                    "--reuse-run-dir", str(run), *selection
                )
                self.assertEqual(snapshot(run), before)
                self.assertEqual(snapshot(self.bundles), bundle_before)
                self.assertFalse((run / "director.log").exists())

    def test_restore_missing_or_conflicting_evidence_never_repairs_or_starts(self):
        for kind in (
            "missing-lock",
            "missing-source",
            "missing-receipt",
            "source",
            "used",
            "receipt",
            "temporary",
        ):
            with self.subTest(kind=kind):
                run = self.preinstall(kind)
                missing = {
                    "missing-lock": ".director.lock",
                    "missing-source": "curio.lua",
                    "missing-receipt": "curio-install.json",
                }
                if kind in missing:
                    (run / missing[kind]).unlink()
                elif kind == "source":
                    put(run / "curio.lua", b"conflict SECRET")
                elif kind == "used":
                    put(run / "curio-used.lua", b"conflict SECRET")
                elif kind == "receipt":
                    put(run / "curio-install.json", b"{partial SECRET")
                else:
                    put(run / ".curio-interrupted", b"partial")
                before, bundle_before = snapshot(run), snapshot(self.bundles)
                self.assert_rejected_without_children(
                    "--reuse-run-dir", str(run), *self.selection
                )
                self.assertEqual(snapshot(run), before)
                self.assertEqual(snapshot(self.bundles), bundle_before)
                self.assertFalse((run / "director.log").exists())

    def test_fresh_existing_run_is_not_adopted(self):
        run = self.preinstall("already-installed")
        before = snapshot(run)
        self.assert_rejected_without_children("--run-dir", str(run), *self.selection)
        self.assertEqual(snapshot(run), before)

    def test_receipt_publication_failure_starts_neither_child_keeps_source(self):
        run = self.path / "publication-failure"
        original = store._publish
        bundle_before = snapshot(self.bundles)

        def fail_receipt(directory, name, raw):
            with self.assertRaises(ValueError):
                Mailbox(run)
            if name == "curio-install.json":
                raise OSError("SECRET injected receipt publication failure")
            return original(directory, name, raw)

        with patch.object(store, "_publish", side_effect=fail_receipt) as publish:
            self.assert_rejected_without_children(
                "--run-dir", str(run), *self.selection
            )
        self.assertEqual(
            [call.args[1] for call in publish.call_args_list],
            ["curio.lua", "curio-install.json"],
        )
        self.assertEqual((run / "curio.lua").read_bytes(), SOURCE)
        self.assertEqual((run / "curio.lua").stat().st_nlink, 1)
        self.assertFalse((run / "curio-install.json").exists())
        self.assertFalse((run / "director.log").exists())
        self.assertEqual(snapshot(self.bundles), bundle_before)
        before = snapshot(run)
        self.assert_rejected_without_children(
            "--reuse-run-dir", str(run), *self.selection
        )
        self.assertEqual(snapshot(run), before)


if __name__ == "__main__":
    unittest.main()
