"""Synthetic byte fixtures only: no compiler, ELF or game execution/evidence."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class SourceBuildIdentityTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            importlib.util.find_spec("native_build_identity"),
            "source-build receipt verifier is not implemented",
        )
        from native_build_identity import IdentityError, verify_source_build

        self.verify = verify_source_build
        self.error = IdentityError
        self.tmp = tempfile.TemporaryDirectory(prefix="identity-unit-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / "tree"
        self.receipts = self.base / "system-gcc13"
        self.root.mkdir()
        self.receipts.mkdir(mode=0o700)
        for name, data in {
            "src/main.c": b"/* unit source */\n",
            "include/base.h": b"/* unit header */\n",
            "GNUmakefile": b"# unit fixture, never executed\n",
        }.items():
            self.put(name, data)
        self.git("init", "-q")
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Unit Fixture",
            "-c",
            "user.email=unit@example.invalid",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-qm",
            "synthetic fixture",
        )
        self.rev = self.git("rev-parse", "HEAD").strip()
        for name, data in {
            "include/date.h": b"unit generated header",
            "src/main.o": b"unit object NOT ELF",
            "util/a.o": b"unit utility object",
            "sys/unix/a.o": b"unit system object",
            "win/tty/a.o": b"unit window object",
            ".chaos-build": b"1\n",
        }.items():
            self.put(name, data)
        pairs = {}
        for name, source in [
            ("dnethack", "src/dnethack"),
            ("nhdat", "dat/nhdat"),
            ("license", "dat/license"),
        ]:
            data = ("synthetic unit bytes: " + name).encode()
            self.put(source, data)
            self.put("dnethackdir/" + name, data)
            pairs[name] = {"sha256": self.digest(data), "size": len(data)}
        self.commands = [
            dict(
                argv=[
                    "/usr/bin/make",
                    "-j2",
                    target,
                    "CHAOS=1",
                    "CC=/usr/bin/cc",
                    "PKG_CONFIG=/usr/bin/pkg-config",
                ],
                log=str(self.receipts / ("1-" + target + ".log")),
                started_eastern="2026-09-15T09:00:00-04:00",
                finished_eastern="2026-09-15T09:01:00-04:00",
                exit_code=0,
            )
            for target in ("clean", "install")
        ]
        self.preflight = dict(
            revision=self.rev,
            tree=self.git("rev-parse", "HEAD^{tree}").strip(),
            environment={
                "PATH": "/usr/bin:/bin",
                "HOME": "/home/hermes",
                "LANG": "C.UTF-8",
                "TZ": "America/New_York",
                "PKG_CONFIG_LIBDIR": "/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig",
            },
            started_eastern="2026-09-15T09:00:00-04:00",
            compiler="cc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0\n",
            pkg_flags="-I/usr/include/lua5.4 -D_DEFAULT_SOURCE -D_XOPEN_SOURCE=600 -llua5.4 -lncursesw -ltinfo \n",
            protected={"/unavailable/original/held-test": "a" * 64},
            disk_free=100,
        )
        self.manifest = dict(
            mode=1,
            revision=self.rev,
            pairs=pairs,
            symbols=[],
            generated_headers=self.hashes("include/*.h"),
            objects=self.hashes("**/*.o"),
            commands=self.commands,
            finished_eastern="2026-09-15T09:01:00-04:00",
            acceptance="Build and binary identity only; no gameplay or tests",
        )
        self.completion = dict(
            finished_modes=[0, 1],
            protected_unchanged=True,
            protected_after=self.preflight["protected"].copy(),
            finished_eastern="2026-09-15T09:02:00-04:00",
            disk_free=100,
        )
        self.save()

    def git(self, *args):
        return subprocess.check_output(
            ["/usr/bin/git", "-C", str(self.root), *args],
            text=True,
            stderr=subprocess.STDOUT,
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_TERMINAL_PROMPT": "0",
            },
        )

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    @staticmethod
    def digest(data):
        return hashlib.sha256(data).hexdigest()

    def hashes(self, pattern):
        return {
            str(p.relative_to(self.root)): self.digest(p.read_bytes())
            for p in self.root.glob(pattern)
        }

    def save(self):
        for name, value in [
            ("preflight", self.preflight),
            ("1-manifest", self.manifest),
            ("1-commands", self.commands),
            ("completion", self.completion),
        ]:
            path = self.receipts / (name + ".json")
            path.write_text(json.dumps(value))
            path.chmod(0o600)

    def check(self, **kwargs):
        return self.verify(
            self.receipts,
            self.root,
            kwargs.pop("expected_revision", self.rev),
            **kwargs,
        )

    def test_valid_source_inputs_without_native_acceptance(self):
        result = self.check()
        self.assertEqual(result.build_root, self.root)
        self.assertEqual(result.tuple_dir, self.root / "dnethackdir")
        self.assertEqual(result.revision, self.rev)
        self.assertEqual(result.mode, 1)
        self.assertEqual(
            result.artifact_hashes["dnethack"],
            self.manifest["pairs"]["dnethack"]["sha256"],
        )
        self.assertIn("native ABI calibration still separate", result.limits)
        self.assertEqual(result.metadata["header_count"], 2)
        self.assertEqual(result.metadata["object_count"], 4)
        self.assertFalse(hasattr(result, "native_accepted"))
        self.assertFalse(hasattr(result, "build_pass"))
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=no"), "")

    def test_revision_format_is_checked_before_git(self):
        from unittest.mock import patch

        for value in ["HEAD", self.rev[:12], self.rev + "\n", "g" * 40, None]:
            with self.subTest(value=value), patch("subprocess.run") as run:
                with self.assertRaisesRegex(self.error, "revision"):
                    self.check(expected_revision=value)
                run.assert_not_called()

    def test_independent_revision_and_tree_binding(self):
        for field in ["manifest_revision", "preflight_revision", "tree", "expected"]:
            with self.subTest(field=field):
                old_m, old_p, old_t = (
                    self.manifest["revision"],
                    self.preflight["revision"],
                    self.preflight["tree"],
                )
                if field == "manifest_revision":
                    self.manifest["revision"] = "0" * 40
                if field == "preflight_revision":
                    self.preflight["revision"] = "0" * 40
                if field == "tree":
                    self.preflight["tree"] = "0" * 40
                self.save()
                with self.assertRaises(self.error):
                    self.check(
                        expected_revision="0" * 40 if field == "expected" else self.rev
                    )
                (
                    self.manifest["revision"],
                    self.preflight["revision"],
                    self.preflight["tree"],
                ) = old_m, old_p, old_t

    def test_unrecorded_subtree_enumeration_error_rejects(self):
        from unittest.mock import patch

        real_scandir = os.scandir
        for parent, suffix in (("src", ".o"), ("include", ".h")):
            hidden = self.root / parent / "unrecorded"
            hidden.mkdir()
            (hidden / ("hidden" + suffix)).write_bytes(b"unrecorded input")
            visits = []

            def inaccessible(path):
                if Path(path) == hidden:
                    visits.append(str(path))
                    raise PermissionError("injected unreadable subtree")
                return real_scandir(path)

            with (
                self.subTest(parent=parent),
                patch("os.scandir", side_effect=inaccessible),
            ):
                with self.assertRaisesRegex(self.error, "unreadable subtree"):
                    self.check()
            self.assertEqual(visits, [str(hidden)])
            (hidden / ("hidden" + suffix)).unlink()
            hidden.rmdir()

    def test_fixture_git_ignores_inherited_selectors_and_config(self):
        from unittest.mock import patch

        ambient = {
            "GIT_DIR": "/foreign/repository",
            "GIT_WORK_TREE": "/foreign/tree",
            "GIT_INDEX_FILE": "/foreign/index",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "core.hooksPath",
            "GIT_CONFIG_VALUE_0": "/foreign/hooks",
        }
        with (
            patch.dict(os.environ, ambient),
            patch("subprocess.check_output", return_value="ok") as run,
        ):
            self.git("rev-parse", "HEAD")
        env = run.call_args.kwargs.get("env")
        self.assertIsNotNone(env, "fixture Git must use an explicit environment")
        assert env is not None
        self.assertFalse(set(ambient).intersection(env))
        self.assertEqual(env["PATH"], "/usr/bin:/bin")
        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(env["GIT_CONFIG_GLOBAL"], "/dev/null")

    def test_dirty_tracked_source(self):
        self.put("src/main.c", b"changed source")
        with self.assertRaisesRegex(self.error, "clean|dirty"):
            self.check()

    def test_git_hidden_dirty_flags_rejected(self):
        self.git("update-index", "--assume-unchanged", "src/main.c")
        self.put("src/main.c", b"hidden dirty source")
        with self.assertRaisesRegex(self.error, "index|clean|dirty"):
            self.check()

    def test_manifest_command_boolean_cannot_alias_integer(self):
        self.manifest["commands"] = json.loads(json.dumps(self.commands))
        self.manifest["commands"][0]["exit_code"] = False
        self.save()
        with self.assertRaises(self.error):
            self.check()

    def test_local_override(self):
        self.put("local.mk", b"CC=foreign")
        with self.assertRaisesRegex(self.error, "local.mk"):
            self.check()

    def test_mode_and_marker_fail_closed(self):
        for mode in [0, "1", True, 2]:
            with self.subTest(mode=mode), self.assertRaisesRegex(self.error, "mode"):
                self.check(mode=mode)
        self.put(".chaos-build", b"0\n")
        with self.assertRaises(self.error):
            self.check()

    def test_complete_input_sets_and_hashes(self):
        for name in [
            "include/date.h",
            "src/main.o",
            "util/a.o",
            "sys/unix/a.o",
            "win/tty/a.o",
        ]:
            path = self.root / name
            original = path.read_bytes()
            for action in ["missing", "changed", "extra"]:
                with self.subTest(name=name, action=action):
                    extra = path.with_name("extra" + path.suffix)
                    if action == "missing":
                        path.unlink()
                    elif action == "changed":
                        path.write_bytes(b"tampered")
                    else:
                        extra.write_bytes(original)
                    with self.assertRaises(self.error):
                        self.check()
                    path.write_bytes(original)
                    if extra.exists():
                        extra.unlink()

    def test_tuple_hash_size_and_linked_identity(self):
        for name in ["dnethack", "nhdat", "license"]:
            for prefix in ["dnethackdir", "src" if name == "dnethack" else "dat"]:
                path = self.root / prefix / name
                original = path.read_bytes()
                path.write_bytes(b"old hypothetical same ABI bytes")
                with (
                    self.subTest(name=name, prefix=prefix),
                    self.assertRaises(self.error),
                ):
                    self.check()
                path.write_bytes(original)
            self.manifest["pairs"][name]["size"] += 1
            self.save()
            with self.assertRaises(self.error):
                self.check()
            self.manifest["pairs"][name]["size"] -= 1
            self.save()

    def test_path_alias_traversal_and_symlink(self):
        original = self.manifest["objects"].copy()
        for key in [
            "/src/main.o",
            "../tree/src/main.o",
            "src/../src/main.o",
            "src//main.o",
            "./src/main.o",
        ]:
            self.manifest["objects"] = {**original, key: original["src/main.o"]}
            self.save()
            with self.subTest(key=key), self.assertRaises(self.error):
                self.check()
        self.manifest["objects"] = original
        self.save()
        path = self.root / "src/main.o"
        data = path.read_bytes()
        path.unlink()
        other = self.base / "foreign.o"
        other.write_bytes(data)
        path.symlink_to(other)
        with self.assertRaises(self.error):
            self.check()
        path.unlink()
        os.link(other, path)
        with self.assertRaises(self.error):
            self.check()

    def test_receipt_schema_and_provenance_fail_closed(self):
        changes = [
            ("preflight", "compiler", "conda GCC 15.2"),
            ("preflight", "pkg_flags", "-I/conda/include"),
            ("preflight", "environment", {"PATH": "/conda/bin"}),
            ("preflight", "disk_free", True),
            ("manifest", "mode", 0),
            ("manifest", "symbols", "not a list"),
            ("manifest", "unknown", "field"),
            ("manifest", "objects", {}),
            ("completion", "finished_modes", [0]),
            ("completion", "protected_unchanged", False),
            ("completion", "protected_after", {}),
        ]
        for attr, key, value in changes:
            obj = getattr(self, attr)
            before = obj.copy()
            obj[key] = value
            self.save()
            with self.subTest(attr=attr, key=key), self.assertRaises(self.error):
                self.check()
            obj.clear()
            obj.update(before)
        self.save()
        path = self.receipts / "1-manifest.json"
        text = path.read_text()
        for bad in [
            "{",
            text.replace('"mode": 1', '"mode": 1, "mode": 1'),
            text.replace('"mode": 1', '"mode": NaN'),
        ]:
            path.write_text(bad)
            with self.assertRaises(self.error):
                self.check()
        path.write_text(text)
        path.chmod(0o666)
        with self.assertRaises(self.error):
            self.check()

    def test_command_receipts_are_metadata_not_instructions(self):
        for key, value in [
            ("exit_code", 2),
            ("exit_code", False),
            ("argv", ["/bin/false"]),
            ("started_eastern", None),
        ]:
            old = self.commands[0][key]
            self.commands[0][key] = value
            self.save()
            with self.subTest(key=key), self.assertRaises(self.error):
                self.check()
            self.commands[0][key] = old
        self.save()
        (self.receipts / "1-commands.json").write_text("[]")
        with self.assertRaises(self.error):
            self.check()


if __name__ == "__main__":
    unittest.main()
