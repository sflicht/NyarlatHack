"""Real offline entrypoints; synthetic bundles/events, never live authorship."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from chaos import curio_store as store


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/generate_curio.py"
SOURCE = "-- exact café\f\r\nreturn {}\r\n".encode()


def put(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)


def snapshot(root):
    return {
        str(p.relative_to(root)): (
            p.lstat().st_ino,
            p.lstat().st_mode,
            p.lstat().st_mtime_ns,
            p.lstat().st_ctime_ns,
            p.read_bytes() if p.is_file() and not p.is_symlink() else None,
        )
        for p in root.rglob("*")
    }


class CurioCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.lua"
        put(self.source, SOURCE)
        self.run_dir = self.root / "run"
        self.run_dir.mkdir(mode=0o700)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "chaos", *map(str, args)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_real_help_install_verify_exact_bytes_and_no_status_upgrade(self):
        for args in [
            ("curio", "--help"),
            ("curio", "install", "--help"),
            ("curio", "continuity", "--help"),
        ]:
            p = self.cli(*args)
            self.assertEqual(p.returncode, 0, p.stderr)
        args = ("--run-dir", self.run_dir, "--source", self.source)
        p = self.cli("curio", "install", *args)
        self.assertEqual(p.returncode, 0, p.stderr)
        receipt = json.loads(p.stdout)
        self.assertEqual(receipt["status"], "candidate_installed_not_admitted")
        self.assertEqual((self.run_dir / "curio.lua").read_bytes(), SOURCE)
        self.assertEqual((self.run_dir / "curio.lua").stat().st_nlink, 1)
        self.assertEqual((self.run_dir / "curio.lua").stat().st_mode & 0o777, 0o600)
        put(self.run_dir / "curio-used.lua", SOURCE)
        before = snapshot(self.root)
        p = self.cli("curio", "verify", *args)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), receipt)
        self.assertEqual(snapshot(self.root), before)
        p = self.cli("curio", "install", *args)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(snapshot(self.root), before)

    def test_exclusive_source_forms_and_sanitized_errors(self):
        for args in [
            [],
            ["--bundle-root", self.root],
            ["--candidate-id", "a" * 64],
            [
                "--source",
                self.source,
                "--bundle-root",
                self.root,
                "--candidate-id",
                "a" * 64,
            ],
            ["--source", "\x1bSECRET"],
            ["--unknown-SECRET"],
        ]:
            before = snapshot(self.root)
            p = self.cli("curio", "install", "--run-dir", self.run_dir, *args)
            self.assertEqual(p.returncode, 2)
            self.assertNotIn("SECRET", p.stderr)
            self.assertNotIn("\x1b", p.stderr)
            self.assertEqual(snapshot(self.root), before)

    def test_verify_conflicts_are_read_only(self):
        for kind in ("missing", "receipt", "used", "symlink", "unsafe"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                run = Path(tmp)
                store.install_saved_source(run, source_file=self.source)
                if kind == "missing":
                    (run / "curio-install.json").unlink()
                elif kind == "receipt":
                    put(run / "curio-install.json", b"{partial SECRET")
                elif kind == "used":
                    put(run / "curio-used.lua", b"different SECRET")
                elif kind == "symlink":
                    (run / "curio.lua").unlink()
                    (run / "curio.lua").symlink_to(self.source)
                else:
                    (run / "curio.lua").chmod(0o644)
                before = snapshot(run)
                p = self.cli(
                    "curio", "verify", "--run-dir", run, "--source", self.source
                )
                self.assertEqual(p.returncode, 2)
                self.assertNotIn("SECRET", p.stderr)
                self.assertEqual(snapshot(run), before)

    def test_continuity_real_commands_and_readonly_notes(self):
        from test_curio_generation import event

        bundles, journal = self.root / "bundles", self.root / "journal"
        bundles.mkdir(mode=0o700)
        journal.mkdir(mode=0o700)
        candidate = store.store_candidate(
            bundles,
            json.dumps(
                dict(
                    lua_source=SOURCE.decode(),
                    continuity_note="Synthetic editorial note é",
                )
            ),
        )
        ident = candidate.candidate_id
        base = ("curio", "continuity")

        def command(op, *args):
            p = self.cli(*base, op, "--journal-root", journal, *args)
            self.assertEqual(p.returncode, 0, p.stderr)
            return json.loads(p.stdout)

        command("init")
        command("register", "--bundle-root", bundles, "--candidate-id", ident)
        p = self.cli(
            "curio",
            "install",
            "--run-dir",
            self.run_dir,
            "--bundle-root",
            bundles,
            "--candidate-id",
            ident,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        command("bind", "--candidate-id", ident, "--run-dir", self.run_dir)
        put(self.run_dir / "events.jsonl", event())  # Synthetic, not native proof.
        command("observe", "--candidate-id", ident)
        before = snapshot(self.root)
        notes = command("notes")
        self.assertEqual(notes[0]["candidate_id"], ident)
        self.assertEqual(notes[0]["status"], "installed")
        self.assertEqual(snapshot(self.root), before)
        p = self.cli(*base, "init", "--journal-root", journal)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(snapshot(self.root), before)


class GenerationScriptTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "opt-in generation entrypoint missing")
        spec = importlib.util.spec_from_file_location("generate_curio_cli", SCRIPT)
        self.script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.script)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.args = []
        for name in (
            "event-file",
            "output-directory",
            "bundle-root",
            "journal-root",
            "ledger",
        ):
            self.args += ["--" + name, str(self.root / name)]

    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                status = self.script.main(args)
            except SystemExit as exc:
                status = exc.code
        return status, out.getvalue(), err.getvalue()

    def test_help_real_subprocess_and_no_optin_no_service_or_writes(self):
        p = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        from chaos import curio_generation

        with (
            patch.object(curio_generation, "generate_curio") as service,
            patch.object(curio_generation, "native_client") as factory,
        ):
            for args in (
                self.args,
                [],
                self.args + ["--execute-live", "--fresh-ledger"],
                self.args + ["--execute-live", "--unknown-SECRET"],
                self.args + ["--execute-live", "--literary-layer", "SECRET"],
            ):
                status, _, err = self.invoke(args)
                self.assertEqual(status, 2)
                self.assertNotIn("SECRET", err)
            service.assert_not_called()
            factory.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_explicit_optin_forwards_only_reviewed_service_parameters_fake_positive(
        self,
    ):
        from chaos import curio_generation

        receipt = {"status": "authored_not_installed", "source_sha256": "a" * 64}
        with patch.object(
            curio_generation, "generate_curio", return_value=receipt
        ) as service:
            status, out, _ = self.invoke(
                self.args
                + [
                    "--execute-live",
                    "--literary-layer",
                    "poe",
                    "--role",
                    "Wizard",
                    "--race",
                    "human",
                ]
            )
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out), receipt)
        expected = {
            k.replace("-", "_"): self.root / k
            for k in (
                "event-file",
                "output-directory",
                "bundle-root",
                "journal-root",
                "ledger",
            )
        }
        expected.update(literary_layer="poe", role="Wizard", race="human")
        self.assertEqual(service.call_args.kwargs, expected)
        service.assert_called_once()

    def test_inspect_only_uses_reader_and_sanitizes_validation_failure(self):
        from chaos import curio_generation

        with (
            patch.object(curio_generation, "generate_curio") as service,
            patch.object(curio_generation, "native_client") as factory,
            patch.object(
                curio_generation,
                "read_generation",
                side_effect=ValueError("\x1bSECRET"),
            ) as read,
        ):
            status, out, err = self.invoke(
                ["--inspect", "--output-directory", str(self.root)]
            )
        self.assertEqual(status, 2)
        self.assertEqual(out, "")
        self.assertIn("ValueError", err)
        self.assertNotIn("SECRET", err)
        read.assert_called_once_with(self.root)
        service.assert_not_called()
        factory.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_real_service_fake_client_retained_ledger_and_real_readonly_inspect(self):
        from chaos import curio_continuity, curio_generation
        from test_curio_generation import RAW, event
        from test_oauth import OAuthTests
        from types import SimpleNamespace as NS

        fake = OAuthTests()
        fake.setUp()
        self.addCleanup(fake.doCleanups)
        fake.Backend(fake.ledger, client_factory=fake.factory).generate(
            "fixture", "fixture"
        )
        retained = json.loads(fake.ledger.read_bytes())["records"][0]
        bundles, journal, run = (self.root / p for p in ("bundles", "journal", "run"))
        for p in (bundles, journal, run):
            p.mkdir(mode=0o700)
        curio_continuity.create_journal(journal)
        events = run / "events.jsonl"
        put(events, event())
        output = self.root / "output"
        calls = []

        def create(**kw):
            calls.append(kw)
            self.assertTrue((output / "prepared.json").exists())
            self.assertEqual(
                json.loads(fake.ledger.read_bytes())["records"][-1]["status"],
                "reserved",
            )
            return NS(
                model="gpt-5.6-luna",
                choices=[NS(message=NS(content=RAW, tool_calls=None))],
                usage=NS(input_tokens=1, output_tokens=1, total_tokens=2),
            )

        fake.client.chat.completions.create = create
        args = [
            "--execute-live",
            "--event-file",
            str(events),
            "--output-directory",
            str(output),
            "--bundle-root",
            str(bundles),
            "--journal-root",
            str(journal),
            "--ledger",
            str(fake.ledger),
        ]
        generate = curio_generation.generate_curio
        with patch.object(
            curio_generation,
            "generate_curio",
            side_effect=lambda **kw: generate(**kw, client_factory=fake.factory),
        ):
            status, _, _ = self.invoke(args[:-1] + [str(self.root / "absent-ledger")])
            self.assertEqual(status, 2)
            self.assertFalse(output.exists())
            self.assertEqual(calls, [])
            status, out, err = self.invoke(args)
        self.assertEqual(status, 0, err)
        receipt = json.loads(out)
        self.assertEqual(receipt["status"], "candidate_stored_registered_not_installed")
        self.assertNotIn("lua_source", out)
        self.assertNotIn("Synthetic note", out)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["model"], "gpt-5.6-luna")
        self.assertEqual(json.loads(fake.ledger.read_bytes())["records"][0], retained)
        self.assertEqual(json.loads(fake.ledger.read_bytes())["attempts"], 2)
        self.assertFalse((run / "curio.lua").exists())
        before, ledger_before = snapshot(self.root), snapshot(fake.ledger.parent)
        p = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--inspect",
                "--output-directory",
                str(output),
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), receipt)
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(snapshot(fake.ledger.parent), ledger_before)

    def test_no_optin_help_and_malformed_never_import_service_in_real_process(self):
        guard = """
import importlib.abc, runpy, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('chaos.curio_generation', 'chaos.oauth', 'agent') or fullname.startswith('agent.'):
            raise AssertionError('FORBIDDEN_IMPORT')
sys.meta_path.insert(0, Guard())
script = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(script, run_name='__main__')
"""
        for args, expected in (
            (["--help"], 0),
            (self.args, 2),
            (self.args + ["--execute-live", "--unknown-SECRET"], 2),
        ):
            p = subprocess.run(
                [sys.executable, "-c", guard, str(SCRIPT), *args],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(p.returncode, expected, p.stderr)
            self.assertNotIn("FORBIDDEN_IMPORT", p.stderr)
            self.assertNotIn("SECRET", p.stderr)
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
