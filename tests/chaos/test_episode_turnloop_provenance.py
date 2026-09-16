"""SYNTHETIC UNIT ONLY integration probes; never launch a native game."""

import copy
import importlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_turnloop_dump_provenance import ProvenanceDumpTests, sha


class IntegrationTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(
            importlib.util.find_spec("turnloop_header_bindings"),
            "independent producer adapter missing",
        )
        return importlib.import_module("turnloop_header_bindings")

    def fixture(self, root):
        f = ProvenanceDumpTests().fixture("reviewed-chaos0", "1", 0)
        receipt = root / "receipt"
        receipt.mkdir()
        tuple_dir = root / "tuple"
        tuple_dir.mkdir()
        for k, v in f["artifacts"].items():
            (tuple_dir / k).write_bytes(v)
        commands = [
            dict(
                argv=[
                    "/usr/bin/make",
                    "-j2",
                    target,
                    "CHAOS=0",
                    "CC=/usr/bin/cc",
                    "PKG_CONFIG=/usr/bin/pkg-config",
                ],
                exit_code=0,
            )
            for target in ("clean", "install")
        ]
        m = dict(
            mode=0,
            revision="1" * 40,
            commands=commands,
            pairs={
                k: dict(sha256=sha(v), size=len(v)) for k, v in f["artifacts"].items()
            },
            generated_headers={"include/date.h": sha(f["date_h"])},
        )
        (receipt / "0-manifest.json").write_text(json.dumps(m))
        (receipt / "0-commands.json").write_text(json.dumps(commands))
        (receipt / "0-date.h").write_bytes(f["date_h"])
        return f, receipt, tuple_dir, m

    def test_receipt_mutations_and_missing_capture(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            f, r, t, m = self.fixture(Path(tmp))
            binding = api.current_binding(r, t, "1" * 40, 0)
            self.assertEqual(binding.build.expected_header, f["expected_header"])
            for field, value in [("revision", "2" * 40), ("mode", 1), ("commands", [])]:
                changed = copy.deepcopy(m)
                changed[field] = value
                (r / "0-manifest.json").write_text(json.dumps(changed))
                with self.subTest(field=field), self.assertRaises(ValueError):
                    api.current_binding(r, t, "1" * 40, 0)
            for name in f["artifacts"]:
                for field, value in [("sha256", "0" * 64), ("size", 0)]:
                    changed = copy.deepcopy(m)
                    changed["pairs"][name][field] = value
                    (r / "0-manifest.json").write_text(json.dumps(changed))
                    with (
                        self.subTest(name=name, field=field),
                        self.assertRaises(ValueError),
                    ):
                        api.current_binding(r, t, "1" * 40, 0)
            (r / "0-manifest.json").write_text(json.dumps(m))
            (r / "0-date.h").unlink()
            with self.assertRaises((ValueError, OSError)):
                api.current_binding(r, t, "1" * 40, 0)

    def test_run_binding_and_complete_dump_entries(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            f, r, t, m = self.fixture(Path(tmp))
            binding = api.current_binding(r, t, "1" * 40, 0)
            binding.verify_tuple(t)
            (t / "license").write_bytes(b"substitution")
            with self.assertRaises(ValueError):
                binding.verify_tuple(t)
            d = Path(tmp) / "dumplog"
            d.mkdir()
            with self.assertRaises(ValueError):
                api.read_dumps(d)
            (d / "1700000000").write_bytes(b"raw")
            self.assertEqual(api.read_dumps(d), {"1700000000": b"raw"})
            for name in ("extra", "directory", "link"):
                p = d / name
                if name == "directory":
                    p.mkdir()
                elif name == "link":
                    p.symlink_to(d / "1700000000")
                else:
                    p.write_bytes(b"raw")
                with self.assertRaises(ValueError):
                    api.read_dumps(d)
                if p.is_dir() and not p.is_symlink():
                    p.rmdir()
                else:
                    p.unlink()

    def test_supplement_does_not_mask_nondump_or_strict(self):
        api = self.api()
        helper = importlib.import_module("turnloop_dump_provenance")
        test = ProvenanceDumpTests()
        test.setUp()
        left = dict(
            inputs=["unit"],
            terminal=b"unit",
            xlog=b"unit",
            dumps={"1700000000": test.dump(test.left).hex()},
        )
        right = dict(left, dumps={"1700000000": test.dump(test.right).hex()})
        from test_episode_turnloop_oracle import compare_runs

        with self.assertRaises(AssertionError):
            compare_runs(left, right)
        a = helper.validate_build(**test.left)
        b = helper.validate_build(**test.right)
        api.compare_run(left, right, a, b)
        for field in ("inputs", "terminal", "xlog"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                api.compare_run(left, dict(right, **{field: b"changed"}), a, b)

    def test_historical_fixed_evidence_mutations(self):
        api = self.api()
        h = importlib.import_module("turnloop_dump_provenance")
        receipt = Path(
            "/home/hermes/.local/share/nyarlathack/evidence/nyarlathack-acceptance-o61fnz7b/stock/manifest.json"
        )
        t = Path("/home/hermes/.local/share/nyarlathack/baselines/ff37b3a7a")
        kwargs = dict(
            revision=api.HISTORICAL_REVISION,
            mode=0,
            receipt=receipt.read_bytes(),
            original_dump=(receipt.parent / "game/dumplog/1700000000").read_bytes(),
            artifacts={
                k: (t / k).read_bytes() for k in ("dnethack", "nhdat", "license")
            },
        )
        b = h.validate_historical_build(**kwargs)
        self.assertIsNone(b.date_h_sha256)
        self.assertEqual(b.source_kind, "historical-recorded-dump")
        for key in ("receipt", "original_dump"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                h.validate_historical_build(**dict(kwargs, **{key: kwargs[key] + b"!"}))
        for key, value in [("revision", "1" * 40), ("mode", 1)]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                h.validate_historical_build(**dict(kwargs, **{key: value}))
        for key in kwargs["artifacts"]:
            artifacts = dict(kwargs["artifacts"])
            artifacts[key] += b"!"
            with self.subTest(key=key), self.assertRaises(ValueError):
                h.validate_historical_build(**dict(kwargs, artifacts=artifacts))

    def test_missing_capture_fails_before_game_or_compiler(self):
        api = self.api()
        import test_episode_turnloop as driver

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f, r, t, m = self.fixture(root)
            current = root / "dnethackdir"
            current.mkdir()
            for k, v in f["artifacts"].items():
                (current / k).write_bytes(v)
            on = copy.deepcopy(m)
            on["mode"] = 1
            for c in on["commands"]:
                c["argv"][3] = "CHAOS=1"
            (r / "1-manifest.json").write_text(json.dumps(on))
            (r / "1-commands.json").write_text(json.dumps(on["commands"]))
            (r / "0-date.h").unlink()
            args = [
                "--root",
                str(root),
                "--receipt",
                str(r),
                "--revision",
                "1" * 40,
                "--off-tuple",
                str(t),
                "--artifacts",
                str(root / "out"),
                "--matrix",
                "--provenance-dumps",
                "--stock-tuple",
                "/home/hermes/.local/share/nyarlathack/baselines/ff37b3a7a",
                "--stock-receipt",
                "/home/hermes/.local/share/nyarlathack/evidence/nyarlathack-acceptance-o61fnz7b/stock/manifest.json",
                "--stock-revision",
                api.HISTORICAL_REVISION,
            ]
            # Artifacts must be outside the checkout; use a second private root.
            with tempfile.TemporaryDirectory() as out:
                args[args.index("--artifacts") + 1] = str(Path(out) / "artifacts")
                with (
                    patch.object(api, "check_profile"),
                    patch.object(driver, "Game") as game,
                    patch.object(driver, "bounded") as compiler,
                ):
                    with self.assertRaisesRegex(ValueError, "regular evidence file"):
                        driver.main(args)
                    game.assert_not_called()
                    compiler.assert_not_called()

    def test_profile_revision_and_source_mutations(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(
                api.subprocess, "check_output", return_value=b"2" * 40 + b"\n"
            ):
                with self.assertRaisesRegex(ValueError, "HEAD"):
                    api.check_profile(root, "1" * 40)
            with patch.object(
                api.subprocess, "check_output", return_value=b"1" * 40 + b"\n"
            ):
                (root / "src").mkdir()
                (root / "src/version.c").write_bytes(b"unsupported runtime suffix")
                with self.assertRaisesRegex(ValueError, "profile"):
                    api.check_profile(root, "1" * 40)

    def test_profile_rejects_local_overrides(self):
        api = self.api()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "local.mk").write_text("CPPFLAGS += -DRUNTIME_PORT_ID")
            with (
                patch.object(
                    api.subprocess, "check_output", return_value=b"1" * 40 + b"\n"
                ),
                patch.object(api, "PROFILE", {}),
            ):
                with self.assertRaisesRegex(ValueError, "override"):
                    api.check_profile(root, "1" * 40)

    def test_opt_in_requires_full_matrix_before_game(self):
        import test_episode_turnloop as driver

        with tempfile.TemporaryDirectory() as tmp, patch.object(driver, "Game") as game:
            p = Path(tmp)
            args = [
                "--root",
                tmp,
                "--receipt",
                tmp,
                "--revision",
                "1" * 40,
                "--off-tuple",
                tmp,
                "--artifacts",
                str(p / "out"),
                "--provenance-dumps",
            ]
            with self.assertRaises(ValueError):
                driver.main(args)
            game.assert_not_called()


if __name__ == "__main__":
    unittest.main()
