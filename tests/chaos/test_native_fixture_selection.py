"""Selection units and read-only fixture AST checks, NOT native evidence.

Identity/calibration backends use synthetic typed results. Only the launcher's
trusted AST prelaunch prefix executes, with mocked preparation and a stop before
temporary-directory creation. No fixture import, compiler, native helper, game,
or held gameplay module runs.
"""

import ast
from collections import Counter
from dataclasses import replace
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from native_build_calibration import CalibrationError, NativeProfile
from native_build_identity import IdentityError, SourceBuildInputs

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "fd7a91deb1dc33244e0f72a47d3a4ec584255852"
FIXTURE = "tests/chaos/test_curio_launcher_gameplay.py"
MODE = "NYARLATHACK_NATIVE_FIXTURE_MODE"
RECEIPT = "NYARLATHACK_NATIVE_BUILD_RECEIPT"
REVISION = "NYARLATHACK_NATIVE_EXPECTED_REVISION"
SOURCES = ("gameplay_support.py", "replay_clock.c", "curio_save_layout.c")
ENV = {
    "PATH": "/usr/bin:/bin",
    "HOME": "/home/hermes",
    "LANG": "C.UTF-8",
    "TZ": "America/New_York",
    "PKG_CONFIG_LIBDIR": "/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def baseline():
    return subprocess.check_output(
        ["/usr/bin/git", "-C", str(ROOT), "show", BASELINE + ":" + FIXTURE],
        env={"PATH": "/usr/bin:/bin", "GIT_NO_REPLACE_OBJECTS": "1"},
        timeout=30,
    )


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("native_fixture_selection"),
            "explicit native fixture selection is not implemented",
        )
        import native_fixture_selection as selection

        self.s = selection
        self.tmp = tempfile.TemporaryDirectory(prefix="selection-unit-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipts = self.root / "trusted-receipts"
        self.env = {
            MODE: "source-build",
            RECEIPT: str(self.receipts),
            REVISION: BASELINE,
        }
        self.blobs = {}
        for name in SOURCES:
            data = (ROOT / "tests/chaos" / name).read_bytes()
            path = self.root / "tests/chaos" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.blobs["tests/chaos/" + name] = data
        self.hashes = {}
        for name in ("dnethack", "nhdat", "license"):
            data = ("synthetic unit bytes, not executable: " + name).encode()
            path = self.root / "dnethackdir" / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(data)
            self.hashes[name] = digest(data)
        self.inputs = SourceBuildInputs(
            self.root,
            self.root / "dnethackdir",
            1,
            BASELINE,
            self.hashes,
            {
                "receipt_dir": str(self.receipts),
                "profile": "system-gcc13-local",
                "environment": ENV.copy(),
                "compiler_receipt": "unit compiler metadata",
                "tree": "b" * 40,
                "header_count": 1,
                "object_count": 1,
            },
        )
        self.identity = self.enterContext(
            patch.object(self.s, "verify_source_build", return_value=self.inputs)
        )
        self.calibrate = self.enterContext(
            patch.object(self.s, "validate_native_profile")
        )
        self.real_git_run = subprocess.run
        self.git = self.enterContext(
            patch.object(self.s.subprocess, "run", side_effect=self.git_blob)
        )

    def git_blob(self, argv, **kwargs):
        self.assertEqual(argv[:4], ["/usr/bin/git", "-C", str(self.root), "show"])
        self.assertTrue(argv[4].startswith(BASELINE + ":tests/chaos/"))
        self.assertEqual(kwargs["env"]["GIT_NO_REPLACE_OBJECTS"], "1")
        self.assertEqual(kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")
        self.assertNotIn("GIT_DIR", kwargs["env"])
        self.assertTrue(kwargs["check"])
        return subprocess.CompletedProcess(
            argv, 0, self.blobs[argv[4].split(":", 1)[1]], b""
        )

    def prepare(self):
        return self.s.prepare(self.root, self.env)

    def archived(self, env=None):
        # Only synthetic fixture pins are substituted here; baseline pin equality
        # is independently tested below against the committed launcher AST.
        with patch.object(self.s, "ARCHIVED_HASHES", self.hashes.copy()):
            return self.s.prepare(self.root, {} if env is None else env)

    def test_default_archived_keeps_ambient_compiler_without_source_backend(self):
        selected = self.archived()
        self.assertEqual(selected.mode, "archived")
        self.assertEqual(selected.tuple_dir, self.root / "dnethackdir")
        self.assertEqual(selected.artifact_hashes, self.hashes)
        self.assertEqual(selected.compiler, "cc")
        self.assertIsNone(selected.environment)
        self.assertIsNone(selected.source_inputs)
        self.assertIsNone(selected.validate_schema({"archive": "not calibrated"}))
        self.identity.assert_not_called()
        self.calibrate.assert_not_called()
        self.git.assert_not_called()

    def test_explicit_archived_matches_default(self):
        self.assertEqual(
            self.archived().record(), self.archived({MODE: "archived"}).record()
        )

    def test_archived_replacement_has_no_source_fallback(self):
        with self.assertRaisesRegex(self.s.SelectionError, "archived.*dnethack"):
            self.s.prepare(self.root, {})
        self.identity.assert_not_called()
        self.git.assert_not_called()

    def test_invalid_context_fails_before_io_or_backend(self):
        contexts = [{MODE: x} for x in ("", "auto", "SOURCE-BUILD", " archived")]
        contexts += [{RECEIPT: x} for x in ("", "/receipt")]
        contexts += [{REVISION: x} for x in ("", BASELINE)]
        contexts += [{MODE: "source-build"}, {MODE: "source-build", RECEIPT: "/r"}]
        contexts += [
            dict(self.env, **{REVISION: x})
            for x in ("", " ", "a" * 39, "a" * 41, "g" * 40, "A" * 40, BASELINE + "\n")
        ]
        contexts += [
            dict(self.env, **{RECEIPT: x})
            for x in ("", " ", "relative", "/a/../b", "/a\x00b")
        ]
        with patch.object(
            Path, "read_bytes", side_effect=AssertionError("premature file read")
        ):
            for env in contexts:
                with self.subTest(env=env), self.assertRaises(self.s.SelectionError):
                    self.s.prepare(self.root, env)
        self.identity.assert_not_called()
        self.git.assert_not_called()
        self.calibrate.assert_not_called()

    def test_source_selection_uses_independent_root_revision_and_exact_environment(
        self,
    ):
        selected = self.prepare()
        self.identity.assert_called_once_with(
            self.receipts, self.root, BASELINE, mode=1
        )
        self.assertIs(selected.source_inputs, self.inputs)
        self.assertEqual(selected.compiler, "/usr/bin/cc")
        self.assertEqual(selected.environment, ENV)
        self.assertEqual(selected.artifact_hashes, self.hashes)
        self.assertEqual(self.git.call_count, len(SOURCES))
        self.calibrate.assert_not_called()
        record = json.loads(json.dumps(selected.record()))
        self.assertEqual(record["source_build"]["build_root"], str(self.root))
        self.assertEqual(record["source_build"]["revision"], BASELINE)
        self.assertEqual(
            record["source_hashes"], {k: digest(v) for k, v in self.blobs.items()}
        )
        self.assertIsNone(record["native_profile"])

    def test_reviewed_source_helper_is_accepted_and_recorded_unit_only(self):
        name = "tests/chaos/gameplay_support.py"
        reviewed = "f426720738d8946b7bf26d41fc341aae4064578f93168c4b87e588efb6588949"
        self.assertEqual(digest(self.blobs[name]), reviewed)
        try:
            selected = self.prepare()
        except self.s.SelectionError as exc:
            self.fail(f"reviewed source helper must pass unit preflight: {exc}")
        self.assertEqual(selected.record()["source_hashes"][name], reviewed)
        self.assertIsNone(selected.native_profile)
        self.calibrate.assert_not_called()
        with self.assertRaisesRegex(self.s.SelectionError, "calibration required"):
            selected.verify_copy(self.root / "dnethackdir")

    def test_source_helper_pin_is_fixed_separate_literal_unit_only(self):
        tree = ast.parse((ROOT / "tests/chaos/native_fixture_selection.py").read_text())
        pins = [
            n.value
            for n in tree.body
            if isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "SOURCE_DRIVER_HASH"
                for t in n.targets
            )
        ]
        self.assertEqual(len(pins), 1)
        self.assertIsInstance(pins[0], ast.Constant)
        assert isinstance(pins[0], ast.Constant)
        self.assertEqual(
            pins[0].value,
            "f426720738d8946b7bf26d41fc341aae4064578f93168c4b87e588efb6588949",
        )
        self.assertNotEqual(pins[0].value, self.s.DRIVER_HASH)

    def test_historical_helper_matching_commit_is_rejected_unit_only(self):
        name = "tests/chaos/gameplay_support.py"
        result = self.real_git_run(
            ["/usr/bin/git", "-C", str(ROOT), "show", BASELINE + ":" + name],
            env={"PATH": "/usr/bin:/bin", "GIT_NO_REPLACE_OBJECTS": "1"},
            capture_output=True,
            check=True,
            timeout=30,
        )
        self.assertEqual(digest(result.stdout), self.s.DRIVER_HASH)
        self.blobs[name] = result.stdout
        (self.root / name).write_bytes(result.stdout)
        with self.assertRaisesRegex(
            self.s.SelectionError, "reviewed driver pin mismatch"
        ):
            self.prepare()
        self.calibrate.assert_not_called()

    def test_reviewed_worktree_with_different_commit_blob_rejected_unit_only(self):
        name = "tests/chaos/gameplay_support.py"
        self.blobs[name] = b"unreviewed committed helper"
        with self.assertRaisesRegex(self.s.SelectionError, "oracle source mismatch"):
            self.prepare()
        self.calibrate.assert_not_called()

    def test_identity_failure_stops_before_oracle_lookup(self):
        for message in (
            "revision mismatch",
            "dirty tracked tree",
            "headers hash mismatch",
            "artifact identity mismatch",
        ):
            self.identity.side_effect = IdentityError(message)
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(IdentityError, message),
            ):
                self.prepare()
        self.git.assert_not_called()
        self.calibrate.assert_not_called()

    def test_mixed_backend_context_rejected(self):
        changes = [
            dict(build_root=self.root / "foreign"),
            dict(tuple_dir=self.root / "off"),
            dict(revision="a" * 40),
            dict(mode=0),
            dict(metadata=dict(self.inputs.metadata, receipt_dir="/foreign")),
        ]
        for change in changes:
            self.identity.return_value = replace(self.inputs, **change)
            with (
                self.subTest(change=change),
                self.assertRaisesRegex(self.s.SelectionError, "context"),
            ):
                self.prepare()
        self.git.assert_not_called()

    def test_changed_oracle_sources_rejected_before_calibration(self):
        for name in SOURCES:
            path = self.root / "tests/chaos" / name
            original = path.read_bytes()
            path.write_bytes(original + b"/* changed */\n")
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(self.s.SelectionError, "source|driver"),
            ):
                self.prepare()
            path.write_bytes(original)
        self.calibrate.assert_not_called()

    def test_reviewed_driver_pin_cannot_be_replaced_by_matching_commit_blob(self):
        name = "tests/chaos/gameplay_support.py"
        self.blobs[name] = b"changed driver"
        (self.root / name).write_bytes(self.blobs[name])
        with self.assertRaisesRegex(self.s.SelectionError, "driver"):
            self.prepare()
        self.calibrate.assert_not_called()

    def test_missing_committed_oracle_fails_closed(self):
        self.git.side_effect = subprocess.CalledProcessError(128, ["/usr/bin/git"])
        with self.assertRaises(self.s.SelectionError):
            self.prepare()
        self.calibrate.assert_not_called()

    def test_schema_validation_passes_reporter_not_save_to_calibrator(self):
        selected = self.prepare()
        schema = {"synthetic": "reporter, not save"}
        profile = NativeProfile(schema, self.hashes["dnethack"], {"synthetic": True})
        self.calibrate.return_value = profile
        self.assertIs(selected.validate_schema(schema), profile)
        self.calibrate.assert_called_once_with(self.inputs, schema)
        self.assertEqual(
            json.loads(json.dumps(selected.record()))["native_profile"]["layout"],
            schema,
        )

    def test_schema_mismatch_blocks_copy_launch_guard(self):
        selected = self.prepare()
        self.calibrate.side_effect = CalibrationError("schema differs")
        with self.assertRaisesRegex(CalibrationError, "schema differs"):
            selected.validate_schema({"internal_compression": True})
        start = Mock()
        with self.assertRaisesRegex(self.s.SelectionError, "calibration"):
            selected.verify_copy(self.root / "dnethackdir")
            start()
        start.assert_not_called()

    def test_changed_helper_copy_fails_before_compiler(self):
        selected = self.prepare()
        helpers = self.root / "helpers"
        helpers.mkdir()
        for name in SOURCES:
            shutil.copy2(self.root / "tests/chaos" / name, helpers / name)
        compiler = Mock()
        self.assertTrue(
            callable(getattr(selected, "verify_helper_copy", None)),
            "helper copy binding is not implemented",
        )
        self.assertEqual(
            selected.verify_helper_copy(helpers),
            {name: digest(self.blobs["tests/chaos/" + name]) for name in SOURCES},
        )
        for name in SOURCES:
            path = helpers / name
            original = path.read_bytes()
            path.write_bytes(b"changed copied helper")
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(self.s.SelectionError, "helper copy"),
            ):
                selected.verify_helper_copy(helpers)
                compiler()
            path.write_bytes(original)
        compiler.assert_not_called()
        self.calibrate.assert_not_called()

    def test_archived_helper_copy_only_records_hashes_without_source_calibration(self):
        selected = self.archived()
        helpers = self.root / "tests/chaos"
        self.assertTrue(
            callable(getattr(selected, "verify_helper_copy", None)),
            "helper copy binding is not implemented",
        )
        self.assertEqual(
            selected.verify_helper_copy(helpers),
            {name: digest(self.blobs["tests/chaos/" + name]) for name in SOURCES},
        )
        self.identity.assert_not_called()
        self.calibrate.assert_not_called()

    def test_failed_recalibration_revokes_previous_copy_guard(self):
        selected = self.prepare()
        self.calibrate.return_value = NativeProfile({}, self.hashes["dnethack"], {})
        selected.validate_schema({})
        self.assertEqual(selected.verify_copy(self.root / "dnethackdir"), self.hashes)
        self.calibrate.side_effect = CalibrationError("changed inputs")
        with self.assertRaisesRegex(CalibrationError, "changed inputs"):
            selected.validate_schema({})
        with self.assertRaisesRegex(self.s.SelectionError, "calibration"):
            selected.verify_copy(self.root / "dnethackdir")

    def test_source_copy_guard_requires_calibration_first(self):
        selected = self.prepare()
        with self.assertRaisesRegex(self.s.SelectionError, "calibration"):
            selected.verify_copy(self.root / "dnethackdir")

    def test_changed_source_after_preflight_rejected_at_schema_gate(self):
        selected = self.prepare()
        (self.root / "tests/chaos/replay_clock.c").write_bytes(
            b"changed after selection"
        )
        with self.assertRaisesRegex(self.s.SelectionError, "source"):
            selected.validate_schema({})
        self.calibrate.assert_not_called()

    def test_copy_guard_checks_all_three_files_before_each_start(self):
        selected = self.archived()
        copy = self.root / "game-copy"
        shutil.copytree(self.root / "dnethackdir", copy)
        start = Mock()
        self.assertEqual(selected.verify_copy(copy), self.hashes)
        start()
        for name in self.hashes:
            original = (copy / name).read_bytes()
            (copy / name).write_bytes(b"replacement")
            with (
                self.subTest(name=name),
                self.assertRaisesRegex(self.s.SelectionError, "copy.*" + name),
            ):
                selected.verify_copy(copy)
                start()
            (copy / name).write_bytes(original)
        self.assertEqual(start.call_count, 1)
        (copy / "license").unlink()
        with self.assertRaises(self.s.SelectionError):
            selected.verify_copy(copy)

    def test_successful_source_order_is_identity_sources_calibration_copy_start(self):
        events = []
        self.identity.side_effect = lambda *a, **kw: (
            events.append("identity") or self.inputs
        )
        old_git = self.git.side_effect
        self.git.side_effect = lambda *a, **kw: (
            events.append("source") or old_git(*a, **kw)
        )
        self.calibrate.side_effect = lambda inputs, schema: (
            events.append("calibration")
            or NativeProfile(schema, self.hashes["dnethack"], {})
        )
        selected = self.prepare()
        events.append("mock compiler; no native execution")
        selected.validate_schema({})
        self.assertEqual(selected.verify_copy(self.root / "dnethackdir"), self.hashes)
        events += ["copy", "mock start"]
        self.assertEqual(
            events,
            [
                "identity",
                "source",
                "source",
                "source",
                "mock compiler; no native execution",
                "calibration",
                "copy",
                "mock start",
            ],
        )


class FixturePrelaunchTests(unittest.TestCase):
    """Execute only the actual fixture prefix with mocks; never native evidence."""

    def run_prelaunch(self, mode, helper, accepted):
        import native_fixture_selection as selection

        tree = ast.parse((ROOT / FIXTURE).read_text())
        fixture = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "CurioLauncherGameplayTests"
        )
        method = next(n for n in fixture.body if isinstance(n, ast.FunctionDef))
        boundary = next(
            i
            for i, n in enumerate(method.body)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "root" for t in n.targets)
        )
        # Include the real mkdtemp statement, but stop there via a sentinel.
        prefix = ast.Module(
            body=[
                n
                for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "expected_driver_hash"
            ]
            + method.body[: boundary + 1],
            type_ignores=[],
        )

        class PrelaunchComplete(Exception):
            pass

        prepare = Mock(return_value=Mock(mode=mode))
        compiler = Mock()
        with (
            patch.object(Path, "read_text", return_value="1\n"),
            patch.object(Path, "read_bytes", return_value=helper),
            patch.object(tempfile, "mkdtemp", side_effect=PrelaunchComplete) as mkdir,
            patch.object(subprocess, "run", compiler),
        ):
            namespace = dict(
                ROOT=ROOT,
                self=self,
                prepare=prepare,
                sha=digest,
                Path=Path,
                tempfile=tempfile,
                SOURCE_DRIVER_HASH=selection.SOURCE_DRIVER_HASH,
            )
            error = PrelaunchComplete if accepted else (AssertionError, KeyError)
            try:
                with self.assertRaises(error):
                    exec(compile(prefix, FIXTURE, "exec"), namespace)
            except PrelaunchComplete:
                self.fail("invalid helper/mode reached temporary-directory creation")
            prepare.assert_called_once_with(ROOT)
            if accepted:
                mkdir.assert_called_once_with(prefix="curio8e2-native-")
            else:
                mkdir.assert_not_called()
            compiler.assert_not_called()

    @staticmethod
    def archived_helper():
        return subprocess.check_output(
            [
                "/usr/bin/git",
                "-C",
                str(ROOT),
                "show",
                BASELINE + ":tests/chaos/gameplay_support.py",
            ],
            env={"PATH": "/usr/bin:/bin", "GIT_NO_REPLACE_OBJECTS": "1"},
            timeout=30,
        )

    def test_reviewed_source_helper_reaches_prelaunch_boundary_unit_only(self):
        self.run_prelaunch(
            "source-build",
            (ROOT / "tests/chaos/gameplay_support.py").read_bytes(),
            True,
        )

    def test_archived_helper_reaches_prelaunch_boundary_unit_only(self):
        helper = self.archived_helper()
        self.assertEqual(
            digest(helper),
            "9d341b28a4ab3f4453b09e4f49a2e8701a7c78345184f487e2f0b32d70db7270",
        )
        self.run_prelaunch("archived", helper, True)

    def test_historical_helper_rejected_in_source_mode_unit_only(self):
        self.run_prelaunch("source-build", self.archived_helper(), False)

    def test_reviewed_helper_rejected_in_archived_mode_unit_only(self):
        self.run_prelaunch(
            "archived", (ROOT / "tests/chaos/gameplay_support.py").read_bytes(), False
        )

    def test_wrong_helper_rejected_in_each_mode_unit_only(self):
        for mode in ("archived", "source-build"):
            with self.subTest(mode=mode):
                self.run_prelaunch(mode, b"wrong helper; unit data only", False)

    def test_unknown_mode_rejects_both_pinned_helpers_unit_only(self):
        for helper in (
            self.archived_helper(),
            (ROOT / "tests/chaos/gameplay_support.py").read_bytes(),
        ):
            with self.subTest(helper=digest(helper)):
                self.run_prelaunch("unknown", helper, False)


class FixtureASTTests(unittest.TestCase):
    def test_archived_pins_equal_committed_baseline_literals(self):
        self.assertIsNotNone(importlib.util.find_spec("native_fixture_selection"))
        import native_fixture_selection as selection

        tree = ast.parse(baseline())
        pins = [
            ast.literal_eval(n.value)
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "installed" for t in n.targets)
        ]
        self.assertEqual(pins, [selection.ARCHIVED_HASHES])
        self.assertIn(
            selection.DRIVER_HASH,
            [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)],
        )

    def test_all_native_assertions_preserved_without_importing_fixture(self):
        self.check_historical_assertions((ROOT / FIXTURE).read_text())

    def test_historical_guard_rejects_wrong_ambient_binding(self):
        source = (ROOT / FIXTURE).read_text()
        mutant = source.replace(
            '1 if policy == "historical" else 0', '99 if policy == "historical" else 0'
        )
        self.assertNotEqual(source, mutant)
        with self.assertRaises(AssertionError):
            self.check_historical_assertions(mutant)

    def test_historical_guard_rejects_wrong_policy_mapping(self):
        source = (ROOT / FIXTURE).read_text()
        mutant = source.replace('"archived": "historical"', '"archived": "current"')
        self.assertNotEqual(source, mutant)
        with self.assertRaises(AssertionError):
            self.check_historical_assertions(mutant)

    def test_historical_guard_rejects_wrong_branch_accounting(self):
        source = (ROOT / FIXTURE).read_text()
        mutant = source.replace(
            'test.assertEqual(fields["spent"], 2)',
            'test.assertEqual(fields["spent"], 99)',
        )
        self.assertNotEqual(source, mutant)
        with self.assertRaises(AssertionError):
            self.check_historical_assertions(mutant)

    def test_historical_guard_rejects_removed_historical_assertion(self):
        source = (ROOT / FIXTURE).read_text()
        mutant = source.replace('test.assertEqual(fields["spent"], 2)', "pass")
        self.assertNotEqual(source, mutant)
        with self.assertRaises(AssertionError):
            self.check_historical_assertions(mutant)

    def check_historical_assertions(self, source):
        def assertions(tree):
            return Counter(
                ast.dump(n)
                for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id in ("self", "test")
                and n.func.attr.startswith("assert")
            )

        old_tree = ast.parse(baseline())
        new_tree = ast.parse(source)
        old_pin = ast.parse(
            'self.assertEqual(sha((ROOT / "tests/chaos/gameplay_support.py").read_bytes()), '
            '"9d341b28a4ab3f4453b09e4f49a2e8701a7c78345184f487e2f0b32d70db7270")',
            mode="eval",
        ).body
        new_pin = ast.parse(
            'self.assertEqual(sha((ROOT / "tests/chaos/gameplay_support.py").read_bytes()), '
            "expected_driver_hash(selection.mode))",
            mode="eval",
        ).body
        # Pin both policy bindings BEFORE any projection can erase their use.
        for name, statement in (
            (
                "policy",
                'policy = {"archived": "historical", "source-build": "current"}[selection.mode]',
            ),
            ("ambient_spent", 'ambient_spent = 1 if policy == "historical" else 0'),
        ):
            bindings = [
                n
                for n in ast.walk(new_tree)
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
            ]
            self.assertEqual(
                [ast.dump(n) for n in bindings],
                [ast.dump(ast.parse(statement).body[0])],
            )
            stores = [
                n
                for n in ast.walk(new_tree)
                if isinstance(n, ast.Name)
                and n.id == name
                and isinstance(n.ctx, ast.Store)
            ]
            self.assertEqual(len(stores), 1)

        # Only these three complete assertion calls changed their expected
        # accounting expressions. No general name substitution/constant folding.
        rewrites = (
            (
                'self.assertEqual([e["spent"] for e in curio], [ambient_spent, ambient_spent + 1])',
                'self.assertEqual([e["spent"] for e in curio], [1, 2])',
            ),
            (
                'self.assertEqual(accepted[0]["spent"], ambient_spent)',
                'self.assertEqual(accepted[0]["spent"], 1)',
            ),
            (
                'self.assertEqual((e["status"], e["detail"], e["spent"]), ("rejected", "duplicate", ambient_spent + 1))',
                'self.assertEqual((e["status"], e["detail"], e["spent"]), ("rejected", "duplicate", 2))',
            ),
        )
        replacements = {
            ast.dump(ast.parse(before, mode="eval").body): after
            for before, after in rewrites
        }
        transformed = Counter()
        branches = Counter()

        class HistoricalPolicyView(ast.NodeTransformer):
            def visit_If(self, node):
                condition = ast.unparse(node.test)
                if condition == "policy == 'historical'":
                    branches["historical"] += 1
                    return [self.visit(n) for n in node.body]
                if condition == "policy == 'current'":
                    branches["current"] += 1
                    return [self.visit(n) for n in node.orelse]
                return self.generic_visit(node)

            def visit_Call(self, node):
                key = ast.dump(node)
                if key in replacements:
                    transformed[key] += 1
                    return ast.parse(replacements[key], mode="eval").body
                return self.generic_visit(node)

        historical_tree = HistoricalPolicyView().visit(ast.parse(source))
        self.assertEqual(branches, {"historical": 1, "current": 2})
        self.assertEqual(transformed, {key: 1 for key in replacements})
        old_assertions, new_assertions = (
            assertions(old_tree),
            assertions(historical_tree),
        )
        self.assertEqual(old_assertions[ast.dump(old_pin)], 1)
        self.assertEqual(new_assertions[ast.dump(new_pin)], 1)
        # Exactly one approved expected-value transformation, not a subset check
        # or blanket removal of identity assertions. Every other AST must match.
        old_assertions[ast.dump(old_pin)] -= 1
        old_assertions[ast.dump(new_pin)] += 1
        self.assertEqual(+old_assertions, new_assertions)
        expected_gate = ast.parse(
            "def expected_driver_hash(mode):\n"
            "    return {\n"
            '        "archived": "9d341b28a4ab3f4453b09e4f49a2e8701a7c78345184f487e2f0b32d70db7270",\n'
            '        "source-build": SOURCE_DRIVER_HASH,\n'
            "    }[mode]\n"
        ).body[0]
        gates = [
            n
            for n in new_tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "expected_driver_hash"
        ]
        self.assertEqual([ast.dump(n) for n in gates], [ast.dump(expected_gate)])
        imports = [
            ast.dump(n)
            for n in new_tree.body
            if isinstance(n, ast.ImportFrom) and n.module == "native_fixture_selection"
        ]
        self.assertEqual(
            imports,
            [
                ast.dump(
                    ast.parse(
                        "from native_fixture_selection import SOURCE_DRIVER_HASH, prepare"
                    ).body[0]
                )
            ],
        )

    def test_fixture_prelaunch_order_and_compiler_environment_are_explicit(self):
        tree = ast.parse((ROOT / FIXTURE).read_text())
        calls = sorted(
            (n for n in ast.walk(tree) if isinstance(n, ast.Call)),
            key=lambda n: n.lineno,
        )

        def named(name):
            return [n for n in calls if ast.unparse(n.func) == name]

        self.assertEqual(len(named("prepare")), 1, "selection preflight missing")
        prepare = named("prepare")[0]
        self.assertEqual(ast.unparse(prepare.args[0]), "ROOT")
        for name in ("tempfile.mkdtemp", "shutil.copy2", "subprocess.run"):
            self.assertLess(prepare.lineno, named(name)[0].lineno)
        helper_guards = named("selection.verify_helper_copy")
        self.assertEqual(
            len(helper_guards), 1, "pre-compiler helper copy guard missing"
        )
        self.assertLess(named("shutil.copy2")[1].lineno, helper_guards[0].lineno)
        self.assertLess(helper_guards[0].lineno, named("subprocess.run")[0].lineno)
        gate = named("selection.validate_schema")[0]
        self.assertLess(named("subprocess.check_output")[0].lineno, gate.lineno)
        for name in ("Game", "store_candidate", "continuity.create_journal"):
            self.assertLess(gate.lineno, named(name)[0].lineno)
        self.assertEqual(ast.unparse(named("Game")[0].args[0]), "selection.tuple_dir")
        starts, guards = named("g.start"), named("selection.verify_copy")
        self.assertEqual(len(starts), 2)
        self.assertEqual(len(guards), 2)
        self.assertLess(named("Game")[0].lineno, guards[0].lineno)
        self.assertLess(guards[0].lineno, starts[0].lineno)
        self.assertLess(starts[0].lineno, guards[1].lineno)
        self.assertLess(guards[1].lineno, starts[1].lineno)
        for call in named("subprocess.run") + named("subprocess.check_output"):
            self.assertIn("env=selection.environment", ast.unparse(call))
        commands = next(
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "commands" for t in n.targets)
        )
        assert isinstance(commands, ast.List)
        self.assertTrue(
            all(
                isinstance(cmd, ast.List)
                and ast.unparse(cmd.elts[0]) == "selection.compiler"
                for cmd in commands.elts
            )
        )


if __name__ == "__main__":
    unittest.main()
